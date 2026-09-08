package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class StudentScoreDocumentCompletenessTest {
    private fun completeProfile(): JSONObject {
        val subjects = JSONArray()
        val semesters = listOf(1 to 1, 1 to 2, 2 to 1, 2 to 2, 3 to 1)
        var index = 0
        for ((year, semester) in semesters) {
            repeat(5) {
                index++
                subjects.put(JSONObject()
                    .put("gradeYear", year)
                    .put("semester", semester)
                    .put("group", if (it % 2 == 0) "수학" else "국어")
                    .put("subject", "과목$index")
                    .put("grade", 3)
                    .put("credits", 3.0)
                    .put("achievement", JSONObject.NULL))
            }
        }
        return JSONObject()
            .put("status", "IMPORTED")
            .put("academicYear", 2027)
            .put("subjects", subjects)
    }

    @Test
    fun legacyImportedProfileCanBeStructurallyVerifiedWithoutStoredFlag() {
        val profile = completeProfile()
        assertFalse(profile.has("documentCompletenessVerified"))
        val result = StudentScoreDocumentCompleteness.assess(profile)
        assertTrue(result.getBoolean("verified"))
        assertFalse(result.getBoolean("inferredGrades"))
        assertFalse(result.getBoolean("inferredSubjects"))
        assertEquals(25, result.getInt("rowCount"))
    }

    @Test
    fun missingThirdFirstSemesterIsNotDeclaredComplete() {
        val profile = completeProfile()
        val input = profile.getJSONArray("subjects")
        val filtered = JSONArray()
        for (i in 0 until input.length()) {
            val row = input.getJSONObject(i)
            if (!(row.getInt("gradeYear") == 3 && row.getInt("semester") == 1)) filtered.put(row)
        }
        profile.put("subjects", filtered)
        assertFalse(StudentScoreDocumentCompleteness.assess(profile).getBoolean("verified"))
    }

    @Test
    fun missingCreditsAreNotSilentlyInferred() {
        val profile = completeProfile()
        profile.getJSONArray("subjects").getJSONObject(0).put("credits", JSONObject.NULL)
        val result = StudentScoreDocumentCompleteness.assess(profile)
        assertFalse(result.getBoolean("verified"))
        assertEquals(1, result.getInt("missingCreditRows"))
        assertFalse(result.getBoolean("inferredSubjects"))
    }
}
