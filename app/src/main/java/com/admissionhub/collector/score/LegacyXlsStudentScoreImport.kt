package com.admissionhub.collector.score

import org.apache.poi.hssf.usermodel.HSSFWorkbook
import org.apache.poi.ss.usermodel.CellType
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.math.BigDecimal

/**
 * Read-only BIFF8/OLE2 (.xls) bridge for the same review-first transcript flow used by XLSX.
 * Formula expressions are never evaluated; only POI's stored cached result is read.
 */
object LegacyXlsStudentScoreImport {
    private const val MAX_ROWS = 5000
    private const val MAX_COLUMNS = 200
    private val OLE2 = byteArrayOf(0xD0.toByte(), 0xCF.toByte(), 0x11, 0xE0.toByte(), 0xA1.toByte(), 0xB1.toByte(), 0x1A, 0xE1.toByte())

    fun looksLikeXls(bytes: ByteArray): Boolean = bytes.size >= OLE2.size && OLE2.indices.all { bytes[it] == OLE2[it] }

    fun parse(bytes: ByteArray): XlsxStudentScoreImport.Workbook {
        require(bytes.isNotEmpty()) { "Excel 파일이 비어 있습니다." }
        require(bytes.size <= XlsxStudentScoreImport.MAX_FILE_BYTES) { "Excel 파일은 20MB 이하만 가져올 수 있습니다." }
        require(looksLikeXls(bytes)) { "구형 Excel(.xls) OLE2 형식이 아닙니다." }
        HSSFWorkbook(ByteArrayInputStream(bytes)).use { workbook ->
            require(workbook.numberOfSheets in 1..128) { "읽을 수 있는 시트 수를 초과했습니다." }
            val sheets = mutableListOf<XlsxStudentScoreImport.Sheet>()
            var workbookFormulaCells = 0
            for (si in 0 until workbook.numberOfSheets) {
                val sheet = workbook.getSheetAt(si)
                require(sheet.lastRowNum + 1 <= MAX_ROWS) { "${sheet.sheetName}: 행 수가 안전 한도를 초과합니다." }
                val outRows = mutableListOf<XlsxStudentScoreImport.Row>()
                for (ri in 0..sheet.lastRowNum) {
                    val row = sheet.getRow(ri) ?: continue
                    require(row.lastCellNum.toInt().coerceAtLeast(0) <= MAX_COLUMNS) { "${sheet.sheetName}: 열 수가 안전 한도를 초과합니다." }
                    val cells = linkedMapOf<Int, XlsxStudentScoreImport.Cell>()
                    val last = row.lastCellNum.toInt().coerceAtLeast(0)
                    for (ci in 0 until minOf(last, MAX_COLUMNS)) {
                        val cell = row.getCell(ci) ?: continue
                        val formula = cell.cellType == CellType.FORMULA
                        val value = cachedText(cell)
                        if (formula) workbookFormulaCells++
                        if (value.isNotBlank() || formula) cells[ci] = XlsxStudentScoreImport.Cell(ri + 1, ci, value, formula)
                    }
                    if (cells.isNotEmpty()) outRows += XlsxStudentScoreImport.Row(ri + 1, cells)
                }
                val merges = mutableListOf<XlsxStudentScoreImport.MergeRange>()
                require(sheet.numMergedRegions <= 5000) { "${sheet.sheetName}: 병합 범위가 너무 많습니다." }
                for (mi in 0 until sheet.numMergedRegions) {
                    val region = sheet.getMergedRegion(mi)
                    if (region.firstRow >= MAX_ROWS || region.firstColumn >= MAX_COLUMNS) continue
                    merges += XlsxStudentScoreImport.MergeRange(
                        region.firstRow + 1,
                        minOf(region.lastRow + 1, MAX_ROWS),
                        region.firstColumn,
                        minOf(region.lastColumn, MAX_COLUMNS - 1)
                    )
                }
                sheets += XlsxStudentScoreImport.Sheet(sheet.sheetName.take(120), outRows, merges)
            }
            require(sheets.isNotEmpty()) { "Excel 파일에서 읽을 수 있는 시트를 찾지 못했습니다." }
            return XlsxStudentScoreImport.Workbook(sheets, 0, workbookFormulaCells)
        }
    }

    private fun cachedText(cell: org.apache.poi.ss.usermodel.Cell): String {
        val type = if (cell.cellType == CellType.FORMULA) cell.cachedFormulaResultType else cell.cellType
        return when (type) {
            CellType.STRING -> cell.stringCellValue.orEmpty().trim()
            CellType.NUMERIC -> numberText(cell.numericCellValue)
            CellType.BOOLEAN -> if (cell.booleanCellValue) "TRUE" else "FALSE"
            CellType.ERROR, CellType.BLANK, CellType._NONE -> ""
            CellType.FORMULA -> ""
        }
    }

    private fun numberText(value: Double): String {
        if (!value.isFinite()) return ""
        val rounded = value.toLong()
        if (value == rounded.toDouble()) return rounded.toString()
        return BigDecimal.valueOf(value).stripTrailingZeros().toPlainString()
    }
}
