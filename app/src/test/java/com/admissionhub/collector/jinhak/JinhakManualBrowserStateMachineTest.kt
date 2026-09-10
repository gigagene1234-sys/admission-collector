package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Test

class JinhakManualBrowserStateMachineTest {
    @Test
    fun loginSearchAndRootRemainPassiveBeforeStorage() {
        val urls = listOf(
            "https://www.jinhak.com/",
            "https://www.jinhak.com/jh/member/login",
            "https://www.jinhak.com/jh/high3/early/four-year-university/search"
        )
        urls.forEach { url ->
            assertEquals(JinhakManualBrowserStateMachine.Phase.MANUAL_BROWSER,
                JinhakManualBrowserStateMachine.phase(url, false))
            assertTrue(JinhakManualBrowserStateMachine.isPassiveManualBrowser(url, false))
        }
    }

    @Test
    fun exactStorageArmsAndActiveReportsTraverse() {
        val storage = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        val report = "https://www.jinhak.com/jh/high3/early/four-year-university/report/pass-predict"
        assertEquals(JinhakManualBrowserStateMachine.Phase.STORAGE_ARMED,
            JinhakManualBrowserStateMachine.phase(storage, false))
        assertEquals(JinhakManualBrowserStateMachine.Phase.REPORT_TRAVERSAL,
            JinhakManualBrowserStateMachine.phase(report, true))
    }

    @Test
    fun leavingScopeDuringTraversalStopsWithoutAuthRecovery() {
        val search = "https://www.jinhak.com/jh/high3/early/four-year-university/search"
        assertEquals(JinhakManualBrowserStateMachine.Phase.STOP_ONLY,
            JinhakManualBrowserStateMachine.phase(search, true))
        assertTrue(JinhakManualBrowserStateMachine.shouldStopOnly(search, true))
        assertFalse(JinhakManualBrowserStateMachine.AUTO_LOGIN)
        assertFalse(JinhakManualBrowserStateMachine.AUTH_PROBE)
        assertFalse(JinhakManualBrowserStateMachine.SESSION_RESTORE)
        assertFalse(JinhakManualBrowserStateMachine.CREDENTIAL_AUTOFILL)
        assertFalse(JinhakManualBrowserStateMachine.INTERCEPT_MANUAL_BROWSER_NAVIGATION)
        assertFalse(JinhakManualBrowserStateMachine.STOP_LOADING_IN_MANUAL_BROWSER)
    }
}
