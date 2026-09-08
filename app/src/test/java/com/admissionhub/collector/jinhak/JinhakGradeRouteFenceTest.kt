package com.admissionhub.collector.jinhak

import org.junit.Assert.*
import org.junit.Test

class JinhakGradeRouteFenceTest {
    @Test
    fun high1High2AndHigh12AreBlocked() {
        assertTrue(JinhakGradeRouteFence.isBlockedLowerGrade("https://www.jinhak.com/jh/high1/home"))
        assertTrue(JinhakGradeRouteFence.isBlockedLowerGrade("https://www.jinhak.com/jh/high2/early/search"))
        assertTrue(JinhakGradeRouteFence.isBlockedLowerGrade("https://www.jinhak.com/jh/high12/main"))
    }

    @Test
    fun high3AndLoginRemainAllowed() {
        assertFalse(JinhakGradeRouteFence.isBlockedLowerGrade("https://www.jinhak.com/jh/high3/early/four-year-university/library"))
        assertFalse(JinhakGradeRouteFence.isBlockedLowerGrade("https://www.jinhak.com/jh/member/login"))
        assertTrue(JinhakGradeRouteFence.isHigh3("https://www.jinhak.com/jh/high3/early/four-year-university/library"))
    }

    @Test
    fun protectedCoreIsAlwaysHigh3() {
        val core = JinhakGradeRouteFence.protectedHigh3Core()
        assertTrue(core.isNotBlank())
        assertTrue(JinhakGradeRouteFence.isHigh3(core))
        assertFalse(JinhakGradeRouteFence.isBlockedLowerGrade(core))
    }
}
