package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class JinhakAuthEventStateTest {
    @Test
    fun lowerGradeAlwaysDropsWithoutRecoveryAction() {
        val urls = listOf(
            "https://www.jinhak.com/jh/high1/",
            "https://www.jinhak.com/jh/high2/",
            "https://www.jinhak.com/jh/high12/",
            "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh12%2F"
        )
        urls.forEach { url ->
            assertEquals(JinhakAuthEventState.Event.LOWER_GRADE, JinhakAuthEventState.classify(url))
            assertEquals(JinhakAuthEventState.Action.DROP_REQUEST, JinhakAuthEventState.action(url))
        }
    }

    @Test
    fun genericProductLoginIsLegacyObserveOnlyAndStrictSandboxBlocksIt() {
        val url = "https://www.jinhak.com/jh/member/login"
        // The legacy pure event model is side-effect free. It may observe an unknown/noncanonical
        // route, but v0.17.4's authoritative visible-navigation policy blocks this router.
        assertEquals(JinhakAuthEventState.Event.OTHER_JINHAK, JinhakAuthEventState.classify(url))
        assertEquals(JinhakAuthEventState.Action.OBSERVE_WITHOUT_NAVIGATION, JinhakAuthEventState.action(url))
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_GENERIC_LOGIN,
            JinhakStrictHigh3Sandbox.decision(url)
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsVisibleMainFrame(url))
    }

    @Test
    fun memberLoginWithoutHigh3ReturnCannotBecomeStrictVisibleLoginSurface() {
        val login = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx"
        assertEquals(JinhakAuthEventState.Event.OTHER_JINHAK, JinhakAuthEventState.classify(login))
        assertEquals(JinhakAuthEventState.Action.OBSERVE_WITHOUT_NAVIGATION, JinhakAuthEventState.action(login))
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN,
            JinhakStrictHigh3Sandbox.decision(login)
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsVisibleMainFrame(login))
        assertFalse(JinhakGradeRouteFence.isBlockedLowerGrade(login))
    }

    @Test
    fun canonicalMemberLoginWithHigh3ReturnWaitsForSiteServerReturn() {
        val high3 = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        val login = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh3%2Fearly%2Ffour-year-university%2Flibrary"
        assertEquals(JinhakAuthEventState.Event.MEMBER_LOGIN, JinhakAuthEventState.classify(login))
        assertEquals(JinhakAuthEventState.Action.WAIT_FOR_SERVER_RETURN, JinhakAuthEventState.action(login))
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN,
            JinhakStrictHigh3Sandbox.decision(login)
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(login))
        assertEquals(high3, JinhakHigh3AuthRoute.returnUrl(login))
    }

    @Test
    fun high3NavigationEventIsHandedToLegacyObserverWithoutLoginRewrite() {
        val high3 = JinhakGradeRouteFence.protectedHigh3Core()
        assertEquals(JinhakAuthEventState.Event.HIGH3, JinhakAuthEventState.classify(high3))
        assertEquals(JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION, JinhakAuthEventState.action(high3))
    }

    @Test
    fun unknownHigh3PageIsStillHigh3AndNotRewritten() {
        val url = "https://www.jinhak.com/jh/high3/new-future-page"
        assertEquals(JinhakAuthEventState.Event.HIGH3, JinhakAuthEventState.classify(url))
        assertEquals(JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION, JinhakAuthEventState.action(url))
    }
}
