package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
    fun genericProductLoginIsOneShotRewriteOnly() {
        val url = "https://www.jinhak.com/jh/member/login"
        assertEquals(JinhakAuthEventState.Event.GENERIC_PRODUCT_LOGIN, JinhakAuthEventState.classify(url))
        assertEquals(JinhakAuthEventState.Action.OPEN_CANONICAL_HIGH3_AUTH_ONCE, JinhakAuthEventState.action(url))
    }

    @Test
    fun canonicalMemberLoginWaitsForServerReturn() {
        val high3 = JinhakGradeRouteFence.protectedHigh3Core()
        val login = JinhakHigh3AuthRoute.canonicalLoginUrl(high3)
        assertTrue(JinhakHigh3AuthRoute.isMemberLoginSurface(login))
        assertEquals(JinhakAuthEventState.Event.MEMBER_LOGIN, JinhakAuthEventState.classify(login))
        assertEquals(JinhakAuthEventState.Action.WAIT_FOR_SERVER_RETURN, JinhakAuthEventState.action(login))
        assertFalse(JinhakGradeRouteFence.isBlockedLowerGrade(login))
    }

    @Test
    fun high3IsVerifiedOnlyAfterReturn() {
        val high3 = JinhakGradeRouteFence.protectedHigh3Core()
        assertEquals(JinhakAuthEventState.Event.HIGH3, JinhakAuthEventState.classify(high3))
        assertEquals(JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION, JinhakAuthEventState.action(high3))
    }

    @Test
    fun unknownSameProviderPageIsObservedNotStopped() {
        val url = "https://www.jinhak.com/jh/high3/new-future-page"
        assertEquals(JinhakAuthEventState.Event.HIGH3, JinhakAuthEventState.classify(url))
        assertEquals(JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION, JinhakAuthEventState.action(url))
    }
}
