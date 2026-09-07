package com.admissionhub.collector.canonical

import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONArray
import org.json.JSONObject

/**
 * The persisted canonical card keeps only a bounded diagnostic sample. This local-only rescan is
 * used when the user asks for scores/results so a directly-bound historical row cannot disappear
 * merely because many university-wide current rows were sampled first.
 */
object AdigaFullEvidenceRescan {
    const val SCHEMA_VERSION = 1

    fun scanSelected(store: LocalCollectorStore, sessionId: String, candidates: List<JSONObject>): JSONObject {
        val runId = store.providerRunIdForUnifiedSession(sessionId, "adiga")
            ?: return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("byIdentity", JSONObject()).put("recordsScanned", 0)
        val refs = candidates.mapNotNull { candidate ->
            val identity = candidate.optString("applicationIdentityKey").takeIf { it.isNotBlank() } ?: return@mapNotNull null
            val ref = AdigaOfficialAdmissionEvidence.AppRef(
                candidate.optInt("academicYear"), candidate.optString("university"), candidate.optString("department"),
                candidate.optString("admission"), candidate.optString("admissionCategory")
            )
            Triple(identity, candidate, ref)
        }
        val buckets = linkedMapOf<String, MutableList<JSONObject>>()
        refs.forEach { buckets[it.first] = mutableListOf() }
        var scanned = 0
        var inspected = 0
        store.readableDatabase.rawQuery(
            "SELECT record_type,year,university,json FROM records WHERE run_id=? AND provider='adiga' AND record_type IN ('current-admission-criteria-table','historical-admission-result-table') ORDER BY year DESC,updated_at",
            arrayOf(runId)
        ).use { cursor ->
            while (cursor.moveToNext()) {
                scanned++
                val recordType = cursor.getString(0).orEmpty()
                val recordYear = if (cursor.isNull(1)) 0 else cursor.getInt(1)
                val rawUniversity = if (cursor.isNull(2)) "" else cursor.getString(2)
                val recordUniversityKey = CanonicalSixApplicationGraph.normalizeUniversityKey(rawUniversity)
                if (recordUniversityKey.isBlank()) continue
                val matching = refs.filter { (_, candidate, _) ->
                    CanonicalSixApplicationGraph.normalizeUniversityKey(candidate.optString("university")) == recordUniversityKey
                }
                if (matching.isEmpty()) continue
                val record = runCatching { JSONObject(cursor.getString(3)) }.getOrNull() ?: continue
                for ((identity, _, ref) in matching) {
                    inspected++
                    buckets.getValue(identity).addAll(AdigaOfficialAdmissionEvidence.inspect(recordType, recordYear, record, ref))
                }
            }
        }
        val byIdentity = JSONObject()
        for ((identity, rows) in buckets) {
            val deduped = JSONArray()
            val seen = linkedSetOf<String>()
            for (row in rows) {
                val key = listOf(
                    row.optString("sourceRowFingerprint"), row.optString("scope"), row.optInt("rowIndex", -1),
                    row.optInt("scopeRowIndex", -1), row.optInt("departmentRowIndex", -1)
                ).joinToString("|")
                if (seen.add(key)) deduped.put(row)
            }
            byIdentity.put(identity, deduped)
        }
        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("runId", runId)
            .put("recordsScanned", scanned)
            .put("candidateRecordInspections", inspected)
            .put("byIdentity", byIdentity)
            .put("networkUsed", false)
            .put("credentialsRead", false)
            .put("slotsMutated", false)
    }
}
