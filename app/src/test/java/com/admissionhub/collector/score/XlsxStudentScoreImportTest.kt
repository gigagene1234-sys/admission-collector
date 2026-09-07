package com.admissionhub.collector.score

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class XlsxStudentScoreImportTest {
    private fun xlsx(sheet1: String, sheet2: String = "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData/></worksheet>"): ByteArray {
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { zip ->
            fun add(name: String, text: String) {
                zip.putNextEntry(ZipEntry(name)); zip.write(text.toByteArray()); zip.closeEntry()
            }
            add("xl/workbook.xml", """
                <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                  <sheets><sheet name="성적" sheetId="1" r:id="rId1"/><sheet name="기타" sheetId="2" r:id="rId2"/></sheets>
                </workbook>
            """.trimIndent())
            add("xl/_rels/workbook.xml.rels", """
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                  <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
                  <Relationship Id="rId2" Type="worksheet" Target="worksheets/sheet2.xml"/>
                  <Relationship Id="ext" Type="external" Target="https://example.com/evil" TargetMode="External"/>
                </Relationships>
            """.trimIndent())
            add("xl/sharedStrings.xml", """
                <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
                  <si><t>수학</t></si><si><r><t>물</t></r><r><t>리</t></r></si>
                </sst>
            """.trimIndent())
            add("xl/worksheets/sheet1.xml", sheet1)
            add("xl/worksheets/sheet2.xml", sheet2)
        }
        return out.toByteArray()
    }

    private val transcriptSheet = """
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData>
            <row r="1">
              <c r="A1" t="inlineStr"><is><t>학년</t></is></c>
              <c r="B1" t="inlineStr"><is><t>학기</t></is></c>
              <c r="C1" t="inlineStr"><is><t>교과</t></is></c>
              <c r="D1" t="inlineStr"><is><t>과목</t></is></c>
              <c r="E1" t="inlineStr"><is><t>석차등급</t></is></c>
              <c r="F1" t="inlineStr"><is><t>이수단위</t></is></c>
              <c r="G1" t="inlineStr"><is><t>성취도</t></is></c>
            </row>
            <row r="2">
              <c r="A2"><v>1</v></c><c r="B2"><v>1</v></c>
              <c r="C2" t="inlineStr"><is><t>수학</t></is></c><c r="D2" t="s"><v>0</v></c>
              <c r="E2"><v>3</v></c><c r="F2"><f>2+2</f><v>4</v></c><c r="G2" t="inlineStr"><is><t>A</t></is></c>
            </row>
            <row r="3">
              <c r="C3" t="inlineStr"><is><t>과학</t></is></c><c r="D3" t="s"><v>1</v></c>
              <c r="E3"></c><c r="F3"><v>3</v></c><c r="G3" t="inlineStr"><is><t>A</t></is></c>
            </row>
          </sheetData>
          <mergeCells count="2"><mergeCell ref="A2:A3"/><mergeCell ref="B2:B3"/></mergeCells>
        </worksheet>
    """.trimIndent()

    @Test fun readsMultipleSheetsSharedStringsMergesAndCachedFormulaWithoutEvaluation() {
        val workbook = XlsxStudentScoreImport.parse(xlsx(transcriptSheet))
        assertEquals(2, workbook.sheets.size)
        assertEquals("성적", workbook.sheets[0].name)
        assertEquals(2, workbook.sharedStringCount)
        assertEquals(1, workbook.formulaCellCount)
        assertEquals("물리", workbook.sheets[0].directValue(3, 3))
        assertEquals("1", workbook.sheets[0].structuralValue(3, 0).value)
        assertTrue(workbook.sheets[0].structuralValue(3, 0).fromMergedCell)
    }

    @Test fun mapsTranscriptAndPreservesBlankGradeInsteadOfZero() {
        val workbook = XlsxStudentScoreImport.parse(xlsx(transcriptSheet))
        val sheet = workbook.sheets[0]
        val header = XlsxStudentScoreImport.suggestHeaderRow(sheet)
        assertEquals(1, header)
        val mapping = XlsxStudentScoreImport.suggestMapping(sheet, header)
        assertEquals(0, mapping[XlsxStudentScoreImport.Field.GRADE_YEAR])
        assertEquals(3, mapping[XlsxStudentScoreImport.Field.SUBJECT])
        assertEquals(4, mapping[XlsxStudentScoreImport.Field.GRADE])
        val profile = XlsxStudentScoreImport.buildProfile(workbook, 0, header, mapping, 2027, true, "학생부.xlsx")
        assertEquals(2, profile.getInt("rowCount"))
        assertEquals(1, profile.getInt("ungradedRows"))
        assertEquals(1, profile.getInt("xlsxFormulaCachedCellsUsed"))
        assertEquals(2, profile.getInt("xlsxMergedStructuralFills"))
        val subjects = profile.getJSONArray("subjects")
        assertTrue(subjects.getJSONObject(1).isNull("grade"))
        assertEquals(3.0, profile.getDouble("ownWeightedGrade"), 0.000001)
        assertEquals("DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY", profile.getString("xlsxFormulaPolicy"))
    }

    @Test fun unmergedBlankYearSemesterAreNotInvented() {
        val noMerges = transcriptSheet.replace("<mergeCells count=\"2\"><mergeCell ref=\"A2:A3\"/><mergeCell ref=\"B2:B3\"/></mergeCells>", "")
        val workbook = XlsxStudentScoreImport.parse(xlsx(noMerges))
        val mapping = XlsxStudentScoreImport.suggestMapping(workbook.sheets[0], 1)
        val error = runCatching { XlsxStudentScoreImport.buildProfile(workbook, 0, 1, mapping, 2027, true, "학생부.xlsx") }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error!!.message.orEmpty().contains("학년·학기·과목"))
    }

    @Test fun duplicateColumnMappingIsRejected() {
        val workbook = XlsxStudentScoreImport.parse(xlsx(transcriptSheet))
        val mapping = XlsxStudentScoreImport.suggestMapping(workbook.sheets[0], 1).toMutableMap()
        mapping[XlsxStudentScoreImport.Field.SEMESTER] = mapping[XlsxStudentScoreImport.Field.GRADE_YEAR]!!
        val error = runCatching { XlsxStudentScoreImport.buildProfile(workbook, 0, 1, mapping, 2027, true, "학생부.xlsx") }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error!!.message.orEmpty().contains("중복"))
    }

    @Test fun malformedZipTraversalIsRejected() {
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { zip ->
            zip.putNextEntry(ZipEntry("../xl/workbook.xml")); zip.write("x".toByteArray()); zip.closeEntry()
        }
        val error = runCatching { XlsxStudentScoreImport.parse(out.toByteArray()) }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error!!.message.orEmpty().contains("워크북 밖"))
    }

    @Test fun missingRequiredColumnIsRejectedAtProfileBuild() {
        val workbook = XlsxStudentScoreImport.parse(xlsx(transcriptSheet))
        val mapping = XlsxStudentScoreImport.suggestMapping(workbook.sheets[0], 1).toMutableMap()
        mapping[XlsxStudentScoreImport.Field.SUBJECT] = -1
        val error = runCatching { XlsxStudentScoreImport.buildProfile(workbook, 0, 1, mapping, 2027, true, "학생부.xlsx") }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error!!.message.orEmpty().contains("과목 열"))
    }
}
