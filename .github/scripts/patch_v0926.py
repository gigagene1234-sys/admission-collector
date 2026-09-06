from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
LEDGER = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionTargetLedger.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


main = MAIN.read_text()
ledger = LEDGER.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.9.25"',
    'private const val BUILD_CODE = 109250',
    'private fun maybeSealJinhakCoreCoverage(trigger: String)',
    'private fun scheduleJinhakLoginRecovery(reason: String)',
    'private fun isJinhakPostMissionClosureReady(): Boolean',
    'coreCoverageClosureFences',
    'missionCoveragePersistence',
]:
    if token not in main:
        raise SystemExit('v0.9.25 MainActivity precondition failed: ' + token)
if 'fun hasMission(identityKey: String?)' not in ledger:
    raise SystemExit('v0.9.25 mission target ledger precondition failed')

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.9.25"', 'private const val VERSION = "0.9.26"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 109250', 'private const val BUILD_CODE = 109260', 'main build code')
gradle = replace_once(gradle, 'versionCode = 109250', 'versionCode = 109260', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.9.25"', 'versionName = "0.9.26"', 'gradle version name')
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.25 Mission Coverage Terminal Seal',
    'Admission Collector v0.9.26 Incomplete Coverage Recovery Fence',
    'manifest label'
)

# Recovery state: this is deliberately independent from the monotonic navigation target ledger.
main = replace_once(
    main,
    '''    private var jinhakCoreCoverageClosureFences = 0
    private var jinhakCoreCoverageClosurePending = false
    private var jinhakTerminalSeals = 0
''',
    '''    private var jinhakCoreCoverageClosureFences = 0
    private var jinhakCoreCoverageClosurePending = false
    private val jinhakIncompleteCoverageRecoveryAttempts = linkedMapOf<String, Int>()
    private var jinhakIncompleteCoverageRecoveryEpisodes = 0
    private var jinhakIncompleteCoverageRecoveryActions = 0
    private var jinhakIncompleteCoverageRecoverySuccesses = 0
    private var jinhakIncompleteCoverageFinishes = 0
    private var jinhakIncompleteCoverageActiveIdentity: String? = null
    private var jinhakLoginUrlStateCorrections = 0
    private var jinhakTerminalSeals = 0
''',
    'recovery fields'
)
main = replace_once(
    main,
    '''        jinhakCoreCoverageClosureFences = 0
        jinhakCoreCoverageClosurePending = false
        jinhakTerminalSeals = 0
''',
    '''        jinhakCoreCoverageClosureFences = 0
        jinhakCoreCoverageClosurePending = false
        jinhakIncompleteCoverageRecoveryAttempts.clear()
        jinhakIncompleteCoverageRecoveryEpisodes = 0
        jinhakIncompleteCoverageRecoveryActions = 0
        jinhakIncompleteCoverageRecoverySuccesses = 0
        jinhakIncompleteCoverageFinishes = 0
        jinhakIncompleteCoverageActiveIdentity = null
        jinhakLoginUrlStateCorrections = 0
        jinhakTerminalSeals = 0
''',
    'recovery reset'
)

# A bounded retry is intentional: once prediction targets are fully resolved, the collector must
# never fall back to an unbounded generic tail merely because a report lane is missing.
main = replace_once(
    main,
    '''        private const val JINHAK_LOGIN_RECOVERY_TIMEOUT_MS = 60_000L
        private const val MAX_JINHAK_LOGIN_RECOVERY_POLLS = 40
        private const val MAX_JINHAK_CONSECUTIVE_STALLS = 4
''',
    '''        private const val JINHAK_LOGIN_RECOVERY_TIMEOUT_MS = 60_000L
        private const val MAX_JINHAK_LOGIN_RECOVERY_POLLS = 40
        private const val MAX_JINHAK_INCOMPLETE_COVERAGE_RECOVERY_ATTEMPTS = 2
        private const val MAX_JINHAK_CONSECUTIVE_STALLS = 4
''',
    'recovery constant'
)

# A confirmed prediction target remains monotonic/confirmed.  Recovery borrows only its sanitized
# same-card candidate; it does not regress the target state back to pending.
ledger = replace_once(
    ledger,
    '    fun hasMission(identityKey: String?): Boolean = identityKey != null && targets.values.any { it.identityKey == identityKey }\n',
    '''    fun recoveryCandidateForIdentity(identityKey: String?): JinhakAgentNavigator.Candidate? {
        if (identityKey.isNullOrBlank()) return null
        return sortedTargets().firstOrNull { it.identityKey == identityKey }?.candidate()
    }

    fun hasMission(identityKey: String?): Boolean = identityKey != null && targets.values.any { it.identityKey == identityKey }
''',
    'coverage recovery candidate'
)

# Coverage-repair policy.  It works only on the saved-application library route, reopens the exact
# SAME-APPLICATION candidate at most twice, and then terminates as incomplete rather than entering
# unrelated generic navigation.
helpers_anchor = '    private fun maybeSealJinhakCoreCoverage(trigger: String) {\n'
helpers = r'''    private fun missingJinhakCoreLanes(identityKey: String): Set<String> {
        val covered = jinhakMissionCoverageLedger.lanes(identityKey)
        return JinhakMissionCoverageLedger.CORE_LANES.filterNot { it in covered }.toSet()
    }

    private fun incompleteJinhakCoverageIdentities(): List<String> =
        currentExpectedJinhakMissionIdentities()
            .filter { missingJinhakCoreLanes(it).isNotEmpty() }
            .sorted()

    private fun isJinhakSavedApplicationLibrary(route: String): Boolean {
        val normalized = canonicalizeBatchUrl(route).lowercase()
        return normalized.contains("/jh/high3/early/four-year-university/library")
    }

    private fun nextJinhakIncompleteCoverageRecoveryCandidate(
        trigger: String,
        route: String
    ): JinhakAgentNavigator.Candidate? {
        if (!batchRunning || provider != ProviderId.JINHAK || batchPausedForLogin) return null
        if (!isJinhakSavedApplicationLibrary(route)) return null
        if (jinhakMissionTargetLedger.outstandingCount() != 0) return null
        val expected = currentExpectedJinhakMissionIdentities()
        if (expected.size < 6) return null
        val incomplete = incompleteJinhakCoverageIdentities()
        if (incomplete.isEmpty()) return null

        for (identity in incomplete) {
            val attempts = jinhakIncompleteCoverageRecoveryAttempts[identity] ?: 0
            if (attempts >= MAX_JINHAK_INCOMPLETE_COVERAGE_RECOVERY_ATTEMPTS) continue
            val candidate = jinhakMissionTargetLedger.recoveryCandidateForIdentity(identity)
            if (candidate == null) {
                jinhakIncompleteCoverageRecoveryAttempts[identity] = MAX_JINHAK_INCOMPLETE_COVERAGE_RECOVERY_ATTEMPTS
                recordRuntimeEvent("jinhak-incomplete-coverage-unrecoverable", JSONObject()
                    .put("trigger", trigger.take(80))
                    .put("applicationIdentityHash", identity.take(24))
                    .put("missingLanes", JSONArray(missingJinhakCoreLanes(identity).toList())))
                continue
            }
            val nextAttempt = attempts + 1
            jinhakIncompleteCoverageRecoveryAttempts[identity] = nextAttempt
            jinhakIncompleteCoverageRecoveryEpisodes += 1
            jinhakIncompleteCoverageRecoveryActions += 1
            jinhakIncompleteCoverageActiveIdentity = identity
            // A recovery candidate is intentionally replayed even if its action key was seen in
            // the original prediction mission.  The persistent target remains CONFIRMED.
            jinhakAgentActionSeen.remove(actionKeyFor(candidate))
            recordRuntimeEvent("jinhak-incomplete-coverage-recovery-start", JSONObject()
                .put("trigger", trigger.take(80))
                .put("applicationIdentityHash", identity.take(24))
                .put("attempt", nextAttempt)
                .put("maxAttempts", MAX_JINHAK_INCOMPLETE_COVERAGE_RECOVERY_ATTEMPTS)
                .put("missingLanes", JSONArray(missingJinhakCoreLanes(identity).toList()))
                .put("genericTailAllowed", false))
            return candidate
        }
        return null
    }

    private fun jinhakIncompleteCoverageRecoveryExhausted(): Boolean {
        val incomplete = incompleteJinhakCoverageIdentities()
        if (incomplete.isEmpty()) return false
        return incomplete.all { identity ->
            (jinhakIncompleteCoverageRecoveryAttempts[identity] ?: 0) >= MAX_JINHAK_INCOMPLETE_COVERAGE_RECOVERY_ATTEMPTS ||
                jinhakMissionTargetLedger.recoveryCandidateForIdentity(identity) == null
        }
    }

    private fun maybeFinishJinhakIncompleteCoverage(trigger: String, route: String): Boolean {
        if (!batchRunning || provider != ProviderId.JINHAK || batchPausedForLogin || jinhakCoreCoverageClosurePending) return false
        if (!isJinhakSavedApplicationLibrary(route)) return false
        if (jinhakMissionTargetLedger.outstandingCount() != 0) return false
        val expected = currentExpectedJinhakMissionIdentities()
        if (expected.size < 6) return false
        val incomplete = incompleteJinhakCoverageIdentities()
        if (incomplete.isEmpty() || !jinhakIncompleteCoverageRecoveryExhausted()) return false
        if (jinhakApplicationMissionReturns < expected.size) return false

        jinhakCoreCoverageClosurePending = true
        jinhakIncompleteCoverageFinishes += 1
        jinhakIncompleteCoverageActiveIdentity = null
        recordRuntimeEvent("jinhak-incomplete-coverage-terminal-fence", JSONObject()
            .put("trigger", trigger.take(80))
            .put("coverage", jinhakCoreCoverageAudit())
            .put("incompleteIdentities", incomplete.size)
            .put("recoveryEpisodes", jinhakIncompleteCoverageRecoveryEpisodes)
            .put("genericActionsAvoided", (MAX_JINHAK_GENERIC_ACTIONS - jinhakGenericActionsExecuted).coerceAtLeast(0)))
        persistLiveJinhakDiagnostics("incomplete-coverage-terminal-fence", force = true)
        handler.postDelayed({
            if (batchRunning && provider == ProviderId.JINHAK) {
                finishBatch("completed-with-incomplete-coverage")
            }
        }, 120L)
        return true
    }

'''
main = replace_once(main, helpers_anchor, helpers + helpers_anchor, 'insert incomplete coverage helpers')

# When a repair fills the last missing lane(s), close the recovery episode immediately and let the
# existing all-core-complete fence finish the Jinhak phase.
main = replace_once(
    main,
    '''            handler.post { maybeSealJinhakCoreCoverage("coverage:$lane") }
        }
        return mapChanged || ledgerChanged
''',
    '''            handler.post { maybeSealJinhakCoreCoverage("coverage:$lane") }
        }
        if (jinhakIncompleteCoverageActiveIdentity == identity &&
            JinhakMissionCoverageLedger.CORE_LANES.all { it in jinhakMissionCoverageLedger.lanes(identity) }) {
            jinhakIncompleteCoverageRecoverySuccesses += 1
            jinhakIncompleteCoverageActiveIdentity = null
            recordRuntimeEvent("jinhak-incomplete-coverage-recovery-complete", JSONObject()
                .put("applicationIdentityHash", identity.take(24))
                .put("coverageLanes", jinhakMissionCoverageLedger.lanes(identity).size))
        }
        return mapChanged || ledgerChanged
''',
    'coverage recovery completion hook'
)

# Before generic navigation is considered, give incomplete application coverage a bounded,
# same-card repair attempt.  Once attempts are exhausted, schedule an incomplete terminal finish.
main = replace_once(
    main,
    '''        var exhaustedCurrentMission = false

        val selection = when {
            ledgerTarget != null -> JinhakMissionLaneSequencer.Selection(
''',
    '''        var exhaustedCurrentMission = false
        val incompleteCoverageRecoveryCandidate = if (ledgerTarget == null && jinhakMissionTargetLedger.outstandingCount() == 0) {
            nextJinhakIncompleteCoverageRecoveryCandidate("selection", route)
        } else null
        val incompleteCoverageTerminal = incompleteCoverageRecoveryCandidate == null &&
            maybeFinishJinhakIncompleteCoverage("selection", route)

        val selection = when {
            incompleteCoverageRecoveryCandidate != null -> JinhakMissionLaneSequencer.Selection(
                candidate = incompleteCoverageRecoveryCandidate,
                missionExhaustedAtOrigin = true,
                requestedLane = "current-prediction"
            )
            incompleteCoverageTerminal -> JinhakMissionLaneSequencer.Selection(null, false, "reference")
            ledgerTarget != null -> JinhakMissionLaneSequencer.Selection(
''',
    'selection recovery fence'
)

# Strong login-route evidence.  A URL that is literally the provider login route may no longer
# coexist with authVerified=true / batchPausedForLogin=false.  This closes the v0.9.25 state gap.
main = replace_once(
    main,
    '''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val recoveryActive = startupLoginPreflightActive || jinhakTransitionAuthGateActive || (batchRunning && batchPausedForLogin)
''',
    '''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val currentUrl = if (::webView.isInitialized) webView.url.orEmpty() else ""
        if (batchRunning && isProviderLoginUrl(ProviderId.JINHAK, currentUrl) && !batchPausedForLogin) {
            jinhakLoginUrlStateCorrections += 1
            batchPausedForLogin = true
            batchCollecting = false
            batchNavigationWatchdogRecovery = false
            batchCloudFinalCheckInProgress = false
            disarmBatchNavigationWatchdog()
            jinhakAuthVerifiedForBatch = false
            jinhakProtectedCoreStablePasses = 0
            jinhakCoreBootstrapState = "batch-login-route-wait"
            jinhakReauthCycles += 1
            recordRuntimeEvent("jinhak-login-url-state-correction", JSONObject()
                .put("reason", reason.take(80))
                .put("loginSafePath", runtimeSafePath(currentUrl))
                .put("missionOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("coverageRecoveryExhausted", jinhakIncompleteCoverageRecoveryExhausted()))
            persistJinhakAuthDiagnostics("login-url-state-correction")
        }
        val recoveryActive = startupLoginPreflightActive || jinhakTransitionAuthGateActive || (batchRunning && batchPausedForLogin)
''',
    'strong login state correction'
)

# Post-mission login closure no longer waits for all 180 generic actions.  If coverage is complete
# or its bounded recovery is exhausted, a login route is terminal rather than a reason to explore
# unrelated pages.  Active WebView ownership may be terminal-sealed on the login route itself.
old_post = '''    private fun isJinhakPostMissionClosureReady(): Boolean {
        if (provider != ProviderId.JINHAK || !batchRunning) return false
        val ledgerSummary = jinhakMissionTargetLedger.summary()
        val targetCount = ledgerSummary.optInt("targets", 0)
        if (targetCount <= 0 || jinhakMissionTargetLedger.outstandingCount() != 0) return false
        if (jinhakActiveMissionTargetId != null || jinhakAgentActionInFlight || batchCollecting) return false
        if (jinhakMissionCells.hasActiveOwnership()) return false
        if (::slowLanePool.isInitialized && slowLanePool.hasWork()) return false
        return jinhakGenericActionsExecuted >= MAX_JINHAK_GENERIC_ACTIONS
    }
'''
new_post = '''    private fun isJinhakPostMissionClosureReady(): Boolean {
        if (provider != ProviderId.JINHAK || !batchRunning) return false
        val ledgerSummary = jinhakMissionTargetLedger.summary()
        val targetCount = ledgerSummary.optInt("targets", 0)
        if (targetCount <= 0 || jinhakMissionTargetLedger.outstandingCount() != 0) return false
        val onLoginRoute = ::webView.isInitialized && isProviderLoginUrl(ProviderId.JINHAK, webView.url.orEmpty())
        if (!onLoginRoute) {
            if (jinhakActiveMissionTargetId != null || jinhakAgentActionInFlight || batchCollecting) return false
            if (jinhakMissionCells.hasActiveOwnership()) return false
            if (::slowLanePool.isInitialized && slowLanePool.hasWork()) return false
        }
        val expected = currentExpectedJinhakMissionIdentities()
        if (expected.size >= 6) {
            val audit = jinhakMissionCoverageLedger.summary(expected)
            if (audit.optBoolean("coreComplete", false)) return true
            if (jinhakIncompleteCoverageRecoveryExhausted()) return true
        }
        return jinhakGenericActionsExecuted >= MAX_JINHAK_GENERIC_ACTIONS
    }
'''
main = replace_once(main, old_post, new_post, 'post mission closure policy')

# Export the acceptance diagnostics needed for the next real-device run.
main = replace_once(
    main,
    '''                        .put("coreCoverageClosureFences", jinhakCoreCoverageClosureFences)
                        .put("coreCoverageClosurePending", jinhakCoreCoverageClosurePending)
                        .put("terminalSeals", jinhakTerminalSeals)
''',
    '''                        .put("coreCoverageClosureFences", jinhakCoreCoverageClosureFences)
                        .put("coreCoverageClosurePending", jinhakCoreCoverageClosurePending)
                        .put("incompleteCoverageRecoveryEpisodes", jinhakIncompleteCoverageRecoveryEpisodes)
                        .put("incompleteCoverageRecoveryActions", jinhakIncompleteCoverageRecoveryActions)
                        .put("incompleteCoverageRecoverySuccesses", jinhakIncompleteCoverageRecoverySuccesses)
                        .put("incompleteCoverageFinishes", jinhakIncompleteCoverageFinishes)
                        .put("incompleteCoverageRecoveryExhausted", jinhakIncompleteCoverageRecoveryExhausted())
                        .put("incompleteCoverageActiveIdentityHash", jinhakIncompleteCoverageActiveIdentity?.take(24) ?: JSONObject.NULL)
                        .put("incompleteCoverageRecoveryAttempts", JSONObject(jinhakIncompleteCoverageRecoveryAttempts.mapKeys { it.key.take(24) } as Map<*, *>))
                        .put("loginUrlStateCorrections", jinhakLoginUrlStateCorrections)
                        .put("terminalSeals", jinhakTerminalSeals)
''',
    'recovery diagnostics'
)

MAIN.write_text(main)
LEDGER.write_text(ledger)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('v0.9.26 patch applied')
