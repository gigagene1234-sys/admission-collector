package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/**
 * Recognizes Korean transcript exports where one physical course row contains separate
 * 1학기/2학기 score blocks, e.g. `1학기 단위수/학점`, `1학기 석차등급`, ... .
 *
 * Safety rules:
 * - the school year comes only from an explicit 학년 cell in the workbook;
 * - the semester comes only from the explicit `1학기`/`2학기` header prefix;
 * - blank, dash and numeric zero rank grades remain null (never grade 0);
 * - no missing year/semester/grade/credit is inferred from general knowledge.
 */
object KoreanWideSemesterTranscriptRecognizer {
    const val SCHEMA_VERSION = 1

    private data class SemesterColumns(
        var credits: Int = -1,
        var grade: Int = -1,
        var achievement: Int = -1,
        val distribution: MutableMap<String, Int> = linkedMapOf()
    )

    private data class Header(
        val row: Int,
        val year: Int,
        val group: Int,
        val subject: Int,
        val semester: Map<Int, SemesterColumns>,
        val score: Int
    )

    fun recognizeBest(
        workbook: XlsxStudentScoreImport.Workbook,
        admissionYear: Int,
        fileName: String,
        sourceType: String
    ): JSONObject? {
        data class Candidate(val profile: JSONObject, val score: Int)
        val candidates = mutableListOf<Candidate>()
        workbook.sheets.forEachIndexed { sheetIndex, sheet ->
            val header = findHeader(sheet) ?: return@forEachIndexed
            val raw = JSONArray()
            val extras = linkedMapOf<String, JSONObject>()
            var physicalRowsUsed = 0
            var semesterRows = 0
            var zeroGradesNormalized = 0

            for (row in sheet.rows.sortedBy { it.index }) {
                if (row.index <= header.row) continue
                val year = parseYear(value(sheet, row.index, header.year, structural = true)) ?: continue
                if (year !in 1..3) continue
                val subject = value(sheet, row.index, header.subject).trim()
                if (subject.isBlank() || isNonCourseLabel(subject) || subject.length > 120) continue
                val group = if (header.group >= 0) value(sheet, row.index, header.group).trim() else ""
                var usedThisPhysicalRow = false

                for (semester in 1..2) {
                    val cols = header.semester[semester] ?: continue
                    val creditsRaw = if (cols.credits >= 0) value(sheet, row.index, cols.credits).trim() else ""
                    val gradeRaw = if (cols.grade >= 0) value(sheet, row.index, cols.grade).trim() else ""
                    val achievementRaw = if (cols.achievement >= 0) value(sheet, row.index, cols.achievement).trim() else ""
                    val credits = normalizeCredits(creditsRaw)
                    val grade = normalizeGrade(gradeRaw)
                    if (gradeRaw.trim() in setOf("0", "0.0")) zeroGradesNormalized++
                    val achievement = normalizeAchievement(achievementRaw)

                    // A semester exists only when the workbook explicitly carries a transcript
                    // measure for that semester. Empty semester blocks are not invented.
                    val active = credits.isNotBlank() || grade.isNotBlank() || achievement.isNotBlank()
                    if (!active) continue

                    raw.put(JSONObject()
                        .put("gradeYear", year.toString())
                        .put("semester", semester.toString())
                        .put("group", group)
                        .put("subject", subject)
                        .put("grade", grade)
                        .put("credits", credits)
                        .put("achievement", achievement))

                    val distribution = JSONObject()
                    for ((letter, col) in cols.distribution) {
                        normalizePercent(value(sheet, row.index, col)).takeIf { it.isNotBlank() }?.let { distribution.put(letter, it.toDouble()) }
                    }
                    if (distribution.length() > 0) extras[identity(year, semester, subject)] = distribution
                    semesterRows++
                    usedThisPhysicalRow = true
                }
                if (usedThisPhysicalRow) physicalRowsUsed++
            }

            if (raw.length() == 0) return@forEachIndexed
            val profile = runCatching {
                StudentScoreImport.parse(
                    JSONObject().put("academicYear", admissionYear).put("subjects", raw).toString(),
                    admissionYear,
                    false
                )
            }.getOrNull() ?: return@forEachIndexed

            // Keep optional achievement distributions as evidence for official calculators that
            // explicitly require them. StudentScoreImport remains the validator of core fields.
            val subjects = profile.optJSONArray("subjects") ?: JSONArray()
            for (i in 0 until subjects.length()) {
                val item = subjects.optJSONObject(i) ?: continue
                val key = identity(item.optInt("gradeYear"), item.optInt("semester"), item.optString("subject"))
                extras[key]?.let { item.put("achievementDistribution", JSONObject(it.toString())) }
            }

            val graded = profile.optInt("gradedRows", 0)
            val withCredits = profile.optInt("rowCount", 0) - profile.optInt("missingCreditRows", 0)
            val score = semesterRows * 100 + graded * 8 + withCredits * 3 + header.score
            candidates += Candidate(
                profile.put("sourceType", sourceType)
                    .put("xlsxFileName", fileName.take(240))
                    .put("xlsxSheetName", sheet.name)
                    .put("xlsxSheetIndex", sheetIndex)
                    .put("xlsxHeaderRow", header.row)
                    .put("automaticRecognition", true)
                    .put("automaticRecognitionSchema", SCHEMA_VERSION)
                    .put("recognitionMode", "wide-semester-columns")
                    .put("explicitStructureOnly", true)
                    .put("widePhysicalCourseRows", physicalRowsUsed)
                    .put("wideSemesterRows", semesterRows)
                    .put("zeroRankGradesNormalizedToNull", zeroGradesNormalized)
                    .put("xlsxFormulaPolicy", "DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY")
                    .put("xlsxBlankGradePolicy", "PRESERVE_NULL_ZERO_AS_NULL")
                    .put("xlsxStructuralFillPolicy", "EXPLICIT_YEAR_CELL_AND_SEMESTER_HEADER_ONLY"),
                score
            )
        }
        return candidates.maxByOrNull { it.score }?.profile
    }

    private fun findHeader(sheet: XlsxStudentScoreImport.Sheet): Header? {
        var best: Header? = null
        for (row in sheet.rows.sortedBy { it.index }.take(100)) {
            val labels = row.cells.mapValues { normalizeHeader(it.value.value) }
            fun col(vararg aliases: String): Int {
                val normalizedAliases = aliases.map(::normalizeHeader)
                return labels.entries.firstOrNull { (_, v) -> normalizedAliases.any { a -> v == a } }?.key ?: -1
            }
            val year = col("학년")
            val subject = col("과목", "과목명", "교과목", "교과목명")
            val group = col("교과", "교과군", "교과영역")
            if (year < 0 || subject < 0) continue

            val semesters = linkedMapOf<Int, SemesterColumns>()
            for (semester in 1..2) {
                val sc = SemesterColumns()
                for ((column, label) in labels) {
                    if (!label.startsWith("${semester}학기")) continue
                    val suffix = label.removePrefix("${semester}학기")
                    when {
                        suffix.contains("단위수") || suffix.contains("학점") -> if (sc.credits < 0) sc.credits = column
                        suffix.contains("석차등급") || suffix == "등급" -> if (sc.grade < 0) sc.grade = column
                        suffix.startsWith("성취도별분포") -> {
                            Regex("성취도별분포([abcde])").find(suffix)?.groupValues?.getOrNull(1)?.uppercase(Locale.ROOT)?.let { sc.distribution[it] = column }
                        }
                        suffix == "성취도" || suffix == "성취수준" -> if (sc.achievement < 0) sc.achievement = column
                    }
                }
                if (sc.credits >= 0 || sc.grade >= 0 || sc.achievement >= 0) semesters[semester] = sc
            }
            if (semesters.isEmpty()) continue
            val score = 100 + semesters.size * 25 + semesters.values.sumOf {
                listOf(it.credits, it.grade, it.achievement).count { c -> c >= 0 } * 6 + it.distribution.size
            } + if (group >= 0) 5 else 0
            val candidate = Header(row.index, year, group, subject, semesters, score)
            if (best == null || candidate.score > best!!.score) best = candidate
        }
        return best
    }

    private fun value(sheet: XlsxStudentScoreImport.Sheet, row: Int, col: Int, structural: Boolean = false): String {
        if (col < 0) return ""
        return if (structural) sheet.structuralValue(row, col).value else sheet.cell(row, col)?.value.orEmpty()
    }

    private fun parseYear(raw: String): Int? {
        val n = normalizeHeader(raw)
        return when {
            n.matches(Regex("[123]")) -> n.toInt()
            n.matches(Regex("[123]학년")) -> n.substring(0, 1).toInt()
            else -> null
        }
    }

    private fun normalizeCredits(raw: String): String {
        val v = raw.trim().replace(",", "")
        if (v.isBlank() || v in setOf("-", "—", "미기재", "0", "0.0")) return ""
        return v.toDoubleOrNull()?.takeIf { it.isFinite() && it > 0.0 }?.let(::plainNumber).orEmpty()
    }

    private fun normalizeGrade(raw: String): String {
        val v = raw.trim().replace(",", "")
        if (v.isBlank() || v in setOf("-", "—", "미기재", "0", "0.0")) return ""
        val n = v.toDoubleOrNull() ?: return ""
        if (!n.isFinite() || n !in 1.0..9.0 || n % 1.0 != 0.0) return ""
        return n.toInt().toString()
    }

    private fun normalizeAchievement(raw: String): String {
        val v = raw.trim().uppercase(Locale.ROOT)
        return if (v in setOf("A", "B", "C", "D", "E", "P")) v else ""
    }

    private fun normalizePercent(raw: String): String {
        val v = raw.trim().removeSuffix("%").replace(",", "")
        if (v.isBlank() || v in setOf("-", "—")) return ""
        val n = v.toDoubleOrNull() ?: return ""
        return n.takeIf { it.isFinite() && it in 0.0..100.0 }?.let(::plainNumber).orEmpty()
    }

    private fun plainNumber(value: Double): String = if (value % 1.0 == 0.0) value.toInt().toString() else value.toString()

    private fun identity(year: Int, semester: Int, subject: String): String = "$year|$semester|${normalizeHeader(subject)}"

    private fun isNonCourseLabel(raw: String): Boolean = normalizeHeader(raw) in setOf(
        "과목", "과목명", "교과목", "교과목명", "합계", "총계", "평균", "이수단위합계", "학점합계"
    )

    private fun normalizeHeader(raw: String): String = raw.trim().lowercase(Locale.ROOT)
        .replace("Ⅰ", "1").replace("Ⅱ", "2")
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\):]"), "")
        .replace(Regex("[^0-9a-z가-힣]"), "")
}
