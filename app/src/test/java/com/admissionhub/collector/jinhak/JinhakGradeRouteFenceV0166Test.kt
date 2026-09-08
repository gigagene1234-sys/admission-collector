package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakGradeRouteFenceV0166Test {
    @Test
    fun nestedEncodedLowerGradeReturnTargetsAreBlocked() {
        assertTrue(
            JinhakGradeRouteFence.isBlockedLowerGrade(
                "https://www.jinhak.com/jh/member/login?returnUrl=%252Fjh%252Fhigh2%252Fearly%252Fsearch"
            )
        )
        assertTrue(
            JinhakGradeRouteFence.isBlockedLowerGrade(
                "https://www.jinhak.com/jh/member/login?next=%25252Fjh%25252Fhigh1%25252Fhome"
            )
        )
    }

    @Test
    fun high3AndUnclassifiedHigh3RoutesRemainAllowed() {
        assertFalse(
            JinhakGradeRouteFence.isBlockedLowerGrade(
                "https://www.jinhak.com/jh/high3/new-unclassified/page"
            )
        )
        assertFalse(
            JinhakGradeRouteFence.isBlockedLowerGrade(
                "https://www.jinhak.com/jh/member/login?returnUrl=%2Fjh%2Fhigh3%2Fnew-unclassified%2Fpage"
            )
        )
    }
}
