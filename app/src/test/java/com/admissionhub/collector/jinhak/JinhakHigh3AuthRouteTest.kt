package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.URI

class JinhakHigh3AuthRouteTest {
    @Test
    fun canonicalLoginUsesMemberHostAndExplicitHigh3ReturnUrl() {
        val target = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        val login = JinhakHigh3AuthRoute.canonicalLoginUrl(target)
        val uri = URI(login)

        assertEquals("member.jinhak.com", uri.host)
        assertTrue(uri.path.endsWith("/MemberLogIn.aspx"))
        assertEquals(target, JinhakHigh3AuthRoute.returnUrl(login))
        assertTrue(JinhakHigh3AuthRoute.isCanonicalMemberLogin(login))
        assertFalse(JinhakGradeRouteFence.isBlockedLowerGrade(login))
    }

    @Test
    fun lowerGradeReturnTargetCanNeverBecomeAuthDestination() {
        val requested = "https://www.jinhak.com/jh/high2/early"
        val login = JinhakHigh3AuthRoute.canonicalLoginUrl(requested)
        val actualReturn = JinhakHigh3AuthRoute.returnUrl(login)

        assertEquals(JinhakGradeRouteFence.protectedHigh3Core(), actualReturn)
        assertTrue(actualReturn?.contains("/jh/high3/") == true)
        assertFalse(actualReturn?.contains("/jh/high2/") == true)
    }

    @Test
    fun genericProductLoginIsRewriteOnlyNotCollectorAuthEntry() {
        val generic = "https://www.jinhak.com/jh/member/login"
        assertTrue(JinhakHigh3AuthRoute.isGenericProductLogin(generic))
        assertEquals(
            JinhakHigh3AuthRoute.MainFrameDecision.REWRITE_GENERIC_LOGIN,
            JinhakHigh3AuthRoute.decision(generic)
        )
    }

    @Test
    fun lowerGradeNavigationIsBlockedBeforeAnyUiPolicy() {
        val low = "https://www.jinhak.com/jh/high12/early/foo"
        assertEquals(
            JinhakHigh3AuthRoute.MainFrameDecision.BLOCK_LOWER_GRADE,
            JinhakHigh3AuthRoute.decision(low)
        )
    }

    @Test
    fun memberLoginWithLowerGradeNestedReturnIsRejected() {
        val bad = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh1%2Ffoo"
        assertFalse(JinhakHigh3AuthRoute.isCanonicalMemberLogin(bad))
        assertEquals(
            JinhakHigh3AuthRoute.MainFrameDecision.BLOCK_LOWER_GRADE,
            JinhakHigh3AuthRoute.decision(bad)
        )
    }
}
