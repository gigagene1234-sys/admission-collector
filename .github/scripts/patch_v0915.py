from pathlib import Path

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

# -----------------------------------------------------------------------------
# v0.9.15: Jinhak Mission Stall / Snapshot Error Circuit Fence.
#
# Real-device v0.9.14 evidence showed that the hidden-renderer circuit breaker
# successfully kept renderer loss recoverable, but later a resumed mission could
# remain on the Jinhak saved-application origin indefinitely: 7,047 attempted
# snapshots, 0 successful snapshots, 7,049 error events, 57 outstanding mission
# targets and ~4.8 hours without meaningful progress. The existing 60-second
# no-progress fence deliberately refused to act while mission targets were
# outstanding, so it could never terminate this failure mode.
#
# This patch changes only bounded mission-stall handling. It does NOT change
# identity semantics, same-card binding, lane discovery, auth, privacy, route
# scope, SlowLane worker policy, or mission-state monotonicity.
# -----------------------------------------------------------------------------

# 1) Mission-stall counters and bounded recovery state.
field_anchor = '''    private var jinhakSlowLaneRendererFallbacks = 0
    private var jinhakSlowLaneRendererCircuitOpens = 0
'''
field_new = field_anchor + '''    private var jinhakMissionStallFenceTrips = 0
    private var jinhakMissionStallRecoveryAttempts = 0
    private var jinhakMissionStallTerminalStops = 0
    private var jinhakMissionOriginSnapshotErrorStreak = 0
    private var jinhakMissionOriginSnapshotErrorTotal = 0
    private var jinhakLastMissionOriginSnapshotErrorType = ""
'''
if field_anchor not in m:
    raise SystemExit('v0.9.15 field anchor not found')
m = m.replace(field_anchor, field_new, 1)

const_anchor = '''        private const val JINHAK_NO_PROGRESS_FENCE_MS = 60_000L
        private const val JINHAK_PROGRESS_FENCE_POLL_MS = 15_000L
'''
const_new = '''        private const val JINHAK_NO_PROGRESS_FENCE_MS = 60_000L
        private const val JINHAK_PROGRESS_FENCE_POLL_MS = 15_000L
        private const val MAX_JINHAK_MISSION_STALL_RECOVERIES = 2
        private const val MAX_JINHAK_MISSION_ORIGIN_ERROR_STREAK = 5
'''
if const_anchor not in m:
    raise SystemExit('v0.9.15 constant anchor not found')
m = m.replace(const_anchor, const_new, 1)

# 2) Reset only the fast error streak on any genuine successful mission-oriented
# progress. Recovery budget is reset only by actual mission progress, not by a
# generic heartbeat/reference navigation state.
old_progress = '''    private fun noteJinhakMeaningfulProgress(reason: String, forceDiagnostics: Boolean = false) {
        if (provider != ProviderId.JINHAK) return
        jinhakLastMeaningfulProgressAtMs = System.currentTimeMillis()
        recordRuntimeEvent("jinhak-meaningful-progress", JSONObject()
            .put("reason", reason.take(80))
            .put("safePath", runtimeSafePath(webView.url ?: currentBatchTarget ?: "")))
        persistLiveJinhakDiagnostics(reason, forceDiagnostics)
    }
'''
new_progress = '''    private fun noteJinhakMeaningfulProgress(reason: String, forceDiagnostics: Boolean = false) {
        if (provider != ProviderId.JINHAK) return
        jinhakLastMeaningfulProgressAtMs = System.currentTimeMillis()
        if (reason in setOf("mission-target-confirmed", "mission-target-captured", "slow-lane-completed")) {
            jinhakMissionStallRecoveryAttempts = 0
            jinhakMissionOriginSnapshotErrorStreak = 0
        }
        recordRuntimeEvent("jinhak-meaningful-progress", JSONObject()
            .put("reason", reason.take(80))
            .put("safePath", runtimeSafePath(webView.url ?: currentBatchTarget ?: "")))
        persistLiveJinhakDiagnostics(reason, forceDiagnostics)
    }
'''
if old_progress not in m:
    raise SystemExit('v0.9.15 progress anchor not found')
m = m.replace(old_progress, new_progress, 1)

# 3) Live diagnostics must expose the exact bounded-stall state and page-state
# error classes. This closes the v0.9.14 diagnosability gap where 7k errors were
# visible in aggregate but their page-state class was absent from the live export.
live_anchor = '''                .put("referenceRepeatSkips", jinhakReferenceRepeatSkips)
                .put("noProgressFences", jinhakNoProgressFences)
                .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
'''
live_new = '''                .put("referenceRepeatSkips", jinhakReferenceRepeatSkips)
                .put("noProgressFences", jinhakNoProgressFences)
                .put("missionStallFenceTrips", jinhakMissionStallFenceTrips)
                .put("missionStallRecoveryAttempts", jinhakMissionStallRecoveryAttempts)
                .put("missionStallTerminalStops", jinhakMissionStallTerminalStops)
                .put("missionOriginSnapshotErrorStreak", jinhakMissionOriginSnapshotErrorStreak)
                .put("missionOriginSnapshotErrorTotal", jinhakMissionOriginSnapshotErrorTotal)
                .put("lastMissionOriginSnapshotErrorType", jinhakLastMissionOriginSnapshotErrorType.take(80))
                .put("jinhakPageStateErrorTypes", JSONObject(jinhakPageStateErrorTypes as Map<*, *>))
                .put("slowLaneRendererGoneCount", slowStats?.rendererGoneCount ?: 0)
                .put("slowLaneRendererCircuitOpen", slowStats?.rendererCircuitOpen ?: false)
                .put("slowLaneRendererFallbacks", jinhakSlowLaneRendererFallbacks)
                .put("slowLaneRendererCircuitOpenFallbacks", jinhakSlowLaneRendererCircuitOpens)
                .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
'''
if live_anchor not in m:
    raise SystemExit('v0.9.15 live diagnostic anchor not found')
m = m.replace(live_anchor, live_new, 1)

# 4) One helper owns all mission-stall recovery/termination decisions. Recovery
# is deterministic and bounded: at most two origin reloads. If there is no
# actionable pending origin, or the recovery budget is exhausted, every remaining
# non-terminal target is terminalized as an infrastructure stall and the batch
# finishes with local errors instead of running forever.
helper_anchor = '''    private fun armJinhakProgressFence() {
'''
helper = '''    private fun recoverOrStopJinhakMissionStall(
        trigger: String,
        errorType: String? = null,
        countAsNoProgressFence: Boolean = false
    ): Boolean {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return false
        val outstanding = jinhakMissionTargetLedger.outstandingCount()
        if (outstanding <= 0) return false
        val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
        if (slowWork || jinhakAgentActionInFlight || batchCollecting) return false

        jinhakMissionStallFenceTrips += 1
        if (countAsNoProgressFence) jinhakNoProgressFences += 1
        val pendingBefore = jinhakMissionTargetLedger.pendingCount()
        val preferredIdentity = jinhakMissionContext?.identityKey
        val origin = jinhakMissionTargetLedger.originForNextPending(preferredIdentity)
        val now = System.currentTimeMillis()

        if (jinhakMissionStallRecoveryAttempts < MAX_JINHAK_MISSION_STALL_RECOVERIES && !origin.isNullOrBlank()) {
            jinhakMissionStallRecoveryAttempts += 1
            val attempt = jinhakMissionStallRecoveryAttempts
            batchErrors.put(JSONObject()
                .put("type", "jinhak-mission-stall-recovery")
                .put("trigger", trigger.take(80))
                .put("errorType", errorType ?: JSONObject.NULL)
                .put("attempt", attempt)
                .put("maxAttempts", MAX_JINHAK_MISSION_STALL_RECOVERIES)
                .put("outstanding", outstanding)
                .put("pending", pendingBefore)
                .put("originSafePath", runtimeSafePath(origin)))
            localRunId?.let { runId ->
                localStore.markDocument(runId, origin, "pending", attempt, "jinhak-mission-stall-recovery")
            }
            jinhakMissionOriginSnapshotErrorStreak = 0
            jinhakAgentActionInFlight = false
            jinhakMissionNeedsReturn = false
            jinhakReportBridgeContext = null
            batchCollecting = false
            batchNavigationWatchdogRecovery = false
            batchReadinessPolling = false
            pendingBatchPageAction = null
            activeBatchPageAction = null
            currentBatchTarget = canonicalizeBatchUrl(origin)
            jinhakAbsoluteTargetKey = ""
            ++jinhakAbsoluteTargetGeneration
            ++jinhakStallWatchdogGeneration
            runCatching { webView.stopLoading() }

            // This timestamp is a recovery checkpoint, not evidence that a target was
            // confirmed. It only prevents the 15-second fence poller from firing twice
            // while the bounded origin reload is being attempted.
            jinhakLastMeaningfulProgressAtMs = now
            recordRuntimeEvent("jinhak-mission-stall-recovery", JSONObject()
                .put("trigger", trigger.take(80))
                .put("errorType", errorType ?: JSONObject.NULL)
                .put("attempt", attempt)
                .put("outstanding", outstanding)
                .put("pending", pendingBefore)
                .put("originSafePath", runtimeSafePath(origin)))
            persistLiveJinhakDiagnostics("mission-stall-recovery", force = true)
            status.text = "진학사 미션 정체 감지 · 저장된 target은 유지하고 수시저장소 origin을 제한 재시도합니다. ($attempt/$MAX_JINHAK_MISSION_STALL_RECOVERIES)"
            handler.postDelayed({
                if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
                val retryOrigin = currentBatchTarget
                if (!retryOrigin.isNullOrBlank() && isProviderUrl(retryOrigin)) webView.loadUrl(retryOrigin)
                else loadNextBatchPage()
            }, 900L + attempt * 600L)
            return true
        }

        jinhakMissionStallTerminalStops += 1
        val reason = if (origin.isNullOrBlank()) {
            "mission-stall-no-actionable-pending-origin"
        } else {
            "mission-stall-fence-exhausted"
        }
        val terminalized = jinhakMissionTargetLedger.failAllOutstanding(reason)
        batchErrors.put(JSONObject()
            .put("type", "jinhak-mission-stall-terminal-stop")
            .put("trigger", trigger.take(80))
            .put("errorType", errorType ?: JSONObject.NULL)
            .put("reason", reason)
            .put("outstandingBeforeFence", outstanding)
            .put("pendingBeforeFence", pendingBefore)
            .put("terminalized", terminalized))
        recordRuntimeEvent("jinhak-mission-stall-terminal-stop", JSONObject()
            .put("trigger", trigger.take(80))
            .put("errorType", errorType ?: JSONObject.NULL)
            .put("reason", reason)
            .put("outstandingBeforeFence", outstanding)
            .put("terminalized", terminalized)
            .put("ledger", jinhakMissionTargetLedger.summary()))
        persistLiveJinhakDiagnostics("mission-stall-terminal-stop", force = true)
        status.text = "진학사 미션 정체 복구 한도 도달 · 남은 target을 오류로 보존하고 이번 실행을 종료합니다."
        handler.postDelayed({
            if (batchRunning && provider == ProviderId.JINHAK) finishBatch("completed-with-local-errors")
        }, 120L)
        return true
    }

''' + helper_anchor
if helper_anchor not in m:
    raise SystemExit('v0.9.15 progress fence function anchor not found')
m = m.replace(helper_anchor, helper, 1)

# 5) Existing no-progress fence used to explicitly refuse ownership while any
# mission target was outstanding. Give a stalled mission a bounded recovery path
# when no slow worker/action/snapshot currently owns it.
old_wait = '''                    } else {
                        // Mission/slow-worker work owns the target. Existing 35s slow-lane fences
                        // remain authoritative; expose the stalled state without stealing ownership.
                        persistLiveJinhakDiagnostics("progress-wait-mission", force = true)
                    }
'''
new_wait = '''                    } else if (ledgerOutstanding > 0 && !slowWork && !jinhakAgentActionInFlight && !batchCollecting) {
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
'''
if old_wait not in m:
    raise SystemExit('v0.9.15 mission wait fence anchor not found')
m = m.replace(old_wait, new_wait, 1)

# 6) Fast error circuit: the v0.9.14 loop produced multiple page-state errors per
# second. Five consecutive mission-origin errors trigger the same bounded recovery
# immediately instead of waiting 60 seconds. A successful snapshot resets streak.
error_anchor = '''                if (provider == ProviderId.JINHAK) {
                    jinhakPageStateErrorTypes[errorType] = (jinhakPageStateErrorTypes[errorType] ?: 0) + 1
                    val failedRoute = canonicalizeBatchUrl(
'''
error_new = '''                if (provider == ProviderId.JINHAK) {
                    jinhakPageStateErrorTypes[errorType] = (jinhakPageStateErrorTypes[errorType] ?: 0) + 1
                    if (jinhakMissionTargetLedger.outstandingCount() > 0) {
                        jinhakMissionOriginSnapshotErrorTotal += 1
                        jinhakMissionOriginSnapshotErrorStreak += 1
                        jinhakLastMissionOriginSnapshotErrorType = errorType.take(80)
                        if (jinhakMissionOriginSnapshotErrorStreak >= MAX_JINHAK_MISSION_ORIGIN_ERROR_STREAK &&
                            recoverOrStopJinhakMissionStall(
                                trigger = "mission-origin-snapshot-error-circuit",
                                errorType = errorType,
                                countAsNoProgressFence = false
                            )) {
                            return@collectSnapshot
                        }
                    }
                    val failedRoute = canonicalizeBatchUrl(
'''
if error_anchor not in m:
    raise SystemExit('v0.9.15 page-state error anchor not found')
m = m.replace(error_anchor, error_new, 1)

success_anchor = '''            val session = snapshot.optJSONObject("session") ?: JSONObject()
'''
success_new = '''            if (provider == ProviderId.JINHAK) {
                jinhakMissionOriginSnapshotErrorStreak = 0
            }
            val session = snapshot.optJSONObject("session") ?: JSONObject()
'''
# There are several session anchors in the file. Limit replacement to the first
# one after collectSnapshotForBatch's page-state block by using the preceding text.
collect_marker = '    private fun collectSnapshotForBatch() {'
pos = m.find(collect_marker)
if pos < 0:
    raise SystemExit('collectSnapshotForBatch marker not found')
idx = m.find(success_anchor, pos)
if idx < 0:
    raise SystemExit('v0.9.15 successful snapshot reset anchor not found')
m = m[:idx] + success_new + m[idx + len(success_anchor):]

# 7) New-batch counters reset. Mission persistence itself remains untouched.
reset_anchor = '''        jinhakSameCardReplayResolutionCounts.clear()
        if (provider == ProviderId.JINHAK && jinhakAuthVerifiedForBatch) {
'''
reset_new = '''        jinhakSameCardReplayResolutionCounts.clear()
        jinhakMissionStallFenceTrips = 0
        jinhakMissionStallRecoveryAttempts = 0
        jinhakMissionStallTerminalStops = 0
        jinhakMissionOriginSnapshotErrorStreak = 0
        jinhakMissionOriginSnapshotErrorTotal = 0
        jinhakLastMissionOriginSnapshotErrorType = ""
        if (provider == ProviderId.JINHAK && jinhakAuthVerifiedForBatch) {
'''
if reset_anchor not in m:
    raise SystemExit('v0.9.15 batch reset anchor not found')
m = m.replace(reset_anchor, reset_new, 1)

# 8) Final diagnostics and batch summary also carry the stall telemetry.
final_diag_anchor = '''                        .put("noProgressFences", jinhakNoProgressFences)
                        .put("secondsSinceMeaningfulProgress", if (jinhakLastMeaningfulProgressAtMs > 0L) (System.currentTimeMillis() - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L) / 1000.0 else JSONObject.NULL)
'''
final_diag_new = '''                        .put("noProgressFences", jinhakNoProgressFences)
                        .put("missionStallFenceTrips", jinhakMissionStallFenceTrips)
                        .put("missionStallRecoveryAttempts", jinhakMissionStallRecoveryAttempts)
                        .put("missionStallTerminalStops", jinhakMissionStallTerminalStops)
                        .put("missionOriginSnapshotErrorStreak", jinhakMissionOriginSnapshotErrorStreak)
                        .put("missionOriginSnapshotErrorTotal", jinhakMissionOriginSnapshotErrorTotal)
                        .put("lastMissionOriginSnapshotErrorType", jinhakLastMissionOriginSnapshotErrorType.take(80))
                        .put("jinhakPageStateErrorTypes", JSONObject(jinhakPageStateErrorTypes as Map<*, *>))
                        .put("secondsSinceMeaningfulProgress", if (jinhakLastMeaningfulProgressAtMs > 0L) (System.currentTimeMillis() - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L) / 1000.0 else JSONObject.NULL)
'''
if final_diag_anchor not in m:
    raise SystemExit('v0.9.15 final diagnostic anchor not found')
m = m.replace(final_diag_anchor, final_diag_new, 1)

batch_summary_anchor = '''                .put("jinhakNoProgressFences", jinhakNoProgressFences)
                .put("jinhakApplicationBoundActions", jinhakApplicationBoundActions)
'''
batch_summary_new = '''                .put("jinhakNoProgressFences", jinhakNoProgressFences)
                .put("jinhakMissionStallFenceTrips", jinhakMissionStallFenceTrips)
                .put("jinhakMissionStallRecoveryAttempts", jinhakMissionStallRecoveryAttempts)
                .put("jinhakMissionStallTerminalStops", jinhakMissionStallTerminalStops)
                .put("jinhakMissionOriginSnapshotErrorStreak", jinhakMissionOriginSnapshotErrorStreak)
                .put("jinhakMissionOriginSnapshotErrorTotal", jinhakMissionOriginSnapshotErrorTotal)
                .put("jinhakLastMissionOriginSnapshotErrorType", jinhakLastMissionOriginSnapshotErrorType.take(80))
                .put("jinhakApplicationBoundActions", jinhakApplicationBoundActions)
'''
if batch_summary_anchor not in m:
    raise SystemExit('v0.9.15 batch summary anchor not found')
m = m.replace(batch_summary_anchor, batch_summary_new, 1)

# 9) Version metadata only; no unrelated product changes.
m = m.replace('private const val VERSION = "0.9.14"', 'private const val VERSION = "0.9.15"', 1)
m = m.replace('private const val BUILD_CODE = 109140', 'private const val BUILD_CODE = 109150', 1)
g = g.replace('versionCode = 109140', 'versionCode = 109150', 1)
g = g.replace('versionName = "0.9.14"', 'versionName = "0.9.15"', 1)
manifest = manifest.replace(
    'Admission Collector v0.9.14 WebView Renderer Circuit Breaker',
    'Admission Collector v0.9.15 Mission Stall Fence',
    1
)

# Strong postconditions. Keep one-version/one-problem surface bounded.
required = {
    'version': 'private const val VERSION = "0.9.15"' in m and 'private const val BUILD_CODE = 109150' in m,
    'bounded-recovery': 'MAX_JINHAK_MISSION_STALL_RECOVERIES = 2' in m and 'recoverOrStopJinhakMissionStall' in m,
    'fast-error-circuit': 'MAX_JINHAK_MISSION_ORIGIN_ERROR_STREAK = 5' in m and 'mission-origin-snapshot-error-circuit' in m,
    'terminal-fence': 'failAllOutstanding(reason)' in m and 'jinhak-mission-stall-terminal-stop' in m,
    'live-error-types': '.put("jinhakPageStateErrorTypes", JSONObject(jinhakPageStateErrorTypes as Map<*, *>))' in m,
    'renderer-preserved': 'jinhak-slow-lane-renderer-fallback-main' in m and 'slowLaneRendererCircuitOpen' in m,
    'same-card-preserved': 'same-card-action-not-found' in m and 'MAX_JINHAK_SAME_CARD_REPLAY_ATTEMPTS = 3' in m,
    'auth-preserved': 'protected-core-stable' in m and 'scheduleJinhakLoginRecovery' in m,
    'susi-core-preserved': 'isDefaultSusiCoreTraversalUrl' in m,
}
failed = [k for k, ok in required.items() if not ok]
if failed:
    raise SystemExit('v0.9.15 postcondition failed: ' + ', '.join(failed))

main_path.write_text(m)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('Applied v0.9.15 Mission Stall Fence patch')
