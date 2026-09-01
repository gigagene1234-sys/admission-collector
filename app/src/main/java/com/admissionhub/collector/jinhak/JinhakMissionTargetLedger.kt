package com.admissionhub.collector.jinhak

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONObject

/**
 * v0.8.6 navigation-persistent target ledger.
 *
 * The ledger snapshots all safe, same-card application report targets before the foreground
 * browser leaves the saved-application page. It stores only the already-sanitized candidate
 * label/context and local navigation route; it never reads cookies, storage, form values or
 * neighbouring-card identity. Targets survive report/origin navigation within the collection run.
 */
class JinhakMissionTargetLedger {
    enum class State { PENDING, CLICKED, DEFERRED, CONFIRMED, FAILED, SKIPPED }

    data class Target(
        val targetId: String,
        val identityKey: String,
        val lane: String,
        val label: String,
        val kind: String,
        val originRoute: String,
        var scanIndex: Int,
        var tag: String,
        var missionPriority: Int,
        var contextText: String,
        var applicationContext: JinhakApplicationMission.Context,
        var state: State = State.PENDING,
        var attempts: Int = 0,
        var failureReason: String? = null,
        var updatedAtMs: Long = System.currentTimeMillis()
    ) {
        fun candidate(): JinhakAgentNavigator.Candidate = JinhakAgentNavigator.Candidate(
            scanIndex = scanIndex,
            label = label,
            tag = tag,
            kind = kind,
            missionPriority = missionPriority.coerceAtLeast(180),
            contextText = contextText,
            applicationContext = applicationContext,
            promotedMissionAction = true
        )
    }

    private val laneOrder = listOf(
        "current-prediction",
        "mock-support",
        "actual-admit",
        "score-analysis",
        "university-result",
        "strategy"
    )
    private val targets = linkedMapOf<String, Target>()

    fun clear() = targets.clear()

    /** Capture every safe application-bound report target currently visible before navigation. */
    fun capture(originRoute: String, candidates: List<JinhakAgentNavigator.Candidate>): Int {
        if (originRoute.isBlank()) return 0
        var added = 0
        for (candidate in candidates) {
            val context = candidate.applicationContext ?: continue
            val identity = context.identityKey ?: continue
            val lane = JinhakMissionLaneSequencer.laneForLabel(candidate.label, candidate.kind)
            if (lane == "reference") continue
            val id = RecordUtils.sha256(listOf(identity, lane, candidate.label, candidate.kind, originRoute).joinToString("|"))
            val existing = targets[id]
            if (existing == null) {
                targets[id] = Target(
                    targetId = id,
                    identityKey = identity,
                    lane = lane,
                    label = candidate.label,
                    kind = candidate.kind,
                    originRoute = originRoute,
                    scanIndex = candidate.scanIndex,
                    tag = candidate.tag,
                    missionPriority = candidate.missionPriority,
                    contextText = candidate.contextText,
                    applicationContext = context
                )
                added += 1
            } else if (existing.state == State.PENDING || existing.state == State.FAILED) {
                // Refresh volatile SPA indexes from the latest same-card snapshot. Do not replace
                // the immutable application identity/lane/label that formed the ledger key.
                existing.scanIndex = candidate.scanIndex
                existing.tag = candidate.tag
                existing.missionPriority = maxOf(existing.missionPriority, candidate.missionPriority)
                existing.contextText = candidate.contextText
                existing.applicationContext = context
                existing.updatedAtMs = System.currentTimeMillis()
            }
        }
        return added
    }

    fun hasMission(identityKey: String?): Boolean = identityKey != null && targets.values.any { it.identityKey == identityKey }

    fun hasActionablePending(): Boolean = targets.values.any { it.state == State.PENDING }

    fun outstandingCount(): Int = targets.values.count {
        it.state == State.PENDING || it.state == State.CLICKED || it.state == State.DEFERRED
    }

    fun pendingCount(): Int = targets.values.count { it.state == State.PENDING }

    fun originForNextPending(preferredIdentityKey: String? = null): String? {
        val preferred = preferredIdentityKey?.let { key ->
            sortedTargets().firstOrNull { it.identityKey == key && it.state == State.PENDING }
        }
        return preferred?.originRoute ?: sortedTargets().firstOrNull { it.state == State.PENDING }?.originRoute
    }

    fun nextPendingAtOrigin(
        originRoute: String,
        preferredIdentityKey: String?,
        coveredLanes: Set<String>
    ): Target? {
        if (originRoute.isBlank()) return null
        val sameOrigin = sortedTargets().filter { it.originRoute == originRoute && it.state == State.PENDING }
        val preferred = if (preferredIdentityKey != null) {
            sameOrigin.firstOrNull { it.identityKey == preferredIdentityKey && it.lane !in coveredLanes }
        } else null
        if (preferred != null) return preferred
        return sameOrigin.firstOrNull { target ->
            val laneAlreadyConfirmed = targets.values.any {
                it.identityKey == target.identityKey && it.lane == target.lane && it.state == State.CONFIRMED
            }
            !laneAlreadyConfirmed
        }
    }

    fun markAttempted(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.attempts += 1
        target.updatedAtMs = System.currentTimeMillis()
        return true
    }

    fun markClicked(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.state = State.CLICKED
        target.failureReason = null
        target.updatedAtMs = System.currentTimeMillis()
        return true
    }

    fun markDeferred(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.state = State.DEFERRED
        target.updatedAtMs = System.currentTimeMillis()
        return true
    }

    fun markConfirmed(targetId: String?, identityKey: String?, lane: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        if (identityKey.isNullOrBlank() || target.identityKey != identityKey || lane == "reference" || target.lane != lane) return false
        target.state = State.CONFIRMED
        target.failureReason = null
        target.updatedAtMs = System.currentTimeMillis()
        // One confirmed lane is sufficient. Keep alternate same-lane entry points as evidence but
        // do not click them after the report has already been proven for this application.
        targets.values.filter {
            it.targetId != target.targetId && it.identityKey == target.identityKey && it.lane == target.lane && it.state == State.PENDING
        }.forEach {
            it.state = State.SKIPPED
            it.failureReason = "lane-confirmed-by-alternate-target"
            it.updatedAtMs = System.currentTimeMillis()
        }
        return true
    }

    fun markFailed(targetId: String?, reason: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.state = State.FAILED
        target.failureReason = reason.take(100)
        target.updatedAtMs = System.currentTimeMillis()
        return true
    }

    fun failAllPending(reason: String) {
        targets.values.filter { it.state == State.PENDING }.forEach {
            it.state = State.FAILED
            it.failureReason = reason.take(100)
            it.updatedAtMs = System.currentTimeMillis()
        }
    }

    fun stateOf(targetId: String?): State? = targetId?.let { targets[it]?.state }

    fun target(targetId: String?): Target? = targetId?.let { targets[it] }

    fun summary(): JSONObject {
        val out = JSONObject()
        val stateCounts = JSONObject()
        for (state in State.entries) stateCounts.put(state.name.lowercase(), targets.values.count { it.state == state })
        val laneCounts = JSONObject()
        for (lane in laneOrder) {
            val laneTargets = targets.values.filter { it.lane == lane }
            laneCounts.put(lane, JSONObject()
                .put("targets", laneTargets.size)
                .put("pending", laneTargets.count { it.state == State.PENDING })
                .put("clicked", laneTargets.count { it.state == State.CLICKED })
                .put("deferred", laneTargets.count { it.state == State.DEFERRED })
                .put("confirmed", laneTargets.count { it.state == State.CONFIRMED })
                .put("failed", laneTargets.count { it.state == State.FAILED })
                .put("skipped", laneTargets.count { it.state == State.SKIPPED }))
        }
        val identities = targets.values.map { it.identityKey }.toSet()
        val confirmedLaneCounts = identities.associateWith { key ->
            targets.values.filter { it.identityKey == key && it.state == State.CONFIRMED }.map { it.lane }.toSet().size
        }
        val failureReasons = linkedMapOf<String, Int>()
        targets.values.filter { it.state == State.FAILED }.forEach { target ->
            val reason = target.failureReason ?: "unknown"
            failureReasons[reason] = (failureReasons[reason] ?: 0) + 1
        }
        return out
            .put("identities", identities.size)
            .put("targets", targets.size)
            .put("pending", pendingCount())
            .put("outstanding", outstandingCount())
            .put("states", stateCounts)
            .put("lanes", laneCounts)
            .put("identitiesWithFourOrMoreConfirmedTargets", confirmedLaneCounts.values.count { it >= 4 })
            .put("identitiesWithSixOrMoreConfirmedTargets", confirmedLaneCounts.values.count { it >= 6 })
            .put("failureReasons", JSONObject(failureReasons as Map<*, *>))
    }

    private fun sortedTargets(): List<Target> = targets.values.sortedWith(
        compareBy<Target> { laneOrder.indexOf(it.lane).let { rank -> if (rank >= 0) rank else laneOrder.size } }
            .thenByDescending { it.missionPriority }
            .thenBy { it.targetId }
    )
}
