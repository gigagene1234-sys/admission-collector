package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakSingleSurfaceStoragePolicyTest {
    @Test
    fun singleSurfaceIsMandatoryAndExternalAppIsNotAnAuthBridge() {
        assertTrue(JinhakSingleSurfaceStoragePolicy.ENABLED)
        assertEquals("collector-main-webview", JinhakSingleSurfaceStoragePolicy.AUTH_AND_COLLECTION_SURFACE)
        assertFalse(JinhakSingleSurfaceStoragePolicy.EXTERNAL_APP_SESSION_BRIDGE)
    }

    @Test
    fun onlyStorageAndLoginAreForegroundStates() {
        assertTrue(JinhakSingleSurfaceStoragePolicy.isAllowedForegroundState(JinhakSiteTopology.protectedCoreProbeUrl()))
        assertFalse(JinhakSingleSurfaceStoragePolicy.isAllowedForegroundState("https://www.jinhak.com/jh/high3/early/four-year-university/search"))
        assertFalse(JinhakSingleSurfaceStoragePolicy.isAllowedForegroundState("https://www.jinhak.com/"))
    }

    @Test
    fun adigaCompletedDeltaNeverGoesNegative() {
        assertEquals(13, JinhakSingleSurfaceStoragePolicy.completedDelta(500, 513))
        assertEquals(0, JinhakSingleSurfaceStoragePolicy.completedDelta(513, 500))
    }
}
