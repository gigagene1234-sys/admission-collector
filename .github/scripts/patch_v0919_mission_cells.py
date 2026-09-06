from pathlib import Path

MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
GRADLE = Path('app/build.gradle.kts')
MANIFEST = Path('app/src/main/AndroidManifest.xml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)


m = MAIN.read_text()
if 'private const val VERSION = "0.9.19"' in m:
    print('v0.9.19 already integrated; no-op')
    raise SystemExit(0)
if 'private const val VERSION = "0.9.18"' not in m:
    raise SystemExit('unexpected MainActivity baseline; expected v0.9.18')

m = replace_once(
    m,
    'import com.admissionhub.collector.jinhak.JinhakMissionTargetLedger\n',
    'import com.admissionhub.collector.jinhak.JinhakMissionTargetLedger\nimport com.admissionhub.collector.jinhak.JinhakMissionCellSupervisor\n',
    'cell import'
)

m = replace_once(
    m,
    '    private lateinit var slowLanePool: JinhakSlowLanePool\n',
    '    private lateinit var slowLanePool: JinhakSlowLanePool\n    private val jinhakMissionCells = JinhakMissionCellSupervisor()\n',
    'cell field'
)

m = replace_once(
    m,
    '    private fun configureWebView() {\n        runtimeRendererRecovering = false\n',
    '    private fun configureWebView() {\n        runtimeRendererRecovering = false\n        jinhakMissionCells.markRendererReady("configure-webview")\n',
    'renderer ready hook'
)

m = replace_once(
    m,
    '        jinhakAgentActionInFlight = true\n        jinhakAgentActionsExecuted += 1\n',
    '''        val actionCellToken = jinhakMissionCells.beginAction(
            targetId = ledgerTargetIdForAction ?: jinhakMissionContext?.identityKey,
            safePath = runtimeSafePath(route),
            detail = "${candidate.kind}:${candidate.label.take(48)}"
        )
        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
''',
    'action ownership start'
)

m = replace_once(
    m,
    '''        webView.evaluateJavascript(JinhakAgentNavigator.executionScript(candidate)) { encoded ->
            val result = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull() ?: JSONObject()
            jinhakAgentActionInFlight = false
            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
''',
    '''        webView.evaluateJavascript(JinhakAgentNavigator.executionScript(candidate)) { encoded ->
            val result = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull() ?: JSONObject()
            val actionCallbackAccepted = jinhakMissionCells.finishAction(
                actionCellToken,
                success = result.optBoolean("ok", false),
                reason = result.optString("reason", if (result.optBoolean("ok", false)) "ok" else "unknown-agent-action-failure")
            )
            if (!actionCallbackAccepted) {
                persistLiveJinhakDiagnostics("late-action-callback-ignored", force = true)
                return@evaluateJavascript
            }
            jinhakAgentActionInFlight = false
            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
''',
    'action callback token gate'
)

m = replace_once(
    m,
    '''    private fun collectSnapshotForBatch() {
        if (!batchRunning || batchPausedForLogin || batchCollecting) return
        batchCollecting = true
        collectSnapshot(webView) { snapshot ->
            batchCollecting = false
            if (!batchRunning || snapshot == null) return@collectSnapshot
''',
    '''    private fun collectSnapshotForBatch() {
        if (!batchRunning || batchPausedForLogin || batchCollecting) return
        val snapshotCellToken = if (provider == ProviderId.JINHAK) {
            jinhakMissionCells.beginSnapshot(
                targetId = jinhakActiveMissionTargetId ?: jinhakMissionContext?.identityKey,
                safePath = runtimeSafePath(webView.url ?: currentBatchTarget ?: ""),
                detail = "batch-snapshot"
            )
        } else null
        batchCollecting = true
        collectSnapshot(webView) { snapshot ->
            if (snapshotCellToken != null) {
                val snapshotCallbackAccepted = jinhakMissionCells.finishSnapshot(
                    snapshotCellToken,
                    success = snapshot != null,
                    reason = if (snapshot != null) "snapshot-ready" else "snapshot-null"
                )
                if (!snapshotCallbackAccepted) {
                    persistLiveJinhakDiagnostics("late-snapshot-callback-ignored", force = true)
                    return@collectSnapshot
                }
            }
            batchCollecting = false
            if (!batchRunning || snapshot == null) return@collectSnapshot
''',
    'snapshot ownership gate'
)

m = replace_once(
    m,
    '''                if (elapsed >= JINHAK_NO_PROGRESS_FENCE_MS) {
                    val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
                    val ledgerOutstanding = jinhakMissionTargetLedger.outstandingCount()
                    if (ledgerOutstanding == 0 && !slowWork && !jinhakAgentActionInFlight && !batchCollecting) {
''',
    '''                if (elapsed >= JINHAK_NO_PROGRESS_FENCE_MS) {
                    val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
                    val ledgerOutstanding = jinhakMissionTargetLedger.outstandingCount()
                    val cellExpiry = jinhakMissionCells.expireStaleOwnership(now)
                    if (cellExpiry.actionExpired) jinhakAgentActionInFlight = false
                    if (cellExpiry.snapshotExpired) batchCollecting = false
                    if (cellExpiry.expiredAny) {
                        recordRuntimeEvent("jinhak-cell-stale-ownership", cellExpiry.toJson())
                        persistLiveJinhakDiagnostics("cell-stale-ownership", force = true)
                    }
                    if (ledgerOutstanding == 0 && !slowWork && !jinhakMissionCells.hasActiveOwnership() && !jinhakAgentActionInFlight && !batchCollecting) {
''',
    'progress fence cell expiry'
)

m = replace_once(
    m,
    '''                    } else if (ledgerOutstanding > 0 && !slowWork && !jinhakAgentActionInFlight && !batchCollecting) {
                        if (!recoverOrStopJinhakMissionStall(
                                trigger = "no-progress-mission",
                                countAsNoProgressFence = true
                            )) {
                            persistLiveJinhakDiagnostics("progress-wait-mission", force = true)
                        }
                    } else {
                        // A real slow worker/action/snapshot still owns the target. Do not steal it.
                        persistLiveJinhakDiagnostics("progress-wait-mission", force = true)
                    }
''',
    '''                    } else if (ledgerOutstanding > 0) {
                        val cellBusy = jinhakMissionCells.hasActiveOwnership()
                        if (!slowWork && !cellBusy && !jinhakAgentActionInFlight && !batchCollecting) {
                            if (!recoverOrStopJinhakMissionStall(
                                    trigger = "no-progress-mission",
                                    countAsNoProgressFence = true
                                )) {
                                persistLiveJinhakDiagnostics("progress-wait-mission", force = true)
                            }
                        } else {
                            // Lower cells own their lifecycle and expose exactly what blocks recovery.
                            persistLiveJinhakDiagnostics("progress-wait-mission", force = true)
                        }
                    } else {
                        persistLiveJinhakDiagnostics("progress-wait-mission", force = true)
                    }
''',
    'progress fence ownership branch'
)

m = replace_once(
    m,
    '''        val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
        if (slowWork || jinhakAgentActionInFlight || batchCollecting) return false

        jinhakMissionStallFenceTrips += 1
''',
    '''        val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
        val cellBusy = jinhakMissionCells.hasActiveOwnership()
        if (slowWork || cellBusy || jinhakAgentActionInFlight || batchCollecting) return false

        jinhakMissionStallFenceTrips += 1
        jinhakMissionCells.invalidateAll("mission-stall-recovery:$trigger")
''',
    'stall recovery cell gate'
)

m = replace_once(
    m,
    '''            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                if (runtimeRendererRecovering) return true
                runtimeRendererRecovering = true

                val deadView = view ?: webView
''',
    '''            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                if (runtimeRendererRecovering) return true
                runtimeRendererRecovering = true
                val cellInvalidation = jinhakMissionCells.onRendererGone(
                    reason = if (detail?.didCrash() == true) "foreground-crash" else "foreground-renderer-gone"
                )
                if (cellInvalidation.actionInvalidated) jinhakAgentActionInFlight = false
                if (cellInvalidation.snapshotInvalidated) batchCollecting = false

                val deadView = view ?: webView
''',
    'renderer invalidation hook'
)

m = replace_once(
    m,
    '''        jinhakMissionStallFenceTrips = 0
        jinhakMissionStallRecoveryAttempts = 0
        jinhakMissionStallTerminalStops = 0
        jinhakMissionOriginSnapshotErrorStreak = 0
''',
    '''        jinhakMissionStallFenceTrips = 0
        jinhakMissionStallRecoveryAttempts = 0
        jinhakMissionStallTerminalStops = 0
        jinhakMissionCells.resetForRun("batch-runtime-reset")
        jinhakMissionOriginSnapshotErrorStreak = 0
''',
    'cell run reset'
)

m = replace_once(
    m,
    '''                .put("secondsSinceMeaningfulProgress", sinceProgress ?: JSONObject.NULL)
                .put("activeMissionTarget", jinhakActiveMissionTargetId != null)
''',
    '''                .put("secondsSinceMeaningfulProgress", sinceProgress ?: JSONObject.NULL)
                .put("missionCells", jinhakMissionCells.diagnostics(now))
                .put("legacyAgentActionInFlight", jinhakAgentActionInFlight)
                .put("legacyBatchCollecting", batchCollecting)
                .put("activeMissionTarget", jinhakActiveMissionTargetId != null)
''',
    'live cell diagnostics'
)

m = replace_once(
    m,
    '''                        .put("secondsSinceMeaningfulProgress", if (jinhakLastMeaningfulProgressAtMs > 0L) (System.currentTimeMillis() - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L) / 1000.0 else JSONObject.NULL)
                        .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
''',
    '''                        .put("secondsSinceMeaningfulProgress", if (jinhakLastMeaningfulProgressAtMs > 0L) (System.currentTimeMillis() - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L) / 1000.0 else JSONObject.NULL)
                        .put("missionCells", jinhakMissionCells.diagnostics(System.currentTimeMillis()))
                        .put("legacyAgentActionInFlight", jinhakAgentActionInFlight)
                        .put("legacyBatchCollecting", batchCollecting)
                        .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
''',
    'final cell diagnostics'
)

m = replace_once(m, 'private const val VERSION = "0.9.18"', 'private const val VERSION = "0.9.19"', 'version')
m = replace_once(m, 'private const val BUILD_CODE = 109180', 'private const val BUILD_CODE = 109190', 'build code')
MAIN.write_text(m)

g = GRADLE.read_text()
g = replace_once(g, 'versionCode = 109180', 'versionCode = 109190', 'gradle version code')
g = replace_once(g, 'versionName = "0.9.18"', 'versionName = "0.9.19"', 'gradle version name')
GRADLE.write_text(g)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.18 Auth Proof Resume Gate',
    'Admission Collector v0.9.19 Mission Cell Ownership',
    'manifest label'
)
MANIFEST.write_text(manifest)

print('v0.9.19 Mission Cell Ownership integration patch applied')
