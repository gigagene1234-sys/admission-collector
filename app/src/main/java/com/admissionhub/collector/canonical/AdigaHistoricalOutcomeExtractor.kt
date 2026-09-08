package com.admissionhub.collector.canonical

import org.json.JSONObject

/** Extracts only header-verified, application-bound historical result rows. */
object AdigaHistoricalOutcomeExtractor {
    const val SCHEMA_VERSION = 2

    fun extract(
        rows: List<List<String>>,
        scopeRowIndex: Int,
        departmentRowIndex: Int,
        metrics: JSONObject,
        recordYear: Int
    ): JSONObject? {
        if (scopeRowIndex !in rows.indices || departmentRowIndex !in rows.indices || departmentRowIndex <= scopeRowIndex) return null
        val scope = rows[scopeRowIndex]
        val headerRows = rows.subList(scopeRowIndex + 1, departmentRowIndex)
        val admissionLabel = scope.drop(1).firstOrNull { it.trim().isNotBlank() }.orEmpty().trim()
        return extractVerifiedRow(
            data = rows[departmentRowIndex],
            headerRows = headerRows,
            metrics = metrics,
            recordYear = recordYear,
            admissionLabel = admissionLabel,
            bindingMethod = "same-official-table-explicit-scope-segment"
        )
    }

    /**
     * Historical tables do not always have a separate "모집단위 | 전형명" scope row. When the
     * application admission and recruitment unit are both already verified on the SAME data row,
     * this method may extract its numeric outcome. It does not perform identity matching itself;
     * callers must invoke it only after exact admission + exact/suffix-equivalent department match.
     *
     * To avoid treating arbitrary numbers as admission outcomes, nearby official header rows must
     * explicitly contain 모집인원, 경쟁률, 50/70 cut and either 대학별환산 or 학생부등급 semantics.
     */
    fun extractSameRow(
        rows: List<List<String>>,
        departmentRowIndex: Int,
        metrics: JSONObject,
        recordYear: Int,
        admissionLabel: String
    ): JSONObject? {
        if (departmentRowIndex !in rows.indices) return null
        val start = (departmentRowIndex - 8).coerceAtLeast(0)
        val nearby = rows.subList(start, departmentRowIndex)
        if (nearby.isEmpty()) return null

        // Prefer the smallest suffix of nearby rows that still proves the standard official result
        // header. This keeps previous recruitment-unit data rows out of headerEvidence.
        var verifiedHeaders: List<List<String>>? = null
        for (candidateStart in nearby.indices.reversed()) {
            val candidate = nearby.subList(candidateStart, nearby.size)
            if (headerSemantics(candidate) != null) verifiedHeaders = candidate
        }
        val headers = verifiedHeaders ?: return null
        return extractVerifiedRow(
            data = rows[departmentRowIndex],
            headerRows = headers,
            metrics = metrics,
            recordYear = recordYear,
            admissionLabel = admissionLabel,
            bindingMethod = "same-official-table-same-row"
        )
    }

    private data class HeaderSemantics(
        val hasCapacity: Boolean,
        val hasCompetition: Boolean,
        val hasWaitlist: Boolean,
        val hasConverted: Boolean,
        val hasGrade: Boolean,
        val hasCut: Boolean,
        val text: String
    )

    private fun headerSemantics(headerRows: List<List<String>>): HeaderSemantics? {
        val text = headerRows.flatten().joinToString(" ").replace(Regex("\\s+"), " ").trim()
        if (text.isBlank()) return null
        val hasCapacity = "모집인원" in text
        val hasCompetition = "경쟁률" in text
        val hasWaitlist = "충원" in text
        val hasConverted = "대학별환산" in text || "대학별 환산" in text
        val normalized = text.replace(Regex("\\s+"), "")
        val hasGrade = "최종등록자교과성적학생부등급" in normalized ||
            "최종등록자학생부등급" in normalized || "학생부등급" in normalized
        val has50 = Regex("50\\s*%?\\s*cut|50cut", RegexOption.IGNORE_CASE).containsMatchIn(text)
        val has70 = Regex("70\\s*%?\\s*cut|70cut", RegexOption.IGNORE_CASE).containsMatchIn(text)
        val hasCut = has50 && has70
        if (!hasCapacity || !hasCompetition || !hasCut || (!hasConverted && !hasGrade)) return null
        return HeaderSemantics(hasCapacity, hasCompetition, hasWaitlist, hasConverted, hasGrade, hasCut, text)
    }

    private fun extractVerifiedRow(
        data: List<String>,
        headerRows: List<List<String>>,
        metrics: JSONObject,
        recordYear: Int,
        admissionLabel: String,
        bindingMethod: String
    ): JSONObject? {
        if (data.isEmpty() || data.first().trim().isBlank()) return null
        val header = headerSemantics(headerRows) ?: return null
        val out = JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("headersVerified", true)
            .put("bindingMethod", bindingMethod)
            .put("bindingInferred", false)
            .put("recordYear", recordYear)
            .put("historicalResultYear", metrics.optInt("historicalResultYear", recordYear).takeIf { it in 2000..2100 } ?: recordYear)
            .put("admissionLabel", admissionLabel.trim())
            .put("recruitmentUnit", data[0].trim())
            .put("capacity", number(data.getOrNull(1)))
            .put("competitionRate", number(data.getOrNull(2)))
            .put("waitlist", if (header.hasWaitlist) number(data.getOrNull(3)) else JSONObject.NULL)
            .put("headerEvidence", header.text.take(1000))
            .put("rowEvidence", data.joinToString(" | ").take(1200))

        // The currently collected Adiga historical result tables use the standard order
        // 모집단위 / 모집인원 / 경쟁률 / 충원 / 50 cut / 70 cut / 총점 / 등급50 / 등급70.
        // We only use these positions after the official header semantics above are proved.
        if (header.hasConverted && data.size >= 7) {
            out.put("converted50", number(data.getOrNull(4)))
                .put("converted70", number(data.getOrNull(5)))
                .put("convertedMax", number(data.getOrNull(6)))
                .put("convertedScale", "대학별환산")
            if (header.hasGrade && data.size >= 9) {
                out.put("grade50", number(data.getOrNull(7)))
                    .put("grade70", number(data.getOrNull(8)))
                    .put("gradeScale", "최종등록자 교과성적 학생부등급")
            }
        } else if (header.hasGrade && data.size >= 6) {
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
