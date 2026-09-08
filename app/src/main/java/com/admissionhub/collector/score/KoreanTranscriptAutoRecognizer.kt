package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/**
 * Evidence-safe fallback recognizer for Korean school transcript workbooks.
 *
 * School exports often encode 학년/학기 as explicit section rows or merged labels instead of
 * repeating them in dedicated columns. The strict XLS/XLSX importer intentionally does not guess
 * those values, so v0.15 adds this second automatic pass. It propagates only explicit structural
 * markers found in the workbook itself; no year, semester, subject group, grade or credit is
 * invented from general knowledge.
 */
object KoreanTranscriptAutoRecognizer {
    const val SCHEMA_VERSION = 1

    data class Result(val profile: JSONObject, val score: Int)

    fun recognizeBest(
        workbook: XlsxStudentScoreImport.Workbook,
        admissionYear: Int,
        fileName: String,
        sourceType: String
    ): JSONObject? {
        val candidates = workbook.sheets.mapIndexedNotNull { index, sheet ->
            recognizeSheet(workbook, index, sheet, admissionYear, fileName, sourceType)
        }
        return candidates.maxByOrNull { it.score }?.profile
    }

    private fun recognizeSheet(
        workbook: XlsxStudentScoreImport.Workbook,
        sheetIndex: Int,
        sheet: XlsxStudentScoreImport.Sheet,
        admissionYear: Int,
        fileName: String,
        sourceType: String
    ): Result? {
        var currentYear: Int? = null
        var currentSemester: Int? = null
        var currentGroup = ""
        var activeMapping: Map<XlsxStudentScoreImport.Field, Int>? = null
        var activeHeaderRow = -1
        var sectionMarkers = 0
        var headerTransitions = 0
        var conflicts = 0
        val raw = JSONArray()
        val identityPayload = linkedMapOf<String, String>()

        val ordered = sheet.rows.sortedBy { it.index }
        for (row in ordered) {
            val nonBlank = row.cells.values.map { it.value.trim() }.filter { it.isNotBlank() }
            if (nonBlank.isEmpty()) continue

            val explicitYear = detectYearMarker(nonBlank)
            val explicitSemester = detectSemesterMarker(nonBlank)
            if (explicitYear != null) {
                if (currentYear != explicitYear) sectionMarkers++
                currentYear = explicitYear
            }
            if (explicitSemester != null) {
                if (currentSemester != explicitSemester) sectionMarkers++
                currentSemester = explicitSemester
            }
            detectGroupMarker(nonBlank)?.let { group ->
                if (currentGroup != group) sectionMarkers++
                currentGroup = group
            }

            if (looksLikeCourseHeader(nonBlank)) {
                val mapping = XlsxStudentScoreImport.suggestMapping(sheet, row.index)
                if ((mapping[XlsxStudentScoreImport.Field.SUBJECT] ?: -1) >= 0) {
                    activeMapping = mapping
                    activeHeaderRow = row.index
                    headerTransitions++
                    continue
                }
            }

            val mapping = activeMapping ?: continue
            if (row.index <= activeHeaderRow) continue

            fun direct(field: XlsxStudentScoreImport.Field): String {
                val col = mapping[field] ?: -1
                if (col < 0) return ""
                return if (field == XlsxStudentScoreImport.Field.GRADE_YEAR || field == XlsxStudentScoreImport.Field.SEMESTER) {
                    sheet.structuralValue(row.index, col).value.trim()
                } else sheet.cell(row.index, col)?.value.orEmpty().trim()
            }

            val subject = direct(XlsxStudentScoreImport.Field.SUBJECT)
            if (subject.isBlank() || isNonCourseLabel(subject)) continue
            if (subject.length > 120) continue

            val directYear = parseYearValue(direct(XlsxStudentScoreImport.Field.GRADE_YEAR))
            val directSemester = parseSemesterValue(direct(XlsxStudentScoreImport.Field.SEMESTER))
            val year = directYear ?: currentYear ?: continue
            val semester = directSemester ?: currentSemester ?: continue
            if (year !in 1..3 || semester !in 1..2) continue

            val group = direct(XlsxStudentScoreImport.Field.GROUP).ifBlank { currentGroup }
            val grade = normalizeOptionalNumber(direct(XlsxStudentScoreImport.Field.GRADE))
            val credits = normalizeOptionalNumber(direct(XlsxStudentScoreImport.Field.CREDITS))
            val achievement = direct(XlsxStudentScoreImport.Field.ACHIEVEMENT).trim().uppercase(Locale.ROOT)

            // At least one transcript measure should accompany a course row. This prevents a
            // timetable/subject list elsewhere in the workbook from outranking the real grade table.
            if (grade.isBlank() && credits.isBlank() && achievement.isBlank()) continue

            val obj = JSONObject()
                .put("gradeYear", year.toString())
                .put("semester", semester.toString())
                .put("group", group)
                .put("subject", subject)
                .put("grade", grade)
                .put("credits", credits)
                .put("achievement", achievement)
            val identity = "$year|$semester|${normalize(subject)}"
            val payload = listOf(group, subject, grade, credits, achievement).joinToString("|")
            val previous = identityPayload[identity]
            when {
                previous == null -> {
                    identityPayload[identity] = payload
                    raw.put(obj)
                }
                previous == payload -> Unit // exact repeated rendering/header block: deterministic dedupe
                else -> conflicts++
            }
        }

        if (raw.length() == 0 || conflicts > 0) return null
        // This fallback must be anchored by explicit workbook structure; otherwise the strict
        // importer/advanced mapping remains the safer path.
        val mapping = activeMapping ?: return null
        val hasDedicatedYearSemester = (mapping[XlsxStudentScoreImport.Field.GRADE_YEAR] ?: -1) >= 0 &&
            (mapping[XlsxStudentScoreImport.Field.SEMESTER] ?: -1) >= 0
        if (sectionMarkers == 0 && !hasDedicatedYearSemester) return null

        val profile = runCatching {
            StudentScoreImport.parse(
                JSONObject().put("academicYear", admissionYear).put("subjects", raw).toString(),
                admissionYear,
                false
            )
        }.getOrNull() ?: return null

        val graded = profile.optInt("gradedRows", 0)
        val withCredits = profile.optInt("rowCount", 0) - profile.optInt("missingCreditRows", 0)
        val score = profile.optInt("rowCount", 0) * 100 + graded * 8 + withCredits * 3 + sectionMarkers * 5 + headerTransitions * 2
        return Result(
            profile.put("sourceType", sourceType)
                .put("xlsxFileName", fileName.take(240))
                .put("xlsxSheetName", sheet.name)
                .put("xlsxSheetIndex", sheetIndex)
                .put("automaticRecognition", true)
                .put("automaticRecognitionSchema", SCHEMA_VERSION)
                .put("recognitionMode", "explicit-korean-transcript-sections")
                .put("explicitStructureOnly", true)
                .put("sectionMarkersUsed", sectionMarkers)
                .put("headerTransitions", headerTransitions)
                .put("conflictingDuplicateRows", conflicts)
                .put("xlsxFormulaPolicy", "DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY")
                .put("xlsxBlankGradePolicy", "PRESERVE_NULL")
                .put("xlsxStructuralFillPolicy", "EXPLICIT_YEAR_SEMESTER_SECTION_OR_MERGE_ONLY"),
            score
        )
    }

    private fun looksLikeCourseHeader(values: List<String>): Boolean {
        val normalized = values.map(::normalize)
        val subject = normalized.any { it in setOf("과목", "과목명", "교과목", "교과목명", "subject") }
        if (!subject) return false
        val measure = normalized.any {
            it in setOf("등급", "석차등급", "내신등급", "학점", "이수단위", "단위수", "성취도", "성취수준", "grade", "credits", "credit", "achievement")
        }
        return measure || normalized.any { it in setOf("교과", "교과군", "학년", "학기") }
    }

    private fun detectYearMarker(values: List<String>): Int? {
        for (raw in values) {
            val n = normalize(raw)
            Regex("^([123])학년$").matchEntire(n)?.groupValues?.getOrNull(1)?.toIntOrNull()?.let { return it }
            Regex("^([123])학년[12]학기$").matchEntire(n)?.groupValues?.getOrNull(1)?.toIntOrNull()?.let { return it }
        }
        return null
    }

    private fun detectSemesterMarker(values: List<String>): Int? {
        for (raw in values) {
            val n = normalize(raw)
            Regex("^([12])학기$").matchEntire(n)?.groupValues?.getOrNull(1)?.toIntOrNull()?.let { return it }
            Regex("^[123]학년([12])학기$").matchEntire(n)?.groupValues?.getOrNull(1)?.toIntOrNull()?.let { return it }
        }
        return null
    }

    private fun detectGroupMarker(values: List<String>): String? {
        if (values.size > 2) return null
        for (raw in values) {
            val n = normalize(raw)
            return when (n) {
                "국어", "국어교과", "국어교과군" -> "국어"
                "수학", "수학교과", "수학교과군" -> "수학"
                "영어", "영어교과", "영어교과군" -> "영어"
                "사회", "사회교과", "사회교과군" -> "사회"
                "과학", "과학교과", "과학교과군" -> "과학"
                else -> continue
            }
        }
        return null
    }

    private fun parseYearValue(raw: String): Int? {
        val n = normalize(raw)
        return when {
            n.matches(Regex("[123]")) -> n.toInt()
            n.matches(Regex("[123]학년")) -> n.substring(0, 1).toInt()
            else -> null
        }
    }

    private fun parseSemesterValue(raw: String): Int? {
        val n = normalize(raw)
        return when {
            n.matches(Regex("[12]")) -> n.toInt()
            n.matches(Regex("[12]학기")) -> n.substring(0, 1).toInt()
            else -> null
        }
    }

    private fun normalizeOptionalNumber(raw: String): String {
        val v = raw.trim()
        if (v.isBlank() || v in setOf("-", "—", "미기재")) return ""
        return v.replace(",", "")
    }

    private fun isNonCourseLabel(raw: String): Boolean {
        val n = normalize(raw)
        return n in setOf("과목", "과목명", "교과목", "교과목명", "합계", "총계", "평균", "이수단위합계", "학점합계") ||
            n.startsWith("※")
    }

    private fun normalize(raw: String): String = raw.trim().lowercase(Locale.ROOT)
        .replace("Ⅰ", "1").replace("Ⅱ", "2")
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\):]"), "")
        .replace(Regex("[^0-9a-z가-힣※]"), "")
}
