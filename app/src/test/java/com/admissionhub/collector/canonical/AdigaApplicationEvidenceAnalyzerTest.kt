package com.admissionhub.collector.canonical

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AdigaApplicationEvidenceAnalyzerTest {
    private fun candidate(evidence: JSONArray = JSONArray(), matches: JSONArray = JSONArray(), universityCurrent: Int = 1): JSONObject =
        JSONObject()
            .put("academicYear", 2027)
            .put("university", "테스트대")
            .put("department", "철도공학과")
            .put("admission", "지역인재교과")
            .put("adigaBinding", JSONObject()
                .put("officialUniversityCurrent", universityCurrent)
                .put("acceptedSignatures", 0)
                .put("provisionalSignatures", 1)
                .put("officialAdmissionEvidence", evidence)
                .put("matches", matches))

    private fun row(year: Int, scope: String, dept: String, admission: String, text: String = "근거"): JSONObject =
        JSONObject().put("recordType", if (year == 2027) "current-admission-criteria-table" else "historical-admission-result-table")
            .put("recordYear", year).put("scope", scope).put("departmentMatch", dept).put("admissionMatch", admission)
            .put("rowEvidence", text).put("sourcePage", "https://www.adiga.kr/example")

    @Test fun exactCurrentAndHistoricalRowsAreDirectlyBound() {
        val ev = JSONArray()
            .put(row(2027, "row-bound-current", "exact", "exact"))
            .put(row(2026, "historical", "suffix-equivalent", "exact"))
        val out = AdigaApplicationEvidenceAnalyzer.analyze(candidate(ev))
        assertEquals("BOUND_CURRENT_AND_HISTORICAL", out.getString("code"))
        assertEquals(1, out.getInt("currentApplicationBoundCount"))
        assertEquals(1, out.getInt("historicalApplicationBoundCount"))
        assertFalse(out.getBoolean("automaticPromotion"))
    }

    @Test fun departmentSummaryWithoutAdmissionExplainsMissingAdmissionBinding() {
        val matches = JSONArray().put(JSONObject()
            .put("departmentMatch", "suffix-equivalent").put("admissionMatch", "missing"))
        val ev = JSONArray().put(row(2027, "university-current", "none", "related", "학생부교과 공통"))
        val out = AdigaApplicationEvidenceAnalyzer.analyze(candidate(ev, matches, 12))
        assertEquals("DEPARTMENT_FOUND_ADMISSION_MISSING", out.getString("code"))
        assertTrue(out.getString("label").contains("전형"))
        assertEquals(0, out.getInt("currentApplicationBoundCount"))
    }

    @Test fun admissionMentionWithoutDepartmentIsNotPromoted() {
        val ev = JSONArray().put(row(2027, "university-current", "none", "exact", "지역인재교과 공통 기준"))
        val out = AdigaApplicationEvidenceAnalyzer.analyze(candidate(ev))
        assertEquals("ADMISSION_FOUND_DEPARTMENT_MISSING", out.getString("code"))
        assertEquals(0, out.getInt("currentApplicationBoundCount"))
        assertTrue(out.getJSONArray("missing").toString().contains("모집단위"))
    }

    @Test fun universityOnlyEvidenceStaysUniversityOnly() {
        val ev = JSONArray().put(row(2027, "university-current", "none", "category-only", "학생부교과 공통"))
        val out = AdigaApplicationEvidenceAnalyzer.analyze(candidate(ev))
        assertEquals("UNIVERSITY_ONLY", out.getString("code"))
        assertEquals(0, out.getInt("historicalApplicationBoundCount"))
    }

    @Test fun noCurrentUniversityEvidenceIsExplicit() {
        val out = AdigaApplicationEvidenceAnalyzer.analyze(candidate(universityCurrent = 0))
        assertEquals("NO_CURRENT_UNIVERSITY_EVIDENCE", out.getString("code"))
        assertTrue(out.getJSONArray("missing").toString().contains("지원년도 대학 공식자료"))
    }

    @Test fun historicalRowWithWrongAdmissionIsNotDirectlyBound() {
        val ev = JSONArray().put(row(2026, "historical", "exact", "related", "과거 다른 전형"))
        val matches = JSONArray().put(JSONObject().put("departmentMatch", "exact").put("admissionMatch", "missing"))
        val out = AdigaApplicationEvidenceAnalyzer.analyze(candidate(ev, matches))
        assertEquals(0, out.getInt("historicalApplicationBoundCount"))
        assertTrue(out.getJSONArray("missing").toString().contains("과거 입결"))
    }

    @Test fun authoritativeHistoricalSegmentCountSurvivesBoundedSampleTruncation() {
        val matches = JSONArray().put(JSONObject().put("departmentMatch", "exact").put("admissionMatch", "missing"))
        val ev = JSONArray().put(row(2027, "university-current", "none", "exact", "지역인재교과"))
        val c = candidate(ev, matches, 59)
        c.getJSONObject("adigaBinding").put("officialTableSegmentHistorical", 1)
        val out = AdigaApplicationEvidenceAnalyzer.analyze(c)
        assertEquals("CURRENT_COMPONENTS_AND_HISTORICAL_BOUND", out.getString("code"))
        assertEquals(1, out.getInt("historicalApplicationBoundCount"))
        assertTrue(out.getBoolean("boundedEvidenceSampleTruncated"))
        assertTrue(out.getString("label").contains("과거 동일 조합 입결"))
    }
}
