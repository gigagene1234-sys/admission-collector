package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakSiteTopologyV0172Test {
    @Test
    fun publicHigh3SearchIsTheFirstMissionBootstrap() {
        val bootstrap = JinhakSiteTopology.userSessionBootstrapUrl()
        assertTrue(bootstrap.endsWith("/jh/high3/early/four-year-university/search"))
        assertEquals(bootstrap, JinhakSiteTopology.missionSeeds().first())
        assertTrue(JinhakSiteTopology.isUserSessionBootstrapUrl(bootstrap))
        assertTrue(JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(bootstrap))
        assertTrue(JinhakSiteTopology.isCoreMissionRoute(bootstrap))
    }

    @Test
    fun protectedLibraryRemainsASeparateMissionTarget() {
        val protectedCore = JinhakSiteTopology.protectedCoreProbeUrl()
        assertTrue(protectedCore.endsWith("/jh/high3/early/four-year-university/library"))
        assertFalse(JinhakSiteTopology.isUserSessionBootstrapUrl(protectedCore))
        assertTrue(JinhakSiteTopology.missionSeeds().contains(protectedCore))
        assertTrue(JinhakSiteTopology.missionSeeds().indexOf(protectedCore) > 0)
    }
}
