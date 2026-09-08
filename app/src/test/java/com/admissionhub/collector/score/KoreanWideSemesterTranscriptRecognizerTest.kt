package com.admissionhub.collector.score

import org.junit.Assert.*
import org.junit.Test

class KoreanWideSemesterTranscriptRecognizerTest {
    private fun row(index: Int, vararg values: String): XlsxStudentScoreImport.Row =
        XlsxStudentScoreImport.Row(index, values.mapIndexedNotNull { col, value ->
            value.takeIf { it.isNotEmpty() }?.let { col to XlsxStudentScoreImport.Cell(index, col, it, false) }
        }.toMap())

    private fun workbook(vararg rows: XlsxStudentScoreImport.Row): XlsxStudentScoreImport.Workbook =
        XlsxStudentScoreImport.Workbook(
            listOf(XlsxStudentScoreImport.Sheet("Sheet1", rows.toList(), emptyList())), 0, 0
        )

    @Test
    fun onePhysicalCourseRowSplitsIntoExplicitSemesterRows() {
        val wb = workbook(
            row(1,
                "학년", "교과구분종류", "교과", "과목",
                "1학기 단위수/학점", "1학기 석차등급", "1학기 원점수", "1학기 과목평균", "1학기 표준편차", "1학기 수강자수", "1학기 성취도",
                "1학기 성취도별분포(A)", "1학기 성취도별분포(B)", "1학기 성취도별분포(C)", "1학기 성취도별분포(D)", "1학기 성취도별분포(E)",
                "2학기 단위수/학점", "2학기 석차등급", "2학기 원점수", "2학기 과목평균", "2학기 표준편차", "2학기 수강자수", "2학기 성취도",
                "2학기 성취도별분포(A)", "2학기 성취도별분포(B)", "2학기 성취도별분포(C)", "2학기 성취도별분포(D)", "2학기 성취도별분포(E)"
            ),
            row(2, "1", "일반", "국어", "국어", "4", "3", "", "", "", "", "B", "", "", "", "", "", "4", "4", "", "", "", "", "B")
        )
        val profile = KoreanWideSemesterTranscriptRecognizer.recognizeBest(wb, 2027, "학생부 성적 관리.xls", "XLS")
        assertNotNull(profile)
        profile!!
        assertEquals("wide-semester-columns", profile.getString("recognitionMode"))
        assertEquals(2, profile.getInt("rowCount"))
        val subjects = profile.getJSONArray("subjects")
        assertEquals(1, subjects.getJSONObject(0).getInt("semester"))
        assertEquals(3.0, subjects.getJSONObject(0).getDouble("grade"), 0.0)
        assertEquals(2, subjects.getJSONObject(1).getInt("semester"))
        assertEquals(4.0, subjects.getJSONObject(1).getDouble("grade"), 0.0)
    }

    @Test
    fun zeroOrBlankRankGradeBecomesNullButCareerAchievementIsKept() {
        val wb = workbook(
            row(1, "학년", "교과", "과목", "1학기 단위수/학점", "1학기 석차등급", "1학기 성취도", "1학기 성취도별분포(A)", "1학기 성취도별분포(B)", "1학기 성취도별분포(C)"),
            row(2, "3", "과학", "물리학Ⅱ", "3", "0", "A", "83.3", "8.3", "8.3")
        )
        val profile = KoreanWideSemesterTranscriptRecognizer.recognizeBest(wb, 2027, "학생부.xls", "XLS")!!
        assertEquals(1, profile.getInt("rowCount"))
        assertEquals(1, profile.getInt("ungradedRows"))
        val course = profile.getJSONArray("subjects").getJSONObject(0)
        assertTrue(course.isNull("grade"))
        assertEquals("A", course.getString("achievement"))
        val dist = course.getJSONObject("achievementDistribution")
        assertEquals(83.3, dist.getDouble("A"), 0.0001)
        assertEquals(1, profile.getInt("zeroRankGradesNormalizedToNull"))
    }

    @Test
    fun emptySecondSemesterBlockIsNotInvented() {
        val wb = workbook(
            row(1, "학년", "교과", "과목", "1학기 단위수/학점", "1학기 석차등급", "1학기 성취도", "2학기 단위수/학점", "2학기 석차등급", "2학기 성취도"),
            row(2, "1", "수학", "인공지능 수학", "", "", "", "2", "0", "A")
        )
        val profile = KoreanWideSemesterTranscriptRecognizer.recognizeBest(wb, 2027, "학생부.xls", "XLS")!!
        assertEquals(1, profile.getInt("rowCount"))
        val course = profile.getJSONArray("subjects").getJSONObject(0)
        assertEquals(2, course.getInt("semester"))
        assertEquals("인공지능 수학", course.getString("subject"))
        assertTrue(course.isNull("grade"))
    }

    @Test
    fun noExplicitSemesterHeadersAreRejected() {
        val wb = workbook(
            row(1, "학년", "교과", "과목", "단위수", "석차등급", "성취도"),
            row(2, "1", "국어", "독서", "4", "3", "B")
        )
        assertNull(KoreanWideSemesterTranscriptRecognizer.recognizeBest(wb, 2027, "목록.xls", "XLS"))
    }
}
