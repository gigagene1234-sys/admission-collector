package com.admissionhub.collector.score

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.database.Cursor
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.text.InputType
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import com.admissionhub.collector.local.LocalCollectorStore
import java.io.ByteArrayOutputStream
import java.util.Locale

/** Native review-first Excel transcript import. The workbook never leaves the device. */
class XlsxImportActivity : Activity() {
    private lateinit var store: LocalCollectorStore
    private lateinit var root: LinearLayout
    private var workbook: XlsxStudentScoreImport.Workbook? = null
    private var fileName: String = "학생부.xlsx"
    private var sourceFormat: String = "XLSX"
    private var selectedSheet = 0
    private var headerRow = 1
    private val mappingSpinners = linkedMapOf<XlsxStudentScoreImport.Field, Spinner>()
    private var yearEditor: EditText? = null
    private var completeCheck: CheckBox? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = LocalCollectorStore(this)
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(18), dp(20), dp(20)) }
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
        renderEmpty()
        openPicker()
    }

    private fun renderEmpty() {
        root.removeAllViews()
        text("학생부 Excel 가져오기", 20f)
        text("실제 .xls(Excel 97~2003)와 .xlsx를 모두 읽습니다. 파일은 기기에서만 처리하며, 수식은 실행하지 않고 저장된 캐시값만 읽습니다. 빈 석차등급은 0으로 바꾸지 않습니다.")
        button("XLS / XLSX 파일 선택") { openPicker() }
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
        root.removeAllViews(); text("Excel 분석 중…", 18f); text(fileName)
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
                    else -> error("선택한 파일은 지원되는 .xls 또는 .xlsx 형식이 아닙니다. 파일 이름이 아니라 실제 Excel 형식을 확인했습니다.")
                }
            }
            runOnUiThread {
                result.onSuccess {
                    workbook = it
                    selectedSheet = 0
                    headerRow = XlsxStudentScoreImport.suggestHeaderRow(it.sheets[0])
                    renderWorkbook()
                }.onFailure { showError(it.message ?: "Excel 파일을 읽지 못했습니다.", true) }
            }
        }.start()
    }

    private fun renderWorkbook() {
        val wb = workbook ?: return renderEmpty()
        val sheet = wb.sheets[selectedSheet.coerceIn(wb.sheets.indices)]
        root.removeAllViews(); mappingSpinners.clear()
        text("학생부 Excel 가져오기", 20f)
        text("$fileName · $sourceFormat · 시트 ${wb.sheets.size}개 · 워크북 수식 셀 ${wb.formulaCellCount}개")
        if (wb.formulaCellCount > 0) text("수식은 계산하지 않습니다. 파일에 저장된 캐시값만 미리보기와 가져오기에 사용하며 저장 전에 사용된 수식 셀 수를 다시 표시합니다.")

        text("1. 시트 선택", 16f)
        Spinner(this).apply {
            adapter = ArrayAdapter(this@XlsxImportActivity, android.R.layout.simple_spinner_dropdown_item, wb.sheets.mapIndexed { i, s -> "${i + 1}. ${s.name}" })
            setSelection(selectedSheet)
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    if (position != selectedSheet) {
                        selectedSheet = position
                        headerRow = XlsxStudentScoreImport.suggestHeaderRow(wb.sheets[position])
                        root.post { renderWorkbook() }
                    }
                }
            }
            root.addView(this)
        }

        val headerCandidates = sheet.rows.take(80).ifEmpty { listOf(XlsxStudentScoreImport.Row(1, emptyMap())) }
        if (headerCandidates.none { it.index == headerRow }) headerRow = XlsxStudentScoreImport.suggestHeaderRow(sheet)
        text("2. 열 제목이 있는 행 선택", 16f)
        val headerLabels = headerCandidates.map { row ->
            val preview = (0..minOf(sheet.maxColumn(), 8)).map { sheet.directValue(row.index, it).trim() }.filter { it.isNotBlank() }.joinToString(" | ").take(100)
            "${row.index}행${if (preview.isBlank()) "" else " · $preview"}"
        }
        Spinner(this).apply {
            adapter = ArrayAdapter(this@XlsxImportActivity, android.R.layout.simple_spinner_dropdown_item, headerLabels)
            val current = headerCandidates.indexOfFirst { it.index == headerRow }.coerceAtLeast(0)
            setSelection(current)
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    val chosen = headerCandidates[position].index
                    if (chosen != headerRow) { headerRow = chosen; root.post { renderWorkbook() } }
                }
            }
            root.addView(this)
        }

        text("3. Excel 열 연결", 16f)
        text("자동 연결 결과를 확인하고 잘못 연결된 열은 직접 바꾸세요. 학년·학기·과목은 필수입니다.")
        val suggested = XlsxStudentScoreImport.suggestMapping(sheet, headerRow)
        val maxColumn = sheet.maxColumn()
        val options = mutableListOf("미사용")
        for (column in 0..maxColumn) {
            val header = XlsxStudentScoreImport.headerLabel(sheet, headerRow, column).ifBlank { "제목 없음" }
            options += "${XlsxStudentScoreImport.columnName(column)} · $header"
        }
        for (field in XlsxStudentScoreImport.Field.values()) {
            text("${field.label}${if (field.required) " *" else ""}")
            Spinner(this).apply {
                adapter = ArrayAdapter(this@XlsxImportActivity, android.R.layout.simple_spinner_dropdown_item, options)
                setSelection(((suggested[field] ?: -1) + 1).coerceIn(0, options.lastIndex))
                mappingSpinners[field] = this
                root.addView(this)
            }
        }

        text("4. 원본 미리보기", 16f)
        text(rawPreview(sheet, headerRow), 12f)
        if (sheet.merges.isNotEmpty()) text("병합 셀 ${sheet.merges.size}개 감지 · 학년/학기는 파일에 실제 병합된 범위에서만 상단 값을 이어받습니다.")

        val defaultYear = intent.getStringExtra(EXTRA_SESSION_ID)?.let { id ->
            store.loadCanonicalApplicationCandidates(id).optJSONObject(0)?.optInt("academicYear")
        }?.takeIf { it in 2000..2100 } ?: store.currentStudentScoreProfile().optInt("academicYear", 2027).takeIf { it in 2000..2100 } ?: 2027
        text("5. 저장 전 확인", 16f)
        yearEditor = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            setText(defaultYear.toString())
            hint = "지원 학년도"
            root.addView(this)
        }
        completeCheck = CheckBox(this).apply {
            text = "이 시트와 열 연결이 판단에 사용할 학생부 과목·학기를 빠짐없이 포함하는지 확인했습니다."
            root.addView(this)
        }
        button("가져올 성적 검토") { reviewBeforeSave(wb, sheet) }
        button("다른 Excel 파일 선택") { openPicker() }
    }

    private fun reviewBeforeSave(wb: XlsxStudentScoreImport.Workbook, sheet: XlsxStudentScoreImport.Sheet) {
        val mapping = XlsxStudentScoreImport.Field.values().associateWith { field ->
            (mappingSpinners[field]?.selectedItemPosition ?: 0) - 1
        }
        val year = yearEditor?.text?.toString()?.trim()?.toIntOrNull()
        if (year == null) return showError("지원 학년도를 숫자로 입력하세요.")
        val profile = runCatching {
            XlsxStudentScoreImport.buildProfile(
                wb, selectedSheet, headerRow, mapping, year,
                completeCheck?.isChecked == true, fileName
            ).put("sourceType", sourceFormat)
        }.getOrElse { return showError(it.message ?: "열 연결을 확인하세요.") }
        val average = if (profile.isNull("ownWeightedGrade")) "산출 보류" else String.format(Locale.US, "%.4f", profile.optDouble("ownWeightedGrade"))
        val message = buildString {
            append("형식: ").append(sourceFormat).append('\n')
            append("시트: ").append(profile.optString("xlsxSheetName")).append('\n')
            append("과목: ").append(profile.optInt("rowCount")).append("개 · 등급 없음 ").append(profile.optInt("ungradedRows")).append("개\n")
            append("입력 과목 가중평균: ").append(average).append("\n")
            append("가져오기에 사용된 수식 캐시 셀: ").append(profile.optInt("xlsxFormulaCachedCellsUsed")).append("개\n")
            append("병합된 학년/학기에서 이어받은 값: ").append(profile.optInt("xlsxMergedStructuralFills")).append("개\n\n")
            append("수식은 실행하지 않았고 빈 등급은 빈칸으로 보존했습니다. 저장 뒤 수집된 어디가 공식 산식·입결을 다시 연결해 대학별 환산 가능 여부를 재계산합니다.")
        }
        AlertDialog.Builder(this).setTitle("Excel 저장 전 확인").setMessage(message)
            .setNegativeButton("열 연결 다시 보기", null)
            .setPositiveButton("이 성적 저장") { _, _ ->
                runCatching {
                    store.saveStudentScoreImport(profile)
                    intent.getStringExtra(EXTRA_SESSION_ID)?.takeIf { it.isNotBlank() }?.let { sessionId ->
                        store.rebuildCanonicalApplicationGraph(sessionId)
                        AdigaAutoScoreMaterializer.materializeSelected(store, sessionId, profile)
                    }
                }.onSuccess {
                    Toast.makeText(this, "Excel 성적 저장 · 공식 산식/입결 재계산 완료", Toast.LENGTH_SHORT).show()
                    setResult(RESULT_OK); finish()
                }.onFailure { showError(it.message ?: "성적 저장에 실패했습니다.") }
            }.show()
    }

    private fun rawPreview(sheet: XlsxStudentScoreImport.Sheet, header: Int): String {
        val start = maxOf(1, header - 2)
        val rows = sheet.rows.filter { it.index >= start }.take(24)
        val maxCol = minOf(sheet.maxColumn(), 10)
        return buildString {
            for (row in rows) {
                append(row.index).append("행  ")
                for (column in 0..maxCol) {
                    val value = sheet.directValue(row.index, column).replace('\n', ' ').trim()
                    if (value.isNotBlank()) append(XlsxStudentScoreImport.columnName(column)).append('=').append(value.take(28)).append("  ")
                }
                append('\n')
            }
        }.ifBlank { "표시할 셀이 없습니다." }
    }

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

    private fun text(value: String, size: Float = 14f) = TextView(this).apply {
        text = value; textSize = size; setTextIsSelectable(true); setPadding(0, dp(6), 0, dp(5)); root.addView(this)
    }
    private fun button(label: String, action: () -> Unit) = Button(this).apply { text = label; setOnClickListener { action() }; root.addView(this) }
    private fun showError(message: String, offerFile: Boolean = false) {
        AlertDialog.Builder(this).setTitle("Excel 확인").setMessage(message)
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
        private const val PICK_EXCEL = 14141
    }
}
