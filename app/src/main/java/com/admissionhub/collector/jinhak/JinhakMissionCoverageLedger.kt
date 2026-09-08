package com.admissionhub.collector.jinhak

import org.json.JSONArray
import org.json.JSONObject

/**
 * Monotonic per-application report coverage ledger.
 *
 * v0.14.2 restores university-result as a required integrated lane. Strategy remains tracked
 * but optional because some application cards do not expose a strategy route.
 */
class JinhakMissionCoverageLedger {
    private val lanesByIdentity = linkedMapOf<String, MutableSet<String>>()
    private val sourceByKey = linkedMapOf<String, String>()

    fun clear() {
        lanesByIdentity.clear()
        sourceByKey.clear()
    }

    fun confirm(identityKey: String?, lane: String, source: String = "runtime"): Boolean {
        val identity = identityKey?.takeIf { it.isNotBlank() } ?: return false
        if (lane.isBlank() || lane == "reference") return false
        val changed = lanesByIdentity.getOrPut(identity) { linkedSetOf() }.add(lane)
        if (changed) sourceByKey["$identity|$lane"] = source.take(80)
        return changed
    }

    fun restore(payloads: List<JSONObject>): Int {
        var restored = 0
        payloads.forEach { obj ->
            val identity = obj.optString("identityKey").takeIf { it.isNotBlank() && it != "null" } ?: return@forEach
            val lane = obj.optString("lane").takeIf { it.isNotBlank() && it != "reference" && it != "null" } ?: return@forEach
            if (confirm(identity, lane, obj.optString("source", "sqlite-restore"))) restored += 1
        }
        return restored
    }

    fun lanes(identityKey: String): Set<String> = lanesByIdentity[identityKey]?.toSet().orEmpty()

    fun allCoreComplete(expectedIdentities: Set<String>): Boolean =
        expectedIdentities.isNotEmpty() && expectedIdentities.all { identity ->
            val lanes = lanesByIdentity[identity].orEmpty()
            CORE_LANES.all(lanes::contains)
        }

    fun summary(expectedIdentities: Set<String> = lanesByIdentity.keys): JSONObject {
        val expected = expectedIdentities.filter { it.isNotBlank() }.toSet()
        val laneCounts = JSONObject()
        ALL_TRACKED_LANES.forEach { lane ->
            laneCounts.put(lane, expected.count { lanesByIdentity[it]?.contains(lane) == true })
        }
        val complete = expected.count { identity -> CORE_LANES.all { it in lanes(identity) } }
        val missingByLane = JSONObject()
        CORE_LANES.forEach { lane -> missingByLane.put(lane, (expected.size - laneCounts.optInt(lane)).coerceAtLeast(0)) }
        return JSONObject()
            .put("schemaVersion", 2)
            .put("expectedIdentities", expected.size)
            .put("knownIdentities", lanesByIdentity.size)
            .put("requiredCoreLanes", JSONArray(CORE_LANES))
            .put("optionalExtendedLanes", JSONArray(OPTIONAL_EXTENDED_LANES))
            .put("laneCoverage", laneCounts)
            .put("completeIdentities", complete)
            .put("incompleteIdentities", (expected.size - complete).coerceAtLeast(0))
            .put("coreComplete", expected.isNotEmpty() && complete == expected.size)
            .put("missingByLane", missingByLane)
            .put("credentialStored", false)
            .put("sessionSecretStored", false)
    }

    companion object {
        val CORE_LANES = listOf(
            "saved-application",
            "current-prediction",
            "mock-support",
            "actual-admit",
            "score-analysis",
            "university-result"
        )
        val OPTIONAL_EXTENDED_LANES = listOf("strategy")
        private val ALL_TRACKED_LANES = CORE_LANES + OPTIONAL_EXTENDED_LANES
    }
}
