package com.admissionhub.collector.canonical

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AdigaHistoricalOutcomeExtractorV15Test {
    @Test
    fun extractsStandardSameRowOnlyWithVerifiedHeaders() {
        val rows = listOf(
            listOf("모집단위", "모집인원", "경쟁률", "충원합격", "최종등록자 대학별 환산점수", "", "총점(학생부)", "최종등록자 교과성적 학생부등급", ""),
            listOf("", "", "", "", "50% cut", "70% cut", "", "50% cut", "70% cut"),
            listOf("철도차량시스템공", "13", "5.33", "4", "820.5", "810.2", "1000", "3.20", "3.50")
        )
        val metrics = JSONObject().put("historicalResultYear", 2026)
        val out = AdigaHistoricalOutcomeExtractor.extractSameRow(rows, 2, metrics, 2027, "학생부교과")
        assertNotNull(out)
        out!!
        assertTrue(out.getBoolean("headersVerified"))
        assertFalse(out.getBoolean("bindingInferred"))
        assertEquals("same-official-table-same-row", out.getString("bindingMethod"))
        assertEquals(2026, out.getInt("historicalResultYear"))
        assertEquals(820.5, out.getDouble("converted50"), 0.0001)
        assertEquals(810.2, out.getDouble("converted70"), 0.0001)
        assertEquals(3.20, out.getDouble("grade50"), 0.0001)
        assertEquals(3.50, out.getDouble("grade70"), 0.0001)
    }

    @Test
    fun refusesNumbersWhenOfficialCutHeadersAreMissing() {
        val rows = listOf(
            listOf("모집단위", "모집인원", "경쟁률", "대학별 환산점수"),
            listOf("철도차량시스템공", "13", "5.33", "820.5", "810.2")
        )
        assertNull(AdigaHistoricalOutcomeExtractor.extractSameRow(rows, 1, JSONObject(), 2026, "학생부교과"))
    }
}
