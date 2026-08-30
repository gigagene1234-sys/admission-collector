package com.admissionhub.collector.parser

import org.json.JSONArray
import org.json.JSONObject

object GenericAdmissionParser {
    data class InferredContext(
        val university: String?,
        val department: String?,
        val admission: String?,
        val year: Int?
    )

    fun normalize(snapshot: JSONObject): JSONArray {
        val result = JSONArray()
        val inherited = inferSnapshotContext(snapshot)
        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until tables.length()) {
            val table = tables.optJSONObject(ti) ?: continue
            val caption = table.optString("caption")
            val rows = table.optJSONArray("rows") ?: continue
            for (ri in 0 until rows.length()) {
                val row = rows.optJSONArray(ri) ?: continue
                val cells = mutableListOf<String>()
                for (ci in 0 until row.length()) cells.add(row.optString(ci))
                val evidence = listOf(caption, cells.joinToString(" | ")).filter { it.isNotBlank() }.joinToString(" | ")
                buildRecord(evidence, inherited)?.let { result.put(it) }
            }
        }
        return RecordUtils.dedupe(result)
    }

    fun collectText(snapshot: JSONObject): String {
        val parts = mutableListOf<String>()
        parts += snapshot.optString("title")
        val context = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until context.length()) context.optString(i).trim().takeIf { it.isNotBlank() }?.let(parts::add)
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 120)) blocks.optString(i).trim().takeIf { it.isNotBlank() }?.let(parts::add)
        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until minOf(tables.length(), 120)) {
            val table = tables.optJSONObject(ti) ?: continue
            table.optString("caption").trim().takeIf { it.isNotBlank() }?.let(parts::add)
            val rows = table.optJSONArray("rows") ?: continue
            for (ri in 0 until minOf(rows.length(), 250)) {
                val row = rows.optJSONArray(ri) ?: continue
                val cells = mutableListOf<String>()
                for (ci in 0 until minOf(row.length(), 40)) cells.add(row.optString(ci))
                if (cells.isNotEmpty()) parts += cells.joinToString(" | ")
            }
        }
        return parts.joinToString(" \n ").replace(Regex("\\s+"), " ").take(60000)
    }

    fun inferSnapshotContext(snapshot: JSONObject): InferredContext {
        val priority = mutableListOf<String>()
        val selected = snapshot.optJSONArray("selectionContext") ?: JSONArray()
        for (i in 0 until minOf(selected.length(), 80)) selected.optString(i).trim().takeIf { it.isNotBlank() }?.let(priority::add)
        snapshot.optString("title").trim().takeIf { it.isNotBlank() }?.let(priority::add)
        val context = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until minOf(context.length(), 80)) context.optString(i).trim().takeIf { it.isNotBlank() }?.let(priority::add)
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 30)) blocks.optString(i).trim().takeIf { it.isNotBlank() }?.let(priority::add)
        val first = inferContext(priority.joinToString(" | "))
        if (first.university != null && first.department != null) return first
        val fallback = inferContext(collectText(snapshot).take(12000))
        return InferredContext(
            first.university ?: fallback.university,
            first.department ?: fallback.department,
            first.admission ?: fallback.admission,
            first.year ?: fallback.year
        )
    }

    fun inferContext(text: String): InferredContext {
        val normalized = text.replace(Regex("\\s+"), " ").trim()
        val university = bestUniversity(normalized)
        val department = bestDepartment(normalized)
        val admission = bestAdmission(normalized)
        val year = Regex("(?:^|[^0-9])(20[0-9]{2})(?:학년도|년도|년)?")
            .find(normalized)?.groupValues?.getOrNull(1)?.toIntOrNull()
        return InferredContext(university, department, admission, year)
    }

    private fun bestUniversity(text: String): String? {
        val universityMatches = Regex("([가-힣A-Za-z0-9·.()\\-]{2,35}대학교(?:\\[[^\\]]{1,12}\\])?)")
            .findAll(text).map { cleanCandidate(it.groupValues[1]) }.filter { it.length in 4..45 }.toList()
        universityMatches.firstOrNull()?.let { return it }

        // Bare "대학" is usually a college/faculty or prose fragment on Jinhak pages.
        // Prefer a missing university over attaching prediction metrics to a false institution.
        return Regex("([가-힣A-Za-z0-9·.()-]{2,35}(?:교육대학교|과학기술원))")
            .findAll(text)
            .map { cleanCandidate(it.groupValues[1]) }
            .firstOrNull { it.length in 4..45 }
    }

    private fun bestDepartment(text: String): String? {
        val noise = Regex("(지원|합격|예측|반영|학생부|전형|대학교|대학검색|모집인원|경쟁률)")
        val suffix = Regex("(학과|학부|전공|모집단위|자율전공)$")
        val segments = text.split('|').map { cleanCandidate(it) }.filter { it.isNotBlank() }
        val candidates = mutableListOf<String>()
        for (segment in segments) {
            val labeled = Regex("(?:학과|학부|모집단위|전공)\\s*[:：]\\s*([가-힣A-Za-z0-9·.()&・\\- ]{2,40})").find(segment)?.groupValues?.getOrNull(1)
            if (!labeled.isNullOrBlank()) candidates += cleanCandidate(labeled)
            Regex("([가-힣A-Za-z0-9·.()&・\\-]{2,35}(?:학과|학부|전공|모집단위))")
                .findAll(segment).forEach { candidates += cleanCandidate(it.groupValues[1]) }
        }
        return candidates
            .filter { it.length in 2..40 && suffix.containsMatchIn(it) && !noise.containsMatchIn(it) }
            .minByOrNull { it.length }
    }

    private fun bestAdmission(text: String): String? {
        val segments = text.split('|').map { cleanCandidate(it) }.filter { it.isNotBlank() }
        val candidates = mutableListOf<String>()
        val known = Regex("((?:학생부교과|학생부종합|교과|종합|지역인재|학교장추천|일반|면접|교과면접|서류|고른기회|농어촌|기회균형)[가-힣A-Za-z0-9·.()_\\- ]{0,24}전형)")
        for (segment in segments) {
            Regex("(?:전형명|전형)\\s*[:：]\\s*([가-힣A-Za-z0-9·.()_\\- ]{2,35}(?:전형)?)")
                .find(segment)?.groupValues?.getOrNull(1)?.let { candidates += cleanCandidate(it) }
            known.findAll(segment).forEach { candidates += cleanCandidate(it.groupValues[1]) }
        }
        return candidates.firstOrNull {
            it.length in 2..40 && !Regex("[①-⑳]|[0-9]+\\)|학생부 반영비율|있는 전형|없는 서류|설명|안내|^서류\\s*평가\\s*전형$|^서류\\s*전형$|^면접\\s*전형$").containsMatchIn(it)
        }
    }

    private fun cleanCandidate(value: String): String = value
        .replace(Regex("^[^가-힣A-Za-z0-9]+|[^가-힣A-Za-z0-9)\\]]+$"), "")
        .replace(Regex("\\s+"), " ")
        .trim()

    private fun buildRecord(evidenceRaw: String, inherited: InferredContext): JSONObject? {
        val evidence = evidenceRaw.replace(Regex("\\s+"), " ").trim().take(7000)
        if (evidence.length < 2) return null

        val local = inferContext(evidence)
        val year = local.year ?: inherited.year
        val university = local.university ?: inherited.university
        val department = local.department ?: inherited.department
        val admission = local.admission ?: inherited.admission

        fun findNumber(pattern: String): Double? = Regex(pattern, RegexOption.IGNORE_CASE).find(evidence)?.groupValues?.getOrNull(1)?.replace(",", "")?.toDoubleOrNull()
        fun findInt(pattern: String): Int? = Regex(pattern, RegexOption.IGNORE_CASE).find(evidence)?.groupValues?.getOrNull(1)?.replace(",", "")?.toIntOrNull()

        val competition = Regex("(?:경쟁률)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?(?:\\s*[:대]\\s*1)?)").find(evidence)?.groupValues?.getOrNull(1)
        val judgment = Regex("(?:판정|합격예측|지원판정)\\s*[:：]?\\s*(안정|적정|소신|위험|상향|하향|가능|불안|유리|불리)").find(evidence)?.groupValues?.getOrNull(1)

        val metrics = JSONObject()
            .put("myScore", findNumber("(?:내\\s*(?:환산)?점수|나의\\s*(?:환산)?점수|산출점수|환산점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("grade", findNumber("(?:등급|반영\\s*평균등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("cut50", findNumber("(?:50%\\s*(?:컷|cut|등급|점수)|산출점수\\s*50%)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("cut70", findNumber("(?:70%\\s*(?:컷|cut|등급|점수)|산출점수\\s*70%)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("averageGrade", findNumber("(?:(?:최종등록자|등록자|합격자)\\s*)?(?:평균등급|평균 등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("lowestGrade", findNumber("(?:최저등급|최저 등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("competition", competition ?: JSONObject.NULL)
            .put("capacity", findInt("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)") ?: JSONObject.NULL)
            .put("applicants", findInt("(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)") ?: JSONObject.NULL)
            .put("additionalAdmits", findInt("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)") ?: JSONObject.NULL)
            .put("jinhakBars", findInt("(?:칸수|칸\\s*수)\\s*[:：]?\\s*([0-9]+)") ?: JSONObject.NULL)
            .put("jinhakJudgment", judgment ?: JSONObject.NULL)

        val hasMetric = metrics.keys().asSequence().any { !metrics.isNull(it) }
        if (!hasMetric) return null

        val confidence = when {
            university != null && department != null -> "high"
            university != null || department != null || admission != null -> "medium"
            else -> "raw"
        }

        return JSONObject()
            .put("recordType", "generic-admission-metric")
            .put("year", year ?: JSONObject.NULL)
            .put("university", university ?: JSONObject.NULL)
            .put("department", department ?: JSONObject.NULL)
            .put("admission", admission ?: JSONObject.NULL)
            .put("metrics", metrics)
            .put("confidence", confidence)
            .put("rawEvidence", evidence)
    }
}
