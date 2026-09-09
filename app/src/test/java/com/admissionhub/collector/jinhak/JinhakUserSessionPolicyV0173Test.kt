package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakUserSessionPolicyV0173Test {
    private val high3ReturnLogin =
        "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx?ReturnURL=https%3A%2F%2Fwww.jinhak.com%2Fjh%2Fhigh3%2Fearly%2Ffour-year-university%2Fsearch"

    @Test
    fun exactMemberLoginOnlyArmsWhenBoundToHigh3Return() {
        assertEquals(
            JinhakUserSessionPolicy.ConfirmationDecision.ARM_AFTER_SITE_LOGIN,
            JinhakUserSessionPolicy.confirmationDecision(high3ReturnLogin)
        )
        assertEquals(
            JinhakUserSessionPolicy.ConfirmationDecision.WAIT_FOR_HIGH3,
            JinhakUserSessionPolicy.confirmationDecision("https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx")
        )
    }

    @Test
    fun sharedGenericProductLoginCannotActivateOrArmStrictSession() {
        assertEquals(
            JinhakUserSessionPolicy.ConfirmationDecision.WAIT_FOR_HIGH3,
            JinhakUserSessionPolicy.confirmationDecision("https://www.jinhak.com/jh/member/login")
        )
    }

    @Test
    fun confirmationOnHigh3CanActivateCurrentVisibleRoute() {
        assertEquals(
            JinhakUserSessionPolicy.ConfirmationDecision.ACTIVATE_CURRENT_HIGH3,
            JinhakUserSessionPolicy.confirmationDecision("https://www.jinhak.com/jh/high3/early/four-year-university/search")
        )
    }

    @Test
    fun lateHigh3BoundMemberLoginCallbackIsIgnoredWhenHigh3IsAlreadyVisible() {
        assertTrue(
            JinhakUserSessionPolicy.shouldIgnoreStaleLoginCallback(
                high3ReturnLogin,
                "https://www.jinhak.com/jh/high3/early/four-year-university/search"
            )
        )
        assertFalse(
            JinhakUserSessionPolicy.shouldIgnoreStaleLoginCallback(high3ReturnLogin, high3ReturnLogin)
        )
    }

    @Test
    fun lowerGradeNeverActivates() {
        assertEquals(
            JinhakUserSessionPolicy.ConfirmationDecision.WAIT_FOR_HIGH3,
            JinhakUserSessionPolicy.confirmationDecision("https://www.jinhak.com/jh/high2/early/search")
        )
    }
}
