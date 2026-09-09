package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakRuntimeStabilityV0175Test {
    @Test
    fun genericSearchIsOnlyBenignAsSameDocumentAlias() {
        val url = "https://www.jinhak.com/jh/search"
        assertTrue(JinhakStrictHigh3Sandbox.isBenignSameDocumentHistoryAlias(url))
        assertFalse(JinhakStrictHigh3Sandbox.allowsVisibleMainFrame(url))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url))
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_OTHER_JINHAK,
            JinhakStrictHigh3Sandbox.decision(url)
        )
    }

    @Test
    fun lowerGradePayloadNeverQualifiesAsBenignAlias() {
        val url = "https://www.jinhak.com/jh/search?next=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh2%2Fearly"
        assertTrue(JinhakGradeRouteFence.isBlockedLowerGrade(url))
        assertFalse(JinhakStrictHigh3Sandbox.isBenignSameDocumentHistoryAlias(url))
        assertFalse(JinhakStrictHigh3Sandbox.allowsVisibleMainFrame(url))
    }

    @Test
    fun strictHigh3NavigationContractIsUnchanged() {
        val high3 = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3,
            JinhakStrictHigh3Sandbox.decision(high3)
        )
        assertTrue(JinhakStrictHigh3Sandbox.allowsVisibleMainFrame(high3))
        assertTrue(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(high3))
    }

    @Test
    fun genericLoginRouterRemainsBlocked() {
        val login = "https://www.jinhak.com/jh/member/login"
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_GENERIC_LOGIN,
            JinhakStrictHigh3Sandbox.decision(login)
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsVisibleMainFrame(login))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(login))
    }
}
