from pathlib import Path

MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
STORE = Path('app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt')
TOPO = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt')
GRADLE = Path('app/build.gradle.kts')
MANIFEST = Path('app/src/main/AndroidManifest.xml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


main = MAIN.read_text()

# Runtime fence state. These counters are deliberately route/state based rather than
# timer-only so a dynamic reference page cannot keep resetting the existing 35s target watchdog.
main = replace_once(
    main,
    '    private var jinhakGenericActionsExecuted = 0\n',
    '    private var jinhakGenericActionsExecuted = 0\n'
    '    private val jinhakReferenceRouteCaptureCounts = linkedMapOf<String, Int>()\n'
    '    private var jinhakReferenceRepeatSkips = 0\n'
    '    private var jinhakNoProgressFences = 0\n'
    '    private var jinhakLastMeaningfulProgressAtMs = 0L\n'
    '    private var jinhakProgressFenceGeneration = 0\n'
    '    private var jinhakLastLiveDiagnosticsAtMs = 0L\n',
    'stall fence fields'
)

main = replace_once(
    main,
    '        private const val MAX_JINHAK_MISSION_ACTIONS = 220\n',
    '        private const val MAX_JINHAK_MISSION_ACTIONS = 220\n'
    '        private const val MAX_JINHAK_REFERENCE_ROUTE_CAPTURES = 2\n'
    '        private const val JINHAK_NO_PROGRESS_FENCE_MS = 60_000L\n'
    '        private const val JINHAK_PROGRESS_FENCE_POLL_MS = 15_000L\n'
    '        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L\n',
    'stall fence constants'
)
main = replace_once(
    main,
    '        private const val VERSION = "0.8.8"\n        private const val BUILD_CODE = 10880\n',
    '        private const val VERSION = "0.8.9"\n        private const val BUILD_CODE = 10890\n',
    'main version'
)

main = replace_once(
    main,
    '        jinhakGenericActionsExecuted = 0\n',
    '        jinhakGenericActionsExecuted = 0\n'
    '        jinhakReferenceRouteCaptureCounts.clear()\n'
    '        jinhakReferenceRepeatSkips = 0\n'
    '        jinhakNoProgressFences = 0\n'
    '        jinhakLastMeaningfulProgressAtMs = if (provider == ProviderId.JINHAK) System.currentTimeMillis() else 0L\n'
    '        jinhakLastLiveDiagnosticsAtMs = 0L\n'
    '        ++jinhakProgressFenceGeneration\n',
    'reset stall fence state'
)

main = replace_once(
    main,
    '    private fun beginBatchNavigation(runId: String?) {\n        enqueueProviderSeeds()\n',
    '    private fun beginBatchNavigation(runId: String?) {\n'
    '        if (provider == ProviderId.JINHAK) armJinhakProgressFence()\n'
    '        enqueueProviderSeeds()\n',
    'arm global Jinhak progress fence'
)

# Add the progress/diagnostic helpers immediately before the existing navigation watchdogs.
watchdog_anchor = '    private fun armBatchNavigationWatchdog(expectedUrl: String) {\n'
if '    private fun persistLiveJinhakDiagnostics(trigger: String, force: Boolean = false) {' not in main:
    helper = r'''    private fun isJinhakLowValueReferencePageType(pageType: String): Boolean = pageType in setOf(
        "jinhak-recommended-university",
        "jinhak-admission-strategy",
        "jinhak-admission-knowledge",
        "jinhak-admission-feature",
        "jinhak-editorial-content",
        "jinhak-media-content",
        "jinhak-home",
        "jinhak-other"
    )

    private fun noteJinhakMeaningfulProgress(reason: String, forceDiagnostics: Boolean = false) {
        if (provider != ProviderId.JINHAK) return
        jinhakLastMeaningfulProgressAtMs = System.currentTimeMillis()
        recordRuntimeEvent("jinhak-meaningful-progress", JSONObject()
            .put("reason", reason.take(80))
            .put("safePath", runtimeSafePath(webView.url ?: currentBatchTarget ?: "")))
        persistLiveJinhakDiagnostics(reason, forceDiagnostics)
    }

    private fun persistLiveJinhakDiagnostics(trigger: String, force: Boolean = false) {
        if (provider != ProviderId.JINHAK || !unifiedRunning || unifiedPhase != "jinhak") return
        val sessionId = unifiedSessionId ?: return
        val now = System.currentTimeMillis()
        if (!force && now - jinhakLastLiveDiagnosticsAtMs < JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS) return
        jinhakLastLiveDiagnosticsAtMs = now
        val slowStats = if (::slowLanePool.isInitialized) slowLanePool.stats() else null
        val sinceProgress = if (jinhakLastMeaningfulProgressAtMs > 0L) {
            ((now - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L)) / 1000.0
        } else null
        localStore.recordSyncState(
            sessionId,
            "JINHAK_CRAWL_DIAGNOSTICS",
            ProviderId.JINHAK.wireName,
            JSONObject()
                .put("live", true)
                .put("trigger", trigger.take(80))
                .put("attemptedSnapshots", batchPageCount)
                .put("successfulSnapshots", batchSnapshots.length())
                .put("errorEvents", batchErrors.length())
                .put("agentActionsExecuted", jinhakAgentActionsExecuted)
                .put("missionActionsExecuted", jinhakMissionActionsExecuted)
                .put("genericActionsExecuted", jinhakGenericActionsExecuted)
                .put("missionActionLimit", MAX_JINHAK_MISSION_ACTIONS)
                .put("genericActionLimit", MAX_JINHAK_GENERIC_ACTIONS)
                .put("applicationAnchorActionsPromoted", jinhakMissionAnchorPromotedKeys.size)
                .put("applicationAnchorStructuredBindings", jinhakMissionAnchorStructuredKeys.size)
                .put("applicationAnchorActionsParsed", jinhakMissionAnchorParsedKeys.size)
                .put("applicationAnchorActionsAttempted", jinhakMissionAnchorActionsAttempted)
                .put("applicationAnchorActionsClicked", jinhakMissionAnchorClickedKeys.size)
                .put("applicationAnchorReportConfirmed", jinhakReportConfirmedKeys.size)
                .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
                .put("missionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                .put("missionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("referenceRoutesTracked", jinhakReferenceRouteCaptureCounts.size)
                .put("referenceRepeatSkips", jinhakReferenceRepeatSkips)
                .put("noProgressFences", jinhakNoProgressFences)
                .put("secondsSinceMeaningfulProgress", sinceProgress ?: JSONObject.NULL)
                .put("activeMissionTarget", jinhakActiveMissionTargetId != null)
                .put("slowLaneRunning", slowStats?.running ?: 0)
                .put("slowLaneQueued", slowStats?.queued ?: 0)
                .put("safePath", runtimeSafePath(webView.url ?: currentBatchTarget ?: "")),
            false,
            updateOrchestrator = false
        )
    }

    private fun armJinhakProgressFence() {
        if (provider != ProviderId.JINHAK) return
        if (jinhakLastMeaningfulProgressAtMs == 0L) jinhakLastMeaningfulProgressAtMs = System.currentTimeMillis()
        val generation = ++jinhakProgressFenceGeneration
        val poller = object : Runnable {
            override fun run() {
                if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || generation != jinhakProgressFenceGeneration) return
                val now = System.currentTimeMillis()
                val elapsed = now - jinhakLastMeaningfulProgressAtMs
                if (elapsed >= JINHAK_NO_PROGRESS_FENCE_MS) {
                    val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
                    val ledgerOutstanding = jinhakMissionTargetLedger.outstandingCount()
                    if (ledgerOutstanding == 0 && !slowWork && !jinhakAgentActionInFlight && !batchCollecting) {
                        val stalled = canonicalizeBatchUrl(webView.url ?: currentBatchTarget ?: "")
                        jinhakNoProgressFences += 1
                        batchErrors.put(JSONObject()
                            .put("type", "jinhak-no-progress-fence")
                            .put("safePath", runtimeSafePath(stalled))
                            .put("elapsedMs", elapsed))
                        localRunId?.let { runId ->
                            if (stalled.isNotBlank()) localStore.markDocument(runId, stalled, "error", 0, "jinhak-no-progress-fence")
                        }
                        if (stalled.isNotBlank()) {
                            batchVisited.add(stalled)
                            batchQueued.remove(stalled)
                        }
                        currentBatchTarget = null
                        pendingBatchPageAction = null
                        activeBatchPageAction = null
                        batchCollecting = false
                        batchNavigationWatchdogRecovery = false
                        jinhakAbsoluteTargetKey = ""
                        ++jinhakAbsoluteTargetGeneration
                        ++jinhakStallWatchdogGeneration
                        runCatching { webView.stopLoading() }
                        jinhakLastMeaningfulProgressAtMs = now
                        recordRuntimeEvent("jinhak-no-progress-fence", JSONObject()
                            .put("safePath", runtimeSafePath(stalled))
                            .put("elapsedMs", elapsed)
                            .put("referencePageType", lastJinhakDigest.optString("pageType")))
                        persistLiveJinhakDiagnostics("no-progress-fence", force = true)
                        status.text = "60초 동안 새 수집 진전이 없어 현재 일반 탐색 페이지를 종료하고 다음 대상으로 진행합니다."
                        handler.postDelayed({ if (batchRunning && !batchPausedForLogin) loadNextBatchPage() }, 220L)
                    } else {
                        // Mission/slow-worker work owns the target. Existing 35s slow-lane fences
                        // remain authoritative; expose the stalled state without stealing ownership.
                        persistLiveJinhakDiagnostics("progress-wait-mission", force = true)
                    }
                } else {
                    persistLiveJinhakDiagnostics("progress-heartbeat")
                }
                handler.postDelayed(this, JINHAK_PROGRESS_FENCE_POLL_MS)
            }
        }
        handler.postDelayed(poller, JINHAK_PROGRESS_FENCE_POLL_MS)
    }

'''
    if watchdog_anchor not in main:
        raise SystemExit('watchdog insertion anchor not found')
    main = main.replace(watchdog_anchor, helper + watchdog_anchor, 1)

# Current unified status text should describe the narrowed high-value route order.
main = replace_once(
    main,
    '        status.text = "통합 수집 2/2 · 진학사 목적형 분석 준비: 저장대학→합격예측→모의지원→실제합격자→대학입결→전략 순으로 우선 탐색합니다."\n',
    '        status.text = "통합 수집 2/2 · 진학사 목적형 분석 준비: 저장대학→합격예측→모의지원→실제합격자→대학입결→성적/최저 순으로 우선 탐색합니다."\n',
    'Jinhak mission status text'
)

# Recommendation cards are useful evidence but must never become persistent application ledger origins.
main = replace_once(
    main,
    '                val ledgerAdded = jinhakMissionTargetLedger.capture(ledgerOrigin, parsedMissionCandidates)\n',
    '                val ledgerAdded = if (pageTypeNow == "jinhak-recommended-university") {\n'
    '                    recordRuntimeEvent("jinhak-recommendation-ledger-suppressed", JSONObject()\n'
    '                        .put("safePath", runtimeSafePath(ledgerOrigin))\n'
    '                        .put("candidateCount", parsedMissionCandidates.size))\n'
    '                    0\n'
    '                } else {\n'
    '                    jinhakMissionTargetLedger.capture(ledgerOrigin, parsedMissionCandidates)\n'
    '                }\n',
    'recommendation ledger suppression'
)
main = replace_once(
    main,
    '                if (ledgerAdded > 0) {\n                    recordRuntimeEvent("jinhak-mission-targets-captured", JSONObject()\n',
    '                if (ledgerAdded > 0) {\n'
    '                    noteJinhakMeaningfulProgress("mission-target-captured", forceDiagnostics = true)\n'
    '                    recordRuntimeEvent("jinhak-mission-targets-captured", JSONObject()\n',
    'mission target progress note'
)

# Route-count fence and recommendation action suppression are based on page type + safe route,
# not cross-card inference. The first two low-value captures are retained as evidence.
main = replace_once(
    main,
    '            var jinhakExpansionStateKey: String? = null\n            var jinhakExpandOutgoingLinks = true\n',
    '            var jinhakExpansionStateKey: String? = null\n'
    '            var jinhakExpandOutgoingLinks = true\n'
    '            var jinhakAllowAgentAction = true\n',
    'agent action gating variable'
)

old_expansion = '''                    jinhakExpansionStateKey = expansionIdentity.observationId
                    jinhakExpandOutgoingLinks = jinhakExpandedNavigationStates.add(expansionIdentity.observationId)
                    if (jinhakExpandOutgoingLinks) {
                        jinhakUniqueNavigationStates += 1
                    } else {
                        jinhakRepeatedNavigationStateSkips += 1
                        recordRuntimeEvent("jinhak-repeat-state-expansion-skip", JSONObject()
                            .put("safePath", safeRoute)
                            .put("pageType", snapshot.optString("providerPageType")))
                    }
'''
new_expansion = '''                    jinhakExpansionStateKey = expansionIdentity.observationId
                    jinhakExpandOutgoingLinks = jinhakExpandedNavigationStates.add(expansionIdentity.observationId)
                    val routeCaptureCount = (jinhakReferenceRouteCaptureCounts[safeRoute] ?: 0) + 1
                    jinhakReferenceRouteCaptureCounts[safeRoute] = routeCaptureCount
                    val lowValueReference = isJinhakLowValueReferencePageType(snapshot.optString("providerPageType"))
                    if (snapshot.optString("providerPageType") == "jinhak-recommended-university") {
                        jinhakAllowAgentAction = false
                    }
                    if (lowValueReference && routeCaptureCount > MAX_JINHAK_REFERENCE_ROUTE_CAPTURES &&
                        jinhakMissionTargetLedger.outstandingCount() == 0 && jinhakMissionContext?.identityKey == null) {
                        jinhakExpandOutgoingLinks = false
                        jinhakAllowAgentAction = false
                        jinhakReferenceRepeatSkips += 1
                        recordRuntimeEvent("jinhak-reference-route-repeat-skip", JSONObject()
                            .put("safePath", safeRoute)
                            .put("pageType", snapshot.optString("providerPageType"))
                            .put("captureCount", routeCaptureCount))
                    }
                    if (jinhakExpandOutgoingLinks) {
                        jinhakUniqueNavigationStates += 1
                        noteJinhakMeaningfulProgress("unique-navigation-state")
                    } else {
                        jinhakRepeatedNavigationStateSkips += 1
                        recordRuntimeEvent("jinhak-repeat-state-expansion-skip", JSONObject()
                            .put("safePath", safeRoute)
                            .put("pageType", snapshot.optString("providerPageType")))
                    }
'''
main = replace_once(main, old_expansion, new_expansion, 'reference repeat fence')

main = replace_once(
    main,
    '                    localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)\n',
    '                    localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)\n'
    '                    persistLiveJinhakDiagnostics("capture")\n',
    'live diagnostics after capture'
)

main = replace_once(
    main,
    '            if (provider == ProviderId.JINHAK && activeAction == null && maybeExecuteJinhakAgentAction(snapshot, jinhakExpansionStateKey)) {\n',
    '            if (provider == ProviderId.JINHAK && activeAction == null && jinhakAllowAgentAction && maybeExecuteJinhakAgentAction(snapshot, jinhakExpansionStateKey)) {\n',
    'agent gating usage'
)

# Confirmations/clicks are meaningful mission progress and must refresh the global fence.
main = replace_once(
    main,
    '                            if (ledgerConfirmed) {\n                                recordRuntimeEvent("jinhak-mission-target-confirmed", JSONObject()\n',
    '                            if (ledgerConfirmed) {\n'
    '                                noteJinhakMeaningfulProgress("mission-target-confirmed", forceDiagnostics = true)\n'
    '                                recordRuntimeEvent("jinhak-mission-target-confirmed", JSONObject()\n',
    'report confirmation progress note'
)
main = replace_once(
    main,
    '            if (result.optBoolean("ok", false)) {\n                if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markClicked(ledgerTargetIdForAction)\n',
    '            if (result.optBoolean("ok", false)) {\n'
    '                if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markClicked(ledgerTargetIdForAction)\n'
    '                noteJinhakMeaningfulProgress("agent-click", forceDiagnostics = true)\n',
    'agent click progress note'
)

main = replace_once(
    main,
    '            jinhakSlowLaneCompleted += 1\n',
    '            jinhakSlowLaneCompleted += 1\n'
    '            noteJinhakMeaningfulProgress("slow-lane-completed", forceDiagnostics = true)\n',
    'slow lane progress note'
)

# Finished diagnostics retain the existing rich summary and add the new fence telemetry.
main = replace_once(
    main,
    '                        .put("genericActionLimit", MAX_JINHAK_GENERIC_ACTIONS)\n',
    '                        .put("genericActionLimit", MAX_JINHAK_GENERIC_ACTIONS)\n'
    '                        .put("referenceRoutesTracked", jinhakReferenceRouteCaptureCounts.size)\n'
    '                        .put("referenceRepeatSkips", jinhakReferenceRepeatSkips)\n'
    '                        .put("noProgressFences", jinhakNoProgressFences)\n'
    '                        .put("secondsSinceMeaningfulProgress", if (jinhakLastMeaningfulProgressAtMs > 0L) (System.currentTimeMillis() - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L) / 1000.0 else JSONObject.NULL)\n',
    'final stall diagnostics'
)
main = replace_once(
    main,
    '                .put("jinhakGenericActionsExecuted", jinhakGenericActionsExecuted)\n',
    '                .put("jinhakGenericActionsExecuted", jinhakGenericActionsExecuted)\n'
    '                .put("jinhakReferenceRepeatSkips", jinhakReferenceRepeatSkips)\n'
    '                .put("jinhakNoProgressFences", jinhakNoProgressFences)\n',
    'batch stall diagnostics'
)

MAIN.write_text(main)


store = STORE.read_text()
old_signature = '''    fun recordSyncState(
        sessionId: String,
        state: String,
        provider: String?,
        detail: JSONObject,
        requiresUserAction: Boolean
    ) {
'''
new_signature = '''    fun recordSyncState(
        sessionId: String,
        state: String,
        provider: String?,
        detail: JSONObject,
        requiresUserAction: Boolean,
        updateOrchestrator: Boolean = true
    ) {
'''
store = replace_once(store, old_signature, new_signature, 'recordSyncState optional orchestrator')
old_session_update = '''        val session = ContentValues().apply {
            put("orchestrator_state", state)
            put("requires_user_action", if (requiresUserAction) 1 else 0)
            put("updated_at", now)
        }
        writableDatabase.update("unified_sessions", session, "session_id=?", arrayOf(sessionId))
'''
new_session_update = '''        val session = ContentValues().apply {
            if (updateOrchestrator) {
                put("orchestrator_state", state)
                put("requires_user_action", if (requiresUserAction) 1 else 0)
            }
            put("updated_at", now)
        }
        writableDatabase.update("unified_sessions", session, "session_id=?", arrayOf(sessionId))
'''
store = replace_once(store, old_session_update, new_session_update, 'diagnostic state must not replace orchestrator')
STORE.write_text(store)


topo = TOPO.read_text()
topo = replace_once(
    topo,
    '    RECOMMENDATION("recommendation", 82),\n',
    '    RECOMMENDATION("recommendation", 48),\n',
    'recommendation priority'
)
topo = topo.replace(
    ' * result/criteria -> relevant strategy/knowledge. Low-value media stays reachable evidence,\n * but never outranks an unfinished application mission.\n',
    ' * result/criteria -> relevant strategy/knowledge. Recommendation discovery is retained as\n * optional evidence, but is no longer a core mission route and never outranks saved applications.\n',
    1
)
TOPO.write_text(topo)


gradle = GRADLE.read_text()
gradle = replace_once(
    gradle,
    '        versionCode = 10880\n        versionName = "0.8.8"\n',
    '        versionCode = 10890\n        versionName = "0.8.9"\n',
    'gradle version'
)
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Collector v0.8.8 Unique Container Mission Binding"',
    'android:label="Admission Collector v0.8.9 Mission Stall Fence"',
    'manifest label'
)
MANIFEST.write_text(manifest)

print('v0.8.9 patch applied')
