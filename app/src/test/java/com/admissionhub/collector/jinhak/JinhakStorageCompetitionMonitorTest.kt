package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakStorageCompetitionMonitorTest {
    @Test fun explicitCurrentRatioIsAccepted() {
        val metric = JinhakStorageCompetitionMonitor.extract("현재 경쟁률 8.25 : 1 전년도 경쟁률 6.4 : 1")
        assertEquals(8.25, metric.currentApplicationCompetition!!, 0.0001)
        assertEquals("explicit-current-competition-label", metric.currentSource)
        assertEquals(6.4, metric.previousYearCompetition!!, 0.0001)
        assertFalse(metric.hasAmbiguity)
    }

    @Test fun mockAndPreviousAreNeverPromotedToCurrent() {
        val metric = JinhakStorageCompetitionMonitor.extract("전년도 수시 경쟁률 5.2 : 1 모의지원 경쟁률 7.8 : 1")
        assertNull(metric.currentApplicationCompetition)
        assertEquals(5.2, metric.previousYearCompetition!!, 0.0001)
        assertEquals(7.8, metric.mockCompetition!!, 0.0001)
    }

    @Test fun genericCompetitionRemainsUnresolved() {
        val metric = JinhakStorageCompetitionMonitor.extract("경쟁률 9.1 : 1")
        assertNull(metric.currentApplicationCompetition)
        assertEquals(9.1, metric.ambiguousGenericCompetition!!, 0.0001)
        assertTrue(metric.hasAmbiguity)
    }

    @Test fun sameCardExplicitCountsMayDeriveRatio() {
        val metric = JinhakStorageCompetitionMonitor.extract("현재 지원자수 75 모집인원 10")
        assertEquals(7.5, metric.currentApplicationCompetition!!, 0.0001)
        assertEquals("derived-explicit-current-applicants-and-capacity", metric.currentSource)
        assertTrue(metric.derivedFromExplicitCounts)
    }
}
