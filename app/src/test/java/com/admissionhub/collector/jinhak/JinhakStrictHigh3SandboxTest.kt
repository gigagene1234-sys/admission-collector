package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakStrictHigh3SandboxTest {
    private val high3ReturnLogin =
        "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh3%2Fearly%2Ffour-year-university%2Fsearch"

    @Test
    fun high3RoutesAreTheOnlyCollectorNavigableJinhakPages() {
        val urls = listOf(
            "https://www.jinhak.com/jh/high3",
            "https://www.jinhak.com/jh/high3/early/four-year-university/search",
            "https://jinhak.com/jh/high3/univ-major/univ-info/univ-search"
        )
        urls.forEach { url ->
            assertEquals(JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3, JinhakStrictHigh3Sandbox.decision(url))
            assertTrue(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url))
        }
    }

    @Test
    fun sharedRootIsBlocked() {
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_SHARED_ROOT,
            JinhakStrictHigh3Sandbox.decision("https://www.jinhak.com/")
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation("https://www.jinhak.com/"))
    }

    @Test
    fun genericProductLoginRouterIsBlocked() {
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_GENERIC_LOGIN,
            JinhakStrictHigh3Sandbox.decision("https://www.jinhak.com/jh/member/login")
        )
    }

    @Test
    fun exactMemberLoginSurfaceIsAllowedOnlyWhenReturnUrlIsHigh3() {
        assertEquals(JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN, JinhakStrictHigh3Sandbox.decision(high3ReturnLogin))
        assertTrue(JinhakStrictHigh3Sandbox.allowsUserLoginSurface(high3ReturnLogin))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(high3ReturnLogin))
    }

    @Test
    fun memberLoginWithoutReturnUrlIsBlocked() {
        val login = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx"
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN,
            JinhakStrictHigh3Sandbox.decision(login)
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsUserLoginSurface(login))
    }

    @Test
    fun memberLoginWithSharedRootOrExternalReturnIsBlocked() {
        val shared = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fwww.jinhak.com%2F"
        val external = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fexample.com%2F"
        listOf(shared, external).forEach { login ->
            assertEquals(
                JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN,
                JinhakStrictHigh3Sandbox.decision(login)
            )
            assertFalse(JinhakStrictHigh3Sandbox.allowsUserLoginSurface(login))
        }
    }

    @Test
    fun otherMemberPagesAreBlocked() {
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_OTHER_JINHAK,
            JinhakStrictHigh3Sandbox.decision("https://member.jinhak.com/MemberV3/MemberJoin/MemberJoinStep1.aspx")
        )
    }

    @Test
    fun lowerGradeRoutesAreBlocked() {
        listOf(
            "https://www.jinhak.com/jh/high1/",
            "https://www.jinhak.com/jh/high2/early",
            "https://www.jinhak.com/jh/high12"
        ).forEach { url ->
            assertEquals(JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_LOWER_GRADE, JinhakStrictHigh3Sandbox.decision(url))
            assertTrue(JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(url))
        }
    }

    @Test
    fun encodedLowerGradeReturnInsideMemberLoginIsBlockedBeforeLoginAllowance() {
        val nested = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%253A%252F%252Fwww.jinhak.com%252Fjh%252Fhigh2%252Fearly"
        assertEquals(JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_LOWER_GRADE, JinhakStrictHigh3Sandbox.decision(nested))
        assertFalse(JinhakStrictHigh3Sandbox.allowsUserLoginSurface(nested))
    }

    @Test
    fun high3UrlWithEncodedLowerGradeRedirectMaterialIsBlocked() {
        val nested = "https://www.jinhak.com/jh/high3/early/four-year-university/search?next=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh1%2F"
        assertEquals(JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_LOWER_GRADE, JinhakStrictHigh3Sandbox.decision(nested))
    }

    @Test
    fun nonHigh3JinhakProductRoutesAreBlocked() {
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_OTHER_JINHAK,
            JinhakStrictHigh3Sandbox.decision("https://www.jinhak.com/jh/anything-else")
        )
    }

    @Test
    fun externalAndHttpTopLevelNavigationIsBlocked() {
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_EXTERNAL,
            JinhakStrictHigh3Sandbox.decision("https://example.com/jh/high3/")
        )
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_EXTERNAL,
            JinhakStrictHigh3Sandbox.decision("http://www.jinhak.com/jh/high3/")
        )
    }

    @Test
    fun onlyStrictHigh3CanBeSanitizedForAppNavigation() {
        val good = "https://www.jinhak.com/jh/high3/early/four-year-university/search"
        assertEquals(good, JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(good))
        assertNull(JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull("https://www.jinhak.com/"))
        assertNull(JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull("https://www.jinhak.com/jh/high2/"))
        assertNull(JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull("https://www.jinhak.com/jh/member/login"))
        assertNull(JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(high3ReturnLogin))
    }
}
