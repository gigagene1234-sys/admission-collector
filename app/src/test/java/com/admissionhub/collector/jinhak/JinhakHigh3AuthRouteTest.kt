package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.URI

class JinhakHigh3AuthRouteTest {
    @Test
    fun legacyCanonicalLoginShimNeverCreatesMemberLoginUrl() {
        val target = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        val result = JinhakHigh3AuthRoute.canonicalLoginUrl(target)
        val uri = URI(result)

        assertEquals("www.jinhak.com", uri.host)
        assertTrue(uri.path.startsWith("/jh/high3/"))
        assertFalse(result.contains("member.jinhak.com", ignoreCase = true))
    }

    @Test
    fun lowerGradeRequestedTargetFallsBackToProtectedHigh3() {
        val requested = "https://www.jinhak.com/jh/high2/early"
        val result = JinhakHigh3AuthRoute.canonicalLoginUrl(requested)

        assertEquals(JinhakGradeRouteFence.protectedHigh3Core(), result)
        assertTrue(result.contains("/jh/high3/"))
        assertFalse(result.contains("/jh/high2/"))
    }

    @Test
    fun genericProductLoginIsAllowedForSiteOwnedAuthentication() {
        val generic = "https://www.jinhak.com/jh/member/login"
        assertTrue(JinhakHigh3AuthRoute.isGenericProductLogin(generic))
        assertEquals(
            JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_CANONICAL_AUTH,
            JinhakHigh3AuthRoute.decision(generic)
        )
    }

    @Test
    fun memberLoginWithoutCollectorReturnUrlIsAllowedAsSiteSurface() {
        val member = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx"
        assertTrue(JinhakHigh3AuthRoute.isMemberLoginSurface(member))
        assertEquals(
            JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_CANONICAL_AUTH,
            JinhakHigh3AuthRoute.decision(member)
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
