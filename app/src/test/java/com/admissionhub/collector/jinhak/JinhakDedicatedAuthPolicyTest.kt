package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakDedicatedAuthPolicyTest {
    @Test
    fun currentUnifiedLoginIsAuthOnly() {
        val login = "https://www.jinhak.com/jh/member/login"
        assertEquals(JinhakDedicatedAuthPolicy.Route.LOGIN_FORM, JinhakDedicatedAuthPolicy.classify(login))
        assertTrue(JinhakDedicatedAuthPolicy.allowsAuthMainFrame(login))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(login))
    }

    @Test
    fun oldMemberLoginMayBeUsedOnlyByAuthContext() {
        val login = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh3%2Fearly%2Ffour-year-university%2Flibrary"
        assertEquals(JinhakDedicatedAuthPolicy.Route.MEMBER_LOGIN, JinhakDedicatedAuthPolicy.classify(login))
        assertTrue(JinhakDedicatedAuthPolicy.allowsAuthMainFrame(login))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(login))
    }

    @Test
    fun high3IsAuthSuccessAndCollectorDestination() {
        val high3 = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        assertTrue(JinhakDedicatedAuthPolicy.isHigh3Success(high3))
        assertTrue(JinhakDedicatedAuthPolicy.allowsAuthMainFrame(high3))
        assertTrue(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(high3))
    }

    @Test
    fun lowerGradesAreBlockedInBothContextsEvenWhenEncoded() {
        val lower = "https://www.jinhak.com/jh/member/login?next=https%253A%252F%252Fwww.jinhak.com%252Fjh%252Fhigh2%252Fearly"
        assertEquals(JinhakDedicatedAuthPolicy.Route.BLOCK_LOWER_GRADE, JinhakDedicatedAuthPolicy.classify(lower))
        assertFalse(JinhakDedicatedAuthPolicy.allowsAuthMainFrame(lower))
        assertFalse(JinhakStrictHigh3Sandbox.allowsCollectorNavigation(lower))
    }

    @Test
    fun externalMainFrameIsNotAnAuthDestination() {
        val external = "https://example.com/login"
        assertEquals(JinhakDedicatedAuthPolicy.Route.BLOCK_EXTERNAL, JinhakDedicatedAuthPolicy.classify(external))
        assertFalse(JinhakDedicatedAuthPolicy.allowsAuthMainFrame(external))
    }
}
