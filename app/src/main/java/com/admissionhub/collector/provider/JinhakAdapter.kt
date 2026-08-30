package com.admissionhub.collector.provider

import com.admissionhub.collector.parser.GenericAdmissionParser
import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.time.Instant
import java.time.temporal.ChronoUnit

object JinhakAdapter : ProviderAdapter {
    override val id = ProviderId.JINHAK
    override val supportsBatchCrawl = false
    private const val TARGET_YEAR = 2027

    override fun accepts(url: String): Boolean {
        return try {
            val host = URI(url).host?.lowercase() ?: return false
            host == "jinhak.com" || host.endsWith(".jinhak.com")
        } catch (_: Exception) { false }
    }

    override fun isBatchNavigable(url: String): Boolean = false

    override fun classify(snapshot: JSONObject): String {
        val url = snapshot.optString("url").lowercase()
        val text = GenericAdmissionParser.collectText(snapshot)
        val hasPrediction = text.contains("합격예측") || text.contains("모의지원") || Regex("[0-9]{1,2}\\s*칸").containsMatchIn(text)
        val hasActual = text.contains("실제합격자") ||
            (text.contains("입시결과") && Regex("(최종등록|합격자|충원|70%|50%)").containsMatchIn(text))
        val dedicatedMinimum = url.contains("esatminuniv") ||
            (Regex("(수능최저\\s*(검색|대학|조건)|최저학력기준\\s*(검색|대학))").containsMatchIn(text) && !hasPrediction)
        val earlyStorage = text.contains("수시저장소") || text.contains("저장대학") || url.contains("storage") || url.contains("save")
        return when {
            Regex("(login|signin|member/login)").containsMatchIn(url) || text.contains("로그인") && text.contains("비밀번호") -> "jinhak-login"
            earlyStorage -> "jinhak-early-storage"
            hasActual -> "jinhak-actual-admit-report"
            text.contains("합격예측리포트") || text.contains("합격예측 리포트") || hasPrediction -> "jinhak-prediction-report"
            url.contains("sapplysample") || text.contains("모의지원 리포트") || text.contains("모의지원리포트") -> "jinhak-mock-support-report"
            text.contains("성적산출 리포트") || text.contains("성적산출리포트") -> "jinhak-score-calc-report"
            dedicatedMinimum -> "jinhak-sat-minimum"
            url.contains("infoview.aspx") -> "jinhak-student-basic"
            url.contains("four-year-university/search") || text.contains("대학검색") -> "jinhak-university-search"
            url.contains("/curation") || text.contains("큐레이션") -> "jinhak-curation"
            text.contains("추천대학") -> "jinhak-recommended-university"
            else -> "jinhak-other"
        }
    }

    override fun normalize(snapshot: JSONObject): JSONArray {
        val text = GenericAdmissionParser.collectText(snapshot)
        val pageType = classify(snapshot)
        val context = GenericAdmissionParser.inferSnapshotContext(snapshot)
        val observedAt = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()
        val dataScope = dataScope(pageType)
        val inferredYear = context.year ?: if (dataScope == "current-prediction" || dataScope == "current-admission") TARGET_YEAR else null
        val result = JSONArray()

        if (pageType == "jinhak-early-storage") {
            val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
            val seenLogical = linkedSetOf<String>()
            for (i in 0 until cards.length()) {
                val cardObj = cards.optJSONObject(i)
                val evidence = (cardObj?.optString("text") ?: cards.optString(i))
                    .replace(Regex("""\s+"""), " ").trim().take(5000)
                if (evidence.isBlank()) continue
                val local = GenericAdmissionParser.inferContext(evidence)
                val explicitUniversity = cleanStorageUniversity(cardObj?.optString("university"))
                val university = local.university ?: explicitUniversity
                val department = cleanStorageDepartment(local.department)
                val admission = cleanStorageAdmission(local.admission, evidence)
                val universityContextSource = cardObj?.optString("universitySource")
                    ?.takeIf { it.isNotBlank() && it != "missing" }
                val cardMetrics = predictionMetrics(evidence)
                val hasPrimaryPrediction = listOf(
                    "stabilityBars", "predictionProbability", "predictionLabel", "myRank", "predictedCut"
                ).any { cardMetrics.has(it) && !cardMetrics.isNull(it) }
                if (!hasPrimaryPrediction) continue
                val logical = RecordUtils.sha256(listOf(
                    university ?: "", department ?: "", admission ?: "", cardMetrics.toString()
                ).joinToString("|"))
                if (!seenLogical.add(logical)) continue
                val record = JSONObject()
                    .put("recordType", "jinhak-saved-application-prediction")
                    .put("providerPageType", pageType)
                    .put("dataScope", "current-prediction")
                    .put("year", local.year ?: TARGET_YEAR)
                    .put("university", university ?: JSONObject.NULL)
                    .put("department", department ?: JSONObject.NULL)
                    .put("admission", admission ?: JSONObject.NULL)
                    .put("metrics", cardMetrics)
                    .put("observedAt", observedAt)
                    .put("cardIndex", i)
                    .put("contextSource", if (local.university == null && explicitUniversity != null) "scored-card-root+explicit-university-context" else "scored-card-root")
                    .put("universityContextSource", universityContextSource ?: JSONObject.NULL)
                    .put("universityContextDepth", cardObj?.optInt("universityDepth", -1) ?: -1)
                    .put("cardRootScore", cardObj?.optInt("score", 0) ?: 0)
                    .put("confidence", when {
                        university != null && department != null && admission != null -> "high"
                        university != null && department != null -> "medium"
                        department != null -> "low"
                        else -> "raw"
                    })
                    .put("sourcePage", safePath(snapshot.optString("url")))
                    .put("rawEvidence", evidence)
                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = true))
                result.put(record)
            }
            return RecordUtils.dedupe(result)
        }

        val metrics = JSONObject()
        putNumber(metrics, "universityCalculatedScore", Regex("(?:대학별\\s*)?(?:환산점수|산출점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putNumber(metrics, "convertedGrade", Regex("(?:반영\\s*평균등급|환산등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "stabilityBars", Regex("(?:합격안정성|칸수|칸\\s*수)?\\s*[:：]?\\s*([0-9]{1,2})\\s*칸").find(text)?.groupValues?.getOrNull(1))
        putText(metrics, "predictionLabel", Regex("(?:합격예측|지원판정|지원전략)?\\s*[:：]?\\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "mockApplicants", Regex("(?:모의지원자수|모의지원자 수|모의지원자)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "applicants", Regex("(?:현재\\s*)?(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\s*)?경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "myRank", Regex("(?:내\\s*순위|나의\\s*순위|현재\\s*순위)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "predictedCut", Regex("(?:예상\\s*합격선|예상\\s*컷|합격예상점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "additionalAdmits", Regex("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))

        val minimum = Regex("수능최저[^.\\n]{0,100}(충족가능|미충족|불충족|충족)").find(text)?.groupValues?.getOrNull(1)
        if (!minimum.isNullOrBlank()) metrics.put("minimumStatus", minimum)

        if (metrics.keys().asSequence().any { !metrics.isNull(it) }) {
            val summary = JSONObject()
                .put("recordType", if (dataScope == "current-prediction") "jinhak-prediction-snapshot" else "jinhak-page-summary")
                .put("providerPageType", pageType)
                .put("dataScope", dataScope)
                .put("year", inferredYear ?: JSONObject.NULL)
                .put("university", context.university ?: JSONObject.NULL)
                .put("department", context.department ?: JSONObject.NULL)
                .put("admission", context.admission ?: JSONObject.NULL)
                .put("metrics", metrics)
                .put("observedAt", observedAt)
                .put("confidence", when {
                    context.university != null && context.department != null -> "high"
                    context.university != null || context.department != null || context.admission != null -> "medium"
                    else -> "raw"
                })
                .put("sourcePage", safePath(snapshot.optString("url")))
                .put("rawEvidence", text.take(5000))
            summary.put("sourceRowFingerprint", fingerprint(summary, observedAt, preserveSnapshot = dataScope == "current-prediction"))
            result.put(summary)
        }

        val generic = GenericAdmissionParser.normalize(snapshot)
        for (i in 0 until generic.length()) {
            val row = generic.optJSONObject(i) ?: continue
            row.put("providerPageType", pageType)
                .put("dataScope", dataScope)
                .put("observedAt", observedAt)
            if (row.isNull("year") && inferredYear != null) row.put("year", inferredYear)
            row.put("sourcePage", safePath(snapshot.optString("url")))
            row.put("sourceRowFingerprint", fingerprint(row, observedAt, preserveSnapshot = dataScope == "current-prediction"))
            result.put(row)
        }
        return RecordUtils.dedupe(result)
    }

    private fun dataScope(pageType: String): String = when (pageType) {
        "jinhak-actual-admit-report" -> "historical-result"
        "jinhak-prediction-report", "jinhak-mock-support-report", "jinhak-recommended-university", "jinhak-early-storage" -> "current-prediction"
        "jinhak-sat-minimum" -> "current-admission"
        "jinhak-score-calc-report", "jinhak-student-basic" -> "student-profile"
        else -> "reference"
    }

    private fun fingerprint(record: JSONObject, observedAt: String, preserveSnapshot: Boolean): String {
        val stable = listOf(
            record.optString("recordType"), record.optString("year"), record.optString("university"),
            record.optString("department"), record.optString("admission"), record.optJSONObject("metrics")?.toString() ?: "",
            record.optString("rawEvidence").take(1000)
        ).joinToString("|")
        val scope = if (preserveSnapshot) observedAt.substring(0, 16) else "stable"
        return RecordUtils.sha256("jinhak|$scope|$stable")
    }

    private fun cleanStorageUniversity(value: String?): String? {
        val raw = value?.replace(Regex("""\s+"""), " ")?.trim()?.takeIf { it.isNotBlank() } ?: return null
        if (raw.length !in 3..48) return null
        if (Regex("""(등급|경쟁률|합격|예측|지원|전형|모집|학과|학부|전공)""").containsMatchIn(raw)) return null
        val full = Regex("""^[가-힣A-Za-z0-9·.()\-]{2,35}(?:대학교|교육대학교|과학기술원)(?:\[[^\]]{1,12}\])?$""")
        val short = Regex("""^[가-힣A-Za-z0-9·.()\-]{2,24}대$""")
        val shortNoise = setOf("공대", "의대", "법대", "상대", "교대", "사범대", "간호대", "약대", "치대", "한의대", "철도대")
        return when {
            full.matches(raw) -> raw
            short.matches(raw) && raw !in shortNoise -> raw
            else -> null
        }
    }

    private fun cleanStorageDepartment(value: String?): String? {
        val raw = value?.trim()?.takeIf { it.isNotBlank() } ?: return null
        val cleaned = raw.replace(
            Regex("""^(?:지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\(면접형\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)"""),
            ""
        ).trim()
        return cleaned.takeIf { it.length >= 2 } ?: raw
    }

    private fun cleanStorageAdmission(value: String?, evidence: String): String? {
        val polluted = Regex("""(등급|경쟁률|전년도|점수|[0-9]{1,2}\s*칸|합격률|합격확률)""")
        value?.trim()?.takeIf { it.isNotBlank() && it.length <= 40 && !polluted.containsMatchIn(it) }?.let { return it }
        val token = Regex("""(지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\(면접형\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)""")
            .find(evidence)?.groupValues?.getOrNull(1)
        return token?.trim()?.takeIf { it.isNotBlank() }
    }

    private fun predictionMetrics(text: String): JSONObject {
        val metrics = JSONObject()
        putNumber(metrics, "universityCalculatedScore", Regex("(?:대학별\\s*)?(?:환산점수|산출점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putNumber(metrics, "convertedGrade", Regex("(?:반영\\s*평균등급|환산등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "stabilityBars", Regex("(?:합격안정성|칸수|칸\\s*수)?\\s*[:：]?\\s*([0-9]{1,2})\\s*칸").find(text)?.groupValues?.getOrNull(1))
        putNumber(metrics, "predictionProbability", Regex("(?:예상\\s*)?(?:합격률|합격확률|합격가능성)\\s*[:：]?\\s*([0-9]{1,3}(?:\\.[0-9]+)?)\\s*%").find(text)?.groupValues?.getOrNull(1))
        putText(metrics, "predictionLabel", Regex("(?:합격예측|지원판정|지원전략)?\\s*[:：]?\\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "mockApplicants", Regex("(?:모의지원자수|모의지원자 수|모의지원자)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "applicants", Regex("(?:현재\\s*)?(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\s*)?경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "myRank", Regex("(?:내\\s*순위|나의\\s*순위|현재\\s*순위)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "predictedCut", Regex("(?:예상\\s*합격선|예상\\s*컷|합격예상점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "additionalAdmits", Regex("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        return metrics
    }

    private fun putNumber(obj: JSONObject, key: String, value: String?) {
        val n = value?.toDoubleOrNull() ?: return
        obj.put(key, n)
    }
    private fun putInt(obj: JSONObject, key: String, value: String?) {
        val n = value?.toIntOrNull() ?: return
        obj.put(key, n)
    }
    private fun putText(obj: JSONObject, key: String, value: String?) {
        value?.trim()?.takeIf { it.isNotBlank() }?.let { obj.put(key, it) }
    }
    private fun safePath(url: String): String = try {
        val uri = URI(url)
        "${uri.scheme ?: "https"}://${uri.host ?: ""}${uri.path ?: "/"}"
    } catch (_: Exception) { url.substringBefore('?').substringBefore('#') }
}
