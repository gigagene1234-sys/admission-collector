package com.admissionhub.collector.jinhak

import org.json.JSONObject

/**
 * Prevents unrelated 4-digit years (graduation eligibility, article dates, current cycle)
 * from being promoted to an admission-result year.
 */
object JinhakReportYearGuard {
    const val SEMANTICS_VERSION = 1

    fun resolvePageYear(pageType: String, text: String, currentCycle: Int = 2027): Int? = when (pageType) {
        "jinhak-prediction-report", "jinhak-mock-support-report", "jinhak-early-storage",
        "jinhak-recommended-university", "jinhak-score-calc-report", "jinhak-sat-minimum" -> currentCycle
        "jinhak-actual-admit-report" -> explicitHistoricalAcademicYear(text, currentCycle)
        else -> null
    }

    /**
     * A historical page-level year is accepted only if exactly one past admission academic year
     * is explicitly labelled as `20xx학년도`. Multiple years mean the page is a multi-year report,
     * so the summary year must remain null and row evidence should carry its own explicit year.
     */
    fun explicitHistoricalAcademicYear(text: String, currentCycle: Int = 2027): Int? {
        val years = Regex("(20[0-9]{2})\\s*학년도")
            .findAll(text)
            .mapNotNull { it.groupValues.getOrNull(1)?.toIntOrNull() }
            .filter { it in 2000 until currentCycle }
            .distinct()
            .toList()
        return years.singleOrNull()
    }

    fun sanitizeHistoricalRowYear(row: JSONObject, currentCycle: Int = 2027): Int? {
        val year = if (row.has("year") && !row.isNull("year")) row.optInt("year", 0) else 0
        if (year !in 2000 until currentCycle) return null
        val raw = buildString {
            append(row.optString("rawEvidence"))
            append(' ')
            append(row.optJSONObject("metrics")?.toString().orEmpty())
        }
        return if (Regex("(?:^|[^0-9])${year}\\s*학년도(?:[^0-9]|$)").containsMatchIn(raw)) year else null
    }

    fun annotate(metrics: JSONObject, pageType: String, resolvedYear: Int?): JSONObject = metrics
        .put("yearSemanticsVersion", SEMANTICS_VERSION)
        .put("yearSource", when {
            pageType == "jinhak-actual-admit-report" && resolvedYear != null -> "explicit-historical-academic-year"
            pageType == "jinhak-actual-admit-report" -> "historical-multi-year-or-unresolved"
            resolvedYear != null -> "current-admission-cycle"
            else -> "unresolved"
        })
}
