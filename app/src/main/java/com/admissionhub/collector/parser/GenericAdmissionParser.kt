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
        val inherited = inferContext(collectText(snapshot).take(10000))
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

    fun inferContext(text: String): InferredContext {
        val universityRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,45}(대학교|대학)(?:\\[(?:본교|분교|제\\d+캠퍼스)\\])?)")
        val deptRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,55}(학과|학부|전공|모집단위))")
        val admissionRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,70}(전형|학생부교과|학생부종합|교과|종합|추천|면접))")
        val yearRegex = Regex("(?:^|[^0-9])(20[0-9]{2})(?:학년도|년도|년)?")
        return InferredContext(
            universityRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            deptRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            admissionRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            yearRegex.find(text)?.groupValues?.getOrNull(1)?.toIntOrNull()
        )
    }

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
            university != null && department != null && admission != null -> "high"
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
