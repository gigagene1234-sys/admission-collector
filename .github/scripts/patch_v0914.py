from pathlib import Path

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
pool_path = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakSlowLanePool.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
p = pool_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

# -----------------------------------------------------------------------------
# v0.9.14: WebView renderer circuit breaker.
# Real-device v0.9.13 evidence reached 30 persisted Jinhak mission targets and 3
# confirmed targets, then recorded two slow-lane-renderer-gone failures while a
# Samsung Device Care dialog reported that the installed WebView version had
# crashed in Admission Collector. Android's termination contract requires a
# WebView whose renderer is gone to be removed/destroyed and never reused.
# v0.9.13 SlowLanePool returned true from onRenderProcessGone but then reset and
# reused that same dead WebView slot. This patch makes renderer loss recoverable,
# serializes the hidden browser lane, opens a per-session circuit breaker after
# the first renderer loss, and returns deferred mission targets to the foreground
# WebView rather than terminally failing them.
# -----------------------------------------------------------------------------

# 1) Slow lane is deliberately single-worker. Two hidden workers are unnecessary
# while the foreground WebView is also rendering and increase renderer pressure.
p = p.replace('private var maxActiveWorkers = 2', 'private var maxActiveWorkers = 1', 1)
p = p.replace('const val DEFAULT_MAX_WORKERS = 2', 'const val DEFAULT_MAX_WORKERS = 1', 1)
p = p.replace(
    '    private var replaySuccesses = 0\n    private var destroyed = false\n',
    '    private var replaySuccesses = 0\n    private var rendererGoneCount = 0\n    private var rendererCircuitOpen = false\n    private var destroyed = false\n',
    1
)

old_stats = '''    data class Stats(
        val queued: Int,
        val running: Int,
        val completed: Int,
        val failed: Int,
        val escalated: Int,
        val progressExtensions: Int,
        val replayAttempts: Int,
        val replaySuccesses: Int,
        val maxActiveWorkers: Int
    )
'''
new_stats = '''    data class Stats(
        val queued: Int,
        val running: Int,
        val completed: Int,
        val failed: Int,
        val escalated: Int,
        val progressExtensions: Int,
        val replayAttempts: Int,
        val replaySuccesses: Int,
        val maxActiveWorkers: Int,
        val rendererGoneCount: Int,
        val rendererCircuitOpen: Boolean
    )
'''
if old_stats not in p:
    raise SystemExit('SlowLane Stats anchor not found')
p = p.replace(old_stats, new_stats, 1)

old_enqueue = '''    fun enqueue(task: Task): Boolean {
        if (destroyed || !isAllowedJinhakUrl(task.targetUrl) || !isAllowedJinhakUrl(task.originUrl.ifBlank { task.targetUrl })) return false
'''
new_enqueue = '''    fun enqueue(task: Task): Boolean {
        if (destroyed || rendererCircuitOpen || !isAllowedJinhakUrl(task.targetUrl) || !isAllowedJinhakUrl(task.originUrl.ifBlank { task.targetUrl })) return false
'''
if old_enqueue not in p:
    raise SystemExit('SlowLane enqueue anchor not found')
p = p.replace(old_enqueue, new_enqueue, 1)

p = p.replace(
    '    fun hasWork(): Boolean = pending.isNotEmpty() || slots.any { it.task != null }\n',
    '    fun hasWork(): Boolean = !rendererCircuitOpen && (pending.isNotEmpty() || slots.any { it.task != null })\n',
    1
)

old_stats_return = '''    fun stats(): Stats = Stats(
        queued = pending.size,
        running = slots.count { it.task != null },
        completed = completedCount,
        failed = failedCount,
        escalated = escalatedCount,
        progressExtensions = progressExtensions,
        replayAttempts = replayAttempts,
        replaySuccesses = replaySuccesses,
        maxActiveWorkers = maxActiveWorkers
    )
'''
new_stats_return = '''    fun stats(): Stats = Stats(
        queued = pending.size,
        running = slots.count { it.task != null },
        completed = completedCount,
        failed = failedCount,
        escalated = escalatedCount,
        progressExtensions = progressExtensions,
        replayAttempts = replayAttempts,
        replaySuccesses = replaySuccesses,
        maxActiveWorkers = maxActiveWorkers,
        rendererGoneCount = rendererGoneCount,
        rendererCircuitOpen = rendererCircuitOpen
    )
'''
if old_stats_return not in p:
    raise SystemExit('SlowLane stats return anchor not found')
p = p.replace(old_stats_return, new_stats_return, 1)

# 2) Never reuse a WebView after renderer termination. Remove/destroy the dead
# instance, open a circuit breaker, and drain queued tasks back to MainActivity.
old_renderer = '''            override fun onRenderProcessGone(v: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                val task = slot.task
                if (task != null) finishFailure(slot, "slow-lane-renderer-gone")
                return true
            }
'''
new_renderer = '''            override fun onRenderProcessGone(v: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                handleRendererGone(slot)
                return true
            }
'''
if old_renderer not in p:
    raise SystemExit('SlowLane renderer callback anchor not found')
p = p.replace(old_renderer, new_renderer, 1)

finish_failure_anchor = '''    private fun finishFailure(slot: WorkerSlot, reason: String) {
        val task = slot.task ?: return
        failedCount += 1
        listener.onSlowLaneFailed(task, reason, resultStats(slot, laneSatisfied = false))
        resetSlot(slot)
        notifyStats()
        pump()
    }

'''
renderer_handler = finish_failure_anchor + '''    private fun handleRendererGone(slot: WorkerSlot) {
        val activeTask = slot.task
        val activeStats = if (activeTask != null) {
            resultStats(slot, laneSatisfied = false)
        } else {
            ResultStats(slot.id, 0L, 0, 0, false, false)
        }

        rendererGoneCount += 1
        rendererCircuitOpen = true
        slot.heartbeatGeneration += 1
        slot.task = null

        // Android WebView termination contract: this instance is dead and must never
        // be reset or reused. Remove it from both the view hierarchy and worker pool.
        runCatching { slot.webView.stopLoading() }
        runCatching { host.removeView(slot.webView) }
        runCatching { slot.webView.destroy() }
        slots.remove(slot)

        if (activeTask != null) {
            failedCount += 1
            listener.onSlowLaneFailed(activeTask, "slow-lane-renderer-gone", activeStats)
        }

        // Once one hidden renderer dies, do not create another hidden WebView in the
        // same collection session. Return every queued task to the foreground mission
        // scheduler as a recoverable circuit-open event.
        val drained = pending.toList()
        pending.clear()
        pendingKeys.clear()
        drained.forEach { task ->
            failedCount += 1
            listener.onSlowLaneFailed(
                task,
                "slow-lane-renderer-circuit-open",
                ResultStats(0, 0L, 0, 0, false, false)
            )
        }
        notifyStats()
    }

'''
if finish_failure_anchor not in p:
    raise SystemExit('SlowLane finishFailure anchor not found')
p = p.replace(finish_failure_anchor, renderer_handler, 1)

# Prevent accidental slot recreation once the circuit is open.
pump_anchor = '''    private fun pump() {
        if (destroyed) return
'''
pump_new = '''    private fun pump() {
        if (destroyed || rendererCircuitOpen) return
'''
if pump_anchor not in p:
    raise SystemExit('SlowLane pump anchor not found')
p = p.replace(pump_anchor, pump_new, 1)

# 3) MainActivity aggregate counters.
field_anchor = '    private val jinhakSameCardReplayResolutionCounts = linkedMapOf<String, Int>()\n'
field_new = field_anchor + '''    private var jinhakSlowLaneRendererFallbacks = 0
    private var jinhakSlowLaneRendererCircuitOpens = 0
'''
if field_anchor not in m:
    raise SystemExit('MainActivity v0.9.14 field anchor not found')
m = m.replace(field_anchor, field_new, 1)

# 4) If a slow-lane renderer dies, keep its target actionable and return it to
# the foreground WebView. Renderer loss is infrastructure failure, not evidence
# that the application mission itself failed.
old_failed = '''    private fun handleJinhakSlowLaneFailed(
        task: JinhakSlowLanePool.Task,
        reason: String,
        stats: JinhakSlowLanePool.ResultStats
    ) {
        jinhakSlowLaneMissionTargetIds.remove(task.id)?.let { targetId ->
            jinhakMissionTargetLedger.markFailed(targetId, reason)
        }
        jinhakSlowLaneFailed += 1
        val failureClass = reason.substringBefore(':').take(80)
        jinhakSlowLaneFailureReasons[failureClass] = (jinhakSlowLaneFailureReasons[failureClass] ?: 0) + 1
        batchErrors.put(JSONObject()
            .put("type", reason.take(120))
            .put("targetSafePath", runtimeSafePath(task.targetUrl))
            .put("source", "concurrent-slow-lane")
            .put("laneHint", task.laneHint)
            .put("elapsedMs", stats.elapsedMs)
            .put("progressEvents", stats.progressEvents))
        localRunId?.let { runId -> localStore.markDocument(runId, task.targetUrl, "error", 0, reason.take(120)) }
        cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "error", reason.take(120)) { ok -> if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1 } }
        recordRuntimeEvent("jinhak-slow-lane-failed", JSONObject()
            .put("targetSafePath", runtimeSafePath(task.targetUrl))
            .put("reason", reason.take(120))
            .put("elapsedMs", stats.elapsedMs)
            .put("progressEvents", stats.progressEvents))
        if (batchRunning && !batchPausedForLogin) handler.postDelayed({ loadNextBatchPage() }, 80L)
    }
'''
new_failed = '''    private fun handleJinhakSlowLaneFailed(
        task: JinhakSlowLanePool.Task,
        reason: String,
        stats: JinhakSlowLanePool.ResultStats
    ) {
        val failureClass = reason.substringBefore(':').take(80)
        val recoverableRendererFailure = failureClass == "slow-lane-renderer-gone" ||
            failureClass == "slow-lane-renderer-circuit-open"
        val targetId = jinhakSlowLaneMissionTargetIds.remove(task.id)
        if (targetId != null) {
            if (recoverableRendererFailure) {
                jinhakMissionTargetLedger.markRetryableFailure(targetId, failureClass)
                if (jinhakActiveMissionTargetId == targetId) jinhakActiveMissionTargetId = null
            } else {
                jinhakMissionTargetLedger.markFailed(targetId, reason)
            }
        }
        jinhakSlowLaneFailed += 1
        jinhakSlowLaneFailureReasons[failureClass] = (jinhakSlowLaneFailureReasons[failureClass] ?: 0) + 1
        batchErrors.put(JSONObject()
            .put("type", reason.take(120))
            .put("targetSafePath", runtimeSafePath(task.targetUrl))
            .put("source", "concurrent-slow-lane")
            .put("laneHint", task.laneHint)
            .put("recoverable", recoverableRendererFailure)
            .put("elapsedMs", stats.elapsedMs)
            .put("progressEvents", stats.progressEvents))
        localRunId?.let { runId -> localStore.markDocument(runId, task.targetUrl, if (recoverableRendererFailure) "pending" else "error", 0, reason.take(120)) }
        if (!recoverableRendererFailure) {
            cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "error", reason.take(120)) { ok -> if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1 } }
        }
        recordRuntimeEvent("jinhak-slow-lane-failed", JSONObject()
            .put("targetSafePath", runtimeSafePath(task.targetUrl))
            .put("reason", reason.take(120))
            .put("recoverable", recoverableRendererFailure)
            .put("elapsedMs", stats.elapsedMs)
            .put("progressEvents", stats.progressEvents))

        if (recoverableRendererFailure) {
            jinhakSlowLaneRendererFallbacks += 1
            if (failureClass == "slow-lane-renderer-circuit-open") jinhakSlowLaneRendererCircuitOpens += 1
            val fallbackMission = JinhakReportContextBridge.context(task.missionContext)
                ?: JinhakApplicationMission.fromJson(task.missionContext)
            if (fallbackMission?.identityKey != null) jinhakMissionContext = fallbackMission
            val origin = canonicalizeBatchUrl(task.originUrl.ifBlank { task.targetUrl })
            if (origin.isNotBlank()) jinhakMissionOriginRoute = origin
            jinhakMissionNeedsReturn = false
            jinhakReportBridgeContext = null
            currentBatchTarget = origin.takeIf { it.isNotBlank() } ?: currentBatchTarget
            recordRuntimeEvent("jinhak-slow-lane-renderer-fallback-main", JSONObject()
                .put("targetSafePath", runtimeSafePath(task.targetUrl))
                .put("originSafePath", runtimeSafePath(origin))
                .put("failureClass", failureClass)
                .put("missionTargetRestored", targetId != null)
                .put("hiddenRendererCircuitOpen", ::slowLanePool.isInitialized && slowLanePool.stats().rendererCircuitOpen))
            persistLiveJinhakDiagnostics("slow-lane-renderer-fallback", force = true)
            status.text = "숨김 WebView renderer 종료 감지 · slow lane을 차단하고 같은 지원안 target을 메인 WebView로 복귀합니다."
            if (batchRunning && !batchPausedForLogin) {
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin) return@postDelayed
                    val retryOrigin = currentBatchTarget
                    if (!retryOrigin.isNullOrBlank() && isProviderUrl(retryOrigin)) webView.loadUrl(retryOrigin)
                    else loadNextBatchPage()
                }, 350L)
            }
            return
        }
        if (batchRunning && !batchPausedForLogin) handler.postDelayed({ loadNextBatchPage() }, 80L)
    }
'''
if old_failed not in m:
    raise SystemExit('MainActivity slow-lane failure handler anchor not found')
m = m.replace(old_failed, new_failed, 1)

# 5) A circuit-open pool must never convert a later foreground mission to a
# queue-full terminal failure. Return that target to PENDING and its origin.
old_accept = '''            val accepted = ::slowLanePool.isInitialized && slowLanePool.enqueue(task)
            val ledgerTargetForSlowLane = jinhakActiveMissionTargetId
            if (accepted) {
'''
new_accept = '''            val slowLaneCircuitOpen = ::slowLanePool.isInitialized && slowLanePool.stats().rendererCircuitOpen
            val accepted = !slowLaneCircuitOpen && ::slowLanePool.isInitialized && slowLanePool.enqueue(task)
            val ledgerTargetForSlowLane = jinhakActiveMissionTargetId
            if (accepted) {
'''
if old_accept not in m:
    raise SystemExit('MainActivity slow-lane enqueue anchor not found')
m = m.replace(old_accept, new_accept, 1)

old_else = '''            } else {
                if (ledgerTargetForSlowLane != null) {
                    jinhakMissionTargetLedger.markFailed(ledgerTargetForSlowLane, "slow-lane-queue-full")
                    if (jinhakActiveMissionTargetId == ledgerTargetForSlowLane) jinhakActiveMissionTargetId = null
                }
                jinhakSlowLaneFailed += 1
                batchErrors.put(JSONObject()
                    .put("type", "jinhak-slow-lane-queue-full")
                    .put("targetSafePath", runtimeSafePath(target))
                    .put("currentSafePath", runtimeSafePath(current)))
                localRunId?.let { runId -> localStore.markDocument(runId, target, "error", 0, "jinhak-slow-lane-queue-full") }
            }

            // The main browser is now free to continue. A slow worker owns the deferred target.
'''
new_else = '''            } else if (slowLaneCircuitOpen) {
                if (ledgerTargetForSlowLane != null) {
                    jinhakMissionTargetLedger.markRetryableFailure(ledgerTargetForSlowLane, "slow-lane-renderer-circuit-open")
                    if (jinhakActiveMissionTargetId == ledgerTargetForSlowLane) jinhakActiveMissionTargetId = null
                }
                jinhakSlowLaneRendererCircuitOpens += 1
                val origin = canonicalizeBatchUrl(actionOrigin)
                currentBatchTarget = origin.takeIf { it.isNotBlank() } ?: currentBatchTarget
                jinhakMissionNeedsReturn = false
                jinhakReportBridgeContext = null
                recordRuntimeEvent("jinhak-slow-lane-circuit-open-main-fallback", JSONObject()
                    .put("targetSafePath", runtimeSafePath(target))
                    .put("originSafePath", runtimeSafePath(origin))
                    .put("missionTargetRestored", ledgerTargetForSlowLane != null))
                persistLiveJinhakDiagnostics("slow-lane-circuit-open", force = true)
                jinhakAbsoluteTargetKey = ""
                ++jinhakAbsoluteTargetGeneration
                runCatching { webView.stopLoading() }
                status.text = "slow lane renderer circuit이 열려 숨김 WebView를 생성하지 않습니다 · 메인 WebView에서 지원안 미션을 계속합니다."
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin) return@postDelayed
                    val retryOrigin = currentBatchTarget
                    if (!retryOrigin.isNullOrBlank() && isProviderUrl(retryOrigin)) webView.loadUrl(retryOrigin)
                    else loadNextBatchPage()
                }, 350L)
                return@postDelayed
            } else {
                if (ledgerTargetForSlowLane != null) {
                    jinhakMissionTargetLedger.markFailed(ledgerTargetForSlowLane, "slow-lane-queue-full")
                    if (jinhakActiveMissionTargetId == ledgerTargetForSlowLane) jinhakActiveMissionTargetId = null
                }
                jinhakSlowLaneFailed += 1
                batchErrors.put(JSONObject()
                    .put("type", "jinhak-slow-lane-queue-full")
                    .put("targetSafePath", runtimeSafePath(target))
                    .put("currentSafePath", runtimeSafePath(current)))
                localRunId?.let { runId -> localStore.markDocument(runId, target, "error", 0, "jinhak-slow-lane-queue-full") }
            }

            // The main browser is now free to continue. A slow worker owns the deferred target.
'''
if old_else not in m:
    raise SystemExit('MainActivity slow-lane queue-full anchor not found')
m = m.replace(old_else, new_else, 1)

# 6) v0.9.13 replay telemetry was present only in final diagnostics. Add it to
# live diagnostics too so an interrupted/crashed run is still evaluable.
live_anchor = '''                        .put("applicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))
                        .put("reportBridgeArmed", jinhakReportBridgeArmed)
'''
live_new = '''                        .put("applicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))
                        .put("sameCardReplayRetries", jinhakSameCardReplayRetries)
                        .put("sameCardReplayRecovered", jinhakSameCardReplayRecovered)
                        .put("sameCardReplayTerminalFailures", jinhakSameCardReplayTerminalFailures)
                        .put("sameCardReplayResolutionCounts", JSONObject(jinhakSameCardReplayResolutionCounts as Map<*, *>))
                        .put("reportBridgeArmed", jinhakReportBridgeArmed)
'''
if live_anchor in m:
    m = m.replace(live_anchor, live_new)

# Add renderer circuit telemetry anywhere slow lane stats are emitted.
stats_anchor = '.put("slowLaneMaxActiveWorkers", if (::slowLanePool.isInitialized) slowLanePool.stats().maxActiveWorkers else 0)'
stats_new = stats_anchor + '''
                        .put("slowLaneRendererGoneCount", if (::slowLanePool.isInitialized) slowLanePool.stats().rendererGoneCount else 0)
                        .put("slowLaneRendererCircuitOpen", if (::slowLanePool.isInitialized) slowLanePool.stats().rendererCircuitOpen else false)
                        .put("slowLaneRendererFallbacks", jinhakSlowLaneRendererFallbacks)
                        .put("slowLaneRendererCircuitOpenFallbacks", jinhakSlowLaneRendererCircuitOpens)'''
if stats_anchor not in m:
    raise SystemExit('MainActivity slow lane diagnostics anchor not found')
m = m.replace(stats_anchor, stats_new)

# 7) Version metadata.
for old, new in [
    ('private const val VERSION = "0.9.13"', 'private const val VERSION = "0.9.14"'),
    ('private const val BUILD_CODE = 109130', 'private const val BUILD_CODE = 109140'),
]:
    if old not in m:
        raise SystemExit(f'MainActivity version anchor not found: {old}')
    m = m.replace(old, new, 1)

for old, new in [
    ('versionCode = 109130', 'versionCode = 109140'),
    ('versionName = "0.9.13"', 'versionName = "0.9.14"'),
]:
    if old not in g:
        raise SystemExit(f'Gradle version anchor not found: {old}')
    g = g.replace(old, new, 1)

old_label = 'Admission Collector v0.9.13 Same-Card Mission Replay Recovery'
new_label = 'Admission Collector v0.9.14 WebView Renderer Circuit Breaker'
if old_label not in manifest:
    raise SystemExit('Manifest label anchor not found')
manifest = manifest.replace(old_label, new_label, 1)

main_path.write_text(m)
pool_path.write_text(p)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('v0.9.14 patch applied')
