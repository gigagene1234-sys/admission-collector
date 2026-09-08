package com.admissionhub.collector.score

import org.junit.Assert.*
import org.junit.Test

class KoreanTranscriptAutoRecognizerTest {
    private fun row(index: Int, vararg values: String): XlsxStudentScoreImport.Row =
        XlsxStudentScoreImport.Row(index, values.mapIndexedNotNull { col, value ->
            value.takeIf { it.isNotEmpty() }?.let { col to XlsxStudentScoreImport.Cell(index, col, it, false) }
        }.toMap())

    @Test
    fun explicitYearSemesterSectionsBecomeCourseRowsWithoutGuessing() {
        val sheet = XlsxStudentScoreImport.Sheet(
            "교과학습발달상황",
            listOf(
                row(1, "1학년"),
                row(2, "1학기"),
                row(3, "교과", "과목명", "석차등급", "이수단위", "성취도"),
                row(4, "국어", "독서", "3", "4", ""),
                row(5, "수학", "수학Ⅰ", "4", "4", ""),
                row(6, "2학기"),
                row(7, "교과", "과목명", "석차등급", "이수단위", "성취도"),
                row(8, "영어", "영어Ⅰ", "3", "4", "")
            ),
            emptyList()
        )
        val workbook = XlsxStudentScoreImport.Workbook(listOf(sheet), 0, 0)
        val profile = KoreanTranscriptAutoRecognizer.recognizeBest(workbook, 2027, "학생부.xls", "XLS")
        assertNotNull(profile)
        profile!!
        assertEquals("IMPORTED", profile.getString("status"))
        assertEquals(3, profile.getInt("rowCount"))
        assertEquals("explicit-korean-transcript-sections", profile.getString("recognitionMode"))
        val subjects = profile.getJSONArray("subjects")
        assertEquals(1, subjects.getJSONObject(0).getInt("gradeYear"))
        assertEquals(1, subjects.getJSONObject(0).getInt("semester"))
        assertEquals(2, subjects.getJSONObject(2).getInt("semester"))
        assertEquals("영어Ⅰ", subjects.getJSONObject(2).getString("subject"))
    }

    @Test
    fun blankRankGradeIsPreservedWhenAchievementExists() {
        val sheet = XlsxStudentScoreImport.Sheet(
            "성적",
            listOf(
                row(1, "3학년", "1학기"),
                row(2, "교과", "과목", "석차등급", "이수단위", "성취도"),
                row(3, "과학", "물리학Ⅱ", "", "3", "A")
            ),
            emptyList()
        )
        val workbook = XlsxStudentScoreImport.Workbook(listOf(sheet), 0, 0)
        val profile = KoreanTranscriptAutoRecognizer.recognizeBest(workbook, 2027, "학생부.xlsx", "XLSX")
        assertNotNull(profile)
        val course = profile!!.getJSONArray("subjects").getJSONObject(0)
        assertTrue(course.isNull("grade"))
        assertEquals("A", course.getString("achievement"))
        assertEquals(1, profile.getInt("ungradedRows"))
    }

    @Test
    fun noExplicitYearSemesterStructureDoesNotInventThem() {
        val sheet = XlsxStudentScoreImport.Sheet(
            "과목목록",
            listOf(
                row(1, "교과", "과목", "석차등급", "이수단위"),
                row(2, "국어", "독서", "3", "4")
            ),
            emptyList()
        )
        val workbook = XlsxStudentScoreImport.Workbook(listOf(sheet), 0, 0)
        assertNull(KoreanTranscriptAutoRecognizer.recognizeBest(workbook, 2027, "목록.xlsx", "XLSX"))
    }
}
