package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakMissionCellSupervisorLeaseTest {
    @Test fun actionLeaseExpiresAtItsOwnDeadlineIndependentOfParentProgress() {
        val supervisor = JinhakMissionCellSupervisor(staleOwnershipMs = 1_000L)
        supervisor.beginAction("target-a", "safe/path", "report-lane", nowMs = 1_000L)
        val early = supervisor.expireStaleOwnership(nowMs = 1_999L)
        assertFalse(early.actionExpired)
        assertTrue(supervisor.isActionActive())
        val expired = supervisor.expireStaleOwnership(nowMs = 2_000L)
        assertTrue(expired.actionExpired)
        assertFalse(supervisor.isActionActive())
    }

    @Test fun expiredLeaseRejectsLateCallbackGeneration() {
        val supervisor = JinhakMissionCellSupervisor(staleOwnershipMs = 1_000L)
        val token = supervisor.beginAction("target-a", "safe/path", "report-lane", nowMs = 2_000L)
        supervisor.expireStaleOwnership(nowMs = 3_000L)
        assertFalse(supervisor.finishAction(token, true, "late", nowMs = 3_001L))
    }
}
