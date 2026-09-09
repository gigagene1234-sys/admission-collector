package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakSiteTopologyV0172Test {
    @Test
    fun publicHigh3SearchRemainsManualBootstrapButNotFocusedMissionSeed() {
        val bootstrap = JinhakSiteTopology.userSessionBootstrapUrl()
        assertTrue(bootstrap.endsWith("/jh/high3/early/four-year-university/search"))
        assertTrue(JinhakSiteTopology.isUserSessionBootstrapUrl(bootstrap))
        assertTrue(JinhakSiteTopology.isCoreMissionRoute(bootstrap))
        assertFalse(JinhakSiteTopology.missionSeeds().contains(bootstrap))
    }

    @Test
    fun protectedLibraryIsTheFirstFocusedMissionTarget() {
        val protectedCore = JinhakSiteTopology.protectedCoreProbeUrl()
        assertTrue(protectedCore.endsWith("/jh/high3/early/four-year-university/library"))
        assertFalse(JinhakSiteTopology.isUserSessionBootstrapUrl(protectedCore))
        assertTrue(JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(protectedCore))
        assertTrue(JinhakSiteTopology.isCoreMissionRoute(protectedCore))
        assertEquals(protectedCore, JinhakSiteTopology.missionSeeds().first())
    }
}