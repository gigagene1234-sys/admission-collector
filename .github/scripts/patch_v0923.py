from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


main = MAIN.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

required = [
    'private const val VERSION = "0.9.22"',
    'private const val BUILD_CODE = 109220',
    'JINHAK_SINGLE_WEBVIEW_STABILITY_MODE = true',
    'private fun scheduleJinhakLoginRecovery(reason: String)',
    'private fun pollJinhakLoginRecovery(reason: String, generation: Int)',
    'private fun completeJinhakVerifiedAuth(reason: String)',
    'private fun finishBatch(reason: String)',
    'MAX_JINHAK_GENERIC_ACTIONS = 180',
    'jinhakMissionTargetLedger.outstandingCount()',
    'jinhak-login-recovery',
    'jinhak-single-webview-slow-lane-bypass',
]
missing = [x for x in required if x not in main]
if missing:
    raise SystemExit('v0.9.22 source precondition failed: ' + ', '.join(missing))

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.9.22"', 'private const val VERSION = "0.9.23"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 109220', 'private const val BUILD_CODE = 109230', 'main build code')
gradle = replace_once(gradle, 'versionCode = 109220', 'versionCode = 109230', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.9.22"', 'versionName = "0.9.23"', 'gradle version name')
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.22 Single-WebView Stability Guard',
    'Admission Collector v0.9.23 Mission Closure Auth Fence',
    'manifest label'
)

# Per-episode auth recovery state. Existing aggregate counters remain untouched.
main = replace_once(
    main,
    '    private var jinhakRendererFirstCrashCooldowns = 0\n    private var jinhakStallWatchdogGeneration = 0\n',
    '''    private var jinhakRendererFirstCrashCooldowns = 0
    private var jinhakLoginRecoveryEpisodeStartedAtMs = 0L
    private var jinhakLoginRecoveryEpisodePolls = 0
    private var jinhakLoginRecoveryFenceTrips = 0
    private var jinhakPostMissionClosureFences = 0
    private var jinhakStallWatchdogGeneration = 0
''',
    'auth recovery episode fields'
)

main = replace_once(
    main,
    '        private const val JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS = 2_000L\n        private const val MAX_JINHAK_CONSECUTIVE_STALLS = 4\n',
    '''        private const val JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS = 2_000L
        private const val JINHAK_LOGIN_RECOVERY_TIMEOUT_MS = 60_000L
        private const val MAX_JINHAK_LOGIN_RECOVERY_POLLS = 40
        private const val MAX_JINHAK_CONSECUTIVE_STALLS = 4
''',
    'auth recovery fence constants'
)

# Reset only new per-batch diagnostics; persisted mission/auth proof remains preserved.
main = replace_once(
    main,
    '        jinhakMissionStallFenceTrips = 0\n        jinhakMissionStallRecoveryAttempts = 0\n        jinhakMissionStallTerminalStops = 0\n        jinhakMissionCells.resetForRun("batch-runtime-reset")\n',
    '''        jinhakMissionStallFenceTrips = 0
        jinhakMissionStallRecoveryAttempts = 0
        jinhakMissionStallTerminalStops = 0
        jinhakLoginRecoveryEpisodeStartedAtMs = 0L
        jinhakLoginRecoveryEpisodePolls = 0
        jinhakLoginRecoveryFenceTrips = 0
        jinhakPostMissionClosureFences = 0
        jinhakMissionCells.resetForRun("batch-runtime-reset")
''',
    'new auth fence reset'
)

# Mission-complete + generic-budget-exhausted is a terminal useful-data state. If the next
# generic/reference target redirects to login, do not turn that into a global re-auth loop.
helper = r'''    private fun isJinhakPostMissionClosureReady(): Boolean {
        if (provider != ProviderId.JINHAK || !batchRunning) return false
        val ledgerSummary = jinhakMissionTargetLedger.summary()
        val targetCount = ledgerSummary.optInt("targets", 0)
        if (targetCount <= 0 || jinhakMissionTargetLedger.outstandingCount() != 0) return false
        if (jinhakActiveMissionTargetId != null || jinhakAgentActionInFlight || batchCollecting) return false
        if (jinhakMissionCells.hasActiveOwnership()) return false
        if (::slowLanePool.isInitialized && slowLanePool.hasWork()) return false
        return jinhakGenericActionsExecuted >= MAX_JINHAK_GENERIC_ACTIONS
    }

    private fun finishJinhakPostMissionLoginIfReady(trigger: String): Boolean {
        if (!isJinhakPostMissionClosureReady()) return false
        jinhakPostMissionClosureFences += 1
        val ledger = jinhakMissionTargetLedger.summary()
        recordRuntimeEvent(
            "jinhak-post-mission-login-closure",
            JSONObject()
                .put("trigger", trigger.take(80))
                .put("currentSafePath", runtimeSafePath(webView.url))
                .put("currentTargetSafePath", runtimeSafePath(currentBatchTarget))
                .put("missionOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("genericActionsExecuted", jinhakGenericActionsExecuted)
                .put("genericActionLimit", MAX_JINHAK_GENERIC_ACTIONS)
                .put("ledger", ledger)
                .put("reauthSkipped", true),
            synchronous = true
        )
        persistJinhakAuthDiagnostics("post-mission-login-closure:$trigger")
        persistLiveJinhakDiagnostics("post-mission-login-closure", force = true)
        jinhakLoginRecoveryEpisodeStartedAtMs = 0L
        jinhakLoginRecoveryEpisodePolls = 0
        ++jinhakLoginRecoveryGeneration
        batchPausedForLogin = false
        status.text = "지원안 미션 27개가 모두 끝났고 일반 탐색 한도도 소진되어 추가 로그인 없이 수집을 정상 종료합니다."
        finishBatch("completed")
        return true
    }

'''
main = replace_once(
    main,
    '    private fun scheduleJinhakLoginRecovery(reason: String) {\n',
    helper + '    private fun scheduleJinhakLoginRecovery(reason: String) {\n',
    'post mission closure helper'
)

# Treat login recovery as a single bounded episode. Repeated page-finished/keepalive signals no
# longer start new generations that can keep resetting the recovery indefinitely.
old_schedule = '''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val generation = ++jinhakLoginRecoveryGeneration
        handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, 120L)
    }
'''
new_schedule = '''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val recoveryActive = startupLoginPreflightActive || jinhakTransitionAuthGateActive || (batchRunning && batchPausedForLogin)
        if (!recoveryActive) return
        if (batchRunning && batchPausedForLogin && finishJinhakPostMissionLoginIfReady("schedule:$reason")) return
        if (jinhakLoginRecoveryEpisodeStartedAtMs > 0L) return
        jinhakLoginRecoveryEpisodeStartedAtMs = System.currentTimeMillis()
        jinhakLoginRecoveryEpisodePolls = 0
        val generation = ++jinhakLoginRecoveryGeneration
        recordRuntimeEvent(
            "jinhak-login-recovery-episode-started",
            JSONObject()
                .put("reason", reason.take(80))
                .put("batchRunning", batchRunning)
                .put("batchPausedForLogin", batchPausedForLogin)
                .put("missionOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("genericActionsExecuted", jinhakGenericActionsExecuted)
        )
        handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, 120L)
    }
'''
main = replace_once(main, old_schedule, new_schedule, 'single bounded login recovery episode')

old_poll_prefix = '''    private fun pollJinhakLoginRecovery(reason: String, generation: Int) {
        if (provider != ProviderId.JINHAK || generation != jinhakLoginRecoveryGeneration) return
        val recoveryActive = startupLoginPreflightActive || jinhakTransitionAuthGateActive || (batchRunning && batchPausedForLogin)
        if (!recoveryActive) return
        jinhakLoginRecoveryPolls += 1
        val currentUrl = webView.url.orEmpty()
'''
new_poll_prefix = '''    private fun pollJinhakLoginRecovery(reason: String, generation: Int) {
        if (provider != ProviderId.JINHAK || generation != jinhakLoginRecoveryGeneration) return
        val recoveryActive = startupLoginPreflightActive || jinhakTransitionAuthGateActive || (batchRunning && batchPausedForLogin)
        if (!recoveryActive) {
            jinhakLoginRecoveryEpisodeStartedAtMs = 0L
            jinhakLoginRecoveryEpisodePolls = 0
            return
        }
        if (jinhakLoginRecoveryEpisodeStartedAtMs <= 0L) jinhakLoginRecoveryEpisodeStartedAtMs = System.currentTimeMillis()
        jinhakLoginRecoveryPolls += 1
        jinhakLoginRecoveryEpisodePolls += 1
        val recoveryAgeMs = (System.currentTimeMillis() - jinhakLoginRecoveryEpisodeStartedAtMs).coerceAtLeast(0L)
        if (batchRunning && batchPausedForLogin && finishJinhakPostMissionLoginIfReady("poll:$reason")) return
        if (batchRunning && batchPausedForLogin &&
            (jinhakLoginRecoveryEpisodePolls >= MAX_JINHAK_LOGIN_RECOVERY_POLLS || recoveryAgeMs >= JINHAK_LOGIN_RECOVERY_TIMEOUT_MS)) {
            jinhakLoginRecoveryFenceTrips += 1
            val outstanding = jinhakMissionTargetLedger.outstandingCount()
            batchErrors.put(JSONObject()
                .put("type", "jinhak-auth-recovery-timeout")
                .put("reason", reason.take(80))
                .put("polls", jinhakLoginRecoveryEpisodePolls)
                .put("elapsedMs", recoveryAgeMs)
                .put("missionOutstanding", outstanding)
                .put("currentSafePath", runtimeSafePath(webView.url))
                .put("currentTargetSafePath", runtimeSafePath(currentBatchTarget)))
            recordRuntimeEvent(
                "jinhak-login-recovery-timeout",
                JSONObject()
                    .put("reason", reason.take(80))
                    .put("polls", jinhakLoginRecoveryEpisodePolls)
                    .put("elapsedMs", recoveryAgeMs)
                    .put("missionOutstanding", outstanding)
                    .put("genericActionsExecuted", jinhakGenericActionsExecuted)
                    .put("genericActionLimit", MAX_JINHAK_GENERIC_ACTIONS),
                synchronous = true
            )
            persistJinhakAuthDiagnostics("login-recovery-timeout:$reason")
            persistLiveJinhakDiagnostics("login-recovery-timeout", force = true)
            jinhakLoginRecoveryEpisodeStartedAtMs = 0L
            jinhakLoginRecoveryEpisodePolls = 0
            ++jinhakLoginRecoveryGeneration
            batchPausedForLogin = false
            status.text = "진학사 로그인 복구가 60초 안에 끝나지 않아 무한 반복을 차단했습니다. 수집 데이터와 미션 상태는 보존됩니다."
            finishBatch("completed-with-local-errors")
            return
        }
        val currentUrl = webView.url.orEmpty()
'''
main = replace_once(main, old_poll_prefix, new_poll_prefix, 'bounded login recovery timeout')

# Terminal branch: do not leave a dead recovery episode latched if the protected core seed vanished.
main = replace_once(
    main,
    '            jinhakCoreBootstrapState = "core-auth-probe-missing"\n            persistJinhakAuthDiagnostics("$reason-core-probe-missing")\n            return\n',
    '''            jinhakCoreBootstrapState = "core-auth-probe-missing"
            persistJinhakAuthDiagnostics("$reason-core-probe-missing")
            jinhakLoginRecoveryEpisodeStartedAtMs = 0L
            jinhakLoginRecoveryEpisodePolls = 0
            return
''',
    'core probe missing recovery reset'
)

# Successful auth closes the episode before resuming the original target.
main = replace_once(
    main,
    '        persistJinhakMissionRuntimeState("protected-core-auth-verified")\n        persistJinhakAuthDiagnostics("$reason-auth-verified")\n        ++jinhakLoginRecoveryGeneration\n',
    '''        persistJinhakMissionRuntimeState("protected-core-auth-verified")
        persistJinhakAuthDiagnostics("$reason-auth-verified")
        jinhakLoginRecoveryEpisodeStartedAtMs = 0L
        jinhakLoginRecoveryEpisodePolls = 0
        ++jinhakLoginRecoveryGeneration
''',
    'verified auth recovery episode reset'
)

# Any batch finish cancels delayed login-poll callbacks from that batch.
main = replace_once(
    main,
    '    private fun finishBatch(reason: String) {\n        batchRunning = false\n        batchPausedForLogin = false\n',
    '''    private fun finishBatch(reason: String) {
        jinhakLoginRecoveryEpisodeStartedAtMs = 0L
        jinhakLoginRecoveryEpisodePolls = 0
        ++jinhakLoginRecoveryGeneration
        batchRunning = false
        batchPausedForLogin = false
''',
    'finish batch cancels login recovery'
)

# Auth diagnostics now expose the bounded episode and why it ended.
main = replace_once(
    main,
    '                    .put("loginRecoveryPolls", jinhakLoginRecoveryPolls)\n                    .put("reauthCycles", jinhakReauthCycles)\n',
    '''                    .put("loginRecoveryPolls", jinhakLoginRecoveryPolls)
                    .put("loginRecoveryEpisodePolls", jinhakLoginRecoveryEpisodePolls)
                    .put("loginRecoveryEpisodeAgeMs", if (jinhakLoginRecoveryEpisodeStartedAtMs > 0L) (System.currentTimeMillis() - jinhakLoginRecoveryEpisodeStartedAtMs).coerceAtLeast(0L) else 0L)
                    .put("loginRecoveryTimeoutMs", JINHAK_LOGIN_RECOVERY_TIMEOUT_MS)
                    .put("loginRecoveryMaxPolls", MAX_JINHAK_LOGIN_RECOVERY_POLLS)
                    .put("loginRecoveryFenceTrips", jinhakLoginRecoveryFenceTrips)
                    .put("postMissionClosureFences", jinhakPostMissionClosureFences)
                    .put("missionOutstandingAtAuth", jinhakMissionTargetLedger.outstandingCount())
                    .put("genericActionBudgetExhausted", jinhakGenericActionsExecuted >= MAX_JINHAK_GENERIC_ACTIONS)
                    .put("reauthCycles", jinhakReauthCycles)
''',
    'auth fence diagnostics'
)

# Final Jinhak crawl diagnostics keep the same evidence for the exported postmortem.
main = replace_once(
    main,
    '                        .put("jinhakLoginRecoveryPolls", jinhakLoginRecoveryPolls)\n                        .put("jinhakReauthCycles", jinhakReauthCycles)\n',
    '''                        .put("jinhakLoginRecoveryPolls", jinhakLoginRecoveryPolls)
                        .put("jinhakLoginRecoveryEpisodePolls", jinhakLoginRecoveryEpisodePolls)
                        .put("jinhakLoginRecoveryFenceTrips", jinhakLoginRecoveryFenceTrips)
                        .put("jinhakPostMissionClosureFences", jinhakPostMissionClosureFences)
                        .put("jinhakLoginRecoveryTimeoutMs", JINHAK_LOGIN_RECOVERY_TIMEOUT_MS)
                        .put("jinhakLoginRecoveryMaxPolls", MAX_JINHAK_LOGIN_RECOVERY_POLLS)
                        .put("jinhakReauthCycles", jinhakReauthCycles)
''',
    'terminal auth fence diagnostics'
)

# Safety checks: no capability/security regression, no secrets added.
post_required = [
    'private const val VERSION = "0.9.23"',
    'private const val BUILD_CODE = 109230',
    'JINHAK_LOGIN_RECOVERY_TIMEOUT_MS = 60_000L',
    'MAX_JINHAK_LOGIN_RECOVERY_POLLS = 40',
    'jinhak-post-mission-login-closure',
    'jinhak-login-recovery-episode-started',
    'jinhak-login-recovery-timeout',
    'finishJinhakPostMissionLoginIfReady',
    'JINHAK_SINGLE_WEBVIEW_STABILITY_MODE = true',
    'jinhak-single-webview-slow-lane-bypass',
    'persistJinhakAuthProofCheckpoint',
    'recoverOrStopJinhakMissionStall',
    'same-card-action-not-found',
]
missing_after = [x for x in post_required if x not in main]
if missing_after:
    raise SystemExit('v0.9.23 postcondition failed: ' + ', '.join(missing_after))

for forbidden in [
    '.put("username", credentials.username)',
    '.put("password", credentials.password)',
    '.putString("processPassword"',
    '.putString("processCookie"',
    '.putString("processToken"',
]:
    if forbidden in main:
        raise SystemExit('privacy invariant failed: ' + forbidden)

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('v0.9.23 Mission Closure Auth Fence patch applied')
