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
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.Locale

/**
 * One-screen Excel transcript workflow.
 *
 * File selection -> automatic structure analysis -> visible editable course table -> save ->
 * six-application official conversion/outcome analysis all stay on this screen. No opaque
 * "result" confirmation dialog is used for a successful import.
 */
class XlsxImportActivity : Activity() {
    private lateinit var store: LocalCollectorStore
    private lateinit var root: LinearLayout
    private var workbook: XlsxStudentScoreImport.Workbook? = null
    private var fileName: String = "학생부.xlsx"
    private var sourceFormat: String = "XLSX"
    private var selectedSheet = 0
    private var headerRow = 1
    private val currentMapping = linkedMapOf<XlsxStudentScoreImport.Field, Int>()
    private val mappingSpinners = linkedMapOf<XlsxStudentScoreImport.Field, Spinner>()
    private val editorRows = mutableListOf<CourseEditors>()
    private var editorTableBody: LinearLayout? = null
    private var yearEditor: EditText? = null
    private var completeCheck: CheckBox? = null
    private var liveSummary: TextView? = null
    private var analysisPanel: LinearLayout? = null
    private var autoProfileMetadata: JSONObject? = null

    data class CourseEditors(
        val row: LinearLayout,
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
        store = LocalCollectorStore(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(28))
        }
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
        renderEmpty()
        openPicker()
    }

    private fun renderEmpty() {
        root.removeAllViews()
        text(root, "학생부 Excel 분석 · 입력 · 대학환산", 21f)
        text(root, "XLS/XLSX를 고르면 즉시 구조를 분석하고, 자동 인식된 과목을 바로 아래 표에서 수정할 수 있습니다. 마지막 버튼 한 번으로 저장과 6장 대학환산·공식 입결 분석을 함께 실행합니다.")
        text(root, "파일은 기기에서만 읽습니다. 수식은 실행하지 않고 저장된 캐시값만 사용하며, 빈 석차등급은 0으로 바꾸지 않습니다.")
        button(root, "학생부 XLS / XLSX 선택") { openPicker() }
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
        root.removeAllViews()
        text(root, "학생부 Excel 분석 중…", 20f)
        text(root, fileName)
        Thread {
            val result = runCatching {
                val bytes = readLimited(uri)
                when {
                    LegacyXlsStudentScoreImport.looksLikeXls(bytes) -> {
                        sourceFormat = "XLS"
                        LegacyXlsStudentScoreImport.parse(bytes)
                    }
                    bytes.size >= 4 && bytes[0] == 'P'.code.toByte() && bytes[1] == 'K'.code.toByte() -> {
                        sourceFormat = "XLSX"
                        XlsxStudentScoreImport.parse(bytes)
                    }
                    else -> error("선택한 파일은 실제 .xls 또는 .xlsx 형식이 아닙니다.")
                }
            }
            runOnUiThread {
                result.onSuccess { wb ->
                    workbook = wb
                    selectedSheet = 0
                    headerRow = XlsxStudentScoreImport.suggestHeaderRow(wb.sheets[0])
                    currentMapping.clear()
                    currentMapping.putAll(XlsxStudentScoreImport.suggestMapping(wb.sheets[0], headerRow))
                    renderIntegratedWorkbook()
                }.onFailure { showError(it.message ?: "Excel 파일을 읽지 못했습니다.", true) }
            }
        }.start()
    }

    private fun renderIntegratedWorkbook() {
        val wb = workbook ?: return renderEmpty()
        selectedSheet = selectedSheet.coerceIn(wb.sheets.indices)
        val sheet = wb.sheets[selectedSheet]
        if (currentMapping.isEmpty()) currentMapping.putAll(XlsxStudentScoreImport.suggestMapping(sheet, headerRow))

        root.removeAllViews()
        mappingSpinners.clear()
        editorRows.clear()
        editorTableBody = null
        analysisPanel = null
        autoProfileMetadata = null

        text(root, "학생부 Excel 분석 · 입력 · 대학환산", 21f)
        text(root, "$fileName · $sourceFormat · ${sheet.name} · 시트 ${wb.sheets.size}개 · 수식 셀 ${wb.formulaCellCount}개")
        text(root, "자동 인식값을 아래에서 바로 고칠 수 있습니다. 별도의 결과창을 거치지 않습니다.")

        val compact = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; root.addView(this) }
        text(compact, "시트", 14f, widthDp = 55)
        Spinner(this).apply {
            adapter = ArrayAdapter(this@XlsxImportActivity, android.R.layout.simple_spinner_dropdown_item, wb.sheets.mapIndexed { i, s -> "${i + 1}. ${s.name}" })
            setSelection(selectedSheet)
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    if (position != selectedSheet) {
                        selectedSheet = position
                        val newSheet = wb.sheets[position]
                        headerRow = XlsxStudentScoreImport.suggestHeaderRow(newSheet)
                        currentMapping.clear()
                        currentMapping.putAll(XlsxStudentScoreImport.suggestMapping(newSheet, headerRow))
                        root.post { renderIntegratedWorkbook() }
                    }
                }
            }
            compact.addView(this, LinearLayout.LayoutParams(0, dp(48), 1f))
        }
        button(compact, "다른 파일") { openPicker() }

        val headerCandidates = sheet.rows.take(80).ifEmpty { listOf(XlsxStudentScoreImport.Row(1, emptyMap())) }
        if (headerCandidates.none { it.index == headerRow }) headerRow = XlsxStudentScoreImport.suggestHeaderRow(sheet)
        val headerLine = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; root.addView(this) }
        text(headerLine, "제목행", 14f, widthDp = 55)
        Spinner(this).apply {
            adapter = ArrayAdapter(this@XlsxImportActivity, android.R.layout.simple_spinner_dropdown_item, headerCandidates.map { row ->
                val preview = (0..minOf(sheet.maxColumn(), 8)).map { sheet.directValue(row.index, it).trim() }.filter { it.isNotBlank() }.joinToString(" | ").take(90)
                "${row.index}행${if (preview.isBlank()) "" else " · $preview"}"
            })
            setSelection(headerCandidates.indexOfFirst { it.index == headerRow }.coerceAtLeast(0))
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    val chosen = headerCandidates[position].index
                    if (chosen != headerRow) {
                        headerRow = chosen
                        currentMapping.clear()
                        currentMapping.putAll(XlsxStudentScoreImport.suggestMapping(sheet, headerRow))
                        root.post { renderIntegratedWorkbook() }
                    }
                }
            }
            headerLine.addView(this, LinearLayout.LayoutParams(0, dp(48), 1f))
        }

        val mappingPanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
            setPadding(dp(8), dp(4), dp(8), dp(8))
            root.addView(this)
        }
        val mappingToggle = Button(this).apply {
            text = "열 연결 확인 / 수정"
            setOnClickListener {
                mappingPanel.visibility = if (mappingPanel.visibility == View.VISIBLE) View.GONE else View.VISIBLE
                text = if (mappingPanel.visibility == View.VISIBLE) "열 연결 접기" else "열 연결 확인 / 수정"
            }
            root.addView(this)
        }
        renderMappingControls(sheet, mappingPanel)

        val defaultYear = defaultAdmissionYear()
        val yearLine = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; root.addView(this) }
        text(yearLine, "지원 학년도", 14f, widthDp = 110)
        yearEditor = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            setText(defaultYear.toString())
            setSelectAllOnFocus(true)
            yearLine.addView(this, LinearLayout.LayoutParams(dp(120), dp(48)))
        }

        val auto = runCatching {
            XlsxStudentScoreImport.buildProfile(wb, selectedSheet, headerRow, currentMapping, defaultYear, false, fileName)
                .put("sourceType", sourceFormat)
        }
        if (auto.isFailure) {
            mappingPanel.visibility = View.VISIBLE
            mappingToggle.text = "열 연결 접기"
            text(root, "자동 인식에서 과목표를 만들지 못했습니다: ${auto.exceptionOrNull()?.message ?: "열 연결을 확인하세요."}", 15f)
            text(root, "위 열 연결을 수정한 뒤 아래 버튼을 누르면 같은 화면에서 다시 분석합니다.")
            button(root, "수정한 열 연결로 다시 분석") { renderIntegratedWorkbook() }
            return
        }

        val profile = auto.getOrThrow()
        autoProfileMetadata = JSONObject(profile.toString())
        renderEditableTranscript(profile)

        completeCheck = CheckBox(this).apply {
            text = "현재 표가 판단에 사용할 학생부의 과목·학기를 빠짐없이 포함하는지 확인했습니다."
            isChecked = store.currentStudentScoreProfile().optBoolean("completeTranscriptConfirmedByUser", false)
            root.addView(this)
        }

        button(root, "현재 입력 다시 분석") {
            runCatching { buildEditedProfile(false) }
                .onSuccess { updateLiveSummary(it, "수정값 분석") }
                .onFailure { showError(it.message ?: "입력값을 확인하세요.") }
        }
        button(root, "저장 + 6장 대학환산 · 공식입결 분석") { saveAndAnalyze() }

        analysisPanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(12), 0, dp(10))
            root.addView(this)
        }
    }

    private fun renderMappingControls(sheet: XlsxStudentScoreImport.Sheet, panel: LinearLayout) {
        text(panel, "학년·학기·과목은 필수입니다. 자동 연결이 잘못되었을 때만 수정하세요.")
        val maxColumn = sheet.maxColumn()
        val options = mutableListOf("미사용")
        for (column in 0..maxColumn) {
            val header = XlsxStudentScoreImport.headerLabel(sheet, headerRow, column).ifBlank { "제목 없음" }
            options += "${XlsxStudentScoreImport.columnName(column)} · $header"
        }
        for (field in XlsxStudentScoreImport.Field.values()) {
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; panel.addView(this) }
            text(line, "${field.label}${if (field.required) " *" else ""}", 13f, widthDp = 125)
            Spinner(this).apply {
                adapter = ArrayAdapter(this@XlsxImportActivity, android.R.layout.simple_spinner_dropdown_item, options)
                setSelection(((currentMapping[field] ?: -1) + 1).coerceIn(0, options.lastIndex))
                onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                    override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                    override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                        currentMapping[field] = position - 1
                    }
                }
                mappingSpinners[field] = this
                line.addView(this, LinearLayout.LayoutParams(0, dp(46), 1f))
            }
        }
        button(panel, "이 열 연결로 과목표 다시 만들기") { renderIntegratedWorkbook() }
    }

    private fun renderEditableTranscript(profile: JSONObject) {
        text(root, "자동 분석된 학생부 · 바로 수정 가능", 18f)
        liveSummary = TextView(this).apply {
            textSize = 14f
            setPadding(0, dp(5), 0, dp(8))
            setTextIsSelectable(true)
            root.addView(this)
        }
        updateLiveSummary(profile, "파일 자동 분석")

        val horizontal = HorizontalScrollView(this).apply {
            isFillViewport = false
            root.addView(this, LinearLayout.LayoutParams(-1, -2))
        }
        val table = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; horizontal.addView(this) }
        val header = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; table.addView(this) }
        listOf(
            "학년" to 72, "학기" to 72, "교과" to 130, "과목" to 230,
            "등급" to 82, "학점" to 82, "성취도" to 95, "" to 72
        ).forEach { (label, width) -> text(header, label, 13f, widthDp = width) }
        editorTableBody = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; table.addView(this) }

        val subjects = profile.optJSONArray("subjects") ?: JSONArray()
        for (i in 0 until subjects.length()) addCourseEditor(subjects.optJSONObject(i) ?: JSONObject())
        button(root, "+ 과목 직접 추가") { addCourseEditor(JSONObject()) }
        text(root, "등급이 없는 진로선택 과목은 등급 칸을 비워두고 성취도(A/B/C 등)를 입력하세요. 빈 등급은 평균 계산에서 0으로 처리되지 않습니다.", 12f)
    }

    private fun addCourseEditor(source: JSONObject) {
        val body = editorTableBody ?: return
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; body.addView(this) }
        fun edit(value: String, width: Int, numeric: Boolean = false): EditText = EditText(this).apply {
            setText(value)
            textSize = 13f
            setSingleLine(true)
            setSelectAllOnFocus(true)
            if (numeric) inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            row.addView(this, LinearLayout.LayoutParams(dp(width), dp(48)))
        }
        val editors = CourseEditors(
            row = row,
            year = edit(sourceValue(source, "gradeYear"), 72, true),
            semester = edit(sourceValue(source, "semester"), 72, true),
            group = edit(sourceValue(source, "group"), 130),
            subject = edit(sourceValue(source, "subject"), 230),
            grade = edit(sourceValue(source, "grade"), 82, true),
            credits = edit(sourceValue(source, "credits"), 82, true),
            achievement = edit(sourceValue(source, "achievement"), 95)
        )
        Button(this).apply {
            text = "삭제"
            textSize = 11f
            setOnClickListener {
                editorRows.remove(editors)
                body.removeView(row)
            }
            row.addView(this, LinearLayout.LayoutParams(dp(72), dp(46)))
        }
        editorRows += editors
    }

    private fun sourceValue(source: JSONObject, key: String): String =
        if (!source.has(key) || source.isNull(key)) "" else source.optString(key)

    private fun buildEditedProfile(complete: Boolean): JSONObject {
        val year = yearEditor?.text?.toString()?.trim()?.toIntOrNull() ?: error("지원 학년도를 확인하세요.")
        val subjects = JSONArray()
        for (editors in editorRows) {
            val subject = editors.subject.text.toString().trim()
            val any = listOf(editors.year, editors.semester, editors.group, editors.subject, editors.grade, editors.credits, editors.achievement)
                .any { it.text.toString().trim().isNotBlank() }
            if (!any) continue
            if (subject.isBlank()) error("과목명이 빈 행이 있습니다. 사용하지 않는 행은 삭제하세요.")
            subjects.put(JSONObject()
                .put("gradeYear", editors.year.text.toString().trim())
                .put("semester", editors.semester.text.toString().trim())
                .put("group", editors.group.text.toString().trim())
                .put("subject", subject)
                .put("grade", editors.grade.text.toString().trim())
                .put("credits", editors.credits.text.toString().trim())
                .put("achievement", editors.achievement.text.toString().trim()))
        }
        val raw = JSONObject().put("academicYear", year).put("subjects", subjects)
        val profile = StudentScoreImport.parse(raw.toString(), year, complete)
            .put("sourceType", sourceFormat)
            .put("importUiMode", "INTEGRATED_ANALYZE_EDIT_SAVE")
            .put("xlsxFileName", fileName.take(240))
            .put("xlsxSheetName", workbook?.sheets?.getOrNull(selectedSheet)?.name ?: "")
            .put("xlsxSheetIndex", selectedSheet)
            .put("xlsxHeaderRow", headerRow)
            .put("xlsxColumnMapping", JSONObject().also { obj -> XlsxStudentScoreImport.Field.values().forEach { f -> obj.put(f.jsonKey, currentMapping[f] ?: -1) } })
            .put("xlsxFormulaPolicy", "DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY")
            .put("xlsxBlankGradePolicy", "PRESERVE_NULL")
            .put("xlsxStructuralFillPolicy", "MERGED_YEAR_SEMESTER_ONLY")

        val meta = autoProfileMetadata
        for (key in listOf("xlsxFormulaCachedCellsUsed", "xlsxWorkbookFormulaCells", "xlsxMergedStructuralFills")) {
            if (meta?.has(key) == true) profile.put(key, meta.opt(key))
        }
        return profile
    }

    private fun updateLiveSummary(profile: JSONObject, prefix: String) {
        val average = if (profile.isNull("ownWeightedGrade")) "산출 보류" else String.format(Locale.US, "%.4f", profile.optDouble("ownWeightedGrade"))
        liveSummary?.text = "$prefix · ${profile.optInt("rowCount")}과목 · 등급 ${profile.optInt("gradedRows")} · 등급 없음 ${profile.optInt("ungradedRows")} · 학점 누락 ${profile.optInt("missingCreditRows")} · 입력과목 가중평균 $average"
    }

    private fun saveAndAnalyze() {
        val profile = runCatching { buildEditedProfile(completeCheck?.isChecked == true) }
            .getOrElse { return showError(it.message ?: "학생부 입력을 확인하세요.") }
        if (!profile.optBoolean("completeTranscriptConfirmedByUser", false)) {
            return showError("대학 환산을 실행하려면 현재 과목표가 판단에 사용할 학생부 전체를 포함하는지 확인 체크가 필요합니다.")
        }
        val sessionId = intent.getStringExtra(EXTRA_SESSION_ID)?.takeIf { it.isNotBlank() }
        runCatching {
            store.saveStudentScoreImport(profile)
            if (sessionId != null) {
                store.rebuildCanonicalApplicationGraph(sessionId)
                AdigaAutoScoreMaterializer.materializeSelected(store, sessionId, profile)
            }
        }.onSuccess {
            setResult(RESULT_OK)
            updateLiveSummary(profile, "저장 완료")
            renderAnalysisResults(profile, sessionId)
            Toast.makeText(this, "학생부 저장과 6장 분석을 완료했습니다.", Toast.LENGTH_SHORT).show()
        }.onFailure { showError(it.message ?: "성적 저장 또는 분석에 실패했습니다.") }
    }

    private fun renderAnalysisResults(profile: JSONObject, sessionId: String?) {
        val panel = analysisPanel ?: return
        panel.removeAllViews()
        text(panel, "저장 완료 · 6장 대학환산 / 공식입결 분석", 18f)
        val average = if (profile.isNull("ownWeightedGrade")) "산출 보류" else String.format(Locale.US, "%.4f", profile.optDouble("ownWeightedGrade"))
        text(panel, "학생부 ${profile.optInt("rowCount")}과목 저장 · 자체 가중평균 $average. 아래 대학별 값은 수집된 공식 산식과 같은 척도가 검증된 범위에서만 계산합니다.")
        if (sessionId.isNullOrBlank()) {
            text(panel, "현재 6장 지원안 세션이 연결되지 않아 학생부 저장까지만 완료했습니다.")
            button(panel, "허브로 돌아가기") { finish() }
            return
        }

        val decisions = store.scoreDecisionSummary(sessionId)
        val byIdentity = decisions.optJSONObject("byIdentity") ?: JSONObject()
        val hub = store.canonicalHubSummary(sessionId)
        val candidates = hub.optJSONArray("candidateGraph") ?: JSONArray()
        val candidateByIdentity = linkedMapOf<String, JSONObject>()
        for (i in 0 until candidates.length()) {
            val c = candidates.optJSONObject(i) ?: continue
            val identity = c.optString("applicationIdentityKey")
            if (identity.isNotBlank()) candidateByIdentity[identity] = c
        }
        val slots = hub.optJSONArray("slots") ?: JSONArray()
        for (slotIndex in 0 until minOf(6, slots.length())) {
            val slot = slots.optJSONObject(slotIndex) ?: continue
            if (!slot.optBoolean("occupied", false)) continue
            val identity = slot.optString("applicationIdentityKey")
            val candidate = candidateByIdentity[identity]
            val decision = byIdentity.optJSONObject(identity)
            val title = candidate?.optString("displayLabel")?.takeIf { it.isNotBlank() }
                ?: slot.optString("displayLabel", "${slotIndex + 1}번 지원안")
            text(panel, "${slotIndex + 1}. $title", 16f)
            if (decision == null) {
                text(panel, "분석 결과가 아직 생성되지 않았습니다.")
                continue
            }
            text(panel, decision.optString("conversionLabel", "대학 환산: 미확인"))
            text(panel, decision.optString("officialOutcomeLabel", "공식 입결: 미확인"))
            text(panel, decision.optString("predictionLabel", "진학사: 미확인"))
            val evaluation = decision.optJSONObject("evaluation")
            if (evaluation != null) text(panel, evaluation.optString("decisionLabel", decision.optString("decisionLabel")))
            val conversion = decision.optJSONObject("conversion")
            if (conversion?.optBoolean("verified", false) == true && !conversion.isNull("scoreValue")) {
                val max = if (conversion.isNull("maxScore")) "" else " / ${formatNumber(conversion.optDouble("maxScore"))}"
                text(panel, "공식 산식 계산값: ${formatNumber(conversion.optDouble("scoreValue"))}$max · ${conversion.optString("scoreScale")}")
            } else {
                val reason = conversion?.optJSONObject("detail")?.optString("reason").orEmpty()
                if (reason.isNotBlank()) text(panel, "환산 보류 이유: $reason")
            }
            val outcomes = decision.optJSONArray("officialOutcomes") ?: JSONArray()
            if (outcomes.length() > 0) {
                for (i in 0 until minOf(2, outcomes.length())) {
                    val o = outcomes.optJSONObject(i) ?: continue
                    text(panel, "공식 입결 ${o.optString("metricName", "지표")}: ${if (o.isNull("metricValue")) "값 미확인" else formatNumber(o.optDouble("metricValue"))} ${o.optString("scoreScale")}", 13f)
                }
            }
        }
        val summary = decisions.optJSONObject("summary") ?: JSONObject()
        text(panel, "요약 · 공식 환산 ${summary.optInt("verifiedConversions")}/6 · 공식 입결 ${summary.optInt("officialOutcomeAvailable")}/6 · 직접 비교 가능 ${summary.optInt("comparableDecisions")}/6", 15f)
        button(panel, "허브로 돌아가기") { finish() }
    }

    private fun formatNumber(value: Double): String = if (value % 1.0 == 0.0) value.toLong().toString() else String.format(Locale.US, "%.4f", value).trimEnd('0').trimEnd('.')

    private fun defaultAdmissionYear(): Int = intent.getStringExtra(EXTRA_SESSION_ID)?.let { id ->
        store.loadCanonicalApplicationCandidates(id).optJSONObject(0)?.optInt("academicYear")
    }?.takeIf { it in 2000..2100 }
        ?: store.currentStudentScoreProfile().optInt("academicYear", 2027).takeIf { it in 2000..2100 }
        ?: 2027

    private fun readLimited(uri: Uri): ByteArray {
        contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "파일을 열 수 없습니다." }
            val out = ByteArrayOutputStream()
            val buffer = ByteArray(8192)
            var total = 0
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
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

    private fun text(parent: LinearLayout, value: String, size: Float = 14f, widthDp: Int? = null): TextView = TextView(this).apply {
        text = value
        textSize = size
        setTextIsSelectable(true)
        setPadding(dp(4), dp(6), dp(4), dp(5))
        parent.addView(this, if (widthDp == null) LinearLayout.LayoutParams(-1, -2) else LinearLayout.LayoutParams(dp(widthDp), -2))
    }

    private fun button(parent: LinearLayout, label: String, action: () -> Unit): Button = Button(this).apply {
        text = label
        setOnClickListener { action() }
        parent.addView(this)
    }

    private fun showError(message: String, offerFile: Boolean = false) {
        AlertDialog.Builder(this)
            .setTitle("입력 확인")
            .setMessage(message)
            .setNegativeButton("닫기", null)
            .apply { if (offerFile) setPositiveButton("다른 파일 선택") { _, _ -> openPicker() } }
            .show()
    }

    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        runCatching { store.close() }
        super.onDestroy()
    }

    companion object {
        const val EXTRA_SESSION_ID = "sessionId"
        private const val PICK_EXCEL = 14142
    }
}
