package com.admissionhub.collector.score

import com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer
import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONArray
import org.json.JSONObject

/**
 * Rebuilds only evidence-backed score artifacts for the user's pinned six applications.
 * No slot is added, removed, reordered or replaced here.
 */
object AdigaAutoScoreMaterializer {
    const val SCHEMA_VERSION = 1

    fun materializeSelected(store: LocalCollectorStore, sessionId: String, profile: JSONObject = store.currentStudentScoreProfile()): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("error", "missing-session")
        val candidates = store.loadCanonicalApplicationCandidates(sessionId)
        val byIdentity = (0 until candidates.length()).mapNotNull { candidates.optJSONObject(it) }
            .associateBy { it.optString("applicationIdentityKey") }
        val slots = store.loadHubApplicationSlots()
        val selected = (0 until slots.length()).mapNotNull { slots.optJSONObject(it)?.optString("applicationIdentityKey") }
            .filter { it.isNotBlank() }.distinct()

        var conversionsVerified = 0
        var conversionsHeld = 0
        var historicalOutcomesStored = 0
        val results = JSONArray()

        for (identity in selected) {
            val candidate = byIdentity[identity] ?: continue
            val official = AdigaApplicationEvidenceAnalyzer.analyze(candidate)
            val calculated = OfficialUniversityScoreCalculator.calculate(candidate, profile)
            val verified = calculated.optBoolean("verified", false) && calculated.optString("status") == "verified"
            val directIdentityBinding = official.optInt("currentApplicationBoundCount", 0) > 0
            store.upsertUniversityConversionResult(
                applicationIdentityKey = identity,
                academicYear = candidate.optInt("academicYear"),
                scoreValue = nullableDouble(calculated, "scoreValue"),
                maxScore = nullableDouble(calculated, "maxScore"),
                scoreScale = nullableString(calculated, "scoreScale"),
                comparisonDirection = nullableString(calculated, "comparisonDirection"),
                formulaSource = nullableString(calculated, "formulaSource"),
                formulaVersion = nullableString(calculated, "formulaVersion"),
                identityBindingVerified = directIdentityBinding,
                verified = verified,
                status = calculated.optString("status", "unverified"),
                detail = JSONObject(calculated.optJSONObject("detail")?.toString() ?: "{}")
                    .put("currentComponentsVerified", official.optBoolean("currentComponentsVerified", false))
                    .put("directCurrentApplicationBinding", directIdentityBinding)
                    .put("officialEvidenceCode", official.optString("code"))
            )
            if (verified) conversionsVerified++ else conversionsHeld++

            val historical = official.optJSONArray("historicalOutcomes") ?: JSONArray()
            for (i in 0 until historical.length()) {
                val outcome = historical.optJSONObject(i) ?: continue
                val resultYear = outcome.optInt("historicalResultYear", outcome.optInt("recordYear", 0))
                if (resultYear !in 2000 until candidate.optInt("academicYear", 0)) continue
                val sourceUrl = outcome.optString("sourcePage").takeIf { it.isNotBlank() }
                val sharedDetail = JSONObject()
                    .put("source", "ADIGA_STRUCTURALLY_BOUND_HISTORICAL_TABLE")
                    .put("headersVerified", outcome.optBoolean("headersVerified", false))
                    .put("admissionLabel", outcome.optString("admissionLabel"))
                    .put("recruitmentUnit", outcome.optString("recruitmentUnit"))
                    .put("capacity", outcome.opt("capacity") ?: JSONObject.NULL)
                    .put("competitionRate", outcome.opt("competitionRate") ?: JSONObject.NULL)
                    .put("waitlist", outcome.opt("waitlist") ?: JSONObject.NULL)
                    .put("rowEvidence", outcome.optString("rowEvidence").take(1400))
                    .put("headerEvidence", outcome.optString("headerEvidence").take(1000))

                fun save(metric: String, valueKey: String, scale: String, max: Double?) {
                    val value = nullableDouble(outcome, valueKey) ?: return
                    if (!outcome.optBoolean("headersVerified", false)) return
                    val id = store.storeOfficialAdmissionOutcome(
                        applicationIdentityKey = identity,
                        academicYear = resultYear,
                        metricName = metric,
                        metricValue = value,
                        scoreScale = scale,
                        maxScore = max,
                        sourceName = "어디가 공식 과거 입결 · 동일 전형/모집단위",
                        sourceUrl = sourceUrl,
                        verified = true,
                        primaryReference = false,
                        detail = JSONObject(sharedDetail.toString()).put("metricKey", valueKey)
                    )
                    if (id != null) historicalOutcomesStored++
                }

                val convertedMax = nullableDouble(outcome, "convertedMax")
                val convertedScale = "어디가 ${resultYear} 대학별환산 총점"
                save("최종등록자 50% cut 대학별환산점수", "converted50", convertedScale, convertedMax)
                save("최종등록자 70% cut 대학별환산점수", "converted70", convertedScale, convertedMax)
                val gradeScale = "어디가 ${resultYear} 최종등록자 학생부등급"
                save("최종등록자 50% 학생부등급", "grade50", gradeScale, 9.0)
                save("최종등록자 70% 학생부등급", "grade70", gradeScale, 9.0)
            }

            results.put(JSONObject()
                .put("applicationIdentityKey", identity)
                .put("displayLabel", candidate.optString("displayLabel"))
                .put("officialEvidenceCode", official.optString("code"))
                .put("currentComponentsVerified", official.optBoolean("currentComponentsVerified", false))
                .put("directCurrentBinding", directIdentityBinding)
                .put("conversionStatus", calculated.optString("status"))
                .put("conversionVerified", verified)
                .put("historicalOutcomeRows", historical.length()))
        }

        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("selected", selected.size)
            .put("conversionsVerified", conversionsVerified)
            .put("conversionsHeld", conversionsHeld)
            .put("historicalOutcomesStored", historicalOutcomesStored)
            .put("results", results)
            .put("slotsMutated", false)
            .put("probabilityInferred", false)
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
