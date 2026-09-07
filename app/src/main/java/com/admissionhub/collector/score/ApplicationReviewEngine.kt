package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.time.Instant
import java.time.LocalDate

/** Explains application suitability; no probability, arbitrary thresholds or automatic selection. */
object ApplicationReviewEngine {
    val checks = linkedMapOf("eligibility" to "지원자격", "csat" to "수능최저", "documents" to "제출서류", "multipleApplications" to "복수지원 규칙")
    val checkStates = listOf("미확인", "확인·충족", "미충족", "해당 없음")
    val stringFields = setOf("formulaSource", "formulaExcerpt", "scoreScale", "direction", "outcomeSource", "outcomeExcerpt", "metricName", "methodDescription", "rulesSource", "rulesExcerpt", "deadline", "interviewDate", "note", "profileFingerprint")
    val numberFields = setOf("ownScore", "referenceScore", "maxScore", "outcomeYear")
    fun sanitize(input: JSONObject): JSONObject {
        val out = JSONObject()
        for (key in stringFields) {
            val value = if (input.isNull(key)) "" else input.optString(key).trim()
            require(value.length <= 2000) { "$key 입력은 2000자 이하로 작성하세요." }
            if (key.endsWith("Source") && value.isNotBlank()) require(officialUrl(value)) { "공식 대학·어디가의 HTTPS 출처를 입력하세요." }
            out.put(key, value)
        }
        for (key in numberFields) {
            val raw = if (input.isNull(key)) "" else input.optString(key).trim()
            val n = if (raw.isBlank()) null else raw.toDoubleOrNull()?.takeIf { it.isFinite() } ?: error("$key 숫자를 확인하세요.")
            require(n == null || n >= 0) { "$key 음수는 사용할 수 없습니다." }
            if (key == "outcomeYear") require(n == null || n in 2000.0..2100.0 && n % 1.0 == 0.0) { "입결 학년도를 확인하세요." }
            if (key == "maxScore") require(n == null || n > 0) { "만점은 0보다 커야 합니다." }
            out.put(key, n ?: JSONObject.NULL)
        }
        for (key in checks.keys) { val n = input.optInt(key, 0); require(n in 0..3); out.put(key, n) }
        val direction = out.optString("direction")
        require(direction.isBlank() || direction in setOf("lower-is-better", "higher-is-better")) { "점수 비교 방향을 선택하세요." }
        val deadline = out.optString("deadline")
        require(deadline.isBlank() || runCatching { Instant.parse(deadline) }.isSuccess) { "접수 마감은 시간대가 있는 날짜·시간으로 입력하세요." }
        val interview = out.optString("interviewDate")
        require(interview.isBlank() || runCatching { LocalDate.parse(interview) }.isSuccess) { "면접일은 YYYY-MM-DD 형식입니다." }
        return out.put("sourceReviewConfirmed", input.optBoolean("sourceReviewConfirmed", false))
            .put("rulesReviewConfirmed", input.optBoolean("rulesReviewConfirmed", false))
            .put("verificationMethod", "USER_REVIEWED_OFFICIAL_SOURCE")
    }
    fun officialUrl(raw: String): Boolean = runCatching {
        val u = URI(raw); val h = u.host?.lowercase().orEmpty()
        u.scheme == "https" && u.userInfo == null && u.fragment == null &&
            (h.endsWith(".ac.kr") || h == "adiga.kr" || h.endsWith(".adiga.kr")) &&
            !Regex("(?i)(token|password|secret|session|cookie)=").containsMatchIn(u.rawQuery.orEmpty())
    }.getOrDefault(false)
    fun evaluate(candidate: JSONObject, rawInput: JSONObject, profile: JSONObject, prediction: JSONObject?, now: Instant): JSONObject {
        val input = sanitize(rawInput)
        val missing = JSONArray(); val risks = JSONArray(); val reasons = JSONArray()
        val year = candidate.optInt("academicYear", 0)
        val identity = candidate.optString("applicationIdentityKey")
        val binding = rawInput.optString("applicationIdentityKey") == identity && rawInput.optInt("academicYear") == year && identity.isNotBlank()
        val sourceReviewed = binding && input.optBoolean("sourceReviewConfirmed")
        val officialEvidence = com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer.analyze(candidate)
        val completeProfile = profile.optString("status") == "IMPORTED" && profile.optInt("academicYear") == year && profile.optBoolean("completeTranscriptConfirmedByUser")
        val profileCurrent = completeProfile && profile.optString("fingerprint").isNotBlank() && input.optString("profileFingerprint") == profile.optString("fingerprint")
        fun required(ok: Boolean, text: String) { if (!ok) missing.put(text) }
        required(binding, "이 지원안에 연결된 근거 등록")
        required(completeProfile, "과목별 성적 입력 및 전체 입력 확인")
        required(profileCurrent, "현재 성적을 기준으로 대학 환산값 재확인")
        if (!sourceReviewed) {
            val officialMissing = officialEvidence.optJSONArray("missing") ?: JSONArray()
            if (officialMissing.length() == 0) missing.put("공식 원문에서 전형·모집단위·연도와 현재 성적 기준을 사용자 확인")
            else for (i in 0 until officialMissing.length()) missing.put("어디가 연결: ${officialMissing.optString(i)}")
        }
        required(officialUrl(input.optString("formulaSource")) && input.optString("formulaExcerpt").isNotBlank(), "공식 환산 출처와 산식 근거")
        required(officialUrl(input.optString("outcomeSource")) && input.optString("outcomeExcerpt").isNotBlank(), "공식 과거 입결 출처와 해당 행 근거")
        required(input.optString("scoreScale").isNotBlank() && input.optString("scoreScale") !in setOf("null", "미확인", "unknown", "-") && input.optString("methodDescription").isNotBlank(), "동일한 점수 척도·반영방법 확인")
        required(input.optString("metricName").isNotBlank(), "공식 지표명: 평균·70%컷·100%컷 등")
        required(input.optString("direction") in setOf("lower-is-better", "higher-is-better"), "점수 비교 방향")
        val own = input.number("ownScore"); val reference = input.number("referenceScore"); val max = input.number("maxScore")
        required(own != null && reference != null && max != null && own <= max && reference <= max, "내 환산값·공식 참고값·만점 범위 확인")
        if (input.optString("scoreScale").contains("등급") || input.optString("scoreScale").contains("grade", true))
            required(own != null && own in 1.0..9.0 && reference != null && reference in 1.0..9.0 && max == 9.0, "등급 척도의 1~9 범위 확인")
        val outcomeYear = input.optInt("outcomeYear", 0)
        required(outcomeYear in 2000 until year, "지원년도보다 이전의 공식 입결 학년도")
        val comparisonReady = missing.length() == 0
        var relation = "HOLD"; var margin: Double? = null
        if (comparisonReady && own != null && reference != null) {
            margin = if (input.optString("direction") == "lower-is-better") reference - own else own - reference
            relation = when { margin > 1e-9 -> "ABOVE_REFERENCE"; margin < -1e-9 -> "BELOW_REFERENCE"; else -> "AT_REFERENCE" }
            reasons.put("$outcomeYear ${input.optString("metricName")}: 내 값 $own / 공식 참고값 $reference (${input.optString("scoreScale")})")
            reasons.put("출처의 동일 전형·모집단위·반영방법을 사용자가 확인한 입력에 따른 비교")
            if (relation == "BELOW_REFERENCE") risks.put("성적이 선택한 과거 공식 참고선보다 불리합니다.")
        }
        val rulesReviewed = binding && input.optBoolean("rulesReviewConfirmed") && officialUrl(input.optString("rulesSource")) && input.optString("rulesExcerpt").isNotBlank()
        var unmet = false
        for ((key, label) in checks) when {
            !rulesReviewed || input.optInt(key) == 0 -> missing.put("$label: 해당 연도 공식 규칙 및 충족 여부 확인")
            input.optInt(key) == 2 -> { risks.put("$label 미충족으로 입력됨"); unmet = true }
            else -> reasons.put("$label: ${checkStates[input.optInt(key)]} (사용자 확인)")
        }
        val deadline = input.optString("deadline")
        val expired = rulesReviewed && deadline.isNotBlank() && !now.isBefore(Instant.parse(deadline))
        if (expired) risks.put("입력한 접수 마감시각이 지났습니다. 접수 완료 여부를 확인하세요.")
        if (!rulesReviewed || deadline.isBlank()) missing.put("공식 접수 마감시각")
        if (candidate.optString("admissionCategory") == "종합" || candidate.optString("admission").contains("면접")) risks.put("서류·면접 평가가 포함되어 교과 참고선만으로 최종 합격을 판단할 수 없습니다.")
        val code = when {
            unmet || expired -> "CONDITIONS_RECHECK"
            comparisonReady && relation == "BELOW_REFERENCE" -> "SCORE_RISK"
            missing.length() > 0 -> "HOLD"
            else -> "REVIEWABLE"
        }
        val label = when (code) {
            "CONDITIONS_RECHECK" -> "지원조건·일정 재검토"
            "SCORE_RISK" -> "성적 위험 확인 · 지원 재검토"
            "REVIEWABLE" -> "입력 근거상 지원 검토 가능"
            else -> "자료 보완 후 판단"
        }
        return JSONObject().put("applicationIdentityKey", identity).put("academicYear", year).put("code", code).put("label", label)
            .put("officialEvidence", officialEvidence)
            .put("comparisonReady", comparisonReady).put("relation", relation).put("advantageMargin", margin ?: JSONObject.NULL)
            .put("missing", missing).put("risks", risks).put("reasons", reasons).put("input", input.put("applicationIdentityKey", rawInput.optString("applicationIdentityKey")).put("academicYear", rawInput.optInt("academicYear")))
            .put("prediction", prediction ?: JSONObject.NULL).put("evaluatedAt", now.toString())
            .put("probabilityInferred", false).put("unsupportedThresholdsUsed", false).put("externalCollectionMayMutate", false)
            .put("basis", "USER_REVIEWED_OFFICIAL_SOURCE").put("disclaimer", "과거 입결 비교와 지원 준비 점검입니다. 합격확률·안정/적정/소신 분류를 생성하지 않습니다.")
    }
    fun portfolio(cards: JSONArray): JSONObject {
        val warnings = JSONArray(); val groups = mutableMapOf<String, MutableList<Int>>(); val dates = mutableMapOf<String, MutableList<Int>>()
        val counts = mutableMapOf<String, Int>(); var selected = 0
        for (i in 0 until cards.length()) {
            val c = cards.getJSONObject(i); if (!c.optBoolean("occupied")) continue
            selected++; val review = c.optJSONObject("applicationReview") ?: JSONObject()
            val code = review.optString("code", "HOLD"); counts[code] = (counts[code] ?: 0) + 1
            c.optString("university").takeIf { it.isNotBlank() }?.let { groups.getOrPut(it) { mutableListOf() }.add(c.optInt("slot")) }
            review.optJSONObject("input")?.optString("interviewDate")?.takeIf { it.isNotBlank() }?.let { dates.getOrPut(it) { mutableListOf() }.add(c.optInt("slot")) }
        }
        for ((u, slots) in groups) if (slots.size > 1) warnings.put("$u ${slots.joinToString(", ")}번: 전형별 복수지원 허용 규칙을 확인하세요.")
        for ((date, slots) in dates) if (slots.size > 1) warnings.put("$date ${slots.joinToString(", ")}번: 면접일이 같습니다. 시간·이동 가능 여부를 확인하세요.")
        if (selected < 6) warnings.put("선택 $selected/6 · 비어 있는 지원안을 직접 결정하세요.")
        return JSONObject().put("selected", selected).put("counts", JSONObject(counts as Map<*, *>)).put("warnings", warnings)
            .put("automaticSelection", false).put("probabilityInferred", false)
    }
    private fun JSONObject.number(key: String): Double? = if (!has(key) || isNull(key)) null else optDouble(key).takeIf { it.isFinite() }
}
