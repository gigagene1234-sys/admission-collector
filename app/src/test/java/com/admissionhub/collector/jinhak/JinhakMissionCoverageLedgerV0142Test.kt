package com.admissionhub.collector.jinhak

import org.junit.Assert.*
import org.junit.Test

class JinhakMissionCoverageLedgerV0142Test {
    private val identity = "application-1"

    @Test fun firstFiveLanesNoLongerCloseIntegratedCollection() {
        val ledger = JinhakMissionCoverageLedger()
        listOf("saved-application", "current-prediction", "mock-support", "actual-admit", "score-analysis")
            .forEach { ledger.confirm(identity, it, "test") }

        val summary = ledger.summary(setOf(identity))
        assertFalse(summary.getBoolean("coreComplete"))
        assertEquals(1, summary.getJSONObject("missingByLane").getInt("university-result"))
        assertEquals(0, summary.getJSONObject("laneCoverage").getInt("university-result"))
    }

    @Test fun universityResultCompletesCoreWithoutOptionalStrategy() {
        val ledger = JinhakMissionCoverageLedger()
        JinhakMissionCoverageLedger.CORE_LANES.forEach { ledger.confirm(identity, it, "test") }

        val summary = ledger.summary(setOf(identity))
        assertTrue(summary.getBoolean("coreComplete"))
        assertEquals(1, summary.getInt("completeIdentities"))
        assertEquals(0, summary.getJSONObject("missingByLane").getInt("university-result"))
        assertTrue(summary.getBoolean("strategyOptional"))
        assertEquals(0, summary.getJSONObject("laneCoverage").getInt("strategy"))
    }

    @Test fun persistedRestoreAlsoRequiresUniversityResult() {
        val original = JinhakMissionCoverageLedger()
        listOf("saved-application", "current-prediction", "mock-support", "actual-admit", "score-analysis")
            .forEach { original.confirm(identity, it, "test") }
        assertFalse(original.allCoreComplete(setOf(identity)))

        original.confirm(identity, "university-result", "test")
        assertTrue(original.allCoreComplete(setOf(identity)))
    }
}
