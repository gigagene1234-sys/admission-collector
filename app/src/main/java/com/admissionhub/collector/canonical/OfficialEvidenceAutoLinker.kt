package com.admissionhub.collector.canonical

import android.content.ContentValues
import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/**
 * Rebuilds conservative Adiga evidence bindings for the user's pinned applications from the
 * complete local Adiga record store. It never creates an application, mutates the six slots,
 * infers a missing admission track, or promotes university-wide evidence to an application row.
 */
object OfficialEvidenceAutoLinker {
    const val SCHEMA_VERSION = 1

    fun relinkSelected(store: LocalCollectorStore, sessionId: String): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("error", "missing-session")
        val candidates = store.loadCanonicalApplicationCandidates(sessionId)
        val slots = store.loadHubApplicationSlots()
        val byIdentity = (0 until candidates.length()).mapNotNull { candidates.optJSONObject(it) }
            .associateBy { it.optString("applicationIdentityKey") }
        val selected = (0 until slots.length()).mapNotNull { slots.optJSONObject(it)?.optString("applicationIdentityKey") }
            .filter { it.isNotBlank() }.distinct()
        val selectedCandidates = selected.mapNotNull { byIdentity[it] }
        val rescan = AdigaFullEvidenceRescan.scanSelected(store, sessionId, selectedCandidates)
        val fullByIdentity = rescan.optJSONObject("byIdentity") ?: JSONObject()

        var directlyBound = 0
        var componentVerified = 0
        var updated = 0
        val results = JSONArray()
        val db = store.writableDatabase

        for (identity in selected) {
            val candidate = byIdentity[identity] ?: continue
            val academicYear = candidate.optInt("academicYear", 0)
            val rows = fullByIdentity.optJSONArray(identity) ?: JSONArray()
            val existing = candidate.optJSONObject("adigaBinding") ?: JSONObject()
            val evidence = JSONArray()
            val seen = linkedSetOf<String>()
            var currentDirect = 0
            var historicalDirect = 0
            var universityCurrent = 0
            var rowBoundCurrent = 0
            var segmentCurrent = 0
            var segmentHistorical = 0
            var departmentCandidate = false
            var exactAdmissionCandidate = false
            var relatedAdmissionCandidate = false

            for (i in 0 until rows.length()) {
                val row = rows.optJSONObject(i) ?: continue
                val dept = row.optString("departmentMatch")
                val adm = row.optString("admissionMatch")
                val scope = row.optString("scope")
                val recordYear = row.optInt("recordYear", 0)
                if (dept in setOf("exact", "suffix-equivalent")) departmentCandidate = true
                if (adm == "exact") exactAdmissionCandidate = true
                if (adm in setOf("exact", "related")) relatedAdmissionCandidate = true
                if (recordYear == academicYear || scope == "university-current") universityCurrent++
                val direct = dept in setOf("exact", "suffix-equivalent") && adm == "exact"
                if (direct && recordYear == academicYear && scope in setOf("row-bound-current", "table-segment-current")) {
                    currentDirect++
                    if (scope == "row-bound-current") rowBoundCurrent++ else segmentCurrent++
                }
                if (direct && recordYear in 2000 until academicYear && scope in setOf("historical", "table-segment-historical")) {
                    historicalDirect++
                    if (scope == "table-segment-historical") segmentHistorical++
                }
                val key = listOf(row.optString("sourceRowFingerprint"), scope, row.optInt("rowIndex", -1), row.optInt("scopeRowIndex", -1)).joinToString("|")
                if (seen.add(key) && evidence.length() < 160) evidence.put(JSONObject(row.toString()))
            }

            val currentComponents = universityCurrent > 0 && departmentCandidate && exactAdmissionCandidate
            val binding = JSONObject(existing.toString())
                .put("officialAdmissionEvidence", evidence)
                .put("officialUniversityCurrent", maxOf(existing.optInt("officialUniversityCurrent", 0), universityCurrent))
                .put("officialStructuralCurrent", maxOf(existing.optInt("officialStructuralCurrent", 0), currentDirect))
                .put("officialRowBoundCurrent", maxOf(existing.optInt("officialRowBoundCurrent", 0), rowBoundCurrent))
                .put("officialTableSegmentCurrent", maxOf(existing.optInt("officialTableSegmentCurrent", 0), segmentCurrent))
                .put("officialTableSegmentHistorical", maxOf(existing.optInt("officialTableSegmentHistorical", 0), historicalDirect, segmentHistorical))
                .put("acceptedSignatures", maxOf(existing.optInt("acceptedSignatures", 0), currentDirect + historicalDirect))
                .put("autoRelinkedFromFullLocalAdiga", true)
                .put("autoRelinkedAt", Instant.now().toString())
                .put("fullLocalRecordsScanned", rescan.optInt("recordsScanned", 0))
                .put("currentComponentsVerified", currentComponents)
                .put("departmentCandidate", departmentCandidate)
                .put("exactAdmissionCandidate", exactAdmissionCandidate)
                .put("relatedAdmissionCandidate", relatedAdmissionCandidate)

            val oldQuality = candidate.optString("qualityState", candidate.optString("adigaBindingQuality", "provider-only"))
            val quality = when {
                currentDirect > 0 -> "accepted"
                currentComponents -> "provisional"
                else -> oldQuality
            }
            val values = ContentValues().apply {
                put("adiga_binding_json", binding.toString())
                put("adiga_match_count", maxOf(candidate.optInt("adigaMatchCount", 0), evidence.length()))
                put("adiga_binding_quality", quality)
                put("quality_state", quality)
                put("updated_at", Instant.now().toString())
            }
            val count = db.update(
                "canonical_applications", values,
                "session_id=? AND application_identity_key=?", arrayOf(sessionId, identity)
            )
            if (count > 0) updated++
            if (currentDirect > 0) directlyBound++
            if (currentComponents || currentDirect > 0) componentVerified++
            results.put(JSONObject()
                .put("applicationIdentityKey", identity)
                .put("currentDirect", currentDirect)
                .put("historicalDirect", historicalDirect)
                .put("currentComponentsVerified", currentComponents)
                .put("evidenceRows", evidence.length())
                .put("qualityState", quality))
        }

        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("selected", selected.size)
            .put("updated", updated)
            .put("officialVerified", componentVerified)
            .put("directCurrentBound", directlyBound)
            .put("recordsScanned", rescan.optInt("recordsScanned", 0))
            .put("results", results)
            .put("slotsMutated", false)
            .put("networkUsed", false)
            .put("probabilityInferred", false)
    }
}
