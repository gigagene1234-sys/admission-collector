from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)


m = MAIN.read_text()

m = replace_once(
    m,
    'import com.admissionhub.collector.jinhak.JinhakMissionLaneSequencer\n',
    'import com.admissionhub.collector.jinhak.JinhakMissionLaneSequencer\nimport com.admissionhub.collector.jinhak.JinhakMissionTargetLedger\n',
    'mission ledger import'
)

m = replace_once(
    m,
    '    private val jinhakMissionCoverage = linkedMapOf<String, MutableSet<String>>()\n',
    '    private val jinhakMissionCoverage = linkedMapOf<String, MutableSet<String>>()\n'
    '    private val jinhakMissionTargetLedger = JinhakMissionTargetLedger()\n'
    '    private var jinhakActiveMissionTargetId: String? = null\n'
    '    private val jinhakSlowLaneMissionTargetIds = linkedMapOf<String, String>()\n',
    'mission ledger fields'
)

m = replace_once(m, '        private const val MAX_JINHAK_AGENT_ACTIONS = 180\n', '        private const val MAX_JINHAK_AGENT_ACTIONS = 260\n', 'mission action cap')
m = replace_once(m, '        private const val VERSION = "0.8.5"\n', '        private const val VERSION = "0.8.6"\n', 'collector version')
m = replace_once(m, '        private const val BUILD_CODE = 10850\n', '        private const val BUILD_CODE = 10860\n', 'build code')

m = replace_once(
    m,
    '        jinhakMissionCoverage.clear()\n        jinhakMissionAnchorDiscoveredKeys.clear()\n',
    '        jinhakMissionCoverage.clear()\n'
    '        jinhakMissionTargetLedger.clear()\n'
    '        jinhakActiveMissionTargetId = null\n'
    '        jinhakSlowLaneMissionTargetIds.clear()\n'
    '        jinhakMissionAnchorDiscoveredKeys.clear()\n',
    'mission ledger reset'
)

old_bridge_confirm = '''                        if (bridgeMission?.identityKey != null && lane != "reference" && jinhakReportConfirmedKeys.add(confirmationKey)) {
                            jinhakReportBridgeConfirmed += 1
                        }
'''
new_bridge_confirm = '''                        if (bridgeMission?.identityKey != null && lane != "reference" && jinhakReportConfirmedKeys.add(confirmationKey)) {
                            jinhakReportBridgeConfirmed += 1
                            val ledgerConfirmed = jinhakMissionTargetLedger.markConfirmed(
                                jinhakActiveMissionTargetId,
                                bridgeMission.identityKey,
                                lane
                            )
                            if (ledgerConfirmed) {
                                recordRuntimeEvent("jinhak-mission-target-confirmed", JSONObject()
                                    .put("applicationIdentityHash", bridgeMission.identityKey.take(24))
                                    .put("lane", lane)
                                    .put("safePath", runtimeSafePath(snapshot.optString("url"))))
                                jinhakActiveMissionTargetId = null
                            }
                        }
'''
m = replace_once(m, old_bridge_confirm, new_bridge_confirm, 'report bridge ledger confirmation')

old_candidate_parse = '''                JinhakAgentNavigator.candidates(snapshot).filter { it.promotedMissionAction && it.applicationContext?.identityKey != null }.forEach { candidate ->
                    val key = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
                    jinhakMissionAnchorParsedKeys.add(key)
                }
'''
new_candidate_parse = '''                val parsedMissionCandidates = JinhakAgentNavigator.candidates(snapshot)
                val ledgerOrigin = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                val ledgerAdded = jinhakMissionTargetLedger.capture(ledgerOrigin, parsedMissionCandidates)
                if (ledgerAdded > 0) {
                    recordRuntimeEvent("jinhak-mission-targets-captured", JSONObject()
                        .put("added", ledgerAdded)
                        .put("pending", jinhakMissionTargetLedger.pendingCount())
                        .put("safePath", runtimeSafePath(ledgerOrigin)))
                }
                parsedMissionCandidates.filter { it.promotedMissionAction && it.applicationContext?.identityKey != null }.forEach { candidate ->
                    val key = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
                    jinhakMissionAnchorParsedKeys.add(key)
                }
'''
m = replace_once(m, old_candidate_parse, new_candidate_parse, 'capture persistent mission targets')

start = m.find('    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject, expansionStateKey: String?): Boolean {')
end = m.find('    private fun maybeReturnToJinhakMissionOrigin(snapshot: JSONObject): Boolean {', start)
if start < 0 or end < 0 or end <= start:
    raise SystemExit('agent action function boundaries not found')
new_agent_function = r'''    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject, expansionStateKey: String?): Boolean {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return false
        if (jinhakAgentActionInFlight) return false
        if (jinhakAgentActionsExecuted >= MAX_JINHAK_AGENT_ACTIONS) {
            if (jinhakMissionTargetLedger.hasActionablePending()) {
                jinhakMissionTargetLedger.failAllPending("agent-action-limit")
                recordRuntimeEvent("jinhak-mission-target-limit", JSONObject()
                    .put("limit", MAX_JINHAK_AGENT_ACTIONS)
                    .put("ledger", jinhakMissionTargetLedger.summary()))
            }
            return false
        }

        val route = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        fun actionKeyFor(action: JinhakAgentNavigator.Candidate): String = RecordUtils.sha256(
            "${expansionStateKey ?: runtimeSafePath(route)}|${JinhakAgentNavigator.key(route, action)}"
        )

        val liveCandidates = JinhakAgentNavigator.candidates(snapshot)
        val candidates = liveCandidates.filterNot { jinhakAgentActionSeen.contains(actionKeyFor(it)) }
        val currentMissionKey = jinhakMissionContext?.identityKey
        val covered = currentMissionKey?.let { jinhakMissionCoverage[it]?.toSet() }.orEmpty()
        val atMissionOrigin = currentMissionKey != null && jinhakMissionOriginRoute.isNotBlank() &&
            canonicalizeBatchUrl(route) == canonicalizeBatchUrl(jinhakMissionOriginRoute)

        jinhakMissionTargetLedger.reconcileCoveredLanes(currentMissionKey, covered)
        var ledgerTarget = when {
            atMissionOrigin && currentMissionKey != null ->
                jinhakMissionTargetLedger.nextPendingAtOrigin(route, currentMissionKey, covered)
            currentMissionKey == null ->
                jinhakMissionTargetLedger.nextPendingAtOrigin(route, null, emptySet())
            else -> null
        }
        var exhaustedCurrentMission = false

        val selection = when {
            ledgerTarget != null -> JinhakMissionLaneSequencer.Selection(
                candidate = ledgerTarget!!.candidate(),
                missionExhaustedAtOrigin = false,
                requestedLane = ledgerTarget!!.lane
            )
            atMissionOrigin && currentMissionKey != null && jinhakMissionTargetLedger.hasMission(currentMissionKey) -> {
                exhaustedCurrentMission = true
                ledgerTarget = jinhakMissionTargetLedger.nextPendingAtOrigin(route, null, emptySet())
                if (ledgerTarget != null) {
                    JinhakMissionLaneSequencer.Selection(
                        candidate = ledgerTarget!!.candidate(),
                        missionExhaustedAtOrigin = true,
                        requestedLane = ledgerTarget!!.lane
                    )
                } else {
                    // All captured application targets at this origin are resolved. Only now may
                    // generic read-only navigation resume; application-bound live anchors are not
                    // re-selected outside the persistent ledger.
                    val genericPool = candidates.filter { it.applicationContext?.identityKey == null }
                    val generic = JinhakMissionLaneSequencer.choose(genericPool, null, emptySet(), false)
                    JinhakMissionLaneSequencer.Selection(generic.candidate, true, generic.requestedLane)
                }
            }
            currentMissionKey == null && jinhakMissionTargetLedger.hasActionablePending() ->
                JinhakMissionLaneSequencer.Selection(null, false, "reference")
            else -> JinhakMissionLaneSequencer.choose(candidates, currentMissionKey, covered, atMissionOrigin)
        }

        if ((selection.missionExhaustedAtOrigin || exhaustedCurrentMission) && currentMissionKey != null) {
            recordRuntimeEvent("jinhak-application-mission-lanes-exhausted", JSONObject()
                .put("applicationIdentityHash", currentMissionKey.take(24))
                .put("coverageLanes", covered.size)
                .put("ledgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("safePath", runtimeSafePath(route)))
            jinhakMissionContext = null
            jinhakReportBridgeContext = null
            jinhakMissionOriginRoute = ""
            jinhakMissionNeedsReturn = false
        }

        val candidate = selection.candidate ?: return false
        val ledgerTargetIdForAction = ledgerTarget?.targetId
        jinhakActiveMissionTargetId = ledgerTargetIdForAction
        if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markAttempted(ledgerTargetIdForAction)

        if (candidate.kind == "mission-link-navigation") {
            val selectedKey = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
            jinhakMissionAnchorSelectedKeys.add(selectedKey)
        }
        val actionKey = actionKeyFor(candidate)
        jinhakAgentActionSeen.add(actionKey)

        val actionMission = candidate.applicationContext
        if (actionMission?.identityKey != null) {
            if (jinhakMissionContext?.identityKey != actionMission.identityKey) {
                jinhakMissionContext = actionMission
                jinhakMissionOriginRoute = ledgerTarget?.originRoute ?: route
            }
            jinhakMissionNeedsReturn = true
            jinhakApplicationBoundActions += 1
            jinhakMissionCoverage.getOrPut(actionMission.identityKey) { linkedSetOf() }.add("saved-application")
            recordRuntimeEvent("jinhak-application-mission-start", JSONObject()
                .put("applicationIdentityHash", actionMission.identityKey.take(24))
                .put("missionPriority", candidate.missionPriority)
                .put("requestedLane", selection.requestedLane)
                .put("ledgerTarget", ledgerTargetIdForAction != null)
                .put("safePath", runtimeSafePath(route)))
        } else if (jinhakMissionContext?.identityKey != null) {
            // A report tab may not repeat the application card. The already-bound mission stays active.
            jinhakMissionNeedsReturn = true
        }

        jinhakLastAgentActionLabel = candidate.label
        jinhakLastAgentActionOriginRoute = route
        jinhakLastAgentActionMissionContext = actionMission ?: jinhakMissionContext
        val bridgeMission = jinhakLastAgentActionMissionContext
        if (bridgeMission?.identityKey != null && JinhakReportContextBridge.isReportAction(candidate.label, candidate.kind)) {
            jinhakReportBridgeContext = JinhakReportContextBridge.arm(
                bridgeMission,
                runtimeSafePath(route),
                candidate.label,
                candidate.kind
            )
            jinhakReportBridgeArmed += 1
        }
        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
        if (candidate.kind == "mission-link-navigation") jinhakMissionAnchorActionsAttempted += 1
        currentBatchTarget = route.ifBlank { currentBatchTarget }
        status.text = "진학사 지원안 미션 ${jinhakAgentActionsExecuted}/$MAX_JINHAK_AGENT_ACTIONS · ${candidate.label.take(48)} · ledger ${jinhakMissionTargetLedger.pendingCount()}대기"
        recordRuntimeEvent("jinhak-agent-action", JSONObject()
            .put("safePath", runtimeSafePath(route))
            .put("label", candidate.label.take(80))
            .put("kind", candidate.kind)
            .put("ledgerTarget", ledgerTargetIdForAction != null)
            .put("applicationBound", jinhakMissionContext?.identityKey != null))

        webView.evaluateJavascript(JinhakAgentNavigator.executionScript(candidate)) { encoded ->
            val result = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull() ?: JSONObject()
            jinhakAgentActionInFlight = false
            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
            if (!result.optBoolean("ok", false)) {
                val rejectReason = result.optString("reason", "unknown-agent-action-failure").take(80)
                jinhakAnchorRejectReasons[rejectReason] = (jinhakAnchorRejectReasons[rejectReason] ?: 0) + 1
                if (ledgerTargetIdForAction != null) {
                    jinhakMissionTargetLedger.markFailed(ledgerTargetIdForAction, rejectReason)
                    if (jinhakActiveMissionTargetId == ledgerTargetIdForAction) jinhakActiveMissionTargetId = null
                }
                recordRuntimeEvent("jinhak-agent-action-rejected", JSONObject()
                    .put("safePath", runtimeSafePath(route))
                    .put("label", candidate.label.take(80))
                    .put("kind", candidate.kind)
                    .put("ledgerTarget", ledgerTargetIdForAction != null)
                    .put("reason", rejectReason)
                    .put("primaryReason", result.optString("primaryReason").take(80)))
                if (candidate.kind == "mission-link-navigation") jinhakReportBridgeContext = null
            }
            if (result.optBoolean("ok", false)) {
                if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markClicked(ledgerTargetIdForAction)
                if (candidate.kind == "mission-link-navigation") {
                    jinhakMissionAnchorActionsExecuted += 1
                    val clickedKey = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
                    jinhakMissionAnchorClickedKeys.add(clickedKey)
                }
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin || batchCollecting) return@postDelayed
                    scheduleBatchSnapshot()
                }, 1100L)
            } else if (ledgerTargetIdForAction != null) {
                // Stay on the origin and immediately evaluate the next captured target instead of
                // falling through to the generic URL frontier.
                handler.postDelayed({
                    if (batchRunning && !batchPausedForLogin && !batchCollecting) scheduleBatchSnapshot()
                }, 160L)
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 120L)
            }
        }
        return true
    }
'''
m = m[:start] + new_agent_function + '\n\n' + m[end:]

old_return_comment = '''        // v0.8.5 keeps the same application mission active while returning to the
        // saved-application origin. The sequencer then selects the next missing lane;
        // only an exhausted origin clears the mission before selecting another card.
        jinhakReportBridgeContext = null
'''
new_return_comment = '''        // v0.8.6 keeps the same application mission and its target ledger active while
        // returning to the saved-application origin. A clicked target that never produced a
        // confirmed report is closed explicitly so it cannot block the remaining ledger.
        val returningTargetId = jinhakActiveMissionTargetId
        if (returningTargetId != null && jinhakMissionTargetLedger.stateOf(returningTargetId) == JinhakMissionTargetLedger.State.CLICKED) {
            jinhakMissionTargetLedger.markFailed(returningTargetId, "report-unconfirmed")
        }
        jinhakActiveMissionTargetId = null
        jinhakReportBridgeContext = null
'''
m = replace_once(m, old_return_comment, new_return_comment, 'mission return target closure')

old_load_start = '''    private fun loadNextBatchPage() {
        if (!batchRunning || batchPausedForLogin) return
        if (batchCloudPlansPending > 0) {
            status.text = "Cloud resume 계획 확인 중: ${batchCloudPlansPending}개 목록"
            handler.postDelayed({ loadNextBatchPage() }, 180)
            return
        }

        while (batchPageActions.isNotEmpty()) {
'''
new_load_start = '''    private fun loadNextBatchPage() {
        if (!batchRunning || batchPausedForLogin) return
        if (batchCloudPlansPending > 0) {
            status.text = "Cloud resume 계획 확인 중: ${batchCloudPlansPending}개 목록"
            handler.postDelayed({ loadNextBatchPage() }, 180)
            return
        }

        if (provider == ProviderId.JINHAK) {
            val preferredIdentity = jinhakMissionContext?.identityKey
            if (jinhakMissionTargetLedger.hasActionablePending()) {
                val origin = jinhakMissionTargetLedger.originForNextPending(preferredIdentity)
                if (!origin.isNullOrBlank()) {
                    val current = canonicalizeBatchUrl(webView.url ?: "")
                    val canonicalOrigin = canonicalizeBatchUrl(origin)
                    currentBatchTarget = canonicalOrigin
                    status.text = "지원안 ledger 우선 처리: ${jinhakMissionTargetLedger.pendingCount()}개 target 대기"
                    if (current == canonicalOrigin) {
                        if (!batchCollecting && !jinhakAgentActionInFlight) scheduleBatchSnapshot()
                    } else {
                        webView.loadUrl(canonicalOrigin)
                    }
                    return
                }
            }
            // Deferred mission targets are still outstanding. Do not let editorial/media/frontier
            // work overtake them while a slow worker owns the report.
            if (jinhakMissionTargetLedger.outstandingCount() > 0 && ::slowLanePool.isInitialized && slowLanePool.hasWork()) {
                val slow = slowLanePool.stats()
                status.text = "지원안 ledger 병렬 처리 대기: slow ${slow.running} · 대기 ${slow.queued} · outstanding ${jinhakMissionTargetLedger.outstandingCount()}"
                handler.postDelayed({ if (batchRunning && !batchPausedForLogin) loadNextBatchPage() }, 700L)
                return
            }
        }

        while (batchPageActions.isNotEmpty()) {
'''
m = replace_once(m, old_load_start, new_load_start, 'ledger-first load scheduler')

old_slow_accept = '''            val accepted = ::slowLanePool.isInitialized && slowLanePool.enqueue(task)
            if (accepted) {
                jinhakSlowLaneEscalated += 1
'''
new_slow_accept = '''            val accepted = ::slowLanePool.isInitialized && slowLanePool.enqueue(task)
            val ledgerTargetForSlowLane = jinhakActiveMissionTargetId
            if (accepted) {
                if (ledgerTargetForSlowLane != null) {
                    jinhakMissionTargetLedger.markDeferred(ledgerTargetForSlowLane)
                    jinhakSlowLaneMissionTargetIds[task.id] = ledgerTargetForSlowLane
                    jinhakActiveMissionTargetId = null
                }
                jinhakSlowLaneEscalated += 1
'''
m = replace_once(m, old_slow_accept, new_slow_accept, 'slow lane ledger defer')

old_slow_queue_failure = '''            } else {
                jinhakSlowLaneFailed += 1
                batchErrors.put(JSONObject()
'''
new_slow_queue_failure = '''            } else {
                if (ledgerTargetForSlowLane != null) {
                    jinhakMissionTargetLedger.markFailed(ledgerTargetForSlowLane, "slow-lane-queue-full")
                    if (jinhakActiveMissionTargetId == ledgerTargetForSlowLane) jinhakActiveMissionTargetId = null
                }
                jinhakSlowLaneFailed += 1
                batchErrors.put(JSONObject()
'''
m = replace_once(m, old_slow_queue_failure, new_slow_queue_failure, 'slow lane queue ledger failure')

old_slow_complete_coverage = '''            if (missionKey != null && resolvedLane != "reference") {
                jinhakMissionCoverage.getOrPut(missionKey) { linkedSetOf() }.add(resolvedLane)
            }

            val capturedAt = Instant.now().toString()
'''
new_slow_complete_coverage = '''            if (missionKey != null && resolvedLane != "reference") {
                jinhakMissionCoverage.getOrPut(missionKey) { linkedSetOf() }.add(resolvedLane)
            }
            jinhakSlowLaneMissionTargetIds.remove(task.id)?.let { targetId ->
                val pageLane = JinhakApplicationMission.laneForPageType(pageType)
                if (!jinhakMissionTargetLedger.markConfirmed(targetId, missionKey, pageLane)) {
                    jinhakMissionTargetLedger.markFailed(targetId, "slow-lane-report-unconfirmed")
                }
            }

            val capturedAt = Instant.now().toString()
'''
m = replace_once(m, old_slow_complete_coverage, new_slow_complete_coverage, 'slow lane ledger completion')

old_slow_failed_start = '''    ) {
        jinhakSlowLaneFailed += 1
        val failureClass = reason.substringBefore(':').take(80)
'''
new_slow_failed_start = '''    ) {
        jinhakSlowLaneMissionTargetIds.remove(task.id)?.let { targetId ->
            jinhakMissionTargetLedger.markFailed(targetId, reason)
        }
        jinhakSlowLaneFailed += 1
        val failureClass = reason.substringBefore(':').take(80)
'''
# This exact function signature body occurs once for handleJinhakSlowLaneFailed.
m = replace_once(m, old_slow_failed_start, new_slow_failed_start, 'slow lane ledger failure')

old_diag = '''                        .put("applicationMissionCoverage", JSONObject().apply {
                            val lanes = listOf("saved-application", "current-prediction", "mock-support", "actual-admit", "university-result", "score-analysis", "strategy")
                            for (lane in lanes) put(lane, jinhakMissionCoverage.values.count { it.contains(lane) })
                            put("fourOrMoreLanes", jinhakMissionCoverage.values.count { it.size >= 4 })
                            put("sixOrMoreLanes", jinhakMissionCoverage.values.count { it.size >= 6 })
                        })
                        .put("cloudFrontierPublished", cloudFrontierPublished)
'''
new_diag = '''                        .put("applicationMissionCoverage", JSONObject().apply {
                            val lanes = listOf("saved-application", "current-prediction", "mock-support", "actual-admit", "university-result", "score-analysis", "strategy")
                            for (lane in lanes) put(lane, jinhakMissionCoverage.values.count { it.contains(lane) })
                            put("fourOrMoreLanes", jinhakMissionCoverage.values.count { it.size >= 4 })
                            put("sixOrMoreLanes", jinhakMissionCoverage.values.count { it.size >= 6 })
                        })
                        .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
                        .put("missionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                        .put("missionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                        .put("cloudFrontierPublished", cloudFrontierPublished)
'''
m = replace_once(m, old_diag, new_diag, 'sync diagnostic ledger summary')

old_batch_summary = '''                .put("jinhakApplicationMissionIdentities", jinhakMissionCoverage.size)
                .put("jinhakApplicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
'''
new_batch_summary = '''                .put("jinhakApplicationMissionIdentities", jinhakMissionCoverage.size)
                .put("jinhakMissionTargetLedger", jinhakMissionTargetLedger.summary())
                .put("jinhakMissionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                .put("jinhakMissionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("jinhakApplicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
'''
m = replace_once(m, old_batch_summary, new_batch_summary, 'batch export ledger summary')

MAIN.write_text(m)

# Put the latest compact Jinhak diagnostic detail directly in the session object at the front
# of streaming exports so large JSON files remain easy to analyze without scanning the tail.
s = STORE.read_text()
method_anchor = '    fun unifiedStatus(sessionId: String): JSONObject {\n'
helper = '''    private fun latestSyncStateDetail(sessionId: String, state: String): JSONObject {
        return readableDatabase.rawQuery(
            "SELECT detail_json FROM sync_state_events WHERE session_id=? AND state=? ORDER BY created_at DESC,event_id DESC LIMIT 1",
            arrayOf(sessionId, state)
        ).use { c ->
            if (!c.moveToFirst()) return@use JSONObject()
            runCatching { JSONObject(c.getString(0)) }.getOrDefault(JSONObject())
        }
    }

'''
s = replace_once(s, method_anchor, helper + method_anchor, 'latest sync detail helper')
s = replace_once(
    s,
    '            .put("observationStore", observationStats(sessionId))\n        return out\n',
    '            .put("observationStore", observationStats(sessionId))\n'
    '        out.put("jinhakDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_CRAWL_DIAGNOSTICS"))\n'
    '        return out\n',
    'front-loaded diagnostics summary'
)
STORE.write_text(s)

g = GRADLE.read_text()
g = replace_once(g, '        versionCode = 10850\n', '        versionCode = 10860\n', 'gradle version code')
g = replace_once(g, '        versionName = "0.8.5"\n', '        versionName = "0.8.6"\n', 'gradle version name')
GRADLE.write_text(g)

x = MANIFEST.read_text()
x = replace_once(
    x,
    'android:label="Admission Collector v0.8.5 Mission Lane Sequencer"',
    'android:label="Admission Collector v0.8.6 Persistent Mission Ledger"',
    'manifest label'
)
MANIFEST.write_text(x)

print('Applied v0.8.6 Persistent Mission Target Ledger')
