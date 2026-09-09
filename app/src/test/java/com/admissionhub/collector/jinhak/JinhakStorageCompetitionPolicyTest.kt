package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakStorageCompetitionPolicyTest {
    @Test
    fun acceptsOnlyExactProtectedStorageRoute() {
        assertTrue(JinhakStorageCompetitionPolicy.isStorageUrl("https://www.jinhak.com/jh/high3/early/four-year-university/library"))
        assertTrue(JinhakStorageCompetitionPolicy.isStorageUrl("https://www.jinhak.com/jh/high3/early/four-year-university/library/"))
        assertFalse(JinhakStorageCompetitionPolicy.isStorageUrl("https://www.jinhak.com/jh/high3/early/four-year-university/search"))
        assertFalse(JinhakStorageCompetitionPolicy.isStorageUrl("https://www.jinhak.com/jh/high3/early/four-year-university/report/pass-predict"))
    }

    @Test
    fun extractsExplicitCurrentCompetition() {
        val reading = JinhakStorageCompetitionPolicy.readCompetition("현재 경쟁률 4.25 : 1")
        assertEquals(4.25, reading.currentApplicationCompetition!!, 0.0001)
        assertEquals(4.25, reading.displayedCompetition!!, 0.0001)
        assertTrue(reading.currentSemanticsVerified)
    }

    @Test
    fun doesNotPromoteMockOrHistoricalCompetitionToCurrent() {
        val mock = JinhakStorageCompetitionPolicy.readCompetition("모의지원 경쟁률 8.1 : 1")
        assertNull(mock.currentApplicationCompetition)
        assertNull(mock.displayedCompetition)

        val historical = JinhakStorageCompetitionPolicy.readCompetition("2026학년도 경쟁률 5.2 : 1")
        assertNull(historical.currentApplicationCompetition)
        assertNull(historical.displayedCompetition)
    }

    @Test
    fun preservesUnqualifiedDisplayedCompetitionWithoutCallingItCurrent() {
        val reading = JinhakStorageCompetitionPolicy.readCompetition("경쟁률 3.7 : 1")
        assertNull(reading.currentApplicationCompetition)
        assertEquals(3.7, reading.displayedCompetition!!, 0.0001)
        assertFalse(reading.currentSemanticsVerified)
    }
}
