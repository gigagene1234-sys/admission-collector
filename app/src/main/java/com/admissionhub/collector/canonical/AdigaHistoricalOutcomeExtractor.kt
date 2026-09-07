package com.admissionhub.collector.canonical

import org.json.JSONArray
import org.json.JSONObject

/** Extracts only header-verified, application-bound historical result rows. */
object AdigaHistoricalOutcomeExtractor {
    const val SCHEMA_VERSION = 1

    fun extract(
        rows: List<List<String>>,
        scopeRowIndex: Int,
        departmentRowIndex: Int,
        metrics: JSONObject,
        recordYear: Int
    ): JSONObject? {
        if (scopeRowIndex !in rows.indices || departmentRowIndex !in rows.indices || departmentRowIndex <= scopeRowIndex) return null
        val scope = rows[scopeRowIndex]
        val data = rows[departmentRowIndex]
        if (data.isEmpty() || data.first().trim().isBlank()) return null
        val headerText = rows.subList(scopeRowIndex + 1, departmentRowIndex)
            .flatten().joinToString(" ").replace(Regex("\\s+"), " ")
        val hasCapacity = "모집인원" in headerText
        val hasCompetition = "경쟁률" in headerText
        val hasWaitlist = "충원" in headerText
        val hasConverted = "대학별환산" in headerText || "대학별 환산" in headerText
        val hasGrade = "최종등록자 교과성적 학생부등급" in headerText
        val hasCut = Regex("50\\s*%?\\s*cut|50cut", RegexOption.IGNORE_CASE).containsMatchIn(headerText) &&
            Regex("70\\s*%?\\s*cut|70cut", RegexOption.IGNORE_CASE).containsMatchIn(headerText)
        if (!hasCapacity || !hasCompetition || !hasCut || (!hasConverted && !hasGrade)) return null

        val admissionLabel = scope.drop(1).firstOrNull { it.trim().isNotBlank() }.orEmpty().trim()
        val out = JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("headersVerified", true)
            .put("recordYear", recordYear)
            .put("historicalResultYear", metrics.optInt("historicalResultYear", recordYear).takeIf { it in 2000..2100 } ?: recordYear)
            .put("admissionLabel", admissionLabel)
            .put("recruitmentUnit", data[0].trim())
            .put("capacity", number(data.getOrNull(1)))
            .put("competitionRate", number(data.getOrNull(2)))
            .put("waitlist", if (hasWaitlist) number(data.getOrNull(3)) else JSONObject.NULL)
            .put("headerEvidence", headerText.take(1000))
            .put("rowEvidence", data.joinToString(" | ").take(1200))

        if (hasConverted && data.size >= 7) {
            out.put("converted50", number(data.getOrNull(4)))
                .put("converted70", number(data.getOrNull(5)))
                .put("convertedMax", number(data.getOrNull(6)))
                .put("convertedScale", "대학별환산")
            if (data.size >= 9) {
                out.put("grade50", number(data.getOrNull(7)))
                    .put("grade70", number(data.getOrNull(8)))
                    .put("gradeScale", "최종등록자 교과성적 학생부등급")
            }
        } else if (hasGrade && data.size >= 6) {
            out.put("grade50", number(data.getOrNull(4)))
                .put("grade70", number(data.getOrNull(5)))
                .put("gradeScale", "최종등록자 교과성적 학생부등급")
        }
        val useful = listOf("converted50", "converted70", "grade50", "grade70").any { out.has(it) && !out.isNull(it) }
        return out.takeIf { useful }
    }

    private fun number(raw: String?): Any {
        val s = raw.orEmpty().trim().replace(",", "").removeSuffix("%").trim()
        if (s.isBlank() || s in setOf("-", "—", "·")) return JSONObject.NULL
        return s.toDoubleOrNull()?.takeIf { it.isFinite() } ?: JSONObject.NULL
    }
}
