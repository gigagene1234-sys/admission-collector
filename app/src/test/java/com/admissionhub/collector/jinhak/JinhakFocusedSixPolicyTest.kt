package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakFocusedSixPolicyTest {
    @Test fun storageAndReportRoutesAreFocusedCore() {
        assertTrue(JinhakFocusedSixPolicy.isFocusedCoreUrl("https://www.jinhak.com/jh/high3/early/four-year-university/library"))
        assertTrue(JinhakFocusedSixPolicy.isFocusedCoreUrl("https://www.jinhak.com/jh/high3/early/four-year-university/report/pass-predict"))
        assertTrue(JinhakFocusedSixPolicy.isFocusedCoreUrl("https://www.jinhak.com/jh/high3/early/four-year-university/report/actual-admission"))
        assertTrue(JinhakFocusedSixPolicy.isFocusedCoreUrl("https://www.jinhak.com/jh/high3/early/four-year-university/report/admission-result"))
    }

    @Test fun editorialKnowledgeAndStrategyAreNeverFocusedTargets() {
        assertFalse(JinhakFocusedSixPolicy.isFocusedCoreUrl("https://www.jinhak.com/jh/high3/univ-entrance-info/ipsi-analysis/ipsi-knowledge/15193"))
        assertFalse(JinhakFocusedSixPolicy.isFocusedCoreUrl("https://www.jinhak.com/jh/high3/univ-entrance-info/ipsi-analysis/ipsi-strategy/123"))
        assertFalse(JinhakFocusedSixPolicy.isFocusedCoreUrl("https://www.jinhak.com/jh/high3/jinhak-tv/12"))
    }

    @Test fun sixPinnedApplicationsDisableGenericNavigation() {
        assertFalse(JinhakFocusedSixPolicy.shouldAllowGenericNavigation(6, 0, true))
        assertFalse(JinhakFocusedSixPolicy.shouldAllowGenericNavigation(6, 0, false))
        assertTrue(JinhakFocusedSixPolicy.shouldAllowGenericNavigation(0, 0, true))
    }

    @Test fun repeatedLowValueStateEscapesAfterTwoUnchangedSnapshots() {
        assertFalse(JinhakFocusedSixPolicy.shouldEscapeRepeatedState(1, "jinhak-admission-knowledge", false))
        assertTrue(JinhakFocusedSixPolicy.shouldEscapeRepeatedState(2, "jinhak-admission-knowledge", false))
        assertFalse(JinhakFocusedSixPolicy.shouldEscapeRepeatedState(2, "jinhak-early-storage", true))
    }

    @Test fun pinnedIdentityKeysRequireOccupiedNonBlankSlots() {
        val keys = JinhakFocusedSixPolicy.pinnedIdentityKeys(listOf(
            true to "a", true to "b", false to "c", true to " ", true to "d"
        ))
        assertEquals(setOf("a", "b", "d"), keys)
    }
}