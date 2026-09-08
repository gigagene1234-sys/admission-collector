package com.admissionhub.collector.score

import com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer
import com.admissionhub.collector.canonical.AdigaFullEvidenceRescan
import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONArray
import org.json.JSONObject

/**
 * Rebuilds evidence-backed official score/result artifacts for the pinned six applications.
 * Jinhak is never required for this pass. Candidate metadata may be reused from the latest
 * canonical session, while official evidence is always rescanned from the supplied Adiga session.
 */
object AdigaAutoScoreMaterializer {
    const val SCHEMA_VERSION = 5

    fun materializeSelected(store: LocalCollectorStore, sessionId: String, profile: JSONObject = store.currentStudentScoreProfile()): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("error", "missing-session")
        val slots = store.loadHubApplicationSlots()
        val selected = (0 until slots.length()).mapNotNull { slots.optJSONObject(it)?.optString("applicationIdentityKey") }.filter { it.isNotBlank() }.distinct()

        val currentCandidates = store.loadCanonicalApplicationCandidates(sessionId)
        val byIdentity = linkedMapOf<String, JSONObject>()
        for (i in 0 until currentCandidates.length()) {
            val item = currentCandidates.optJSONObject(i) ?: continue
            item.optString("applicationIdentityKey").takeIf { it.isNotBlank() }?.let { byIdentity[it] = item }
        }

        val missingSelected = selected.filterNot(byIdentity::containsKey)
        var fallbackSessionId: String? = null
        var fallbackCandidatesUsed = 0
        if (missingSelected.isNotEmpty()) {
            fallbackSessionId = store.latestReusableCanonicalSessionId()?.takeIf { it.isNotBlank() && it != sessionId }
            if (!fallbackSessionId.isNullOrBlank()) {
                val fallback = store.loadCanonicalApplicationCandidates(fallbackSessionId)
                for (i in 0 until fallback.length()) {
                    val item = fallback.optJSONObject(i) ?: continue
                    val identity = item.optString("applicationIdentityKey")
                    if (identity in missingSelected && !byIdentity.containsKey(identity)) {
                        byIdentity[identity] = JSONObject(item.toString()).put("candidateMetadataSourceSessionId", fallbackSessionId).put("candidateMetadataFallbackOnly", true)
                        fallbackCandidatesUsed++
                    }
                }
            }
        }

        val selectedCandidates = selected.mapNotNull { byIdentity[it] }
        val fullRescan = AdigaFullEvidenceRescan.scanSelected(store, sessionId, selectedCandidates)
        val fullByIdentity = fullRescan.optJSONObject("byIdentity") ?: JSONObject()
        var conversionsVerified = 0; var conversionsHeld = 0; var historicalOutcomesStored = 0; var directHistoricalRowsFound = 0
        val results = JSONArray()

        for (identity in selected) {
            val candidate = byIdentity[identity] ?: continue
            val official = AdigaApplicationEvidenceAnalyzer.analyze(candidate)
            val calculated = OfficialUniversityScoreCalculator.calculate(candidate, profile)
            val verified = calculated.optBoolean("verified", false) && calculated.optString("status") == "verified"
            val directIdentityBinding = official.optInt("currentApplicationBoundCount", 0) > 0
            val scoringScopeBinding = verified && official.optBoolean("currentComponentsVerified", false)
            val formulaIdentityBinding = verified && calculated.optBoolean("formulaIdentityVerified", false)
            val conversionIdentityBinding = directIdentityBinding || scoringScopeBinding || formulaIdentityBinding
            store.upsertUniversityConversionResult(
                applicationIdentityKey = identity,
                academicYear = candidate.optInt("academicYear"),
                scoreValue = nullableDouble(calculated, "scoreValue"),
                maxScore = nullableDouble(calculated, "maxScore"),
                scoreScale = nullableString(calculated, "scoreScale"),
                comparisonDirection = nullableString(calculated, "comparisonDirection"),
                formulaSource = nullableString(calculated, "formulaSource"),
                formulaVersion = nullableString(calculated, "formulaVersion"),
                identityBindingVerified = conversionIdentityBinding,
                verified = verified,
                status = calculated.optString("status", "unverified"),
                detail = JSONObject(calculated.optJSONObject("detail")?.toString() ?: "{}")
                    .put("currentComponentsVerified", official.optBoolean("currentComponentsVerified", false))
                    .put("scoringScopeBindingVerified", scoringScopeBinding)
                    .put("formulaIdentityBindingVerified", formulaIdentityBinding)
                    .put("conversionIdentityBindingVerified", conversionIdentityBinding)
                    .put("directCurrentApplicationBinding", directIdentityBinding)
                    .put("bindingSemantics", when {
                        directIdentityBinding -> "direct-current-application"
                        scoringScopeBinding -> "same-university-year-official-components+verified-formula"
                        formulaIdentityBinding -> "exact-supported-year-university-admission-formula"
                        else -> "unverified"
                    })
                    .put("historicalBindingRelaxed", false)
                    .put("officialEvidenceCode", official.optString("code"))
                    .put("candidateMetadataFallbackOnly", candidate.optBoolean("candidateMetadataFallbackOnly", false))
                    .put("fullAdigaRescan", true)
                    .put("probabilityInferred", false)
            )
            if (verified && conversionIdentityBinding) conversionsVerified++ else conversionsHeld++

            val fullEvidence = fullByIdentity.optJSONArray(identity) ?: JSONArray()
            val historical = JSONArray(); val seenHistorical = linkedSetOf<String>()
            for (i in 0 until fullEvidence.length()) {
                val evidence = fullEvidence.optJSONObject(i) ?: continue
                if (evidence.optString("scope") !in setOf("historical", "table-segment-historical")) continue
                if (evidence.optString("departmentMatch") !in setOf("exact", "suffix-equivalent")) continue
                if (evidence.optString("admissionMatch") != "exact") continue
                val outcome = evidence.optJSONObject("historicalOutcome") ?: continue
                val key = listOf(outcome.optInt("historicalResultYear", outcome.optInt("recordYear", 0)), outcome.optString("admissionLabel"), outcome.optString("recruitmentUnit"), outcome.optString("rowEvidence")).joinToString("|")
                if (seenHistorical.add(key)) historical.put(JSONObject(outcome.toString()).put("sourcePage", evidence.optString("sourcePage")))
            }
            directHistoricalRowsFound += historical.length()
            historicalOutcomesStored += storeHistoricalOutcomes(store, identity, candidate, historical, "ADIGA_STRUCTURALLY_BOUND_HISTORICAL_TABLE", "어디가 공식 과거 입결 · 동일 전형/모집단위")

            results.put(JSONObject().put("applicationIdentityKey", identity).put("displayLabel", candidate.optString("displayLabel"))
                .put("candidateMetadataFallbackOnly", candidate.optBoolean("candidateMetadataFallbackOnly", false))
                .put("officialEvidenceCode", official.optString("code"))
                .put("currentComponentsVerified", official.optBoolean("currentComponentsVerified", false))
                .put("directCurrentBinding", directIdentityBinding).put("scoringScopeBindingVerified", scoringScopeBinding)
                .put("formulaIdentityBindingVerified", formulaIdentityBinding).put("conversionIdentityBindingVerified", conversionIdentityBinding)
                .put("conversionStatus", calculated.optString("status")).put("conversionVerified", verified && conversionIdentityBinding)
                .put("historicalOutcomeRows", historical.length()))
        }

        // Official fallbacks run after strict same-row binding. They can only add verified official
        // outcomes; they never mutate the six slots or turn a Jinhak prediction into an official result.
        val aliasFallback = AdigaHistoricalAliasFallback.materialize(store, sessionId, selectedCandidates)
        val universityFallback = UniversityOfficialPublishedFallback.materialize(store, selectedCandidates)

        return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("selected", selected.size).put("selectedCandidatesResolved", selectedCandidates.size)
            .put("fallbackCandidateSessionId", fallbackSessionId ?: JSONObject.NULL).put("fallbackCandidatesUsed", fallbackCandidatesUsed)
            .put("conversionsVerified", conversionsVerified).put("conversionsHeld", conversionsHeld)
            .put("directHistoricalRowsFound", directHistoricalRowsFound).put("historicalOutcomesStored", historicalOutcomesStored)
            .put("historicalAliasFallback", aliasFallback).put("universityOfficialFallback", universityFallback)
            .put("fullAdigaRecordsScanned", fullRescan.optInt("recordsScanned")).put("results", results)
            .put("slotsMutated", false).put("networkUsed", false).put("historicalBindingRelaxed", false).put("probabilityInferred", false)
    }

    private fun storeHistoricalOutcomes(
        store: LocalCollectorStore, identity: String, candidate: JSONObject, historical: JSONArray, sourceCode: String, sourceName: String
    ): Int {
        var stored = 0
        for (i in 0 until historical.length()) {
            val outcome = historical.optJSONObject(i) ?: continue
            val resultYear = outcome.optInt("historicalResultYear", outcome.optInt("recordYear", 0))
            if (resultYear !in 2000 until candidate.optInt("academicYear", 0)) continue
            val sourceUrl = outcome.optString("sourcePage").takeIf { it.isNotBlank() }
            val sharedDetail = JSONObject().put("source", sourceCode).put("headersVerified", outcome.optBoolean("headersVerified", false))
                .put("admissionLabel", outcome.optString("admissionLabel")).put("recruitmentUnit", outcome.optString("recruitmentUnit"))
                .put("capacity", outcome.opt("capacity") ?: JSONObject.NULL).put("competitionRate", outcome.opt("competitionRate") ?: JSONObject.NULL)
                .put("waitlist", outcome.opt("waitlist") ?: JSONObject.NULL).put("rowEvidence", outcome.optString("rowEvidence").take(1400))
                .put("headerEvidence", outcome.optString("headerEvidence").take(1000)).put("bindingMethod", outcome.optString("bindingMethod", "official-table-application-bound"))
                .put("bindingInferred", false).put("probabilityInferred", false)
            fun save(metric: String, valueKey: String, scale: String, max: Double?) {
                val value = nullableDouble(outcome, valueKey) ?: return
                if (!outcome.optBoolean("headersVerified", false)) return
                val id = store.storeOfficialAdmissionOutcome(identity, resultYear, metric, value, scale, max, sourceName, sourceUrl, true, false,
                    JSONObject(sharedDetail.toString()).put("metricKey", valueKey))
                if (id != null) stored++
            }
            val convertedMax = nullableDouble(outcome, "convertedMax")
            save("최종등록자 50% cut 대학별환산점수", "converted50", "어디가 $resultYear 대학별환산 총점", convertedMax)
            save("최종등록자 70% cut 대학별환산점수", "converted70", "어디가 $resultYear 대학별환산 총점", convertedMax)
            save("최종등록자 50% 학생부등급", "grade50", "어디가 $resultYear 최종등록자 학생부등급", 9.0)
            save("최종등록자 70% 학생부등급", "grade70", "어디가 $resultYear 최종등록자 학생부등급", 9.0)
        }
        return stored
    }

    private fun nullableDouble(obj: JSONObject, key: String): Double? {
        if (!obj.has(key) || obj.isNull(key)) return null
        return obj.optDouble(key).takeUnless { it.isNaN() || it.isInfinite() }
    }
    private fun nullableString(obj: JSONObject, key: String): String? {
        if (!obj.has(key) || obj.isNull(key)) return null
        return obj.optString(key).trim().takeIf { it.isNotBlank() && it != "null" }
    }
}
