from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
SLOW = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakSlowLanePool.kt'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)

m = MAIN.read_text()

m = once(m,
'''import com.admissionhub.collector.jinhak.JinhakApplicationMission
''',
'''import com.admissionhub.collector.jinhak.JinhakApplicationMission
import com.admissionhub.collector.jinhak.JinhakSlowLanePool
''', 'slow lane import')

m = once(m,
'''    private lateinit var sessionVault: SecureSessionVault
''',
'''    private lateinit var sessionVault: SecureSessionVault
    private lateinit var slowLaneHost: FrameLayout
    private lateinit var slowLanePool: JinhakSlowLanePool
''', 'slow lane fields')

m = once(m,
'''    private var jinhakUnboundSavedApplicationObservations = 0
''',
'''    private var jinhakUnboundSavedApplicationObservations = 0
    private var jinhakLastAgentActionLabel = ""
    private var jinhakLastAgentActionOriginRoute = ""
    private var jinhakLastAgentActionMissionContext: JinhakApplicationMission.Context? = null
    private var jinhakSlowLaneEscalated = 0
    private var jinhakSlowLaneCompleted = 0
    private var jinhakSlowLaneFailed = 0
    private var jinhakSlowLaneUserActionRequired = 0
''', 'slow lane runtime state')

m = once(m,
'''        private const val JINHAK_ABSOLUTE_TARGET_MS = 35_000L
''',
'''        private const val JINHAK_SLOW_ESCALATION_MS = 35_000L
''', '35 second threshold semantics')

m = once(m,
'''        buildUi()
        configureWebView()
''',
'''        buildUi()
        slowLanePool = JinhakSlowLanePool(this, slowLaneHost, object : JinhakSlowLanePool.Listener {
            override fun onSlowLaneCompleted(task: JinhakSlowLanePool.Task, snapshot: JSONObject, stats: JinhakSlowLanePool.ResultStats) {
                handleJinhakSlowLaneCompleted(task, snapshot, stats)
            }
            override fun onSlowLaneFailed(task: JinhakSlowLanePool.Task, reason: String, stats: JinhakSlowLanePool.ResultStats) {
                handleJinhakSlowLaneFailed(task, reason, stats)
            }
            override fun onSlowLaneStatsChanged(stats: JinhakSlowLanePool.Stats) {
                if (batchRunning && provider == ProviderId.JINHAK && stats.running + stats.queued > 0) {
                    sessionState.text = "● 로그인 유지 / 병렬 slow ${stats.running} · 대기 ${stats.queued}"
                }
            }
        })
        configureWebView()
''', 'slow lane pool init')

m = once(m,
'''            if (provider == ProviderId.JINHAK) {
                // SQLite is authoritative. Do not retain large autonomous-crawl copies in RAM.
''',
'''            if (provider == ProviderId.JINHAK) {
                if (::slowLanePool.isInitialized) slowLanePool.setMaxActiveWorkers(1)
                // SQLite is authoritative. Do not retain large autonomous-crawl copies in RAM.
''', 'memory adaptive concurrency')

m = once(m,
'''        val browserStack = FrameLayout(this).apply {
            addView(webView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(batchCover, FrameLayout.LayoutParams(
''',
'''        slowLaneHost = FrameLayout(this).apply {
            alpha = 0.01f
            isClickable = false
            isFocusable = false
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
            translationX = -10000f
            translationY = -10000f
        }
        val browserStack = FrameLayout(this).apply {
            addView(webView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(slowLaneHost, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(batchCover, FrameLayout.LayoutParams(
''', 'offscreen slow lane host')

# startBatch reset
m = once(m,
'''        jinhakUnboundSavedApplicationObservations = 0
        cloudFrontierTaskIds.clear()
''',
'''        jinhakUnboundSavedApplicationObservations = 0
        jinhakLastAgentActionLabel = ""
        jinhakLastAgentActionOriginRoute = ""
        jinhakLastAgentActionMissionContext = null
        jinhakSlowLaneEscalated = 0
        jinhakSlowLaneCompleted = 0
        jinhakSlowLaneFailed = 0
        jinhakSlowLaneUserActionRequired = 0
        if (::slowLanePool.isInitialized) {
            slowLanePool.cancelAll("new-batch-reset")
            slowLanePool.setMaxActiveWorkers(JinhakSlowLanePool.DEFAULT_MAX_WORKERS)
        }
        cloudFrontierTaskIds.clear()
''', 'batch slow lane reset')

# Replace old absolute failure watchdog with escalation.
start = m.find('    private fun armJinhakAbsoluteTargetWatchdog(expectedUrl: String) {')
end = m.find('    private fun showBatchCover()', start)
if start < 0 or end < 0:
    raise SystemExit('absolute watchdog function anchors missing')
new_watchdog = r'''    private fun armJinhakAbsoluteTargetWatchdog(expectedUrl: String) {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return
        val target = canonicalizeBatchUrl(currentBatchTarget ?: expectedUrl)
        if (target.isBlank()) return
        val key = RecordUtils.sha256(target)
        if (key == jinhakAbsoluteTargetKey) return
        jinhakAbsoluteTargetKey = key
        val generation = ++jinhakAbsoluteTargetGeneration
        val startedAt = System.currentTimeMillis()
        recordRuntimeEvent("jinhak-target-start", JSONObject()
            .put("targetSafePath", runtimeSafePath(target))
            .put("currentSafePath", runtimeSafePath(expectedUrl)))

        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
            if (generation != jinhakAbsoluteTargetGeneration || key != jinhakAbsoluteTargetKey) return@postDelayed
            val activeTarget = canonicalizeBatchUrl(currentBatchTarget ?: target)
            if (RecordUtils.sha256(activeTarget) != key) return@postDelayed

            val current = canonicalizeBatchUrl(webView.url ?: expectedUrl)
            val mission = jinhakLastAgentActionMissionContext ?: jinhakMissionContext
            val actionLabel = jinhakLastAgentActionLabel.takeIf { it.isNotBlank() }
            val actionOrigin = jinhakLastAgentActionOriginRoute.takeIf { it.isNotBlank() } ?: target
            val laneHint = jinhakSlowLaneHint(target, actionLabel)
            val priority = jinhakSlowLanePriority(laneHint, target)
            val task = JinhakSlowLanePool.Task(
                id = RecordUtils.sha256(listOf(target, actionOrigin, actionLabel ?: "", mission?.identityKey ?: "", startedAt.toString()).joinToString("|")),
                targetUrl = target,
                originUrl = actionOrigin,
                actionLabel = actionLabel,
                missionContext = mission?.toJson(),
                laneHint = laneHint,
                priority = priority,
                reason = "foreground-35s-slow-escalation"
            )
            val accepted = ::slowLanePool.isInitialized && slowLanePool.enqueue(task)
            if (accepted) {
                jinhakSlowLaneEscalated += 1
                recordRuntimeEvent("jinhak-slow-lane-escalated", JSONObject()
                    .put("targetSafePath", runtimeSafePath(target))
                    .put("currentSafePath", runtimeSafePath(current))
                    .put("elapsedMs", System.currentTimeMillis() - startedAt)
                    .put("laneHint", laneHint)
                    .put("priority", priority)
                    .put("missionBound", mission?.identityKey != null))
                localRunId?.let { runId -> localStore.markDocument(runId, target, "slow-lane", 0, null) }
            } else {
                jinhakSlowLaneFailed += 1
                batchErrors.put(JSONObject()
                    .put("type", "jinhak-slow-lane-queue-full")
                    .put("targetSafePath", runtimeSafePath(target))
                    .put("currentSafePath", runtimeSafePath(current)))
                localRunId?.let { runId -> localStore.markDocument(runId, target, "error", 0, "jinhak-slow-lane-queue-full") }
            }

            // The main browser is now free to continue. A slow worker owns the deferred target.
            batchVisited.add(target)
            batchQueued.remove(target)
            batchCollecting = false
            batchNavigationWatchdogRecovery = false
            batchReadinessPolling = false
            pendingBatchPageAction = null
            activeBatchPageAction = null
            currentBatchTarget = null
            ++jinhakStallWatchdogGeneration
            jinhakAbsoluteTargetKey = ""
            ++jinhakAbsoluteTargetGeneration
            runCatching { webView.stopLoading() }
            status.text = if (accepted) {
                "35초 경과: 느린 페이지를 병렬 slow worker로 넘기고 메인 탐색은 계속합니다."
            } else {
                "35초 경과: slow worker 대기열이 가득 차 해당 페이지를 오류로 기록하고 계속합니다."
            }
            handler.postDelayed({
                if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK) loadNextBatchPage()
            }, 220L)
        }, JINHAK_SLOW_ESCALATION_MS)
    }

    private fun jinhakSlowLaneHint(target: String, actionLabel: String?): String {
        val material = (target + " " + (actionLabel ?: "")).lowercase()
        return when {
            Regex("실제\\s*합격자|actual|passdata").containsMatchIn(material) -> "actual-admit"
            Regex("모의\\s*지원|mock").containsMatchIn(material) -> "mock-support"
            Regex("합격\\s*예측|predict").containsMatchIn(material) -> "current-prediction"
            Regex("성적|환산|score|minimum|최저").containsMatchIn(material) -> "score-analysis"
            Regex("입시\\s*결과|univ-major|univ-info|경쟁률").containsMatchIn(material) -> "university-result"
            Regex("입시\\s*전략|strategy|knowledge").containsMatchIn(material) -> "strategy"
            else -> "reference"
        }
    }

    private fun jinhakSlowLanePriority(lane: String, target: String): Int = when (lane) {
        "actual-admit" -> 120
        "mock-support" -> 116
        "current-prediction" -> 112
        "score-analysis" -> 106
        "university-result" -> 100
        "strategy" -> 70
        else -> if (JinhakSiteTopology.isCoreMissionRoute(target)) 92 else 40
    }

    private fun handleJinhakSlowLaneCompleted(
        task: JinhakSlowLanePool.Task,
        snapshot: JSONObject,
        stats: JinhakSlowLanePool.ResultStats
    ) {
        if (provider != ProviderId.JINHAK) return
        val session = snapshot.optJSONObject("session") ?: JSONObject()
        val gate = snapshot.optJSONObject("interactionGate") ?: JSONObject()
        if (session.optBoolean("needsLogin", false) || gate.optBoolean("requiresUserAction", false)) {
            jinhakSlowLaneUserActionRequired += 1
            handleJinhakSlowLaneFailed(task, "slow-lane-user-action-required", stats)
            return
        }
        runCatching {
            val adapter = ProviderRegistry.adapter(ProviderId.JINHAK)
            snapshot.put("providerPageType", adapter.classify(snapshot))
            task.missionContext?.let { snapshot.put("missionApplicationContext", JSONObject(it.toString())) }
            snapshot.put("collectionTransport", "concurrent-slow-lane")
            snapshot.put("slowLane", JSONObject()
                .put("workerId", stats.workerId)
                .put("elapsedMs", stats.elapsedMs)
                .put("progressEvents", stats.progressEvents)
                .put("replayUsed", stats.replayUsed)
                .put("laneHint", task.laneHint)
                .put("laneSatisfied", stats.laneSatisfied))

            val records = adapter.normalize(snapshot)
            val runId = localRunId ?: localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION).also { localRunId = it }
            val stored = localStore.storeRecords(runId, ProviderId.JINHAK.wireName, records)
            batchLocalRecordsPersisted += stored
            val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url", task.targetUrl)))
            localStore.markDocument(runId, task.targetUrl, "completed")
            if (navKey.isNotBlank()) localStore.markDocument(runId, navKey, "completed")
            cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "completed", null) }

            val mission = JinhakApplicationMission.fromJson(task.missionContext)
            val missionKey = mission?.identityKey
            val pageType = snapshot.optString("providerPageType")
            val resolvedLane = JinhakApplicationMission.laneForPageType(pageType).takeIf { it != "reference" } ?: task.laneHint
            if (missionKey != null && resolvedLane != "reference") {
                jinhakMissionCoverage.getOrPut(missionKey) { linkedSetOf() }.add(resolvedLane)
            }

            val capturedAt = Instant.now().toString()
            val digest = buildJinhakDigest(snapshot, records, runId, capturedAt)
            lastJinhakDigest = digest
            unifiedSessionId?.takeIf { unifiedRunning && unifiedPhase == "jinhak" }?.let { sessionId ->
                localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId)
                val safeRoute = runtimeSafePath(snapshot.optString("url", task.targetUrl))
                val explicitContext = ObservationEvidence.explicitContextFromDigest(digest)
                localStore.storeUnifiedAnalysisCapture(
                    sessionId = sessionId,
                    provider = ProviderId.JINHAK.wireName,
                    pageKey = RecordUtils.sha256(listOf(task.id, navKey, missionKey ?: "").joinToString("|")),
                    pageType = pageType,
                    payload = digest
                )
                localStore.storeObservationEvidence(
                    sessionId = sessionId,
                    runId = runId,
                    provider = ProviderId.JINHAK.wireName,
                    safeRouteKey = safeRoute,
                    pageTypeGuess = pageType,
                    pageTypeConfidence = if (pageType == "jinhak-other") 0.25 else 0.90,
                    authStateClass = "authenticated",
                    explicitContext = explicitContext,
                    evidence = digest,
                    captureVersion = VERSION
                )
                localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)
            }
            batchSnapshots.put(snapshotForLocalExport(snapshot))
            batchPageCount += 1
            jinhakSlowLaneCompleted += 1
            recordRuntimeEvent("jinhak-slow-lane-completed", JSONObject()
                .put("targetSafePath", runtimeSafePath(task.targetUrl))
                .put("pageType", pageType)
                .put("lane", resolvedLane)
                .put("elapsedMs", stats.elapsedMs)
                .put("progressEvents", stats.progressEvents)
                .put("records", records.length())
                .put("missionBound", missionKey != null))
        }.onFailure { error ->
            handleJinhakSlowLaneFailed(task, "slow-lane-persist-failure:${error.javaClass.simpleName}", stats)
            return
        }
        if (batchRunning && !batchPausedForLogin) handler.postDelayed({ loadNextBatchPage() }, 80L)
    }

    private fun handleJinhakSlowLaneFailed(
        task: JinhakSlowLanePool.Task,
        reason: String,
        stats: JinhakSlowLanePool.ResultStats
    ) {
        jinhakSlowLaneFailed += 1
        batchErrors.put(JSONObject()
            .put("type", reason.take(120))
            .put("targetSafePath", runtimeSafePath(task.targetUrl))
            .put("source", "concurrent-slow-lane")
            .put("laneHint", task.laneHint)
            .put("elapsedMs", stats.elapsedMs)
            .put("progressEvents", stats.progressEvents))
        localRunId?.let { runId -> localStore.markDocument(runId, task.targetUrl, "error", 0, reason.take(120)) }
        cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "error", reason.take(120)) }
        recordRuntimeEvent("jinhak-slow-lane-failed", JSONObject()
            .put("targetSafePath", runtimeSafePath(task.targetUrl))
            .put("reason", reason.take(120))
            .put("elapsedMs", stats.elapsedMs)
            .put("progressEvents", stats.progressEvents))
        if (batchRunning && !batchPausedForLogin) handler.postDelayed({ loadNextBatchPage() }, 80L)
    }

'''
m = m[:start] + new_watchdog + m[end:]

# Capture the application-bound replay recipe at action time.
m = once(m,
'''        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
''',
'''        jinhakLastAgentActionLabel = candidate.label
        jinhakLastAgentActionOriginRoute = route
        jinhakLastAgentActionMissionContext = actionMission ?: jinhakMissionContext
        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
''', 'agent replay recipe')

# Clear stale replay recipe when loading an unrelated queued route.
m = once(m,
'''            jinhakMissionContext = null
            jinhakMissionOriginRoute = ""
            jinhakMissionNeedsReturn = false
            currentBatchTarget = next
''',
'''            jinhakMissionContext = null
            jinhakMissionOriginRoute = ""
            jinhakMissionNeedsReturn = false
            jinhakLastAgentActionLabel = ""
            jinhakLastAgentActionOriginRoute = ""
            jinhakLastAgentActionMissionContext = null
            currentBatchTarget = next
''', 'clear replay recipe on queued route')

# Do not finish while slow workers still own tasks. Place after cloud claims are exhausted.
m = once(m,
'''        if (LOCAL_FIRST_BETA && (provider == ProviderId.ADIGA || provider == ProviderId.JINHAK)) verifyLocalCompletionOrFinish()
''',
'''        if (provider == ProviderId.JINHAK && ::slowLanePool.isInitialized && slowLanePool.hasWork()) {
            val slow = slowLanePool.stats()
            status.text = "메인 탐색 완료 · slow worker ${slow.running}개 처리 / ${slow.queued}개 대기: 병렬 작업 종료 후 최종 저장합니다."
            handler.postDelayed({ if (batchRunning && !batchPausedForLogin) loadNextBatchPage() }, 900L)
            return
        }
        if (LOCAL_FIRST_BETA && (provider == ProviderId.ADIGA || provider == ProviderId.JINHAK)) verifyLocalCompletionOrFinish()
''', 'wait for slow lane before finish')

# Stop/cancel paths.
m = once(m,
'''        disarmBatchNavigationWatchdog()
        webView.stopLoading()
''',
'''        disarmBatchNavigationWatchdog()
        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("batch-stopped")
        webView.stopLoading()
''', 'manual stop cancels slow lane')

m = once(m,
'''        disarmBatchNavigationWatchdog()
        jinhakAbsoluteTargetKey = ""
''',
'''        disarmBatchNavigationWatchdog()
        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("unified-finish")
        jinhakAbsoluteTargetKey = ""
''', 'unified finish cancels slow lane')

# Diagnostics in sync-state payload.
m = once(m,
'''                        .put("unboundSavedApplicationObservations", jinhakUnboundSavedApplicationObservations)
                        .put("applicationMissionCoverage", JSONObject().apply {
''',
'''                        .put("unboundSavedApplicationObservations", jinhakUnboundSavedApplicationObservations)
                        .put("slowLaneEscalated", jinhakSlowLaneEscalated)
                        .put("slowLaneCompleted", jinhakSlowLaneCompleted)
                        .put("slowLaneFailed", jinhakSlowLaneFailed)
                        .put("slowLaneUserActionRequired", jinhakSlowLaneUserActionRequired)
                        .put("slowLaneProgressExtensions", if (::slowLanePool.isInitialized) slowLanePool.stats().progressExtensions else 0)
                        .put("slowLaneReplayAttempts", if (::slowLanePool.isInitialized) slowLanePool.stats().replayAttempts else 0)
                        .put("slowLaneReplaySuccesses", if (::slowLanePool.isInitialized) slowLanePool.stats().replaySuccesses else 0)
                        .put("slowLaneMaxActiveWorkers", if (::slowLanePool.isInitialized) slowLanePool.stats().maxActiveWorkers else 0)
                        .put("applicationMissionCoverage", JSONObject().apply {
''', 'sync diagnostics slow lane')

# Batch JSON summary.
m = once(m,
'''                .put("jinhakUnboundSavedApplicationObservations", jinhakUnboundSavedApplicationObservations)
                .put("jinhakSecondsToFirstPopulatedStorage", if (jinhakMissionBootstrapStartedAtMs > 0L && jinhakFirstPopulatedStorageAtMs > 0L) (jinhakFirstPopulatedStorageAtMs - jinhakMissionBootstrapStartedAtMs) / 1000.0 else JSONObject.NULL)
''',
'''                .put("jinhakUnboundSavedApplicationObservations", jinhakUnboundSavedApplicationObservations)
                .put("jinhakSlowLaneEscalated", jinhakSlowLaneEscalated)
                .put("jinhakSlowLaneCompleted", jinhakSlowLaneCompleted)
                .put("jinhakSlowLaneFailed", jinhakSlowLaneFailed)
                .put("jinhakSlowLaneUserActionRequired", jinhakSlowLaneUserActionRequired)
                .put("jinhakSlowLaneProgressExtensions", if (::slowLanePool.isInitialized) slowLanePool.stats().progressExtensions else 0)
                .put("jinhakSlowLaneReplayAttempts", if (::slowLanePool.isInitialized) slowLanePool.stats().replayAttempts else 0)
                .put("jinhakSlowLaneReplaySuccesses", if (::slowLanePool.isInitialized) slowLanePool.stats().replaySuccesses else 0)
                .put("jinhakSlowLaneMaxActiveWorkers", if (::slowLanePool.isInitialized) slowLanePool.stats().maxActiveWorkers else 0)
                .put("jinhakSecondsToFirstPopulatedStorage", if (jinhakMissionBootstrapStartedAtMs > 0L && jinhakFirstPopulatedStorageAtMs > 0L) (jinhakFirstPopulatedStorageAtMs - jinhakMissionBootstrapStartedAtMs) / 1000.0 else JSONObject.NULL)
''', 'batch summary slow lane')

# Add lifecycle cleanup before buildUi.
anchor = '    private fun buildUi() {\n'
if anchor not in m:
    raise SystemExit('buildUi anchor missing')
m = m.replace(anchor, '''    override fun onDestroy() {
        if (::slowLanePool.isInitialized) slowLanePool.destroy()
        super.onDestroy()
    }

''' + anchor, 1)

MAIN.write_text(m)

# Slow pool must render with a normal viewport even though the host is translated offscreen.
s = SLOW.read_text()
s = once(s,
'''        host.addView(view, FrameLayout.LayoutParams(1, 1))
''',
'''        host.addView(view, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ))
''', 'slow worker viewport')
# Do not report an auth/consent screen as a completed slow task.
s = once(s,
'''            completedCount += 1
            listener.onSlowLaneCompleted(task, snapshot, resultStats(slot, laneSatisfied))
''',
'''            val session = snapshot.optJSONObject("session") ?: JSONObject()
            val gate = snapshot.optJSONObject("interactionGate") ?: JSONObject()
            if (session.optBoolean("needsLogin", false) || gate.optBoolean("requiresUserAction", false)) {
                slot.captureInProgress = false
                finishFailure(slot, "slow-lane-user-action-required")
                return@evaluateJavascript
            }
            completedCount += 1
            listener.onSlowLaneCompleted(task, snapshot, resultStats(slot, laneSatisfied))
''', 'slow worker user action boundary')
SLOW.write_text(s)

manifest = MANIFEST.read_text()
manifest = once(manifest,
'android:label="Admission Collector v0.8.3 Mission-First Report Recovery"',
'android:label="Admission Collector v0.8.3 Concurrent Slow Lane"',
'manifest label')
MANIFEST.write_text(manifest)

print('Applied v0.8.3 Concurrent Slow Lane: 35s escalation, 1+2 browser workers, progress heartbeat, mission replay, delayed finalization.')
