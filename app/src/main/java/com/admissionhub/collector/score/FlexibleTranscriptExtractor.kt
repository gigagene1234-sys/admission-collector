package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject

/**
 * Fallback transcript extractor for school-exported XLS/XLSX sheets that repeat headers by term
 * or place 학년/학기 in section labels instead of dedicated columns.
 */
object FlexibleTranscriptExtractor {
    const val SCHEMA_VERSION = 1

    fun extract(
        workbook: XlsxStudentScoreImport.Workbook,
        admissionYear: Int,
        complete: Boolean,
        fileName: String,
        sourceType: String
    ): JSONObject {
        data class Candidate(val score: Int, val profile: JSONObject)
        val candidates = mutableListOf<Candidate>()
        workbook.sheets.forEachIndexed { sheetIndex, sheet ->
            val rows = sheet.rows.sortedBy { it.index }
            var currentYear: String? = null
            var currentSemester: String? = null
            var mapping: Map<XlsxStudentScoreImport.Field, Int>? = null
            var headerRow = -1
            val subjects = JSONArray()
            var mappedFields = 0

            fun rowText(rowIndex: Int): String {
                val row = rows.firstOrNull { it.index == rowIndex } ?: return ""
                return row.cells.toSortedMap().values.joinToString(" ") { it.value }.trim()
            }
            fun updateContext(text: String) {
                Regex("([123])\\s*학년").find(text)?.groupValues?.getOrNull(1)?.let { currentYear = it }
                Regex("([12])\\s*학기").find(text)?.groupValues?.getOrNull(1)?.let { currentSemester = it }
                Regex("(?:^|[^0-9])([123])[-./]([12])(?:[^0-9]|$)").find(text)?.let {
                    currentYear = it.groupValues[1]; currentSemester = it.groupValues[2]
                }
            }

            for (row in rows) {
                val text = rowText(row.index)
                updateContext(text)
                val suggested = XlsxStudentScoreImport.suggestMapping(sheet, row.index)
                val subjectCol = suggested[XlsxStudentScoreImport.Field.SUBJECT] ?: -1
                val gradeCol = suggested[XlsxStudentScoreImport.Field.GRADE] ?: -1
                val creditsCol = suggested[XlsxStudentScoreImport.Field.CREDITS] ?: -1
                val achievementCol = suggested[XlsxStudentScoreImport.Field.ACHIEVEMENT] ?: -1
                val looksHeader = subjectCol >= 0 && listOf(gradeCol, creditsCol, achievementCol).count { it >= 0 } >= 1
                if (looksHeader) {
                    mapping = suggested
                    headerRow = row.index
                    mappedFields = maxOf(mappedFields, suggested.values.count { it >= 0 })
                    continue
                }
                val active = mapping ?: continue
                if (row.index <= headerRow) continue
                val subjectColumn = active[XlsxStudentScoreImport.Field.SUBJECT] ?: -1
                if (subjectColumn < 0) continue
                val subject = sheet.cell(row.index, subjectColumn)?.value.orEmpty().trim()
                if (subject.isBlank()) continue
                if (subject.contains("합계") || subject.contains("평균") || subject.contains("이수단위 합")) continue

                fun direct(field: XlsxStudentScoreImport.Field): String {
                    val col = active[field] ?: -1
                    if (col < 0) return ""
                    return sheet.cell(row.index, col)?.value.orEmpty().trim()
                }
                fun structural(field: XlsxStudentScoreImport.Field): String {
                    val col = active[field] ?: -1
                    if (col < 0) return ""
                    return sheet.structuralValue(row.index, col).value.trim()
                }
                val year = structural(XlsxStudentScoreImport.Field.GRADE_YEAR).ifBlank { currentYear.orEmpty() }
                val semester = structural(XlsxStudentScoreImport.Field.SEMESTER).ifBlank { currentSemester.orEmpty() }
                if (year !in setOf("1", "2", "3") || semester !in setOf("1", "2")) continue
                subjects.put(JSONObject()
                    .put("gradeYear", year)
                    .put("semester", semester)
                    .put("group", direct(XlsxStudentScoreImport.Field.GROUP))
                    .put("subject", subject)
                    .put("grade", direct(XlsxStudentScoreImport.Field.GRADE))
                    .put("credits", direct(XlsxStudentScoreImport.Field.CREDITS))
                    .put("achievement", direct(XlsxStudentScoreImport.Field.ACHIEVEMENT)))
            }
            if (subjects.length() == 0) return@forEachIndexed
            val profile = StudentScoreImport.parse(
                JSONObject().put("academicYear", admissionYear).put("subjects", subjects).toString(),
                admissionYear,
                complete
            ).put("sourceType", sourceType)
                .put("excelFileName", fileName.take(240))
                .put("xlsxSheetName", sheet.name)
                .put("xlsxSheetIndex", sheetIndex)
                .put("automaticRecognition", true)
                .put("flexibleSectionContextRecognition", true)
                .put("formulaPolicy", "DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY")
                .put("blankGradePolicy", "PRESERVE_NULL")
            candidates += Candidate(subjects.length() * 100 + mappedFields * 10 - sheetIndex, profile)
        }
        return candidates.maxByOrNull { it.score }?.profile
            ?: error("학생부 과목표를 자동 인식하지 못했습니다. 학년·학기 표제와 과목/석차등급/이수단위 열을 확인하세요.")
    }
}
