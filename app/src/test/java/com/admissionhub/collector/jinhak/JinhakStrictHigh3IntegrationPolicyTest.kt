package com.admissionhub.collector.jinhak

import com.admissionhub.collector.provider.JinhakAdapter
import com.admissionhub.collector.provider.ProviderId
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakStrictHigh3IntegrationPolicyTest {
    @Test
    fun providerDefaultCanNeverOpenSharedRoot() {
        assertTrue(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(ProviderId.JINHAK.homeUrl))
        assertFalse(ProviderId.JINHAK.homeUrl == "https://www.jinhak.com/")
    }

    @Test
    fun adapterQueuesOnlyProtectedSusiStorageInV0183() {
        val forbidden = listOf(
            "https://www.jinhak.com/",
            "https://www.jinhak.com/jh/member/login",
            "https://www.jinhak.com/jh/high1/",
            "https://www.jinhak.com/jh/high2/",
            "https://www.jinhak.com/jh/high12/",
            "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx",
            JinhakSiteTopology.userSessionBootstrapUrl(),
            "https://www.jinhak.com/jh/high3/early/four-year-university/search",
            "https://www.jinhak.com/jh/high3/early/four-year-university/report/pass-predict"
        )
        forbidden.forEach { url -> assertFalse("v0.18.3 storage-only mode must not queue $url", JinhakAdapter.isBatchNavigable(url)) }
        assertTrue(JinhakAdapter.isBatchNavigable(JinhakSiteTopology.protectedCoreProbeUrl()))
    }

    @Test
    fun everyDeclaredMissionSeedRemainsStrictHigh3ButAdapterUsesStorageOnlySeed() {
        val declared = JinhakSiteTopology.missionSeeds()
        assertTrue(declared.isNotEmpty())
        declared.forEach { seed -> assertTrue("seed must be strict high3: $seed", JinhakStrictHigh3Sandbox.allowsCollectorNavigation(seed)) }

        val adapterSeeds = JinhakAdapter.seedUrls()
        assertTrue(adapterSeeds.size == 1)
        assertTrue(adapterSeeds.single() == JinhakSiteTopology.protectedCoreProbeUrl())
    }
}
