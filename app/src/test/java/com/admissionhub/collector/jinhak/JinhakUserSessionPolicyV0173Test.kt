package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakUserSessionPolicyV0173Test {
    @Test
    fun confirmationOnLoginOnlyArmsNaturalReturn() {
        assertEquals(
            JinhakUserSessionPolicy.ConfirmationDecision.ARM_AFTER_SITE_LOGIN,
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
    fun lateLoginCallbackIsIgnoredWhenHigh3IsAlreadyVisible() {
        assertTrue(
            JinhakUserSessionPolicy.shouldIgnoreStaleLoginCallback(
                "https://www.jinhak.com/jh/member/login",
                "https://www.jinhak.com/jh/high3/early/four-year-university/search"
            )
        )
        assertFalse(
            JinhakUserSessionPolicy.shouldIgnoreStaleLoginCallback(
                "https://www.jinhak.com/jh/member/login",
                "https://www.jinhak.com/jh/member/login"
            )
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
