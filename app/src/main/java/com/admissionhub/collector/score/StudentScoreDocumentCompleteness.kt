package com.admissionhub.collector.score

import org.json.JSONObject

/**
 * Conservative document-structure completeness check for current high-school seniors.
 * It does not infer grades or subjects. It only verifies that the imported school export itself
 * contains the expected semester span (1-1,1-2,2-1,2-2,3-1) and a non-trivial transcript body.
 */
object StudentScoreDocumentCompleteness {
    const val SCHEMA_VERSION = 1

    fun assess(profile: JSONObject): JSONObject {
        val subjects = profile.optJSONArray("subjects")
        if (subjects == null || subjects.length() == 0) return result(false, "no-subjects")
        val semesters = linkedSetOf<String>()
        var rows = 0
        var namedRows = 0
        var missingCredits = 0
        for (i in 0 until subjects.length()) {
            val row = subjects.optJSONObject(i) ?: continue
            rows++
            val year = row.optInt("gradeYear", 0)
            val sem = row.optInt("semester", 0)
            if (year in 1..3 && sem in 1..2) semesters += "$year-$sem"
            if (row.optString("subject").isNotBlank()) namedRows++
            if (!row.has("credits") || row.isNull("credits") || row.optDouble("credits", 0.0) <= 0.0) missingCredits++
        }
        val required = setOf("1-1", "1-2", "2-1", "2-2", "3-1")
        val unexpectedFuture = "3-2" in semesters
        val complete = rows >= 20 && namedRows == rows && missingCredits == 0 && semesters.containsAll(required)
        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("verified", complete)
            .put("method", "school-export-semester-span")
            .put("requiredSemesters", org.json.JSONArray(required.sorted()))
            .put("observedSemesters", org.json.JSONArray(semesters.sorted()))
            .put("rowCount", rows)
            .put("namedRows", namedRows)
            .put("missingCreditRows", missingCredits)
            .put("containsThirdSecondSemester", unexpectedFuture)
            .put("reason", if (complete) "expected-senior-semester-span-present" else "semester-span-or-row-integrity-incomplete")
            .put("inferredGrades", false)
            .put("inferredSubjects", false)
    }

    private fun result(ok: Boolean, reason: String) = JSONObject()
        .put("schemaVersion", SCHEMA_VERSION)
        .put("verified", ok)
        .put("method", "school-export-semester-span")
        .put("reason", reason)
        .put("inferredGrades", false)
        .put("inferredSubjects", false)
}
