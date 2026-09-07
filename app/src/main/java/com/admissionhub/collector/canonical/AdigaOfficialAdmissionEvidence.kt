package com.admissionhub.collector.canonical

import org.json.JSONObject

object AdigaOfficialAdmissionEvidence {
    data class AppRef(
        val year: Int,
        val university: String?,
        val department: String?,
        val admission: String?,
        val admissionCategory: String?
    )

    fun inspect(recordType: String, recordYear: Int, record: JSONObject, app: AppRef): List<JSONObject> {
        if (recordType !in setOf("current-admission-criteria-table", "historical-admission-result-table")) return emptyList()
        val metrics = record.optJSONObject("metrics") ?: return emptyList()
        val rowsJson = metrics.optJSONArray("rows") ?: return emptyList()
        val rows = mutableListOf<List<String>>()
        for (ri in 0 until rowsJson.length()) {
            val row = rowsJson.optJSONArray(ri)
            val cells = if (row == null) emptyList() else (0 until row.length())
                .map { row.optString(it).trim() }
                .filter { it.isNotBlank() }
            rows += cells
        }
        val out = mutableListOf<JSONObject>()
        val currentYear = recordType == "current-admission-criteria-table" && recordYear == app.year

        for (ri in rows.indices) {
            val cells = rows[ri]
            if (cells.isEmpty()) continue
            val admissionQuality = AdigaOfficialTableBindingPolicy.admissionEvidenceQuality(cells, app.admission, app.admissionCategory)
            if (admissionQuality == "none") continue
            val departmentQuality = AdigaOfficialTableBindingPolicy.departmentEvidenceQuality(cells, app.department)
            val scope = when {
                currentYear && departmentQuality in setOf("exact", "suffix-equivalent") && admissionQuality == "exact" -> "row-bound-current"
                currentYear && departmentQuality in setOf("exact", "suffix-equivalent") -> "row-bound-current-related"
                currentYear -> "university-current"
                else -> "historical"
            }
            out += baseEvidence(recordType, recordYear, record)
                .put("rowIndex", ri)
                .put("scope", scope)
                .put("departmentMatch", departmentQuality)
                .put("admissionMatch", admissionQuality)
                .put("rowEvidence", cells.joinToString(" | ").take(1200))
                .put("bindingMethod", "same-row-or-university-evidence")
        }

        val segmentBindings = AdigaOfficialTableBindingPolicy.findExplicitSegmentBindings(
            rows, app.department, app.admission, app.admissionCategory
        )
        for (binding in segmentBindings) {
            val scopeCells = rows.getOrElse(binding.scopeRowIndex) { emptyList() }
            val departmentCells = rows.getOrElse(binding.departmentRowIndex) { emptyList() }
            out += baseEvidence(recordType, recordYear, record)
                .put("scope", if (currentYear) "table-segment-current" else "table-segment-historical")
                .put("scopeRowIndex", binding.scopeRowIndex)
                .put("departmentRowIndex", binding.departmentRowIndex)
                .put("scopeLabel", binding.scopeLabel)
                .put("departmentMatch", binding.departmentMatch)
                .put("admissionMatch", binding.admissionMatch)
                .put("scopeRowEvidence", scopeCells.joinToString(" | ").take(1000))
                .put("departmentRowEvidence", departmentCells.joinToString(" | ").take(1000))
                .put("bindingMethod", "same-official-table-explicit-scope-segment")
                .put("sameOfficialTableSegment", true)
        }
        return dedupe(out)
    }

    private fun baseEvidence(recordType: String, recordYear: Int, record: JSONObject): JSONObject = JSONObject()
        .put("recordType", recordType)
        .put("recordYear", recordYear)
        .put("sourcePage", record.optString("sourcePage").take(500))
        .put("sourceRowFingerprint", record.optString("sourceRowFingerprint").take(100))
        .put("officialSource", true)
        .put("bindingInferred", false)

    private fun dedupe(rows: List<JSONObject>): List<JSONObject> {
        val seen = linkedSetOf<String>()
        val out = mutableListOf<JSONObject>()
        for (row in rows) {
            val key = listOf(
                row.optString("scope"), row.optInt("rowIndex", -1).toString(),
                row.optInt("scopeRowIndex", -1).toString(), row.optInt("departmentRowIndex", -1).toString(),
                row.optString("sourceRowFingerprint")
            ).joinToString("|")
            if (seen.add(key)) out += row
        }
        return out
    }
}
