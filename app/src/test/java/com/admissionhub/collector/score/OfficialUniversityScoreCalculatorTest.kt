package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class OfficialUniversityScoreCalculatorTest {
    private fun candidate(university: String, department: String, admission: String, category: String = "교과"): JSONObject {
        val evidence = JSONArray().put(JSONObject()
            .put("recordType", "current-admission-criteria-table")
            .put("recordYear", 2027)
            .put("scope", "university-current")
            .put("departmentMatch", "none")
            .put("admissionMatch", "exact")
            .put("sourcePage", "https://www.adiga.kr/official"))
        val matches = JSONArray().put(JSONObject().put("departmentMatch", "exact").put("admissionMatch", "missing"))
        return JSONObject()
            .put("academicYear", 2027).put("university", university).put("department", department)
            .put("admission", admission).put("admissionCategory", category)
            .put("adigaBinding", JSONObject().put("officialUniversityCurrent", 1).put("officialAdmissionEvidence", evidence).put("matches", matches))
    }

    private fun profile(rows: List<JSONObject>): JSONObject = JSONObject()
        .put("status", "IMPORTED").put("academicYear", 2027).put("completeTranscriptConfirmedByUser", true)
        .put("subjects", JSONArray(rows))

    private fun row(year: Int, semester: Int, group: String, subject: String, grade: Int? = null, credits: Double? = 3.0, achievement: String = ""): JSONObject =
        JSONObject().put("gradeYear", year).put("semester", semester).put("group", group).put("subject", subject)
            .put("grade", grade ?: JSONObject.NULL).put("credits", credits ?: JSONObject.NULL).put("achievement", achievement)

    @Test fun woosongInterviewUsesSixGradesAndCareerBonus() {
        val rows = listOf(
            row(1,1,"국어","국어1",2), row(1,2,"수학","수학1",3), row(2,1,"사회","사회1",2),
            row(2,1,"영어","영어1",3), row(2,2,"과학","과학1",4), row(3,1,"국어","국어2",4),
            row(3,1,"수학","진로수학",null,3.0,"A"), row(3,1,"과학","진로과학",null,3.0,"B")
        )
        val out = OfficialUniversityScoreCalculator.calculate(candidate("우송대","철도차량시스템","교과면접"), profile(rows))
        assertTrue(out.toString(), out.getBoolean("verified"))
        assertEquals(720.0, out.getDouble("maxScore"), 1e-9)
        assertEquals("우송대 2027 학생부 교과성적", out.getString("scoreScale"))
        assertEquals(6, out.getJSONObject("detail").getInt("selectedCourseCount"))
        assertEquals(8.5, out.getJSONObject("detail").getDouble("careerBonus"), 1e-9)
    }

    @Test fun hanbatEngineeringComputesAcademicPartAndKeepsAttendanceSeparate() {
        val rows = mutableListOf<JSONObject>()
        for (i in 1..3) rows += row(1,1,"국어","국어$i",i,4.0)
        for (i in 1..3) rows += row(1,2,"영어","영어$i",i + 1,4.0)
        for (i in 1..3) rows += row(2,1,"수학","수학$i",i + 1,4.0)
        for (i in 1..4) rows += row(2,2, if (i % 2 == 0) "과학" else "사회", "탐구$i",i + 1,4.0)
        rows += row(3,1,"수학","기하",null,3.0,"A")
        rows += row(3,1,"과학","물리학Ⅱ",null,3.0,"A")
        rows += row(3,1,"과학","화학Ⅱ",null,3.0,"B")
        val out = OfficialUniversityScoreCalculator.calculate(candidate("국립한밭대","반도체시스템공","지역인재교과"), profile(rows))
        assertTrue(out.toString(), out.getBoolean("verified"))
        assertEquals(495.0, out.getDouble("maxScore"), 1e-9)
        assertTrue(out.getJSONObject("detail").getBoolean("attendanceExcluded"))
        assertEquals(50, out.getJSONObject("detail").getInt("attendanceMax"))
    }

    @Test fun knutHolisticTwoIsNotInventedAsGradeConversion() {
        val out = OfficialUniversityScoreCalculator.calculate(
            candidate("국립한국교통대","철도차량시스템공","학생부종합Ⅱ","종합"),
            profile(listOf(row(1,1,"국어","국어",3)))
        )
        assertFalse(out.getBoolean("verified"))
        assertTrue(out.getBoolean("notApplicable"))
        assertEquals("holistic-not-quantitative", out.getString("status"))
    }

    @Test fun unsupportedUniversityStaysHold() {
        val out = OfficialUniversityScoreCalculator.calculate(candidate("충남대","건축","교과일반"), profile(listOf(row(1,1,"국어","국어",3))))
        assertFalse(out.getBoolean("verified"))
        assertEquals("unsupported-official-formula", out.getString("status"))
    }
}
