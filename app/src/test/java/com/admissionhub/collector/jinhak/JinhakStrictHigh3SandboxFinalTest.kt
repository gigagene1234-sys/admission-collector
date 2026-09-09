package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

class JinhakStrictHigh3SandboxFinalTest {
    private fun encode(value: String, rounds: Int): String {
        var current = value
        repeat(rounds) {
            current = URLEncoder.encode(current, StandardCharsets.UTF_8.name())
        }
        return current
    }

    @Test
    fun tenTimesEncodedLowerGradeReturnIsStillBlocked() {
        val lower = "https://www.jinhak.com/jh/high2/early"
        val login = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=${encode(lower, 10)}"
        assertTrue(JinhakGradeRouteFence.isBlockedLowerGrade(login))
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_LOWER_GRADE,
            JinhakStrictHigh3Sandbox.decision(login)
        )
    }

    @Test
    fun deeplyEncodedLowerGradeInsideHigh3QueryIsBlocked() {
        val lower = "https://www.jinhak.com/jh/high1/"
        val high3 = "https://www.jinhak.com/jh/high3/early/four-year-university/search?next=${encode(lower, 9)}"
        assertTrue(JinhakGradeRouteFence.isBlockedLowerGrade(high3))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(high3))
    }

    @Test
    fun memberLoginWithoutReturnUrlIsNotVisibleAllowedSurface() {
        val login = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx"
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN,
            JinhakStrictHigh3Sandbox.decision(login)
        )
        assertFalse(JinhakStrictHigh3Sandbox.allowsUserLoginSurface(login))
    }

    @Test
    fun memberLoginWithDeepEncodedHigh3ReturnIsUserLoginOnly() {
        val high3 = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        val login = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=${encode(high3, 8)}"
        assertEquals(
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN,
            JinhakStrictHigh3Sandbox.decision(login)
        )
        assertTrue(JinhakStrictHigh3Sandbox.allowsUserLoginSurface(login))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(login))
    }

    @Test
    fun backslashLowerGradeVariantCannotBypassFence() {
        val tricky = "https://www.jinhak.com/jh/high3/search?next=https%3A%2F%2Fwww.jinhak.com%5Cjh%5Chigh12%5Cearly"
        assertTrue(JinhakGradeRouteFence.isBlockedLowerGrade(tricky))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(tricky))
    }

    @Test
    fun sharedRootGenericLoginAndOtherProductRemainFailClosed() {
        listOf(
            "https://www.jinhak.com/",
            "https://www.jinhak.com/jh/member/login",
            "https://www.jinhak.com/jh/anything-else"
        ).forEach { url ->
            assertFalse(JinhakStrictHigh3Sandbox.allowsVisibleMainFrame(url))
            assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url))
        }
    }
}
