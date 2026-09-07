package com.admissionhub.collector.canonical

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AdigaOfficialTableBindingPolicyTest {
    @Test fun explicitScopeHeaderBindsDepartmentInsideSameSegment() {
        val rows = listOf(
            listOf("모집단위", "학생부교과(지역인재전형)"),
            listOf("모집인원", "경쟁률"),
            listOf("반도체시스템공학과", "21", "4.2")
        )
        val matches = AdigaOfficialTableBindingPolicy.findExplicitSegmentBindings(
            rows, "반도체시스템공", "지역인재교과", "교과"
        )
        assertEquals(1, matches.size)
        assertEquals(0, matches[0].scopeRowIndex)
        assertEquals(2, matches[0].departmentRowIndex)
        assertEquals("exact", matches[0].admissionMatch)
        assertEquals("suffix-equivalent", matches[0].departmentMatch)
    }

    @Test fun nextScopeHeaderStopsInheritance() {
        val rows = listOf(
            listOf("모집단위", "학생부교과(일반전형)"),
            listOf("기계공학과", "10"),
            listOf("모집단위", "학생부교과(지역인재전형)"),
            listOf("반도체시스템공학과", "20")
        )
        val matches = AdigaOfficialTableBindingPolicy.findExplicitSegmentBindings(
            rows, "반도체시스템공", "교과일반", "교과"
        )
        assertTrue(matches.isEmpty())
    }

    @Test fun universityWideAdmissionMentionDoesNotPropagate() {
        val rows = listOf(
            listOf("교과면접", "학생부80%", "면접20%"),
            listOf("철도차량시스템학과", "20")
        )
        assertFalse(AdigaOfficialTableBindingPolicy.isExplicitScopeDeclaration(rows[0]))
        val matches = AdigaOfficialTableBindingPolicy.findExplicitSegmentBindings(
            rows, "철도차량시스템", "교과면접", "교과"
        )
        assertTrue(matches.isEmpty())
    }

    @Test fun reorderedRegionAndCategoryTokensStillMatchExact() {
        val q = AdigaOfficialTableBindingPolicy.admissionEvidenceQuality(
            listOf("학생부교과(지역인재전형)"), "지역인재교과", "교과"
        )
        assertEquals("exact", q)
    }

    @Test fun combinedJonghapOneAndTwoIsNotExactForTwo() {
        val q = AdigaOfficialTableBindingPolicy.admissionEvidenceQuality(
            listOf("학생부종합Ⅰ학생부종합Ⅱ"), "학생부종합Ⅱ", "종합"
        )
        assertTrue(q == "related" || q == "category-only")
    }
}
