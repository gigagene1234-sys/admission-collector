package com.admissionhub.collector.canonical

import org.json.JSONArray
import org.json.JSONObject

/**
 * Converts conservative Adiga binding records into application-specific diagnostics.
 * Direct current binding remains restricted to same-row / explicit same-table scope.
 * Separately, the UI can now state when the current admission track and recruitment unit are each
 * officially verified, and can expose a directly bound historical result row without pretending
 * that those facts are the same thing.
 */
object AdigaApplicationEvidenceAnalyzer {
    const val SCHEMA_VERSION = 2

    fun analyze(candidate: JSONObject): JSONObject {
        val binding = candidate.optJSONObject("adigaBinding") ?: JSONObject()
        val evidence = binding.optJSONArray("officialAdmissionEvidence") ?: JSONArray()
        val matches = binding.optJSONArray("matches") ?: JSONArray()
        val academicYear = candidate.optInt("academicYear", 0)

        val currentBound = JSONArray()
        val historicalBound = JSONArray()
        val historicalOutcomes = JSONArray()
        val universityCurrent = JSONArray()
        val historicalCandidates = JSONArray()
        var departmentCandidate = false
        var exactAdmissionCandidate = false
        var relatedAdmissionCandidate = false

        for (i in 0 until matches.length()) {
            val match = matches.optJSONObject(i) ?: continue
            if (match.optString("departmentMatch") in setOf("exact", "suffix-equivalent")) departmentCandidate = true
            if (match.optString("admissionMatch") == "exact") exactAdmissionCandidate = true
            if (match.optString("admissionMatch") in setOf("exact", "related")) relatedAdmissionCandidate = true
        }

        for (i in 0 until evidence.length()) {
            val row = evidence.optJSONObject(i) ?: continue
            val recordYear = row.optInt("recordYear", 0)
            val dept = row.optString("departmentMatch")
            val admission = row.optString("admissionMatch")
            val scope = row.optString("scope")
            if (dept in setOf("exact", "suffix-equivalent")) departmentCandidate = true
            if (admission == "exact") exactAdmissionCandidate = true
            if (admission in setOf("exact", "related")) relatedAdmissionCandidate = true

            val directlyBound = dept in setOf("exact", "suffix-equivalent") && admission == "exact" &&
                scope in setOf("row-bound-current", "table-segment-current", "historical", "table-segment-historical")
            when {
                directlyBound && recordYear == academicYear && scope in setOf("row-bound-current", "table-segment-current") -> currentBound.put(compact(row))
                directlyBound && recordYear in 2000 until academicYear -> {
                    val compact = compact(row)
                    row.optJSONObject("historicalOutcome")?.let { compact.put("historicalOutcome", JSONObject(it.toString())); historicalOutcomes.put(JSONObject(it.toString()).put("sourcePage", row.optString("sourcePage"))) }
                    historicalBound.put(compact)
                }
                recordYear == academicYear || scope == "university-current" -> universityCurrent.put(compact(row))
                recordYear in 2000 until academicYear -> historicalCandidates.put(compact(row))
            }
        }

        val officialUniversityCurrentCount = maxOf(binding.optInt("officialUniversityCurrent", 0), universityCurrent.length())
        val accepted = binding.optInt("acceptedSignatures", 0)
        val provisional = binding.optInt("provisionalSignatures", 0)
        val currentComponentsVerified = officialUniversityCurrentCount > 0 && departmentCandidate && exactAdmissionCandidate
        val missing = JSONArray()
        val facts = JSONArray()

        if (officialUniversityCurrentCount > 0) facts.put("지원년도 대학 공식자료 ${officialUniversityCurrentCount}건이 수집되어 있습니다.")
        else missing.put("지원년도 대학 공식자료")

        if (departmentCandidate) facts.put("선택 모집단위가 어디가의 지원년도 대학 모집단위 자료에서 확인됩니다.")
        else missing.put("선택 모집단위와 연결되는 공식 모집단위 자료")

        if (exactAdmissionCandidate) facts.put("선택 전형명과 직접 일치하는 지원년도 공식 전형 표기가 확인됩니다.")
        else if (relatedAdmissionCandidate) missing.put("선택 전형명과 정확 일치하는 공식 전형 표기")
        else missing.put("선택 전형을 식별할 수 있는 공식 전형 표기")

        if (currentBound.length() == 0) {
            if (currentComponentsVerified) missing.put("지원년도에서 전형과 모집단위를 한 행/명시적 표 구간으로 묶는 직접 결합표")
            else missing.put("지원년도에서 전형과 모집단위를 동시에 확인할 수 있는 직접 근거")
        } else facts.put("지원년도 전형·모집단위 직접 결합 근거 ${currentBound.length()}건이 있습니다.")

        if (historicalBound.length() == 0) missing.put("과거 입결에서 전형과 모집단위를 동시에 묶는 공식 행")
        else facts.put("과거 동일 전형·모집단위 직접 연결 근거 ${historicalBound.length()}건이 있습니다.")
        if (historicalOutcomes.length() > 0) facts.put("표 머리글까지 검증해 읽어낸 공식 과거 입결 행 ${historicalOutcomes.length()}건이 있습니다.")

        val code = when {
            currentBound.length() > 0 && historicalBound.length() > 0 -> "BOUND_CURRENT_AND_HISTORICAL"
            currentBound.length() > 0 -> "BOUND_CURRENT_ONLY"
            currentComponentsVerified && historicalBound.length() > 0 -> "CURRENT_COMPONENTS_AND_HISTORICAL_BOUND"
            currentComponentsVerified -> "CURRENT_COMPONENTS_VERIFIED"
            officialUniversityCurrentCount == 0 -> "NO_CURRENT_UNIVERSITY_EVIDENCE"
            departmentCandidate -> "DEPARTMENT_FOUND_ADMISSION_MISSING"
            exactAdmissionCandidate -> "ADMISSION_FOUND_DEPARTMENT_MISSING"
            else -> "UNIVERSITY_ONLY"
        }
        val label = when (code) {
            "BOUND_CURRENT_AND_HISTORICAL" -> "어디가: 현재 전형·모집단위 직접 연결 + 과거 동일 입결 확인"
            "BOUND_CURRENT_ONLY" -> "어디가: 현재 전형·모집단위 직접 연결 확인 · 비교 가능한 과거 행 없음"
            "CURRENT_COMPONENTS_AND_HISTORICAL_BOUND" -> "어디가: 2027 전형·모집단위 각각 공식 확인 + 과거 동일 조합 입결 확인"
            "CURRENT_COMPONENTS_VERIFIED" -> "어디가: 2027 전형·모집단위 각각 공식 확인 · 사이트 표 구조상 직접 결합표는 없음"
            "NO_CURRENT_UNIVERSITY_EVIDENCE" -> "어디가: 지원년도 대학 공식자료 자체가 확인되지 않음"
            "DEPARTMENT_FOUND_ADMISSION_MISSING" -> "어디가: 모집단위는 확인 · 선택 전형명 정확 일치 근거 없음"
            "ADMISSION_FOUND_DEPARTMENT_MISSING" -> "어디가: 전형은 확인 · 선택 모집단위 정확 연결 근거 없음"
            else -> "어디가: 대학 공식자료 있음 · 선택 모집단위/전형 조합 식별 부족"
        }
        val nextAction = when (code) {
            "BOUND_CURRENT_AND_HISTORICAL" -> "직접 연결된 현재 규칙과 과거 입결의 지표·산식·척도를 확인해 비교합니다."
            "BOUND_CURRENT_ONLY" -> "현재 전형 기준은 직접 연결되었습니다. 동일 모집단위·전형의 과거 입결 행이 있으면 추가 비교할 수 있습니다."
            "CURRENT_COMPONENTS_AND_HISTORICAL_BOUND" -> "지원년도에는 전형표와 모집단위표가 분리되어 있어 임의로 한 행으로 합치지 않습니다. 다만 전형과 모집단위는 각각 공식 확인되었고, 과거 동일 조합 입결 행은 별도로 직접 확인되었습니다."
            "CURRENT_COMPONENTS_VERIFIED" -> "지원년도 전형표와 모집단위표가 분리되어 있습니다. 둘은 각각 공식 확인되었지만 조합을 명시한 같은 행이 없어 직접결합으로 승격하지 않습니다."
            "DEPARTMENT_FOUND_ADMISSION_MISSING" -> "모집단위는 공식 확인되었으나 선택 전형명이 정확히 확인되는 지원년도 표가 더 필요합니다."
            "ADMISSION_FOUND_DEPARTMENT_MISSING" -> "전형은 공식 확인되었으나 선택 모집단위를 특정할 공식 근거가 더 필요합니다."
            "NO_CURRENT_UNIVERSITY_EVIDENCE" -> "지원년도 공식 모집요강·어디가 자료 수집 상태를 먼저 확인하세요."
            else -> "대학 단위 자료를 이 원서의 입결로 간주하지 않습니다. 모집단위 식별을 먼저 확정해야 합니다."
        }

        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("code", code)
            .put("label", label)
            .put("nextAction", nextAction)
            .put("academicYear", academicYear)
            .put("officialUniversityCurrentCount", officialUniversityCurrentCount)
            .put("acceptedSignatures", accepted)
            .put("provisionalSignatures", provisional)
            .put("departmentCandidate", departmentCandidate)
            .put("exactAdmissionCandidate", exactAdmissionCandidate)
            .put("currentComponentsVerified", currentComponentsVerified)
            .put("currentApplicationBoundCount", currentBound.length())
            .put("historicalApplicationBoundCount", historicalBound.length())
            .put("historicalOutcomeCount", historicalOutcomes.length())
            .put("currentApplicationBoundEvidence", currentBound)
            .put("historicalApplicationBoundEvidence", historicalBound)
            .put("historicalOutcomes", historicalOutcomes)
            .put("universityCurrentEvidenceSample", sample(universityCurrent, 8))
            .put("historicalEvidenceSample", sample(historicalCandidates, 8))
            .put("facts", facts)
            .put("missing", missing)
            .put("automaticPromotion", false)
            .put("requiresSameRowOrExplicitTableScope", true)
    }

    private fun compact(row: JSONObject): JSONObject = JSONObject()
        .put("recordType", row.optString("recordType"))
        .put("recordYear", row.optInt("recordYear", 0))
        .put("historicalResultYear", row.optInt("historicalResultYear", 0))
        .put("tableIndex", row.optInt("tableIndex", -1))
        .put("scope", row.optString("scope"))
        .put("departmentMatch", row.optString("departmentMatch"))
        .put("admissionMatch", row.optString("admissionMatch"))
        .put("sourcePage", row.optString("sourcePage"))
        .put("rowEvidence", row.optString("rowEvidence").ifBlank {
            listOf(row.optString("scopeRowEvidence"), row.optString("departmentRowEvidence"))
                .filter { it.isNotBlank() }.joinToString(" | ")
        }.take(1800))

    private fun sample(source: JSONArray, limit: Int): JSONArray = JSONArray().also { out ->
        for (i in 0 until minOf(source.length(), limit)) out.put(source.optJSONObject(i))
    }
}
