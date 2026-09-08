package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import org.w3c.dom.Document
import org.w3c.dom.Element
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.util.Locale
import java.util.zip.ZipInputStream
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Local-only XLSX reader for transcript import.
 *
 * - XLSX is treated as an OPC ZIP container; macros and external relationships are never executed.
 * - Formula expressions are never evaluated. If Excel stored a cached value in <v>, that cached value
 *   may be shown/imported and is explicitly counted so the user can review it before saving.
 * - Blank grade cells remain blank. Year/semester values are propagated only when the XLSX explicitly
 *   declares a merged range whose top-left cell contains the value.
 */
object XlsxStudentScoreImport {
    const val MAX_FILE_BYTES = 20 * 1024 * 1024
    private const val MAX_ENTRY_BYTES = 20 * 1024 * 1024
    private const val MAX_TOTAL_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
    private const val MAX_ZIP_ENTRIES = 5000
    private const val MAX_ROWS = 5000
    private const val MAX_COLUMNS = 200

    enum class Field(val jsonKey: String, val label: String, val required: Boolean) {
        GRADE_YEAR("gradeYear", "학년", true),
        SEMESTER("semester", "학기", true),
        GROUP("group", "교과", false),
        SUBJECT("subject", "과목", true),
        GRADE("grade", "석차등급", false),
        CREDITS("credits", "학점/이수단위", false),
        ACHIEVEMENT("achievement", "성취도", false)
    }

    data class Cell(val row: Int, val column: Int, val value: String, val formula: Boolean)
    data class Row(val index: Int, val cells: Map<Int, Cell>)
    data class MergeRange(val firstRow: Int, val lastRow: Int, val firstColumn: Int, val lastColumn: Int) {
        fun contains(row: Int, column: Int): Boolean = row in firstRow..lastRow && column in firstColumn..lastColumn
    }
    data class ValueSource(val value: String, val formula: Boolean, val fromMergedCell: Boolean)
    data class Sheet(val name: String, val rows: List<Row>, val merges: List<MergeRange>) {
        private val byRow: Map<Int, Row> = rows.associateBy { it.index }
        fun cell(row: Int, column: Int): Cell? = byRow[row]?.cells?.get(column)
        fun directValue(row: Int, column: Int): String = cell(row, column)?.value.orEmpty()
        fun structuralValue(row: Int, column: Int): ValueSource {
            cell(row, column)?.let { if (it.value.isNotBlank()) return ValueSource(it.value, it.formula, false) }
            val merge = merges.firstOrNull { it.contains(row, column) } ?: return ValueSource("", false, false)
            val top = cell(merge.firstRow, merge.firstColumn) ?: return ValueSource("", false, false)
            return ValueSource(top.value, top.formula, row != merge.firstRow || column != merge.firstColumn)
        }
        fun maxColumn(): Int = rows.asSequence().flatMap { it.cells.keys.asSequence() }.maxOrNull()?.coerceAtMost(MAX_COLUMNS - 1) ?: 0
        fun formulaCellCount(): Int = rows.sumOf { r -> r.cells.values.count { it.formula } }
    }
    data class Workbook(val sheets: List<Sheet>, val sharedStringCount: Int, val formulaCellCount: Int)

    private val aliases = mapOf(
        Field.GRADE_YEAR to setOf("학년", "학년도", "학년학기", "gradeyear", "year"),
        Field.SEMESTER to setOf("학기", "학년학기", "semester", "term"),
        Field.GROUP to setOf("교과", "교과군", "교과영역", "과목군", "group"),
        Field.SUBJECT to setOf("과목", "과목명", "교과목", "교과목명", "과목명칭", "subject"),
        Field.GRADE to setOf("등급", "석차등급", "석차 등급", "내신등급", "등급(석차)", "grade"),
        Field.CREDITS to setOf("학점", "이수단위", "단위수", "단위 수", "이수학점", "이수 학점", "credits", "credit"),
        Field.ACHIEVEMENT to setOf("성취도", "성취수준", "성취 수준", "성취도(수강자수)", "achievement")
    )

    fun parse(bytes: ByteArray): Workbook {
        require(bytes.isNotEmpty()) { "XLSX 파일이 비어 있습니다." }
        require(bytes.size <= MAX_FILE_BYTES) { "XLSX 파일은 20MB 이하만 가져올 수 있습니다." }
        val entries = unzip(bytes)
        val workbookXml = entries["xl/workbook.xml"] ?: error("XLSX workbook.xml을 찾을 수 없습니다. .xlsx 파일인지 확인하세요.")
        val relsXml = entries["xl/_rels/workbook.xml.rels"] ?: error("XLSX 시트 연결 정보를 찾을 수 없습니다.")
        val shared = entries["xl/sharedStrings.xml"]?.let(::parseSharedStrings) ?: emptyList()
        val rels = parseRelationships(relsXml)
        val workbook = xml(workbookXml)
        val sheetElements = elements(workbook, "sheet")
        require(sheetElements.isNotEmpty()) { "XLSX에 읽을 수 있는 시트가 없습니다." }
        val sheets = mutableListOf<Sheet>()
        for (sheetElement in sheetElements) {
            val name = sheetElement.getAttribute("name").trim().ifBlank { "Sheet${sheets.size + 1}" }.take(120)
            val relId = sheetElement.getAttributeNS("http://schemas.openxmlformats.org/officeDocument/2006/relationships", "id")
                .ifBlank { sheetElement.getAttribute("r:id") }.trim()
            val target = rels[relId] ?: continue
            val path = resolveWorkbookTarget(target)
            val sheetBytes = entries[path] ?: continue
            sheets += parseSheet(name, sheetBytes, shared)
        }
        require(sheets.isNotEmpty()) { "워크북의 시트 XML을 읽지 못했습니다." }
        return Workbook(sheets, shared.size, sheets.sumOf { it.formulaCellCount() })
    }

    fun suggestHeaderRow(sheet: Sheet): Int {
        val candidates = sheet.rows.take(80)
        if (candidates.isEmpty()) return 1
        return candidates.maxWithOrNull(compareBy<Row>({ headerScore(sheet, it.index) }, { -it.index }))?.index ?: candidates.first().index
    }

    fun suggestMapping(sheet: Sheet, headerRow: Int): Map<Field, Int> {
        val maxCol = sheet.maxColumn()
        val result = linkedMapOf<Field, Int>()
        val used = mutableSetOf<Int>()
        for (field in Field.values()) {
            var bestCol = -1
            var bestScore = 0
            for (column in 0..maxCol) {
                if (column in used) continue
                val label = headerLabel(sheet, headerRow, column)
                val score = aliasScore(field, label)
                if (score > bestScore) { bestScore = score; bestCol = column }
            }
            result[field] = if (bestScore > 0) bestCol else -1
            if (bestScore > 0) used += bestCol
        }
        return result
    }

    fun headerLabel(sheet: Sheet, headerRow: Int, column: Int): String {
        val values = linkedSetOf<String>()
        for (row in maxOf(1, headerRow - 2)..headerRow) {
            val v = sheet.structuralValue(row, column).value.trim()
            if (v.isNotBlank()) values += v
        }
        return values.joinToString(" / ").take(120)
    }

    fun buildProfile(
        workbook: Workbook,
        sheetIndex: Int,
        headerRow: Int,
        mapping: Map<Field, Int>,
        admissionYear: Int,
        complete: Boolean,
        fileName: String
    ): JSONObject {
        require(sheetIndex in workbook.sheets.indices) { "시트를 다시 선택하세요." }
        val sheet = workbook.sheets[sheetIndex]
        for (field in Field.values().filter { it.required }) require((mapping[field] ?: -1) >= 0) { "${field.label} 열을 선택하세요." }
        val mappedColumns = mapping.values.filter { it >= 0 }
        require(mappedColumns.distinct().size == mappedColumns.size) { "같은 열을 여러 필드에 중복 연결할 수 없습니다." }

        val subjects = JSONArray()
        var mappedFormulaCells = 0
        var mergedStructuralFills = 0
        for (row in sheet.rows) {
            if (row.index <= headerRow) continue
            if (subjects.length() >= 1000) error("가져올 과목이 1000행을 초과합니다.")
            val out = JSONObject()
            var any = false
            for (field in Field.values()) {
                val column = mapping[field] ?: -1
                if (column < 0) { out.put(field.jsonKey, ""); continue }
                val source = if (field == Field.GRADE_YEAR || field == Field.SEMESTER) sheet.structuralValue(row.index, column)
                    else sheet.cell(row.index, column)?.let { ValueSource(it.value, it.formula, false) } ?: ValueSource("", false, false)
                val value = source.value.trim()
                if (value.isNotBlank()) any = true
                if (source.formula) mappedFormulaCells++
                if (source.fromMergedCell && value.isNotBlank()) mergedStructuralFills++
                out.put(field.jsonKey, value)
            }
            if (!any) continue
            // A stray note row without a subject is not silently converted into a course row.
            if (out.optString(Field.SUBJECT.jsonKey).isBlank()) continue
            subjects.put(out)
        }
        require(subjects.length() > 0) { "선택한 시트·헤더·열 연결에서 과목 행을 찾지 못했습니다." }
        val raw = JSONObject().put("academicYear", admissionYear).put("subjects", subjects)
        val profile = StudentScoreImport.parse(raw.toString(), admissionYear, complete)
        return profile
            .put("sourceType", "XLSX")
            .put("xlsxFileName", fileName.take(240))
            .put("xlsxSheetName", sheet.name)
            .put("xlsxSheetIndex", sheetIndex)
            .put("xlsxHeaderRow", headerRow)
            .put("xlsxColumnMapping", JSONObject().also { obj -> Field.values().forEach { f -> obj.put(f.jsonKey, mapping[f] ?: -1) } })
            .put("xlsxFormulaCachedCellsUsed", mappedFormulaCells)
            .put("xlsxWorkbookFormulaCells", workbook.formulaCellCount)
            .put("xlsxMergedStructuralFills", mergedStructuralFills)
            .put("xlsxFormulaPolicy", "DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY")
            .put("xlsxBlankGradePolicy", "PRESERVE_NULL")
            .put("xlsxStructuralFillPolicy", "MERGED_YEAR_SEMESTER_ONLY")
    }

    fun columnName(index: Int): String {
        require(index >= 0)
        var n = index + 1
        val out = StringBuilder()
        while (n > 0) {
            val r = (n - 1) % 26
            out.append(('A'.code + r).toChar())
            n = (n - 1) / 26
        }
        return out.reverse().toString()
    }

    private fun headerScore(sheet: Sheet, row: Int): Int {
        val mapping = suggestMappingWithoutRecursion(sheet, row)
        var score = mapping.values.count { it >= 0 } * 10
        if ((mapping[Field.SUBJECT] ?: -1) >= 0) score += 30
        if ((mapping[Field.GRADE_YEAR] ?: -1) >= 0) score += 10
        if ((mapping[Field.SEMESTER] ?: -1) >= 0) score += 10
        return score
    }

    private fun suggestMappingWithoutRecursion(sheet: Sheet, headerRow: Int): Map<Field, Int> {
        val maxCol = sheet.maxColumn()
        val result = linkedMapOf<Field, Int>()
        val used = mutableSetOf<Int>()
        for (field in Field.values()) {
            var bestCol = -1; var bestScore = 0
            for (column in 0..maxCol) {
                if (column in used) continue
                val score = aliasScore(field, headerLabel(sheet, headerRow, column))
                if (score > bestScore) { bestScore = score; bestCol = column }
            }
            result[field] = if (bestScore > 0) bestCol else -1
            if (bestScore > 0) used += bestCol
        }
        return result
    }

    private fun aliasScore(field: Field, value: String): Int {
        val n = normalizeHeader(value)
        if (n.isBlank()) return 0
        var best = 0
        for (alias in aliases[field].orEmpty()) {
            val a = normalizeHeader(alias)
            best = maxOf(best, when {
                n == a -> 100
                n.endsWith(a) || n.startsWith(a) -> 80
                a.length >= 2 && n.contains(a) -> 60
                else -> 0
            })
        }
        return best
    }

    private fun normalizeHeader(value: String): String = value.lowercase(Locale.ROOT)
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\):]"), "")
        .replace(Regex("[^0-9a-z가-힣]"), "")

    private fun unzip(bytes: ByteArray): Map<String, ByteArray> {
        val out = linkedMapOf<String, ByteArray>()
        var entries = 0
        var total = 0
        ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                entries++
                require(entries <= MAX_ZIP_ENTRIES) { "XLSX ZIP 항목이 너무 많습니다." }
                val name = safeEntryName(entry.name)
                if (!entry.isDirectory && name.startsWith("xl/")) {
                    val buffer = ByteArray(8192)
                    val data = ByteArrayOutputStream()
                    var entryBytes = 0
                    while (true) {
                        val n = zip.read(buffer)
                        if (n < 0) break
                        entryBytes += n; total += n
                        require(entryBytes <= MAX_ENTRY_BYTES) { "XLSX 내부 XML 항목이 너무 큽니다." }
                        require(total <= MAX_TOTAL_UNCOMPRESSED_BYTES) { "XLSX 압축 해제 크기가 안전 한도를 초과합니다." }
                        data.write(buffer, 0, n)
                    }
                    out[name] = data.toByteArray()
                }
                zip.closeEntry()
            }
        }
        return out
    }

    private fun safeEntryName(raw: String): String {
        require(!raw.contains('\u0000')) { "잘못된 XLSX ZIP 경로입니다." }
        val name = raw.replace('\\', '/').removePrefix("/")
        val parts = name.split('/').filter { it.isNotBlank() && it != "." }
        require(parts.none { it == ".." }) { "XLSX ZIP 경로가 워크북 밖을 가리킵니다." }
        return parts.joinToString("/")
    }

    private fun resolveWorkbookTarget(targetRaw: String): String {
        val target = targetRaw.replace('\\', '/')
        require(!target.contains('\u0000')) { "잘못된 XLSX 시트 경로입니다." }
        val source = if (target.startsWith('/')) target.removePrefix("/") else "xl/$target"
        val stack = mutableListOf<String>()
        for (part in source.split('/')) {
            when {
                part.isBlank() || part == "." -> Unit
                part == ".." -> { require(stack.isNotEmpty()) { "XLSX 시트 경로가 워크북 밖을 가리킵니다." }; stack.removeAt(stack.lastIndex) }
                else -> stack += part
            }
        }
        val path = stack.joinToString("/")
        require(path.startsWith("xl/") && !path.startsWith("xl/../")) { "XLSX 시트 경로가 허용 범위를 벗어났습니다." }
        return path
    }

    private fun parseRelationships(bytes: ByteArray): Map<String, String> {
        val doc = xml(bytes)
        val out = linkedMapOf<String, String>()
        for (e in elements(doc, "Relationship")) {
            if (e.getAttribute("TargetMode").equals("External", ignoreCase = true)) continue
            val id = e.getAttribute("Id").trim(); val target = e.getAttribute("Target").trim()
            if (id.isNotBlank() && target.isNotBlank()) out[id] = target
        }
        return out
    }

    private fun parseSharedStrings(bytes: ByteArray): List<String> {
        val doc = xml(bytes)
        return elements(doc, "si").map { si -> elements(si, "t").joinToString("") { it.textContent ?: "" } }
    }

    private fun parseSheet(name: String, bytes: ByteArray, shared: List<String>): Sheet {
        val doc = xml(bytes)
        val rows = linkedMapOf<Int, MutableMap<Int, Cell>>()
        for (c in elements(doc, "c")) {
            val ref = c.getAttribute("r").trim()
            val position = parseCellRef(ref) ?: continue
            require(position.first <= MAX_ROWS && position.second < MAX_COLUMNS) { "XLSX 시트 범위가 너무 큽니다." }
            val formula = elements(c, "f").isNotEmpty()
            val type = c.getAttribute("t").trim()
            val value = when (type) {
                "s" -> elements(c, "v").firstOrNull()?.textContent?.trim()?.toIntOrNull()?.let { shared.getOrNull(it) }.orEmpty()
                "inlineStr" -> elements(c, "t").joinToString("") { it.textContent ?: "" }
                "b" -> when (elements(c, "v").firstOrNull()?.textContent?.trim()) { "1" -> "TRUE"; "0" -> "FALSE"; else -> "" }
                else -> elements(c, "v").firstOrNull()?.textContent.orEmpty().trim()
            }
            val cell = Cell(position.first, position.second, value, formula)
            rows.getOrPut(position.first) { linkedMapOf() }[position.second] = cell
        }
        val merges = mutableListOf<MergeRange>()
        for (m in elements(doc, "mergeCell")) parseMerge(m.getAttribute("ref"))?.let { merges += it }
        return Sheet(name, rows.entries.sortedBy { it.key }.map { Row(it.key, it.value.toMap()) }, merges)
    }

    private fun parseCellRef(ref: String): Pair<Int, Int>? {
        val match = Regex("^([A-Za-z]+)([0-9]+)$").matchEntire(ref) ?: return null
        var column = 0
        for (ch in match.groupValues[1].uppercase(Locale.ROOT)) column = column * 26 + (ch - 'A' + 1)
        val row = match.groupValues[2].toIntOrNull() ?: return null
        if (row <= 0 || column <= 0) return null
        return row to (column - 1)
    }

    private fun parseMerge(ref: String): MergeRange? {
        val parts = ref.split(':')
        val a = parseCellRef(parts.getOrNull(0).orEmpty()) ?: return null
        val b = parseCellRef(parts.getOrNull(1) ?: parts[0]) ?: return null
        return MergeRange(minOf(a.first, b.first), maxOf(a.first, b.first), minOf(a.second, b.second), maxOf(a.second, b.second))
    }

    private fun xml(bytes: ByteArray): Document {
        val factory = DocumentBuilderFactory.newInstance()
        factory.isNamespaceAware = true
        runCatching { factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true) }
        runCatching { factory.setFeature("http://xml.org/sax/features/external-general-entities", false) }
        runCatching { factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false) }
        runCatching { factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false) }
        runCatching { factory.isXIncludeAware = false }
        factory.isExpandEntityReferences = false
        return factory.newDocumentBuilder().parse(ByteArrayInputStream(bytes))
    }

    private fun elements(document: Document, localName: String): List<Element> =
        document.getElementsByTagNameNS("*", localName).let { nodes -> (0 until nodes.length).mapNotNull { nodes.item(it) as? Element } }
    private fun elements(element: Element, localName: String): List<Element> =
        element.getElementsByTagNameNS("*", localName).let { nodes -> (0 until nodes.length).mapNotNull { nodes.item(it) as? Element } }
}
