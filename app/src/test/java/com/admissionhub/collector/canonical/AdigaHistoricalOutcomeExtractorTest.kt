package com.admissionhub.collector.canonical

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AdigaHistoricalOutcomeExtractorTest {
    @Test fun extractsHanbatStyleConvertedAndGradeCutsOnlyWithVerifiedHeaders() {
        val rows = listOf(
            listOf("모집단위", "학생부교과(일반)전형"),
            listOf("모집인원", "경쟁률", "충원합격순위", "대학별 환산점수", "최종등록자 교과성적 학생부등급"),
            listOf("", "", "", "최종등록자50% cut", "최종등록자70% cut", "총점", "최종등록자50% 학생 성적", "최종등록자70% 학생 성적"),
            listOf("반도체시스템공학과", "16", "8.00", "23", "515.212", "512.280", "545", "3.87", "3.69")
        )
        val metrics = JSONObject().put("historicalResultYear", 2025)
        val out = AdigaHistoricalOutcomeExtractor.extract(rows, 0, 3, metrics, 2025)
        assertNotNull(out)
        out!!
        assertTrue(out.getBoolean("headersVerified"))
        assertEquals("반도체시스템공학과", out.getString("recruitmentUnit"))
        assertEquals(515.212, out.getDouble("converted50"), 1e-9)
        assertEquals(512.280, out.getDouble("converted70"), 1e-9)
        assertEquals(545.0, out.getDouble("convertedMax"), 1e-9)
        assertEquals(3.87, out.getDouble("grade50"), 1e-9)
        assertEquals(3.69, out.getDouble("grade70"), 1e-9)
    }

    @Test fun rejectsChangeSummaryThatIsNotAnOutcomeTable() {
        val rows = listOf(
            listOf("모집단위", "학생부교과(일반)전형"),
            listOf("전형별 주요사항", "학생부 100%"),
            listOf("반도체시스템공학과", "학생부 100%")
        )
        assertNull(AdigaHistoricalOutcomeExtractor.extract(rows, 0, 2, JSONObject().put("historicalResultYear", 2026), 2026))
    }
}
