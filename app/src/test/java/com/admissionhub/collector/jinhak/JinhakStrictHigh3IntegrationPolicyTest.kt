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
    fun adapterNeverQueuesSharedRootGenericLoginOrLowerGrades() {
        val forbidden = listOf(
            "https://www.jinhak.com/",
            "https://www.jinhak.com/jh/member/login",
            "https://www.jinhak.com/jh/high1/",
            "https://www.jinhak.com/jh/high2/",
            "https://www.jinhak.com/jh/high12/",
            "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx"
        )
        forbidden.forEach { url -> assertFalse("must not queue $url", JinhakAdapter.isBatchNavigable(url)) }
        assertTrue(JinhakAdapter.isBatchNavigable(JinhakSiteTopology.userSessionBootstrapUrl()))
        assertTrue(JinhakAdapter.isBatchNavigable(JinhakSiteTopology.protectedCoreProbeUrl()))
    }

    @Test
    fun everyDeclaredMissionSeedIsStrictHigh3() {
        val seeds = JinhakSiteTopology.missionSeeds()
        assertTrue(seeds.isNotEmpty())
        seeds.forEach { seed -> assertTrue("seed must be strict high3: $seed", JinhakStrictHigh3Sandbox.allowsCollectorNavigation(seed)) }
    }
}
