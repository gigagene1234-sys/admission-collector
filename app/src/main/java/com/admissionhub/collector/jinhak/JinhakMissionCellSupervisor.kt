package com.admissionhub.collector.jinhak

import org.json.JSONArray
import org.json.JSONObject
import java.util.ArrayDeque

/**
 * Owns the lifecycle of foreground Jinhak mission operations.
 *
 * The supervisor deliberately does not navigate WebView or mutate the mission ledger.
 * It only owns operation identity, generation, renderer ownership and bounded health
 * diagnostics so the parent mission scheduler can distinguish a live child operation
 * from a stale/orphaned boolean flag.
 */
class JinhakMissionCellSupervisor(
    private val staleOwnershipMs: Long = 60_000L,
    private val eventLimit: Int = 96
) {
    data class Token internal constructor(
        val cell: String,
        val operationId: Long,
        val generation: Int,
        val rendererGeneration: Int
    )

    data class ExpiryResult(
        val actionExpired: Boolean,
        val snapshotExpired: Boolean,
        val actionAgeMs: Long,
        val snapshotAgeMs: Long
    ) {
        val expiredAny: Boolean get() = actionExpired || snapshotExpired

        fun toJson(): JSONObject = JSONObject()
            .put("actionExpired", actionExpired)
            .put("snapshotExpired", snapshotExpired)
            .put("actionAgeMs", actionAgeMs)
            .put("snapshotAgeMs", snapshotAgeMs)
    }

    data class InvalidationResult(
        val actionInvalidated: Boolean,
        val snapshotInvalidated: Boolean,
        val reason: String
    ) {
        val invalidatedAny: Boolean get() = actionInvalidated || snapshotInvalidated

        fun toJson(): JSONObject = JSONObject()
            .put("actionInvalidated", actionInvalidated)
            .put("snapshotInvalidated", snapshotInvalidated)
            .put("reason", reason)
    }

    private data class Lease(
        val operationId: Long,
        val generation: Int,
        val rendererGeneration: Int,
        val targetId: String?,
        val safePath: String,
        val detail: String,
        val startedAtMs: Long,
        var lastEventAtMs: Long
    )

    private val events = ArrayDeque<JSONObject>()
    private var operationSequence = 0L
    private var actionGeneration = 1
    private var snapshotGeneration = 1
    private var rendererGeneration = 1
    private var rendererState = "READY"
    private var rendererLastEventAtMs = System.currentTimeMillis()

    private var actionLease: Lease? = null
    private var snapshotLease: Lease? = null

    private var staleActionRecoveries = 0
    private var staleSnapshotRecoveries = 0
    private var rendererInvalidations = 0
    private var lateCallbacksIgnored = 0
    private var overlapReplacements = 0
    private var actionStarts = 0
    private var snapshotStarts = 0
    private var actionCompletions = 0
    private var snapshotCompletions = 0
    private var terminalState = "ACTIVE"
    private var terminalReason = ""

    @Synchronized
    fun beginAction(
        targetId: String?,
        safePath: String,
        detail: String,
        nowMs: Long = System.currentTimeMillis()
    ): Token = begin(
        cell = CELL_ACTION,
        targetId = targetId,
        safePath = safePath,
        detail = detail,
        nowMs = nowMs
    )

    @Synchronized
    fun finishAction(
        token: Token,
        success: Boolean,
        reason: String,
        nowMs: Long = System.currentTimeMillis()
    ): Boolean = finish(CELL_ACTION, token, success, reason, nowMs)

    @Synchronized
    fun beginSnapshot(
        targetId: String?,
        safePath: String,
        detail: String = "batch-snapshot",
        nowMs: Long = System.currentTimeMillis()
    ): Token = begin(
        cell = CELL_SNAPSHOT,
        targetId = targetId,
        safePath = safePath,
        detail = detail,
        nowMs = nowMs
    )

    @Synchronized
    fun finishSnapshot(
        token: Token,
        success: Boolean,
        reason: String,
        nowMs: Long = System.currentTimeMillis()
    ): Boolean = finish(CELL_SNAPSHOT, token, success, reason, nowMs)

    @Synchronized
    fun hasActiveOwnership(): Boolean = actionLease != null || snapshotLease != null

    @Synchronized
    fun isActionActive(): Boolean = actionLease != null

    @Synchronized
    fun isSnapshotActive(): Boolean = snapshotLease != null

    /**
     * Called only after the parent mission's no-progress threshold has fired.
     * A child operation is expired only when its own lease age also exceeds the bound.
     */
    @Synchronized
    fun expireStaleOwnership(nowMs: Long = System.currentTimeMillis()): ExpiryResult {
        val actionAge = ageMs(actionLease, nowMs)
        val snapshotAge = ageMs(snapshotLease, nowMs)
        val actionExpired = actionLease != null && actionAge >= staleOwnershipMs
        val snapshotExpired = snapshotLease != null && snapshotAge >= staleOwnershipMs

        if (actionExpired) {
            val lease = actionLease
            addEvent(CELL_ACTION, "STALE_EXPIRED", lease, "lease-timeout", nowMs)
            actionLease = null
            actionGeneration += 1
            staleActionRecoveries += 1
        }
        if (snapshotExpired) {
            val lease = snapshotLease
            addEvent(CELL_SNAPSHOT, "STALE_EXPIRED", lease, "lease-timeout", nowMs)
            snapshotLease = null
            snapshotGeneration += 1
            staleSnapshotRecoveries += 1
        }
        return ExpiryResult(actionExpired, snapshotExpired, actionAge, snapshotAge)
    }

    @Synchronized
    fun onRendererGone(
        reason: String,
        nowMs: Long = System.currentTimeMillis()
    ): InvalidationResult {
        rendererState = "DEAD"
        rendererLastEventAtMs = nowMs
        rendererGeneration += 1
        rendererInvalidations += 1
        addEvent(CELL_RENDERER, "GONE", null, reason, nowMs)
        return invalidateAllInternal("renderer-gone:$reason", nowMs)
    }

    @Synchronized
    fun markRendererReady(
        reason: String,
        nowMs: Long = System.currentTimeMillis()
    ) {
        rendererState = "READY"
        rendererLastEventAtMs = nowMs
        addEvent(CELL_RENDERER, "READY", null, reason, nowMs)
    }

    @Synchronized
    fun invalidateAll(
        reason: String,
        nowMs: Long = System.currentTimeMillis()
    ): InvalidationResult = invalidateAllInternal(reason, nowMs)

    @Synchronized
    fun resetForRun(
        reason: String,
        nowMs: Long = System.currentTimeMillis()
    ) {
        actionLease = null
        snapshotLease = null
        actionGeneration += 1
        snapshotGeneration += 1
        events.clear()
        staleActionRecoveries = 0
        staleSnapshotRecoveries = 0
        rendererInvalidations = 0
        lateCallbacksIgnored = 0
        overlapReplacements = 0
        actionStarts = 0
        snapshotStarts = 0
        actionCompletions = 0
        snapshotCompletions = 0
        terminalState = "ACTIVE"
        terminalReason = ""
        addEvent(CELL_SUPERVISOR, "RUN_RESET", null, reason, nowMs)
    }

    @Synchronized
    fun sealComplete(reason: String, nowMs: Long = System.currentTimeMillis()): InvalidationResult {
        val invalidated = invalidateAllInternal("terminal-seal:${reason.take(80)}", nowMs)
        terminalState = "COMPLETE"
        terminalReason = reason.take(120)
        addEvent(CELL_SUPERVISOR, "COMPLETE", null, terminalReason, nowMs)
        return invalidated
    }

    @Synchronized
    fun diagnostics(nowMs: Long = System.currentTimeMillis()): JSONObject {
        val blockedBy = JSONArray()
        if (actionLease != null) blockedBy.put("action")
        if (snapshotLease != null) blockedBy.put("snapshot")

        val timeline = JSONArray()
        events.forEach { event -> timeline.put(JSONObject(event.toString())) }

        val state = when {
            terminalState == "COMPLETE" -> "COMPLETE"
            rendererState == "DEAD" -> "RENDERER_DEAD"
            actionLease != null -> "WAITING_ACTION"
            snapshotLease != null -> "WAITING_SNAPSHOT"
            else -> "IDLE"
        }

        return JSONObject()
            .put("supervisorState", state)
            .put("terminalState", terminalState)
            .put("terminalReason", if (terminalReason.isBlank()) JSONObject.NULL else terminalReason)
            .put("staleOwnershipMs", staleOwnershipMs)
            .put("blockedBy", blockedBy)
            .put("renderer", JSONObject()
                .put("state", rendererState)
                .put("generation", rendererGeneration)
                .put("lastEventAgeMs", (nowMs - rendererLastEventAtMs).coerceAtLeast(0L)))
            .put("action", leaseJson(actionLease, nowMs, actionGeneration))
            .put("snapshot", leaseJson(snapshotLease, nowMs, snapshotGeneration))
            .put("staleActionRecoveries", staleActionRecoveries)
            .put("staleSnapshotRecoveries", staleSnapshotRecoveries)
            .put("rendererInvalidations", rendererInvalidations)
            .put("lateCallbacksIgnored", lateCallbacksIgnored)
            .put("overlapReplacements", overlapReplacements)
            .put("actionStarts", actionStarts)
            .put("snapshotStarts", snapshotStarts)
            .put("actionCompletions", actionCompletions)
            .put("snapshotCompletions", snapshotCompletions)
            .put("recentEvents", timeline)
    }

    private fun begin(
        cell: String,
        targetId: String?,
        safePath: String,
        detail: String,
        nowMs: Long
    ): Token {
        val existing = leaseFor(cell)
        if (existing != null) {
            overlapReplacements += 1
            addEvent(cell, "SUPERSEDED", existing, "new-operation-started", nowMs)
            clearLease(cell)
            bumpGeneration(cell)
        }

        operationSequence += 1
        val generation = generationFor(cell)
        val lease = Lease(
            operationId = operationSequence,
            generation = generation,
            rendererGeneration = rendererGeneration,
            targetId = targetId?.takeIf { it.isNotBlank() },
            safePath = safePath.take(180),
            detail = detail.take(120),
            startedAtMs = nowMs,
            lastEventAtMs = nowMs
        )
        setLease(cell, lease)
        if (cell == CELL_ACTION) actionStarts += 1 else snapshotStarts += 1
        addEvent(cell, "STARTED", lease, "", nowMs)
        return Token(cell, lease.operationId, lease.generation, lease.rendererGeneration)
    }

    private fun finish(
        cell: String,
        token: Token,
        success: Boolean,
        reason: String,
        nowMs: Long
    ): Boolean {
        val current = leaseFor(cell)
        val tokenMatches = current != null &&
            token.cell == cell &&
            current.operationId == token.operationId &&
            current.generation == token.generation &&
            current.rendererGeneration == token.rendererGeneration &&
            token.rendererGeneration == rendererGeneration

        if (!tokenMatches) {
            lateCallbacksIgnored += 1
            addEvent(
                cell,
                "LATE_CALLBACK_IGNORED",
                current,
                "token=${token.operationId}/${token.generation}/${token.rendererGeneration};${reason.take(80)}",
                nowMs
            )
            return false
        }

        current?.lastEventAtMs = nowMs
        addEvent(cell, if (success) "SUCCEEDED" else "FAILED", current, reason, nowMs)
        clearLease(cell)
        if (cell == CELL_ACTION) actionCompletions += 1 else snapshotCompletions += 1
        return true
    }

    private fun invalidateAllInternal(reason: String, nowMs: Long): InvalidationResult {
        val actionInvalidated = actionLease != null
        val snapshotInvalidated = snapshotLease != null
        if (actionInvalidated) addEvent(CELL_ACTION, "INVALIDATED", actionLease, reason, nowMs)
        if (snapshotInvalidated) addEvent(CELL_SNAPSHOT, "INVALIDATED", snapshotLease, reason, nowMs)
        actionLease = null
        snapshotLease = null
        actionGeneration += 1
        snapshotGeneration += 1
        return InvalidationResult(actionInvalidated, snapshotInvalidated, reason.take(120))
    }

    private fun leaseJson(lease: Lease?, nowMs: Long, generation: Int): JSONObject {
        if (lease == null) {
            return JSONObject()
                .put("state", "IDLE")
                .put("generation", generation)
                .put("ageMs", 0L)
        }
        return JSONObject()
            .put("state", "RUNNING")
            .put("operationId", lease.operationId)
            .put("generation", lease.generation)
            .put("rendererGeneration", lease.rendererGeneration)
            .put("targetId", lease.targetId ?: JSONObject.NULL)
            .put("safePath", lease.safePath)
            .put("detail", lease.detail)
            .put("ageMs", ageMs(lease, nowMs))
            .put("lastEventAgeMs", (nowMs - lease.lastEventAtMs).coerceAtLeast(0L))
    }

    private fun addEvent(
        cell: String,
        event: String,
        lease: Lease?,
        reason: String,
        nowMs: Long
    ) {
        val obj = JSONObject()
            .put("atMs", nowMs)
            .put("cell", cell.lowercase())
            .put("event", event)
            .put("rendererGeneration", rendererGeneration)
        if (lease != null) {
            obj.put("operationId", lease.operationId)
                .put("generation", lease.generation)
                .put("ownerRendererGeneration", lease.rendererGeneration)
                .put("targetId", lease.targetId ?: JSONObject.NULL)
                .put("safePath", lease.safePath)
        }
        if (reason.isNotBlank()) obj.put("reason", reason.take(120))
        events.addLast(obj)
        while (events.size > eventLimit) events.removeFirst()
    }

    private fun leaseFor(cell: String): Lease? = if (cell == CELL_ACTION) actionLease else snapshotLease

    private fun setLease(cell: String, lease: Lease) {
        if (cell == CELL_ACTION) actionLease = lease else snapshotLease = lease
    }

    private fun clearLease(cell: String) {
        if (cell == CELL_ACTION) actionLease = null else snapshotLease = null
    }

    private fun generationFor(cell: String): Int = if (cell == CELL_ACTION) actionGeneration else snapshotGeneration

    private fun bumpGeneration(cell: String) {
        if (cell == CELL_ACTION) actionGeneration += 1 else snapshotGeneration += 1
    }

    private fun ageMs(lease: Lease?, nowMs: Long): Long =
        if (lease == null) 0L else (nowMs - lease.startedAtMs).coerceAtLeast(0L)

    companion object {
        private const val CELL_ACTION = "ACTION"
        private const val CELL_SNAPSHOT = "SNAPSHOT"
        private const val CELL_RENDERER = "RENDERER"
        private const val CELL_SUPERVISOR = "SUPERVISOR"
    }
}
