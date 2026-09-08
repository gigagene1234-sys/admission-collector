package com.admissionhub.collector.score

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.database.Cursor
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.text.InputType
import android.view.Gravity
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.Locale

/**
 * One-screen transcript workflow:
 * choose Excel -> automatic sheet/header/column analysis -> visible editable rows -> save + six-card analysis.
 *
 * The normal path has no intermediate mapping/result dialog. If automatic recognition cannot produce a
 * transcript, the user can explicitly open the legacy advanced mapping screen instead.
 */
class UnifiedExcelScoreActivity : Activity() {
    private lateinit var store: LocalCollectorStore
    private lateinit var root: LinearLayout
    private var parsedProfile: JSONObject? = null
    private var sourceFormat = "XLSX"
    private var fileName = "학생부"
    private var sessionId: String? = null
    private lateinit var yearEdit: EditText
    private lateinit var completeCheck: CheckBox
    private val rows = mutableListOf<RowEditors>()

    data class RowEditors(
        val year: EditText,
        val semester: EditText,
        val group: EditText,
        val subject: EditText,
        val grade: EditText,
        val credits: EditText,
        val achievement: EditText
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sessionId = intent.getStringExtra(EXTRA_SESSION_ID)
        store = LocalCollectorStore(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(30))
        }
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
        renderStart()
        openPicker()
    }

    private fun renderStart() {
        root.removeAllViews()
        title("학생부 자동 분석 · 입력")
        info("Excel 파일을 고르면 시트·헤더·열을 자동 분석하고, 인식된 과목을 바로 편집 가능한 형태로 표시합니다. 별도 결과창 없이 이 화면에서 확인한 뒤 한 번에 저장하고 6장 원서를 다시 분석합니다.")
        button("XLS / XLSX 선택") { openPicker() }
    }

    private fun openPicker() {
        startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/*"
            putExtra(Intent.EXTRA_MIME_TYPES, arrayOf(
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/octet-stream"
            ))
        }, PICK_EXCEL)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != PICK_EXCEL || resultCode != RESULT_OK) return
        val uri = data?.data ?: return
        fileName = displayName(uri) ?: "학생부 Excel"
        root.removeAllViews(); title("학생부 분석 중"); info(fileName)
        Thread {
            val result = runCatching {
                val bytes = readLimited(uri)
                val workbook = when {
                    LegacyXlsStudentScoreImport.looksLikeXls(bytes) -> {
                        sourceFormat = "XLS"
                        LegacyXlsStudentScoreImport.parse(bytes)
                    }
                    bytes.size >= 4 && bytes[0] == 'P'.code.toByte() && bytes[1] == 'K'.code.toByte() -> {
                        sourceFormat = "XLSX"
                        XlsxStudentScoreImport.parse(bytes)
                    }
                    else -> throw IllegalArgumentException("실제 .xls 또는 .xlsx 형식이 아닙니다.")
                }
                val strict = runCatching { autoRecognize(workbook) }.getOrNull()
                val importYear = sessionId?.let { id -> store.loadCanonicalApplicationCandidates(id).optJSONObject(0)?.optInt("academicYear") }
                    ?.takeIf { it in 2000..2100 } ?: 2027
                val structural = KoreanTranscriptAutoRecognizer.recognizeBest(
                    workbook = workbook,
                    admissionYear = importYear,
                    fileName = fileName,
                    sourceType = sourceFormat
                )
                val wideSemester = KoreanWideSemesterTranscriptRecognizer.recognizeBest(
                    workbook = workbook,
                    admissionYear = importYear,
                    fileName = fileName,
                    sourceType = sourceFormat
                )
                val recognized = listOfNotNull(strict, structural, wideSemester)
                if (recognized.isEmpty()) throw IllegalArgumentException(
                    "Excel 파일은 열렸지만 학생부 과목 구조를 안전하게 확정하지 못했습니다."
                )
                recognized.maxWithOrNull(compareBy<JSONObject>(
                    { it.optInt("rowCount", 0) },
                    { it.optInt("gradedRows", 0) },
                    { if (it.optString("recognitionMode") == "wide-semester-columns") 1 else 0 }
                ))!!.also { chosen ->
                    val completeness = StudentScoreDocumentCompleteness.assess(chosen)
                    chosen.put("documentCompleteness", completeness)
                        .put("documentCompletenessVerified", completeness.optBoolean("verified", false))
                }
            }
            runOnUiThread {
                result.onSuccess { profile -> parsedProfile = profile; renderEditable(profile) }
                    .onFailure { renderRecognitionFailure(it.message ?: "학생부 표를 자동 인식하지 못했습니다.") }
            }
        }.start()
    }

    /** Try several likely sheets/header rows and keep the valid parse with the largest transcript. */
    private fun autoRecognize(workbook: XlsxStudentScoreImport.Workbook): JSONObject {
        val defaultYear = sessionId?.let { id -> store.loadCanonicalApplicationCandidates(id).optJSONObject(0)?.optInt("academicYear") }
            ?.takeIf { it in 2000..2100 } ?: 2027
        data class Candidate(val score: Int, val profile: JSONObject)
        val candidates = mutableListOf<Candidate>()
        workbook.sheets.forEachIndexed { sheetIndex, sheet ->
            val headerRows = linkedSetOf<Int>()
            headerRows += XlsxStudentScoreImport.suggestHeaderRow(sheet)
            sheet.rows.take(80).forEach { row ->
                val mapping = XlsxStudentScoreImport.suggestMapping(sheet, row.index)
                val required = listOf(
                    XlsxStudentScoreImport.Field.GRADE_YEAR,
                    XlsxStudentScoreImport.Field.SEMESTER,
                    XlsxStudentScoreImport.Field.SUBJECT
                ).count { (mapping[it] ?: -1) >= 0 }
                if (required >= 2) headerRows += row.index
            }
            headerRows.take(24).forEach { header ->
                val mapping = XlsxStudentScoreImport.suggestMapping(sheet, header)
                val requiredOk = listOf(
                    XlsxStudentScoreImport.Field.GRADE_YEAR,
                    XlsxStudentScoreImport.Field.SEMESTER,
                    XlsxStudentScoreImport.Field.SUBJECT
                ).all { (mapping[it] ?: -1) >= 0 }
                if (!requiredOk) return@forEach
                runCatching {
                    XlsxStudentScoreImport.buildProfile(
                        workbook, sheetIndex, header, mapping, defaultYear, false, fileName
                    ).put("sourceType", sourceFormat)
                        .put("automaticRecognition", true)
                }.getOrNull()?.let { profile ->
                    val n = profile.optInt("rowCount")
                    if (n > 0) {
                        val graded = n - profile.optInt("ungradedRows")
                        val optionalMapped = listOf(
                            XlsxStudentScoreImport.Field.GROUP,
                            XlsxStudentScoreImport.Field.GRADE,
                            XlsxStudentScoreImport.Field.CREDITS,
                            XlsxStudentScoreImport.Field.ACHIEVEMENT
                        ).count { (mapping[it] ?: -1) >= 0 }
                        candidates += Candidate(n * 100 + graded * 4 + optionalMapped * 10 - header, profile)
                    }
                }
            }
        }
        return candidates.maxByOrNull { it.score }?.profile
            ?: throw IllegalArgumentException("학년·학기·과목 열을 자동으로 확정하지 못했습니다. 고급 열 연결을 사용하면 직접 지정할 수 있습니다.")
    }

    private fun renderEditable(profile: JSONObject) {
        root.removeAllViews(); rows.clear()
        title("학생부 자동 분석 · 입력")
        val subjects = profile.optJSONArray("subjects") ?: JSONArray()
        val average = if (profile.isNull("ownWeightedGrade")) "산출 대기" else String.format(Locale.US, "%.3f", profile.optDouble("ownWeightedGrade"))
        val recognitionMode = profile.optString("recognitionMode").ifBlank { "strict-column" }
        info("$fileName · $sourceFormat · ${profile.optString("xlsxSheetName")} · ${subjects.length()}과목 인식 · 등급 없음 ${profile.optInt("ungradedRows")}과목 · 현재 가중평균 $average")
        info("자동 인식 방식: $recognitionMode · 학년/학기는 파일에 명시된 열·병합·구간 또는 1학기/2학기 열 머리글만 사용하고 추정하지 않습니다.")
        info("아래 인식값 자체가 입력값입니다. 틀린 셀만 바로 수정한 뒤 맨 아래의 ‘저장 + 6장 통합 분석’을 누르세요.")

        val defaultYear = profile.optInt("academicYear", 2027)
        yearEdit = labeledEdit("지원 학년도", defaultYear.toString(), true)
        completeCheck = CheckBox(this).apply {
            text = "이 파일이 판단에 사용할 학생부 과목·학기를 빠짐없이 포함합니다."
            isChecked = profile.optBoolean("documentCompletenessVerified", false)
            isEnabled = !isChecked
            text = if (isChecked) "학교 Excel 구조에서 1-1~3-1 전체 학기 범위가 확인되었습니다." else "이 파일이 판단에 사용할 학생부 과목·학기를 빠짐없이 포함합니다."
            root.addView(this)
        }

        section("인식된 과목")
        for (i in 0 until subjects.length()) {
            val obj = subjects.optJSONObject(i) ?: continue
            addSubjectRow(i + 1, obj)
        }

        section("저장 및 분석")
        button("저장 + 6장 통합 분석") { saveAndAnalyze() }
        button("다른 Excel 다시 선택") { openPicker() }
        button("고급 시트/열 연결") {
            startActivity(Intent(this, XlsxImportActivity::class.java).putExtra(XlsxImportActivity.EXTRA_SESSION_ID, sessionId))
        }
    }

    private fun addSubjectRow(number: Int, obj: JSONObject) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), dp(8), dp(10), dp(10))
        }
        val heading = TextView(this).apply {
            text = "$number. ${obj.optString("subject")}"
            textSize = 16f
            setPadding(0, 0, 0, dp(5))
        }
        box.addView(heading)

        fun compact(value: String, hint: String, widthWeight: Float = 1f, numeric: Boolean = false): EditText = EditText(this).apply {
            setText(value)
            this.hint = hint
            textSize = 14f
            setSingleLine(true)
            if (numeric) inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            layoutParams = LinearLayout.LayoutParams(0, -2, widthWeight).apply { marginEnd = dp(4) }
        }
        val r1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val year = compact(obj.optString("gradeYear"), "학년", .65f, true)
        val semester = compact(obj.optString("semester"), "학기", .65f, true)
        val group = compact(obj.optString("group"), "교과", 1.2f)
        val subject = compact(obj.optString("subject"), "과목", 2.2f)
        r1.addView(year); r1.addView(semester); r1.addView(group); r1.addView(subject)
        box.addView(r1)

        val r2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val grade = compact(if (obj.isNull("grade")) "" else obj.optString("grade"), "등급", 1f, true)
        val credits = compact(if (obj.isNull("credits")) "" else obj.optString("credits"), "학점", 1f, true)
        val achievement = compact(if (obj.isNull("achievement")) "" else obj.optString("achievement"), "성취도", 1.2f)
        r2.addView(grade); r2.addView(credits); r2.addView(achievement)
        box.addView(r2)
        root.addView(box)
        rows += RowEditors(year, semester, group, subject, grade, credits, achievement)
    }

    private fun saveAndAnalyze() {
        val admissionYear = yearEdit.text.toString().trim().toIntOrNull()
            ?: return showError("지원 학년도를 확인하세요.")
        val rawRows = JSONArray()
        rows.forEachIndexed { i, r ->
            val subject = r.subject.text.toString().trim()
            if (subject.isBlank()) return@forEachIndexed
            val year = r.year.text.toString().trim()
            val semester = r.semester.text.toString().trim()
            if (year.isBlank() || semester.isBlank()) return showError("${i + 1}번째 과목의 학년·학기를 확인하세요.")
            rawRows.put(JSONObject()
                .put("gradeYear", year)
                .put("semester", semester)
                .put("group", r.group.text.toString().trim())
                .put("subject", subject)
                .put("grade", r.grade.text.toString().trim())
                .put("credits", r.credits.text.toString().trim())
                .put("achievement", r.achievement.text.toString().trim()))
        }
        if (rawRows.length() == 0) return showError("저장할 과목이 없습니다.")

        val profile = runCatching {
            StudentScoreImport.parse(
                JSONObject().put("academicYear", admissionYear).put("subjects", rawRows).toString(),
                admissionYear,
                completeCheck.isChecked
            )
        }.getOrElse { return showError(it.message ?: "입력값을 확인하세요.") }
        val source = parsedProfile ?: JSONObject()
        profile.put("sourceType", sourceFormat)
            .put("documentCompleteness", source.optJSONObject("documentCompleteness") ?: JSONObject())
            .put("documentCompletenessVerified", source.optBoolean("documentCompletenessVerified", false))
            .put("excelFileName", fileName.take(240))
            .put("excelSheetName", source.optString("xlsxSheetName"))
            .put("automaticRecognition", true)
            .put("formulaPolicy", "DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY")
            .put("blankGradePolicy", "PRESERVE_NULL")

        val sid = sessionId
        runCatching {
            store.saveStudentScoreImport(profile)
            if (!sid.isNullOrBlank()) {
                store.rebuildCanonicalApplicationGraph(sid)
                AdigaAutoScoreMaterializer.materializeSelected(store, sid, profile)
            }
        }.onSuccess {
            renderSavedResult(profile, sid)
        }.onFailure { showError(it.message ?: "저장 또는 통합 분석에 실패했습니다.") }
    }

    private fun renderSavedResult(profile: JSONObject, sid: String?) {
        root.removeAllViews()
        title("학생부 저장 · 통합 분석 완료")
        val avg = if (profile.isNull("ownWeightedGrade")) "산출 보류" else String.format(Locale.US, "%.3f", profile.optDouble("ownWeightedGrade"))
        info("${profile.optInt("rowCount")}과목 저장 · 등급 없는 과목 ${profile.optInt("ungradedRows")}개 · 입력 과목 가중평균 $avg")
        if (!completeCheck.isChecked) info("대학 환산 산식이 상위과목·이수단위를 사용하므로, 파일이 판단에 사용할 학생부 전체인지 사용자가 확인하기 전에는 환산값만 보류합니다. 공식 과거 입결 수집·연결은 이 확인과 무관하게 자동 진행됩니다.")
        if (!sid.isNullOrBlank()) {
            val decision = store.scoreDecisionSummary(sid)
            val summary = decision.optJSONObject("summary") ?: JSONObject()
            info("대학별 공식 환산 검증 ${summary.optInt("verifiedConversions")}건 · 공식 입결 연결 ${summary.optInt("officialOutcomeAvailable")}건 · 비교 가능 ${summary.optInt("comparableDecisions")}건")
            val byIdentity = decision.optJSONObject("byIdentity") ?: JSONObject()
            val keys = byIdentity.keys()
            while (keys.hasNext()) {
                val item = byIdentity.optJSONObject(keys.next()) ?: continue
                val review = item.optJSONObject("applicationReview") ?: JSONObject()
                val conversion = item.optJSONObject("conversion") ?: JSONObject()
                val label = item.optString("displayLabel").ifBlank { item.optString("applicationIdentityKey").take(12) }
                val score = if (conversion.optBoolean("verified")) {
                    "${conversion.optString("scoreScale")}: ${conversion.optDouble("scoreValue")} / ${conversion.optDouble("maxScore")}"
                } else conversion.optJSONObject("detail")?.optString("reason").orEmpty().ifBlank { "대학별 환산 보류" }
                info("• $label\n  $score\n  ${review.optString("label", "재검토 필요")}")
            }
        }
        button("입력값 다시 보기/수정") { renderEditable(profile) }
        button("완료") { setResult(RESULT_OK); finish() }
        Toast.makeText(this, "학생부 저장과 6장 재분석 완료", Toast.LENGTH_SHORT).show()
    }

    private fun renderRecognitionFailure(message: String) {
        root.removeAllViews(); title("자동 인식 확인 필요")
        info(message)
        info("파일 자체를 읽지 못한 것이 아니라 표의 학년·학기·과목 위치를 자동 확정하지 못한 경우에는 고급 열 연결에서 직접 지정할 수 있습니다.")
        button("고급 시트/열 연결") {
            startActivity(Intent(this, XlsxImportActivity::class.java).putExtra(XlsxImportActivity.EXTRA_SESSION_ID, sessionId))
        }
        button("다른 Excel 선택") { openPicker() }
    }

    private fun labeledEdit(label: String, value: String, numeric: Boolean = false): EditText {
        info(label)
        return EditText(this).apply {
            setText(value); setSingleLine(true)
            if (numeric) inputType = InputType.TYPE_CLASS_NUMBER
            root.addView(this)
        }
    }
    private fun title(value: String) = TextView(this).apply { text = value; textSize = 21f; setPadding(0, dp(4), 0, dp(8)); root.addView(this) }
    private fun section(value: String) = TextView(this).apply { text = value; textSize = 18f; setPadding(0, dp(16), 0, dp(6)); root.addView(this) }
    private fun info(value: String) = TextView(this).apply { text = value; textSize = 14f; setTextIsSelectable(true); setPadding(0, dp(4), 0, dp(5)); root.addView(this) }
    private fun button(label: String, action: () -> Unit) = Button(this).apply { text = label; setOnClickListener { action() }; root.addView(this) }
    private fun showError(message: String) { AlertDialog.Builder(this).setTitle("학생부 입력 확인").setMessage(message).setPositiveButton("확인", null).show() }
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()

    private fun readLimited(uri: Uri): ByteArray {
        contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "파일을 열 수 없습니다." }
            val out = ByteArrayOutputStream(); val buffer = ByteArray(8192); var total = 0
            while (true) {
                val n = input.read(buffer); if (n < 0) break
                total += n
                require(total <= XlsxStudentScoreImport.MAX_FILE_BYTES) { "Excel 파일은 20MB 이하만 가져올 수 있습니다." }
                out.write(buffer, 0, n)
            }
            return out.toByteArray()
        }
    }

    private fun displayName(uri: Uri): String? {
        var cursor: Cursor? = null
        return try {
            cursor = contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            if (cursor != null && cursor.moveToFirst()) cursor.getString(0)?.take(240) else null
        } finally { cursor?.close() }
    }

    override fun onDestroy() {
        runCatching { store.close() }
        super.onDestroy()
    }

    companion object {
        const val EXTRA_SESSION_ID = "sessionId"
        private const val PICK_EXCEL = 14142
    }
}
