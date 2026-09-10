package com.admissionhub.collector.competition

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompetitionBrowserPolicyTest {
    @Test
    fun `targets are exactly the four jinhak competition pages`() {
        assertEquals(listOf("knut", "hanbat", "hannam", "kongju"), CompetitionBrowserPolicy.targets.map { it.id })
        assertTrue(CompetitionBrowserPolicy.targets.all { it.sourceUrl.startsWith("https://addon.jinhakapply.com/") })
        assertTrue(CompetitionBrowserPolicy.targets.all { it.refreshMinutes == 10 })
    }

    @Test
    fun `scheduled check runs one minute after ten minute source boundary`() {
        val base = 100L * 60_000L
        assertFalse(CompetitionBrowserPolicy.isDue(base))
        assertTrue(CompetitionBrowserPolicy.isDue(base + 60_000L))
        assertFalse(CompetitionBrowserPolicy.isDue(base + 2L * 60_000L))
        assertTrue(CompetitionBrowserPolicy.isDue(base + 11L * 60_000L))
    }
}
