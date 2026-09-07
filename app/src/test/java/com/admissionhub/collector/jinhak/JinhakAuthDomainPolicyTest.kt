package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakAuthDomainPolicyTest {
    @Test fun secondRedirectWithFreshCoreQuarantinesTarget() {
        assertEquals(
            JinhakAuthDomainPolicy.RedirectDecision.TARGET_QUARANTINE,
            JinhakAuthDomainPolicy.redirectDecision(2, 2, true)
        )
    }

    @Test fun firstRedirectStillRevalidatesGlobalAuth() {
        assertEquals(
            JinhakAuthDomainPolicy.RedirectDecision.GLOBAL_REAUTH,
            JinhakAuthDomainPolicy.redirectDecision(1, 2, true)
        )
    }

    @Test fun staleCoreProofCannotFastQuarantine() {
        assertEquals(
            JinhakAuthDomainPolicy.RedirectDecision.GLOBAL_REAUTH,
            JinhakAuthDomainPolicy.redirectDecision(2, 2, false)
        )
    }

    @Test fun reportActionWithoutLedgerIdPreservesMissionOwner() {
        assertEquals("mission-17", JinhakAuthDomainPolicy.preserveMissionOwner("mission-17", null))
        assertEquals("mission-18", JinhakAuthDomainPolicy.preserveMissionOwner("mission-17", "mission-18"))
    }

    @Test fun genericNavigationBlockedWhileMissionOutstanding() {
        assertFalse(JinhakAuthDomainPolicy.allowGenericNavigation(2))
        assertTrue(JinhakAuthDomainPolicy.allowGenericNavigation(0))
    }
}
