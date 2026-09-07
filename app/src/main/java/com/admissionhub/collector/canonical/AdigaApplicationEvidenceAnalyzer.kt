package com.admissionhub.collector.canonical

import org.json.JSONArray
import org.json.JSONObject

/**
 * Converts the conservative Adiga binding record into user-facing, application-specific diagnostics.
 *
 * This object never upgrades university-wide evidence into application evidence. A row is considered
 * directly bound only when the persisted binding already proves both the recruitment unit and the
 * admission track in the same row / explicit same-table segment.
 */
object AdigaApplicationEvidenceAnalyzer {
    const val SCHEMA_VERSION = 1

    fun analyze(candidate: JSONObject): JSONObject {
        val binding = candidate.optJSONObject("adigaBinding") ?: JSONObject()
        val evidence = binding.optJSONArray("officialAdmissionEvidence") ?: JSONArray()
        val matches = binding.optJSONArray("matches") ?: JSONArray()
        val academicYear = candidate.optInt("academicYear", 0)

        val currentBound = JSONArray()
        val historicalBound = JSONArray()
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
                directlyBound && recordYear in 2000 until academicYear -> historicalBound.put(compact(row))
                recordYear == academicYear || scope == "university-current" -> universityCurrent.put(compact(row))
                recordYear in 2000 until academicYear -> historicalCandidates.put(compact(row))
            }
        }

        val officialUniversityCurrentCount = maxOf(binding.optInt("officialUniversityCurrent", 0), universityCurrent.length())
        val accepted = binding.optInt("acceptedSignatures", 0)
        val provisional = binding.optInt("provisionalSignatures", 0)
        val missing = JSONArray()
        val facts = JSONArray()

        if (officialUniversityCurrentCount > 0) facts.put("지원년도 대학 공식자료 ${officialUniversityCurrentCount}건이 수집되어 있습니다.")
        else missing.put("지원년도 대학 공식자료")

        if (departmentCandidate) facts.put("모집단위명과 일치하거나 학과·학부 접미어만 다른 후보가 있습니다.")
        else missing.put("선택한 모집단위와 연결되는 공식 행 또는 모집단위 요약")

        if (exactAdmissionCandidate) facts.put("선택 전형명과 정확 일치하는 전형 표기가 공식자료 안에서 확인됩니다.")
        else if (relatedAdmissionCandidate) missing.put("선택 전형명과 정확 일치하는 전형 표기")
        else missing.put("선택 전형을 식별할 수 있는 공식 전형 표기")

        if (currentBound.length() == 0) missing.put("지원년도에서 전형과 모집단위를 동시에 묶는 같은 행·명시적 표 구간")
        else facts.put("지원년도 직접 연결 근거 ${currentBound.length()}건이 있습니다.")

        if (historicalBound.length() == 0) missing.put("과거 입결에서 전형과 모집단위를 동시에 묶는 공식 행")
        else facts.put("과거 입결 직접 연결 근거 ${historicalBound.length()}건이 있습니다.")

        val code = when {
            currentBound.length() > 0 && historicalBound.length() > 0 -> "BOUND_CURRENT_AND_HISTORICAL"
            currentBound.length() > 0 -> "BOUND_CURRENT_ONLY"
            officialUniversityCurrentCount == 0 -> "NO_CURRENT_UNIVERSITY_EVIDENCE"
            departmentCandidate && exactAdmissionCandidate -> "SAME_ROW_BINDING_MISSING"
            departmentCandidate -> "DEPARTMENT_FOUND_ADMISSION_MISSING"
            exactAdmissionCandidate -> "ADMISSION_FOUND_DEPARTMENT_MISSING"
            else -> "UNIVERSITY_ONLY"
        }
        val label = when (code) {
            "BOUND_CURRENT_AND_HISTORICAL" -> "어디가: 현재 전형·모집단위와 과거 입결 직접 연결 확인"
            "BOUND_CURRENT_ONLY" -> "어디가: 현재 전형·모집단위 연결 확인 · 과거 입결 직접행 미확인"
            "NO_CURRENT_UNIVERSITY_EVIDENCE" -> "어디가: 지원년도 대학 공식자료 자체가 확인되지 않음"
            "DEPARTMENT_FOUND_ADMISSION_MISSING" -> "어디가: 모집단위 후보 확인 · 전형 결합 근거 없음"
            "ADMISSION_FOUND_DEPARTMENT_MISSING" -> "어디가: 전형 표기 확인 · 모집단위 결합 근거 없음"
            "SAME_ROW_BINDING_MISSING" -> "어디가: 전형·모집단위 각각 확인 · 같은 공식 행/구간 결합은 미확인"
            else -> "어디가: 대학 공식자료 있음 · 선택 모집단위·전형 직접 연결 근거 없음"
        }
        val nextAction = when (code) {
            "BOUND_CURRENT_AND_HISTORICAL" -> "직접 연결된 원문에서 지표명·값·산식이 같은 척도인지 확인하세요. 자동 합격판정에는 사용하지 않습니다."
            "BOUND_CURRENT_ONLY" -> "현재 전형 기준은 연결되었지만 비교 가능한 과거 입결의 동일 모집단위·전형 행이 더 필요합니다."
            "DEPARTMENT_FOUND_ADMISSION_MISSING" -> "모집단위 후보는 있으나 해당 행에 선택 전형명이 없습니다. 전형명이 명시된 동일 모집단위 공식 행이 필요합니다."
            "ADMISSION_FOUND_DEPARTMENT_MISSING" -> "전형 정보는 있으나 선택 모집단위가 같은 행/명시적 표 구간에 없습니다. 모집단위 연결 근거가 필요합니다."
            "SAME_ROW_BINDING_MISSING" -> "전형명과 모집단위가 서로 다른 공식 행에만 있어 자동 결합하지 않습니다. 같은 행 또는 명시적 표 구간 근거가 필요합니다."
            "NO_CURRENT_UNIVERSITY_EVIDENCE" -> "지원년도 공식 모집요강·어디가 자료 수집 상태를 먼저 확인하세요."
            else -> "대학 단위 자료를 이 원서의 입결로 간주하지 않습니다. 같은 전형·모집단위가 명시된 공식 행이 필요합니다."
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
            .put("currentApplicationBoundCount", currentBound.length())
            .put("historicalApplicationBoundCount", historicalBound.length())
            .put("currentApplicationBoundEvidence", currentBound)
            .put("historicalApplicationBoundEvidence", historicalBound)
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
        .put("scope", row.optString("scope"))
        .put("departmentMatch", row.optString("departmentMatch"))
        .put("admissionMatch", row.optString("admissionMatch"))
        .put("sourcePage", row.optString("sourcePage"))
        .put("rowEvidence", row.optString("rowEvidence").ifBlank {
            listOf(row.optString("scopeRowEvidence"), row.optString("departmentRowEvidence"))
                .filter { it.isNotBlank() }.joinToString(" | ")
        }.take(1600))

    private fun sample(source: JSONArray, limit: Int): JSONArray = JSONArray().also { out ->
        for (i in 0 until minOf(source.length(), limit)) out.put(source.optJSONObject(i))
    }
}
