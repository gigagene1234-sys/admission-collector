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
    fun genericProductLoginIsRecognizedButNeverCanonicalAuth() {
        val generic = "https://www.jinhak.com/jh/member/login"
        assertTrue(JinhakHigh3AuthRoute.isGenericProductLogin(generic))
        assertEquals(
            JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_OTHER_JINHAK,
            JinhakHigh3AuthRoute.decision(generic)
        )
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_GENERIC_LOGIN,
            JinhakStrictHigh3Sandbox.decision(generic)
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsVisibleMainFrame(generic))
    }

    @Test
    fun memberLoginWithoutHigh3ReturnIsOnlyAHostPathMatchAndIsStrictlyBlocked() {
        val member = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx"
        assertTrue(JinhakHigh3AuthRoute.isMemberLoginSurface(member))
        assertFalse(JinhakHigh3AuthRoute.isCanonicalMemberLogin(member))
        assertEquals(
            JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_OTHER_JINHAK,
            JinhakHigh3AuthRoute.decision(member)
        )
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN,
            JinhakStrictHigh3Sandbox.decision(member)
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsUserLoginSurface(member))
    }

    @Test
    fun exactMemberLoginWithHigh3ReturnIsCanonicalUserLoginSurfaceOnly() {
        val member = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh3%2Fearly%2Ffour-year-university%2Flibrary"
        assertTrue(JinhakHigh3AuthRoute.isMemberLoginSurface(member))
        assertTrue(JinhakHigh3AuthRoute.isCanonicalMemberLogin(member))
        assertEquals(
            JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_CANONICAL_AUTH,
            JinhakHigh3AuthRoute.decision(member)
        )
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN,
            JinhakStrictHigh3Sandbox.decision(member)
        )
        assertTrue(JinhakStrictHigh3Sandbox.allowsUserLoginSurface(member))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(member))
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
