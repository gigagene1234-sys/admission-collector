package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakManualStorageReportPolicyTest {
    @Test
    fun storageAndReportsAreOnlyAutonomousScope() {
        assertTrue(JinhakManualStorageReportPolicy.isStorageEntry(
            "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        ))
        assertTrue(JinhakManualStorageReportPolicy.isReportUrl(
            "https://www.jinhak.com/jh/high3/early/four-year-university/report/pass-predict"
        ))
        assertTrue(JinhakManualStorageReportPolicy.isAllowedMissionUrl(
            "https://www.jinhak.com/jh/high3/early/four-year-university/report/actual-admission"
        ))
        assertFalse(JinhakManualStorageReportPolicy.isAllowedMissionUrl(
            "https://www.jinhak.com/jh/high3/early/four-year-university/search"
        ))
        assertFalse(JinhakManualStorageReportPolicy.isAllowedMissionUrl(
            "https://www.jinhak.com/jh/member/login"
        ))
    }

    @Test
    fun storageRequiresBoundApplicationButReportTabsCanUseBridge() {
        val storage = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        val report = "https://www.jinhak.com/jh/high3/early/four-year-university/report/pass-predict"
        assertTrue(JinhakManualStorageReportPolicy.shouldPromoteAction(storage, "합격예측 리포트", true))
        assertFalse(JinhakManualStorageReportPolicy.shouldPromoteAction(storage, "합격예측 리포트", false))
        assertTrue(JinhakManualStorageReportPolicy.shouldPromoteAction(report, "실제 합격자", false))
        assertFalse(JinhakManualStorageReportPolicy.shouldPromoteAction(report, "입시 전략", true))
        assertFalse(JinhakManualStorageReportPolicy.shouldPromoteAction(report, "원서 접수", true))
    }

    @Test
    fun authAndGenericCrawlAreExplicitlyDisabled() {
        assertFalse(JinhakManualStorageReportPolicy.AUTO_LOGIN)
        assertFalse(JinhakManualStorageReportPolicy.APP_SESSION_RESTORE)
        assertFalse(JinhakManualStorageReportPolicy.AUTH_PROOF_CACHE)
        assertFalse(JinhakManualStorageReportPolicy.GENERIC_SITE_CRAWL)
    }
}
