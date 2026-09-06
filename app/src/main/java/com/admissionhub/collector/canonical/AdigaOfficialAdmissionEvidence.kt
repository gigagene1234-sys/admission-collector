package com.admissionhub.collector.canonical

import org.json.JSONArray
import org.json.JSONObject

/**
 * Conservative parser for official Adiga table evidence.
 *
 * It never invents a recruitment-unit/admission binding. A current-year table only earns
 * row-bound support when the SAME table row contains both the application department and
 * admission label. University-level or historical mentions are retained as evidence only.
 */
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
        val rows = metrics.optJSONArray("rows") ?: return emptyList()
        val out = mutableListOf<JSONObject>()
        for (ri in 0 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            val cells = (0 until row.length()).map { row.optString(it).trim() }.filter { it.isNotBlank() }
            if (cells.isEmpty()) continue
            val rowText = cells.joinToString(" | ").take(1200)
            val admissionQuality = admissionEvidenceQuality(cells, app.admission, app.admissionCategory)
            if (admissionQuality == "none") continue
            val departmentQuality = departmentEvidenceQuality(cells, app.department)
            val currentYear = recordType == "current-admission-criteria-table" && recordYear == app.year
            val scope = when {
                currentYear && departmentQuality in setOf("exact", "suffix-equivalent") && admissionQuality == "exact" -> "row-bound-current"
                currentYear && departmentQuality in setOf("exact", "suffix-equivalent") -> "row-bound-current-related"
                currentYear -> "university-current"
                else -> "historical"
            }
            out += JSONObject()
                .put("recordType", recordType)
                .put("recordYear", recordYear)
                .put("rowIndex", ri)
                .put("scope", scope)
                .put("departmentMatch", departmentQuality)
                .put("admissionMatch", admissionQuality)
                .put("rowEvidence", rowText)
                .put("sourcePage", record.optString("sourcePage").take(500))
                .put("sourceRowFingerprint", record.optString("sourceRowFingerprint").take(100))
                .put("officialSource", true)
                .put("bindingInferred", false)
        }
        return out
    }

    private fun admissionEvidenceQuality(cells: List<String>, admission: String?, category: String?): String {
        val target = CanonicalSixApplicationGraph.normalizeAdmissionKey(admission)
        val categoryKey = CanonicalSixApplicationGraph.normalizeAdmissionKey(category)
        val normalized = cells.map(CanonicalSixApplicationGraph::normalizeAdmissionKey)
        if (target.isNotBlank() && normalized.any { it == target || (target.length >= 3 && it.contains(target)) }) return "exact"
        if (target.isNotBlank() && normalized.any { it.length >= 3 && target.contains(it) }) return "related"
        if (categoryKey.isNotBlank() && normalized.any { it == categoryKey || (it.length >= 2 && (it.contains(categoryKey) || categoryKey.contains(it))) }) return "category-only"
        return "none"
    }

    private fun departmentEvidenceQuality(cells: List<String>, department: String?): String {
        var best = "none"
        for (cell in cells) {
            when (CanonicalSixApplicationGraph.departmentMatchQuality(department, cell)) {
                "exact" -> return "exact"
                "suffix-equivalent" -> best = "suffix-equivalent"
            }
        }
        return best
    }
}
