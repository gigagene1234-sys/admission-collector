package com.admissionhub.collector.sync

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalRebindPolicyTest {
    @Test fun sixPinnedAndOlderReusableGraphSuppressesEmptyInterruptedRun() {
        val input = LocalRebindPolicy.Input(6, 27, 0, "running", false)
        assertTrue(LocalRebindPolicy.preferLocalRebind(input))
        assertTrue(LocalRebindPolicy.suppressInterruptedBrowserResume(input))
    }

    @Test fun noReusableGraphDoesNotSuppressResume() {
        val input = LocalRebindPolicy.Input(6, 0, 0, "running", false)
        assertFalse(LocalRebindPolicy.preferLocalRebind(input))
        assertFalse(LocalRebindPolicy.suppressInterruptedBrowserResume(input))
    }

    @Test fun sameActiveReusableSessionKeepsProcessDeathResume() {
        val input = LocalRebindPolicy.Input(6, 27, 27, "running", true)
        assertTrue(LocalRebindPolicy.preferLocalRebind(input))
        assertFalse(LocalRebindPolicy.suppressInterruptedBrowserResume(input))
    }

    @Test fun fewerThanSixPinnedDoesNotTakeOverLaunch() {
        val input = LocalRebindPolicy.Input(5, 27, 0, "running", false)
        assertFalse(LocalRebindPolicy.preferLocalRebind(input))
        assertFalse(LocalRebindPolicy.suppressInterruptedBrowserResume(input))
    }
}
