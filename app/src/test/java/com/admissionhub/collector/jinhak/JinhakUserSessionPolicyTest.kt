package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class JinhakUserSessionPolicyTest {
    @Test
    fun loginSurfacesAlwaysReturnControlToUser() {
        val urls = listOf(
            "https://www.jinhak.com/jh/member/login",
            "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx"
        )
        urls.forEach { url ->
            assertEquals(
                JinhakUserSessionPolicy.NavigationDecision.PAUSE_FOR_USER_SESSION,
                JinhakUserSessionPolicy.decision(url)
            )
        }
    }

    @Test
    fun normalHigh3RoutesAreAllowedUnderUserLoginAssumption() {
        val url = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        assertEquals(
            JinhakUserSessionPolicy.NavigationDecision.ALLOW_ASSUMING_USER_LOGIN,
            JinhakUserSessionPolicy.decision(url)
        )
    }

    @Test
    fun lowerGradeRoutesRemainTransportBlocked() {
        val url = "https://www.jinhak.com/jh/high2/early"
        assertEquals(
            JinhakUserSessionPolicy.NavigationDecision.DROP_LOWER_GRADE,
            JinhakUserSessionPolicy.decision(url)
        )
    }

    @Test
    fun collectorOwnsNoneOfJinhakAuthenticationLifecycle() {
        assertFalse(JinhakUserSessionPolicy.collectorMayVerifyLogin())
        assertFalse(JinhakUserSessionPolicy.collectorMayReadCredentials())
        assertFalse(JinhakUserSessionPolicy.collectorMaySubmitCredentials())
        assertFalse(JinhakUserSessionPolicy.collectorMayRestoreJinhakAuthLease())
        assertFalse(JinhakUserSessionPolicy.collectorMayCaptureJinhakAuthLease())
        assertFalse(JinhakUserSessionPolicy.collectorMayExtendJinhakSession())
        assertFalse(JinhakUserSessionPolicy.collectorMayConstructLoginNavigation())
    }
}
