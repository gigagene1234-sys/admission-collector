from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
POLICY = ROOT / 'app/src/main/java/com/admissionhub/collector/sync/LocalRebindPolicy.kt'
POLICY_TEST = ROOT / 'app/src/test/java/com/admissionhub/collector/sync/LocalRebindPolicyTest.kt'
LEASE_TEST = ROOT / 'app/src/test/java/com/admissionhub/collector/jinhak/JinhakMissionCellSupervisorLeaseTest.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {n}')
    return text.replace(old, new, 1)

main = MAIN.read_text()
store = STORE.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.10.3"',
    'private const val BUILD_CODE = 110030',
    'private const val AUTO_LOGIN_AND_COLLECT_ON_LAUNCH = true',
    'private fun rebuildCanonicalHubFromLatestSessionIfReady(trigger: String)',
    'private fun armJinhakProgressFence()',
    'fun canonicalHubSummary(sessionId: String): JSONObject',
    'official-structural-v2',
]:
    if token not in main and token not in store:
        raise SystemExit('v0.10.3 precondition failed: ' + token)

# ---------------------------------------------------------------------------
# Pure launch decision policy. This is intentionally independent of Android/SQLite.
# ---------------------------------------------------------------------------
POLICY.parent.mkdir(parents=True, exist_ok=True)
POLICY.write_text(r'''package com.admissionhub.collector.sync

/**
 * Decides whether an interrupted browser collection should yield to a previously
 * complete, locally reusable canonical graph. No provider/session secret is involved.
 */
object LocalRebindPolicy {
    data class Input(
        val pinnedSlots: Int,
        val reusableCandidateCount: Int,
        val latestCandidateCount: Int,
        val latestStatus: String,
        val latestIsReusableSource: Boolean
    )

    fun preferLocalRebind(input: Input): Boolean =
        input.pinnedSlots == 6 && input.reusableCandidateCount >= 6

    fun suppressInterruptedBrowserResume(input: Input): Boolean {
        if (!preferLocalRebind(input)) return false
        val active = input.latestStatus.lowercase() in setOf("running", "jinhak", "adiga", "hub-publish")
        if (!active) return false
        // If the newest active session is itself a usable graph, preserve normal process-death resume.
        if (input.latestIsReusableSource && input.latestCandidateCount >= 6) return false
        return input.latestCandidateCount < 6 || !input.latestIsReusableSource
    }
}
''')

POLICY_TEST.parent.mkdir(parents=True, exist_ok=True)
POLICY_TEST.write_text(r'''package com.admissionhub.collector.sync

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalRebindPolicyTest {
    @Test fun sixPinnedAndOlderReusableGraphSuppressesEmptyInterruptedRun() {
        val input = LocalRebindPolicy.Input(6, 27, 0, "running", false)
        assertTrue(LocalRebindPolicy.preferLocalRebind(input))
        assertTrue(LocalRebindPolicy.suppressInterruptedBrowserResume(input))
    }

    @Test fun noReusableGraphDoesNotSuppressResume() {
        val input = LocalRebindPolicy.Input(6, 0, 0, "running", false)
        assertFalse(LocalRebindPolicy.preferLocalRebind(input))
        assertFalse(LocalRebindPolicy.suppressInterruptedBrowserResume(input))
    }

    @Test fun sameActiveReusableSessionKeepsProcessDeathResume() {
        val input = LocalRebindPolicy.Input(6, 27, 27, "running", true)
        assertTrue(LocalRebindPolicy.preferLocalRebind(input))
        assertFalse(LocalRebindPolicy.suppressInterruptedBrowserResume(input))
    }

    @Test fun fewerThanSixPinnedDoesNotTakeOverLaunch() {
        val input = LocalRebindPolicy.Input(5, 27, 0, "running", false)
        assertFalse(LocalRebindPolicy.preferLocalRebind(input))
        assertFalse(LocalRebindPolicy.suppressInterruptedBrowserResume(input))
    }
}
''')

LEASE_TEST.parent.mkdir(parents=True, exist_ok=True)
LEASE_TEST.write_text(r'''package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakMissionCellSupervisorLeaseTest {
    @Test fun actionLeaseExpiresAtItsOwnDeadlineIndependentOfParentProgress() {
        val supervisor = JinhakMissionCellSupervisor(staleOwnershipMs = 100L)
        supervisor.beginAction("target-a", "safe/path", "report-lane", nowMs = 1_000L)
        val early = supervisor.expireStaleOwnership(nowMs = 1_099L)
        assertFalse(early.actionExpired)
        assertTrue(supervisor.isActionActive())
        val expired = supervisor.expireStaleOwnership(nowMs = 1_100L)
        assertTrue(expired.actionExpired)
        assertFalse(supervisor.isActionActive())
    }

    @Test fun expiredLeaseRejectsLateCallbackGeneration() {
        val supervisor = JinhakMissionCellSupervisor(staleOwnershipMs = 100L)
        val token = supervisor.beginAction("target-a", "safe/path", "report-lane", nowMs = 2_000L)
        supervisor.expireStaleOwnership(nowMs = 2_100L)
        assertFalse(supervisor.finishAction(token, true, "late", nowMs = 2_101L))
    }
}
''')

# ---------------------------------------------------------------------------
# LocalStore: cross-session reusable canonical source discovery.
# ---------------------------------------------------------------------------
store = replace_once(
    store,
    'import com.admissionhub.collector.canonical.AdigaOfficialAdmissionEvidence\n',
    'import com.admissionhub.collector.canonical.AdigaOfficialAdmissionEvidence\nimport com.admissionhub.collector.sync.LocalRebindPolicy\n',
    'LocalRebindPolicy import'
)

store_methods_anchor = '''    fun canonicalHubSummary(sessionId: String): JSONObject {'''
store_methods = r'''    fun canonicalApplicationCount(sessionId: String?): Int {
        if (sessionId.isNullOrBlank()) return 0
        return readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM canonical_applications WHERE session_id=?",
            arrayOf(sessionId)
        ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
    }

    fun pinnedHubSlotCount(): Int = readableDatabase.rawQuery(
        "SELECT COUNT(*) FROM hub_application_slots WHERE user_pinned=1",
        emptyArray()
    ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }

    /**
     * Returns the newest canonical session that can resolve every currently pinned Hub slot.
     * This deliberately prefers preserved local evidence over starting a new browser mission.
     */
    fun latestReusableCanonicalSessionId(): String? {
        val pinned = pinnedHubSlotCount()
        val candidates = mutableListOf<String>()
        readableDatabase.rawQuery(
            "SELECT session_id,COUNT(*),MAX(updated_at) FROM canonical_applications GROUP BY session_id HAVING COUNT(*)>=6 ORDER BY MAX(updated_at) DESC",
            emptyArray()
        ).use { c -> while (c.moveToNext()) candidates += c.getString(0) }
        for (sessionId in candidates) {
            if (pinned <= 0) return sessionId
            val matched = readableDatabase.rawQuery(
                "SELECT COUNT(*) FROM canonical_applications WHERE session_id=? AND application_identity_key IN (SELECT application_identity_key FROM hub_application_slots WHERE user_pinned=1)",
                arrayOf(sessionId)
            ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
            if (matched == pinned) return sessionId
        }
        return null
    }

    fun localRebindDecision(): JSONObject {
        val latest = latestUnifiedSession()
        val reusable = latestReusableCanonicalSessionId()
        val latestCandidates = canonicalApplicationCount(latest)
        val reusableCandidates = canonicalApplicationCount(reusable)
        val latestStatus = if (latest.isNullOrBlank()) "none" else readableDatabase.rawQuery(
            "SELECT status FROM unified_sessions WHERE session_id=? LIMIT 1",
            arrayOf(latest)
        ).use { c -> if (c.moveToFirst()) c.getString(0) else "unknown" }
        val pinned = pinnedHubSlotCount()
        val input = LocalRebindPolicy.Input(
            pinnedSlots = pinned,
            reusableCandidateCount = reusableCandidates,
            latestCandidateCount = latestCandidates,
            latestStatus = latestStatus,
            latestIsReusableSource = !latest.isNullOrBlank() && latest == reusable
        )
        return JSONObject()
            .put("schemaVersion", 1)
            .put("pinnedSlots", pinned)
            .put("latestSessionId", latest ?: JSONObject.NULL)
            .put("latestSessionStatus", latestStatus)
            .put("latestCandidateCount", latestCandidates)
            .put("reusableSessionId", reusable ?: JSONObject.NULL)
            .put("reusableCandidateCount", reusableCandidates)
            .put("preferLocalRebind", LocalRebindPolicy.preferLocalRebind(input))
            .put("suppressInterruptedBrowserResume", LocalRebindPolicy.suppressInterruptedBrowserResume(input))
            .put("providerNetworkRequired", false)
            .put("credentialsRead", false)
            .put("sessionSecretsRead", false)
    }

'''
store = replace_once(store, store_methods_anchor, store_methods + store_methods_anchor, 'cross-session store methods')

store = replace_once(
    store,
    '''            .put("selectedRecoveryPlan", selectedSixRecoveryPlan(sessionId))
            .put("slotPolicy", JSONObject()
''',
    '''            .put("selectedRecoveryPlan", selectedSixRecoveryPlan(sessionId))
            .put("crossSessionContinuity", localRebindDecision())
            .put("slotPolicy", JSONObject()
''',
    'canonical summary continuity diagnostics'
)

# ---------------------------------------------------------------------------
# Version + launch behavior.
# ---------------------------------------------------------------------------
main = replace_once(main, 'private const val VERSION = "0.10.3"', 'private const val VERSION = "0.10.4"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 110030', 'private const val BUILD_CODE = 110040', 'main build code')
main = replace_once(main, 'private const val AUTO_LOGIN_AND_COLLECT_ON_LAUNCH = true', 'private const val AUTO_LOGIN_AND_COLLECT_ON_LAUNCH = false', 'disable launch browser collection')
main = replace_once(
    main,
    '        private const val JINHAK_PROGRESS_FENCE_POLL_MS = 15_000L\n',
    '        private const val JINHAK_PROGRESS_FENCE_POLL_MS = 15_000L\n        private const val JINHAK_HARD_CELL_LEASE_POLL_MS = 5_000L\n',
    'hard lease poll constant'
)

gradle = replace_once(gradle, 'versionCode = 110030', 'versionCode = 110040', 'gradle code')
gradle = replace_once(gradle, 'versionName = "0.10.3"', 'versionName = "0.10.4"', 'gradle name')
manifest = replace_once(
    manifest,
    'Admission Hub v0.10.3 Official Table Binding',
    'Admission Hub v0.10.4 Local Rebind Continuity',
    'manifest label'
)

# ---------------------------------------------------------------------------
# Runtime counters and local rebind source.
# ---------------------------------------------------------------------------
main = replace_once(
    main,
    '    private var hubEditsBlockedDuringCollection = 0\n',
    '''    private var hubEditsBlockedDuringCollection = 0
    private var localRebindSourceSessionId: String? = null
    private var localRebindRuns = 0
    private var localRebindResumeSuppressions = 0
    private var jinhakHardLeaseWatchdogGeneration = 0
    private var jinhakHardActionLeaseExpirations = 0
    private var jinhakHardSnapshotLeaseExpirations = 0
    private var jinhakHardLeaseRecoveryDispatches = 0
''',
    'runtime rebind/lease counters'
)

# onCreate: a reusable 6-slot graph wins over an incomplete newer browser run.
old_oncreate = '''        buildUi()
        handler.postDelayed({ rebuildCanonicalHubFromLatestSessionIfReady("app-start") }, 1800L)
        slowLanePool = JinhakSlowLanePool(this, slowLaneHost, object : JinhakSlowLanePool.Listener {'''
new_oncreate = '''        buildUi()
        slowLanePool = JinhakSlowLanePool(this, slowLaneHost, object : JinhakSlowLanePool.Listener {'''
main = replace_once(main, old_oncreate, new_oncreate, 'remove eager latest-session rebuild')

old_resume = '''        configureWebView()
        initializeProcessResumeJournal()
        restoreJinhakAuthProofCheckpoint("activity-create")
        val resumed = resumeInterruptedUnifiedSessionIfNeeded()
        if (!resumed) {
            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {
                handler.postDelayed({ startLaunchAwareCollection() }, 350L)
            } else {
                openProvider(ProviderId.JINHAK)
            }
        }
        handler.postDelayed({ sendPendingRuntimeEvents() }, 1200L)
'''
new_resume = '''        configureWebView()
        initializeProcessResumeJournal()
        restoreJinhakAuthProofCheckpoint("activity-create")
        val localDecision = localStore.localRebindDecision()
        val suppressInterruptedResume = localDecision.optBoolean("suppressInterruptedBrowserResume", false)
        if (suppressInterruptedResume) {
            localRebindResumeSuppressions += 1
            recordRuntimeEvent("local-rebind-suppressed-interrupted-browser-resume", localDecision)
        }
        val resumed = if (suppressInterruptedResume) false else resumeInterruptedUnifiedSessionIfNeeded()
        if (!resumed) {
            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH && !localDecision.optBoolean("preferLocalRebind", false)) {
                handler.postDelayed({ startLaunchAwareCollection() }, 350L)
            } else {
                handler.postDelayed({ runLocalRebindOnly("app-start") }, 300L)
                status.text = "기존 로컬 수집 결과를 우선 재결합합니다. 사이트 재수집은 자동 시작하지 않습니다."
            }
        }
        handler.postDelayed({ sendPendingRuntimeEvents() }, 1200L)
'''
main = replace_once(main, old_resume, new_resume, 'launch local rebind gate')

main = replace_once(
    main,
    '            text = "Admission Collector v$VERSION · build $BUILD_CODE · LOCAL-FIRST"',
    '            text = "Admission Hub v$VERSION · build $BUILD_CODE · LOCAL-FIRST"',
    'header label'
)

# ---------------------------------------------------------------------------
# Hub session continuity: all Hub-only operations use the best resolvable local graph.
# ---------------------------------------------------------------------------
hub_anchor = '''    private fun rebuildCanonicalHubFromLatestSessionIfReady(trigger: String) {'''
hub_helpers = r'''    private fun canonicalHubSessionId(): String? =
        localRebindSourceSessionId
            ?: localStore.latestReusableCanonicalSessionId()
            ?: localStore.latestUnifiedSession()

    private fun runLocalRebindOnly(trigger: String) {
        if (unifiedRunning || batchRunning || startupLoginPreflightActive) return
        val decision = localStore.localRebindDecision()
        val sourceSessionId = decision.optString("reusableSessionId").takeIf { it.isNotBlank() && it != "null" }
            ?: localStore.latestReusableCanonicalSessionId()
            ?: localStore.latestUnifiedSession()
        if (sourceSessionId.isNullOrBlank()) {
            refreshHubState(null)
            status.text = "재사용 가능한 로컬 canonical 데이터가 없습니다. 필요할 때 통합 동기화를 시작하세요."
            return
        }
        val persisted = localStore.jinhakMissionCoveragePersistenceSummary(sourceSessionId)
        if (persisted.optInt("persistedIdentities", 0) <= 0) {
            refreshHubState(sourceSessionId)
            status.text = "로컬 세션은 있으나 canonical 재결합에 필요한 mission evidence가 없습니다."
            return
        }
        localRebindSourceSessionId = sourceSessionId
        // Export/admin actions should refer to the graph being presented, not a newer abandoned browser run.
        unifiedSessionId = sourceSessionId
        localRebindRuns += 1
        val startedAt = System.currentTimeMillis()
        val summary = runCatching { localStore.rebuildCanonicalApplicationGraph(sourceSessionId) }.getOrElse { error ->
            recordRuntimeEvent("local-rebind-failed", JSONObject()
                .put("trigger", trigger.take(80))
                .put("sourceSessionId", sourceSessionId)
                .put("exceptionClass", error.javaClass.name.take(120)))
            localStore.canonicalHubSummary(sourceSessionId)
        }
        val audit = summary.optJSONObject("qualityAudit") ?: JSONObject()
        refreshHubState(sourceSessionId, summary)
        recordRuntimeEvent("local-rebind-complete", JSONObject()
            .put("trigger", trigger.take(80))
            .put("sourceSessionId", sourceSessionId)
            .put("durationMs", System.currentTimeMillis() - startedAt)
            .put("candidateCount", audit.optInt("candidateCount", 0))
            .put("selectedResolvable", audit.optJSONObject("sixSlots")?.optInt("resolvable", 0) ?: 0)
            .put("accepted", audit.optJSONObject("sixSlots")?.optInt("accepted", 0) ?: 0)
            .put("providerNetworkUsed", false))
        status.text = "로컬 재결합 완료 · 후보 ${audit.optInt("candidateCount", 0)} · 지원 6장 ${audit.optJSONObject("sixSlots")?.optInt("resolvable", 0) ?: 0}/6 · 사이트 재수집 없음"
    }

'''
main = replace_once(main, hub_anchor, hub_helpers + hub_anchor, 'local rebind helpers')

# Replace the old rebuild function's direct latest-session lookup.
main = replace_once(
    main,
    '''        val sessionId = localStore.latestUnifiedSession()
        if (sessionId.isNullOrBlank()) {
''',
    '''        val sessionId = canonicalHubSessionId()
        if (sessionId.isNullOrBlank()) {
''',
    'rebuild uses reusable hub session'
)

# In the Hub-only section, use the continuity session for selected-six checks/manager/recovery.
start = main.index('    private fun restoreSelectedSixRecoveryScope(sessionId: String): Boolean')
end = main.index('    @Suppress("SetJavaScriptEnabled")', start)
hub_section = main[start:end]
hub_section = hub_section.replace('localStore.latestUnifiedSession()', 'canonicalHubSessionId()')
main = main[:start] + hub_section + main[end:]

# Manual quality refresh must rebind local evidence, not start browser work.
main = main.replace('else rebuildCanonicalHubFromLatestSessionIfReady("manual-refresh")', 'else runLocalRebindOnly("manual-refresh")', 1)

# ---------------------------------------------------------------------------
# Hard cell lease watchdog: independent of parent meaningful-progress timestamps.
# ---------------------------------------------------------------------------
main = replace_once(
    main,
    '''    private fun armJinhakProgressFence() {
''',
    r'''    private fun armJinhakHardCellLeaseWatchdog() {
        if (provider != ProviderId.JINHAK) return
        val generation = ++jinhakHardLeaseWatchdogGeneration
        val poller = object : Runnable {
            override fun run() {
                if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || generation != jinhakHardLeaseWatchdogGeneration) return
                val expiry = jinhakMissionCells.expireStaleOwnership(System.currentTimeMillis())
                if (expiry.actionExpired) {
                    jinhakHardActionLeaseExpirations += 1
                    jinhakAgentActionInFlight = false
                }
                if (expiry.snapshotExpired) {
                    jinhakHardSnapshotLeaseExpirations += 1
                    batchCollecting = false
                }
                if (expiry.expiredAny) {
                    jinhakHardLeaseRecoveryDispatches += 1
                    jinhakAbsoluteTargetKey = ""
                    ++jinhakAbsoluteTargetGeneration
                    ++jinhakStallWatchdogGeneration
                    runCatching { webView.stopLoading() }
                    recordRuntimeEvent("jinhak-hard-cell-lease-expired", JSONObject()
                        .put("expiry", expiry.toJson())
                        .put("missionOutstanding", jinhakMissionTargetLedger.outstandingCount())
                        .put("activeMissionTarget", jinhakActiveMissionTargetId ?: JSONObject.NULL))
                    persistLiveJinhakDiagnostics("hard-cell-lease-expired", force = true)
                    handler.postDelayed({
                        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
                        val recovered = if (jinhakMissionTargetLedger.outstandingCount() > 0) {
                            recoverOrStopJinhakMissionStall("hard-cell-lease", countAsNoProgressFence = false)
                        } else false
                        if (!recovered && batchRunning && !batchPausedForLogin) loadNextBatchPage()
                    }, 180L)
                }
                handler.postDelayed(this, JINHAK_HARD_CELL_LEASE_POLL_MS)
            }
        }
        handler.postDelayed(poller, JINHAK_HARD_CELL_LEASE_POLL_MS)
    }

    private fun armJinhakProgressFence() {
''',
    'hard lease watchdog insertion'
)

main = replace_once(
    main,
    '        if (provider == ProviderId.JINHAK) armJinhakProgressFence()\n',
    '''        if (provider == ProviderId.JINHAK) {
            armJinhakProgressFence()
            armJinhakHardCellLeaseWatchdog()
        }
''',
    'arm both Jinhak fences'
)

main = replace_once(
    main,
    '''    private fun disarmBatchNavigationWatchdog() {
        batchNavigationWatchdogGeneration += 1
        jinhakStallWatchdogGeneration += 1
    }
''',
    '''    private fun disarmBatchNavigationWatchdog() {
        batchNavigationWatchdogGeneration += 1
        jinhakStallWatchdogGeneration += 1
        jinhakHardLeaseWatchdogGeneration += 1
    }
''',
    'disarm hard lease watchdog'
)

# Extend live diagnostics with local continuity + hard lease counters.
main = main.replace(
    '.put("hubEditsBlockedDuringCollection", hubEditsBlockedDuringCollection)',
    '.put("hubEditsBlockedDuringCollection", hubEditsBlockedDuringCollection)\n                .put("localRebindRuns", localRebindRuns)\n                .put("localRebindResumeSuppressions", localRebindResumeSuppressions)\n                .put("localRebindSourceSessionId", localRebindSourceSessionId ?: JSONObject.NULL)\n                .put("hardActionLeaseExpirations", jinhakHardActionLeaseExpirations)\n                .put("hardSnapshotLeaseExpirations", jinhakHardSnapshotLeaseExpirations)\n                .put("hardLeaseRecoveryDispatches", jinhakHardLeaseRecoveryDispatches)',
    1
)

# Postconditions.
checks = {
    'version': 'private const val VERSION = "0.10.4"' in main and 'versionName = "0.10.4"' in gradle,
    'launch-auto-off': 'private const val AUTO_LOGIN_AND_COLLECT_ON_LAUNCH = false' in main,
    'rebind-policy': 'localRebindDecision()' in main and 'latestReusableCanonicalSessionId()' in store,
    'cross-session-summary': 'crossSessionContinuity' in store,
    'hard-lease-watchdog': 'armJinhakHardCellLeaseWatchdog()' in main and 'hardActionLeaseExpirations' in main,
    'tests': POLICY_TEST.exists() and LEASE_TEST.exists(),
    'privacy': 'credentialsRead' in store and 'sessionSecretsRead' in store,
}
failed = [k for k,v in checks.items() if not v]
if failed:
    raise SystemExit('v0.10.4 postcondition failure: ' + ', '.join(failed))

MAIN.write_text(main)
STORE.write_text(store)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('v0.10.4 Local Rebind Continuity + Hard Action Lease patch applied')
