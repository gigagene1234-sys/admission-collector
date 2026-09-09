package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakStorageOnlyPolicyTest {
    @Test fun exactEarlyLibraryIsOnlyCollectionRoute() {
        assertTrue(JinhakStorageOnlyPolicy.isLibrary(JinhakStorageOnlyPolicy.LIBRARY_URL))
        assertFalse(JinhakStorageOnlyPolicy.isLibrary("https://www.jinhak.com/jh/high3/univ-entrance-info/search/index"))
        assertFalse(JinhakStorageOnlyPolicy.isLibrary("https://www.jinhak.com/jh/high3/early/four-year-university/mock-support"))
        assertFalse(JinhakStorageOnlyPolicy.isLibrary("https://www.jinhak.com/jh/high3/regular/four-year-university/storage"))
    }

    @Test fun lowerGradeAlwaysBlocked() {
        assertEquals(
            JinhakStorageOnlyPolicy.MainFrameDecision.BLOCK_LOWER_GRADE,
            JinhakStorageOnlyPolicy.decision("https://www.jinhak.com/jh/high2/early/library")
        )
    }

    @Test fun publicHigh3IsNotCollectionNavigation() {
        assertEquals(
            JinhakStorageOnlyPolicy.MainFrameDecision.BLOCK_NON_LIBRARY,
            JinhakStorageOnlyPolicy.decision("https://www.jinhak.com/jh/high3/univ-entrance-info/search/index")
        )
    }

    @Test fun refreshRequiresProtectedLibraryState() {
        assertTrue(JinhakStorageOnlyPolicy.shouldScheduleRefresh(true, true, JinhakStorageOnlyPolicy.LIBRARY_URL))
        assertFalse(JinhakStorageOnlyPolicy.shouldScheduleRefresh(true, false, JinhakStorageOnlyPolicy.LIBRARY_URL))
        assertFalse(JinhakStorageOnlyPolicy.shouldScheduleRefresh(true, true, "https://www.jinhak.com/jh/high3"))
    }
}
