package com.admissionhub.collector.score

import org.apache.poi.hssf.usermodel.HSSFWorkbook
import org.apache.poi.ss.util.CellRangeAddress
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream

class LegacyXlsStudentScoreImportTest {
    @Test fun parsesOle2XlsIntoSharedReviewWorkbookModel() {
        val bytes = ByteArrayOutputStream().use { out ->
            HSSFWorkbook().use { wb ->
                val s = wb.createSheet("학생부")
                val header = s.createRow(0)
                listOf("학년","학기","교과","과목","석차등급","학점","성취도").forEachIndexed { i, v -> header.createCell(i).setCellValue(v) }
                val r1 = s.createRow(1)
                r1.createCell(0).setCellValue(1.0); r1.createCell(1).setCellValue(1.0); r1.createCell(2).setCellValue("국어")
                r1.createCell(3).setCellValue("국어"); r1.createCell(4).setCellValue(3.0); r1.createCell(5).setCellValue(4.0)
                val r2 = s.createRow(2)
                r2.createCell(2).setCellValue("수학"); r2.createCell(3).setCellValue("수학"); r2.createCell(4).setCellValue(4.0); r2.createCell(5).setCellValue(4.0)
                s.addMergedRegion(CellRangeAddress(1, 2, 0, 0))
                s.addMergedRegion(CellRangeAddress(1, 2, 1, 1))
                wb.write(out)
            }
            out.toByteArray()
        }
        assertTrue(LegacyXlsStudentScoreImport.looksLikeXls(bytes))
        val parsed = LegacyXlsStudentScoreImport.parse(bytes)
        assertEquals(1, parsed.sheets.size)
        val sheet = parsed.sheets[0]
        assertEquals("학생부", sheet.name)
        assertEquals(1, XlsxStudentScoreImport.suggestHeaderRow(sheet))
        assertEquals("1", sheet.structuralValue(3, 0).value)
        assertTrue(sheet.structuralValue(3, 0).fromMergedCell)
        val map = XlsxStudentScoreImport.suggestMapping(sheet, 1)
        val profile = XlsxStudentScoreImport.buildProfile(parsed, 0, 1, map, 2027, true, "학생부 성적 관리.xls")
        assertEquals(2, profile.getInt("rowCount"))
        assertEquals(3.5, profile.getDouble("ownWeightedGrade"), 1e-9)
        assertEquals(2, profile.getInt("xlsxMergedStructuralFills"))
    }

    @Test fun rejectsZipXlsxAsLegacyXls() {
        assertFalse(LegacyXlsStudentScoreImport.looksLikeXls(byteArrayOf('P'.code.toByte(),'K'.code.toByte(),3,4)))
    }
}
