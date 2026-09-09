package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakProtectedSessionPolicyTest {
    @Test fun publicSearchIsNotAuthProof() {
        assertFalse(JinhakProtectedSessionPolicy.isProtectedProofUrl(
            "https://www.jinhak.com/jh/high3/early/four-year-university/search"
        ))
    }

    @Test fun strategyIsNotAuthProof() {
        assertFalse(JinhakProtectedSessionPolicy.isProtectedProofUrl(
            "https://www.jinhak.com/jh/high3/ipsi-analysis/ipsi-strategy"
        ))
    }

    @Test fun savedApplicationLibraryIsProtectedProof() {
        assertTrue(JinhakProtectedSessionPolicy.isProtectedProofUrl(
            "https://www.jinhak.com/jh/high3/early/four-year-university/library"
        ))
    }

    @Test fun reportIsProtectedProof() {
        assertTrue(JinhakProtectedSessionPolicy.isProtectedProofUrl(
            "https://www.jinhak.com/jh/high3/early/four-year-university/report/pass-predict?id=1"
        ))
    }

    @Test fun stallFenceRequiresVerifiedMissionTargets() {
        assertFalse(JinhakProtectedSessionPolicy.shouldRunMissionStallFence(false, 6))
        assertFalse(JinhakProtectedSessionPolicy.shouldRunMissionStallFence(true, 0))
        assertTrue(JinhakProtectedSessionPolicy.shouldRunMissionStallFence(true, 1))
    }
}
