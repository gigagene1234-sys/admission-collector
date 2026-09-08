package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject

/**
 * Evidence-only completeness check for Korean school transcript exports.
 * It never invents grades, credits, years, or semesters.
 */
object TranscriptCompletenessPolicy {
    const val SCHEMA_VERSION = 1
    private val requiredEarlySemesters = listOf("1-1", "1-2", "2-1", "2-2", "3-1")

    fun evaluate(profile: JSONObject): JSONObject {
        val subjects = profile.optJSONArray("subjects") ?: JSONArray()
        val observed = linkedSetOf<String>()
        var usableRows = 0
        var missingCredits = 0
        for (i in 0 until subjects.length()) {
            val row = subjects.optJSONObject(i) ?: continue
            val year = row.optInt("gradeYear", -1)
            val semester = row.optInt("semester", -1)
            val subject = row.optString("subject").trim()
            if (year !in 1..3 || semester !in 1..2 || subject.isBlank()) continue
            usableRows += 1
            observed += "$year-$semester"
            if (!row.has("credits") || row.isNull("credits") || row.optDouble("credits", 0.0) <= 0.0) missingCredits += 1
        }
        val sourceType = profile.optString("sourceType").uppercase()
        val automatic = profile.optBoolean("automaticRecognition", false)
        val imported = profile.optString("status") == "IMPORTED"
        val missing = requiredEarlySemesters.filterNot { it in observed }
        val structurallyComplete = imported && automatic && sourceType in setOf("XLS", "XLSX") &&
            usableRows > 0 && missing.isEmpty() && missingCredits == 0
        val userConfirmed = profile.optBoolean("completeTranscriptConfirmedByUser", false)
        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("purpose", "2027-early-admission-through-grade3-semester1")
            .put("userConfirmed", userConfirmed)
            .put("structurallyCompleteForEarlyApplication", structurallyComplete)
            .put("acceptedForQuantitativeCalculation", userConfirmed || structurallyComplete)
            .put("basis", when {
                userConfirmed -> "user-confirmed"
                structurallyComplete -> "school-excel-explicit-semester-coverage"
                else -> "incomplete-or-unverified"
            })
            .put("requiredSemesters", JSONArray(requiredEarlySemesters))
            .put("observedSemesters", JSONArray(observed.toList()))
            .put("missingSemesters", JSONArray(missing))
            .put("usableRows", usableRows)
            .put("missingCreditRows", missingCredits)
            .put("grade3Semester2Required", false)
            .put("fieldsInferred", false)
    }
}
