from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
LEDGER = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionTargetLedger.kt'
POLICY = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakAuthDomainPolicy.kt'
TEST = ROOT / 'app/src/test/java/com/admissionhub/collector/jinhak/JinhakAuthDomainPolicyTest.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, found {n}')
    return text.replace(old, new, 1)

main = MAIN.read_text()
ledger = LEDGER.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.10.1"',
    'private const val BUILD_CODE = 110010',
    'private fun startSelectedSixRecovery()',
    'private fun scheduleJinhakLoginRecovery(reason: String)',
    'private fun noteJinhakTargetAuthRedirectEpisode(source: String): Int',
    'private fun quarantineJinhakTargetSpecificAuthRedirect(retry: String?, reason: String): Boolean',
    'jinhakActiveMissionTargetId = ledgerTargetIdForAction',
]:
    if token not in main:
        raise SystemExit('v0.10.1 source precondition failed: ' + token)

# Pure policy + Mission Lab unit test: after repeated auth issues, move classification out of UI callbacks.
POLICY.parent.mkdir(parents=True, exist_ok=True)
POLICY.write_text(r'''package com.admissionhub.collector.jinhak

/**
 * Pure decision policy for v0.10.2 auth-domain separation.
 *
 * A provider-wide login failure and a target-specific redirect are different domains.
 * A repeated redirect for the same target after a recent protected-core proof is therefore
 * quarantined as a target failure instead of forcing another global re-authentication cycle.
 */
object JinhakAuthDomainPolicy {
    enum class RedirectDecision { GLOBAL_REAUTH, TARGET_QUARANTINE }

    fun redirectDecision(
        redirectCycles: Int,
        threshold: Int,
        protectedCoreFresh: Boolean
    ): RedirectDecision = if (
        protectedCoreFresh && threshold > 0 && redirectCycles >= threshold
    ) RedirectDecision.TARGET_QUARANTINE else RedirectDecision.GLOBAL_REAUTH

    /** Never drop an active mission owner merely because a report/generic action has no ledger id. */
    fun preserveMissionOwner(currentOwner: String?, candidateLedgerTarget: String?): String? =
        candidateLedgerTarget ?: currentOwner

    /** Generic exploration is legal only after all persistent mission work is terminal. */
    fun allowGenericNavigation(missionOutstanding: Int): Boolean = missionOutstanding <= 0
}
''')

TEST.parent.mkdir(parents=True, exist_ok=True)
TEST.write_text(r'''package com.admissionhub.collector.jinhak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakAuthDomainPolicyTest {
    @Test fun secondRedirectWithFreshCoreQuarantinesTarget() {
        assertEquals(
            JinhakAuthDomainPolicy.RedirectDecision.TARGET_QUARANTINE,
            JinhakAuthDomainPolicy.redirectDecision(2, 2, true)
        )
    }

    @Test fun firstRedirectStillRevalidatesGlobalAuth() {
        assertEquals(
            JinhakAuthDomainPolicy.RedirectDecision.GLOBAL_REAUTH,
            JinhakAuthDomainPolicy.redirectDecision(1, 2, true)
        )
    }

    @Test fun staleCoreProofCannotFastQuarantine() {
        assertEquals(
            JinhakAuthDomainPolicy.RedirectDecision.GLOBAL_REAUTH,
            JinhakAuthDomainPolicy.redirectDecision(2, 2, false)
        )
    }

    @Test fun reportActionWithoutLedgerIdPreservesMissionOwner() {
        assertEquals("mission-17", JinhakAuthDomainPolicy.preserveMissionOwner("mission-17", null))
        assertEquals("mission-18", JinhakAuthDomainPolicy.preserveMissionOwner("mission-17", "mission-18"))
    }

    @Test fun genericNavigationBlockedWhileMissionOutstanding() {
        assertFalse(JinhakAuthDomainPolicy.allowGenericNavigation(2))
        assertTrue(JinhakAuthDomainPolicy.allowGenericNavigation(0))
    }
}
''')

# Version and label.
main = replace_once(main, 'private const val VERSION = "0.10.1"', 'private const val VERSION = "0.10.2"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 110010', 'private const val BUILD_CODE = 110020', 'build code')
gradle = replace_once(gradle, 'versionCode = 110010', 'versionCode = 110020', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.10.1"', 'versionName = "0.10.2"', 'gradle version name')
manifest = replace_once(manifest, 'Admission Hub v0.10.1 Selected Six Recovery', 'Admission Hub v0.10.2 Auth Ownership Repair', 'manifest label')

# JUnit Mission Lab dependency.
if 'testImplementation("junit:junit:4.13.2")' not in gradle:
    gradle = gradle.rstrip() + '\n\ndependencies {\n    testImplementation("junit:junit:4.13.2")\n}\n'

# Explicit policy import.
main = replace_once(
    main,
    'import com.admissionhub.collector.jinhak.JinhakMissionCellSupervisor\n',
    'import com.admissionhub.collector.jinhak.JinhakMissionCellSupervisor\nimport com.admissionhub.collector.jinhak.JinhakAuthDomainPolicy\n',
    'policy import'
)

# Diagnostics/counters for the newly separated domains.
main = replace_once(
    main,
    '    private var jinhakLastTargetAuthRedirectSafePath = ""\n',
    '    private var jinhakLastTargetAuthRedirectSafePath = ""\n'
    '    private var jinhakFreshCoreFastQuarantines = 0\n'
    '    private var jinhakOrphanOutstandingRecoveries = 0\n'
    '    private var jinhakActiveOwnerPreservations = 0\n'
    '    private var hubEditsBlockedDuringCollection = 0\n',
    'new mission/auth counters'
)
main = replace_once(
    main,
    '    private var credentialAutoLoginFailures = 0\n    private var credentialAutoLoginLastResult = ""\n',
    '    private var credentialAutoLoginFailures = 0\n'
    '    private var credentialAutoLoginSuppressedInFlight = 0\n'
    '    private var credentialAutoLoginSuppressedThrottle = 0\n'
    '    private var credentialAutoLoginSuppressedNoCredential = 0\n'
    '    private var credentialAutoLoginSuppressedProbeLost = 0\n'
    '    private var credentialAutoLoginSuppressedRetryLimit = 0\n'
    '    private var credentialAutoLoginLastResult = ""\n',
    'auto login suppression counters'
)
main = replace_once(
    main,
    '        private const val MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES = 2\n',
    '        private const val MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES = 2\n'
    '        private const val JINHAK_TARGET_REDIRECT_FRESH_CORE_MS = 120_000L\n',
    'fresh core constant'
)

# Startup: when six slots already exist, do not automatically launch a 27-target recrawl.
old_startup = '''            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {
                if (isFreshJinhakRealAuthProbe()) {
                    handler.postDelayed({ startAutomaticLoginAndCollectionSequence("app-launch-restored-real-auth") }, 350L)
                } else {
                    handler.postDelayed({ startJinhakRealAuthProbe(autoContinue = true, trigger = "app-launch") }, 350L)
                }
            } else {
                openProvider(ProviderId.JINHAK)
            }
'''
new_startup = '''            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {
                handler.postDelayed({ startLaunchAwareCollection() }, 350L)
            } else {
                openProvider(ProviderId.JINHAK)
            }
'''
main = replace_once(main, old_startup, new_startup, 'launch-aware collection')

# Manual main button also prefers selected-six repair when six selected slots are incomplete.
main = replace_once(main, '                    else -> startUnifiedCollection()\n', '                    else -> startPreferredHubCollection()\n', 'unified button preferred path')

helper_anchor = '    private fun startSelectedSixRecovery() {\n'
helpers = r'''    private fun selectedSixRecoveryNeeded(): Boolean {
        val sessionId = localStore.latestUnifiedSession() ?: return false
        val audit = localStore.canonicalHubSummary(sessionId).optJSONObject("qualityAudit") ?: return false
        val slots = audit.optJSONObject("sixSlots") ?: return false
        return slots.optInt("selected", 0) == 6 && slots.optInt("fullCoreCoverage", 0) < 6
    }

    private fun selectedSixAlreadyComplete(): Boolean {
        val sessionId = localStore.latestUnifiedSession() ?: return false
        val audit = localStore.canonicalHubSummary(sessionId).optJSONObject("qualityAudit") ?: return false
        val slots = audit.optJSONObject("sixSlots") ?: return false
        return slots.optInt("selected", 0) == 6 && slots.optInt("fullCoreCoverage", 0) == 6
    }

    private fun startLaunchAwareCollection() {
        // On app launch, six-slot Hub state is authoritative. Never silently spend another
        // full 27-target run when the user has already fixed their six applications.
        when {
            selectedSixRecoveryNeeded() -> startSelectedSixRecovery()
            selectedSixAlreadyComplete() -> {
                rebuildCanonicalHubFromLatestSessionIfReady("launch-six-complete")
                openProvider(ProviderId.JINHAK)
                status.text = "선택한 6장의 핵심 coverage가 완료되어 앱 시작 시 전체 재수집을 생략했습니다. 필요할 때 통합 수집 버튼으로 갱신하세요."
            }
            isFreshJinhakRealAuthProbe() -> startAutomaticLoginAndCollectionSequence("app-launch-restored-real-auth")
            else -> startJinhakRealAuthProbe(autoContinue = true, trigger = "app-launch")
        }
    }

    private fun startPreferredHubCollection() {
        if (selectedSixRecoveryNeeded()) {
            startSelectedSixRecovery()
        } else {
            startUnifiedCollection()
        }
    }

'''
main = replace_once(main, helper_anchor, helpers + helper_anchor, 'selected-six preferred helpers')

# While collection is active, the slot graph is immutable for this session.
main = replace_once(
    main,
    '    private fun showHubSixManager() {\n        val sessionId = localStore.latestUnifiedSession()\n',
    '    private fun showHubSixManager() {\n'
    '        if (unifiedRunning || batchRunning || startupLoginPreflightActive) {\n'
    '            hubEditsBlockedDuringCollection += 1\n'
    '            Toast.makeText(this, "수집 중에는 지원 6장을 변경할 수 없습니다. 현재 작업 종료 후 변경해주세요.", Toast.LENGTH_LONG).show()\n'
    '            return\n'
    '        }\n'
    '        val sessionId = localStore.latestUnifiedSession()\n',
    'hub edit fence'
)
main = replace_once(
    main,
    '    private fun publishHubAuditState(sessionId: String, summary: JSONObject, trigger: String) {\n        val audit = summary.optJSONObject("qualityAudit") ?: return\n',
    '    private fun publishHubAuditState(sessionId: String, summary: JSONObject, trigger: String) {\n'
    '        if (unifiedRunning || batchRunning || startupLoginPreflightActive) {\n'
    '            hubEditsBlockedDuringCollection += 1\n'
    '            recordRuntimeEvent("hub-publish-blocked-during-collection", JSONObject().put("trigger", trigger.take(80)))\n'
    '            return\n'
    '        }\n'
    '        val audit = summary.optJSONObject("qualityAudit") ?: return\n',
    'hub publish fence'
)

# Auth-domain classification helper adjacent to target redirect tracking.
auth_anchor = '    private fun noteJinhakTargetAuthRedirectEpisode(source: String): Int {\n'
auth_helper = r'''    private fun hasFreshProtectedCoreProofForTargetRedirect(): Boolean {
        if (!jinhakAuthVerifiedForBatch || jinhakLastAuthEvidence != "protected-core-stable" || jinhakLastCoreVerifiedAtMs <= 0L) return false
        val ageMs = (System.currentTimeMillis() - jinhakLastCoreVerifiedAtMs).coerceAtLeast(0L)
        return ageMs <= JINHAK_TARGET_REDIRECT_FRESH_CORE_MS
    }

    private fun fastQuarantineRepeatedTargetRedirect(cycles: Int, reason: String): Boolean {
        val decision = JinhakAuthDomainPolicy.redirectDecision(
            cycles,
            MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES,
            hasFreshProtectedCoreProofForTargetRedirect()
        )
        if (decision != JinhakAuthDomainPolicy.RedirectDecision.TARGET_QUARANTINE) return false
        val quarantined = quarantineJinhakTargetSpecificAuthRedirect(currentBatchTarget, reason)
        if (quarantined) {
            jinhakFreshCoreFastQuarantines += 1
            recordRuntimeEvent("jinhak-fresh-core-fast-target-quarantine", JSONObject()
                .put("cycles", cycles)
                .put("targetSafePath", runtimeSafePath(currentBatchTarget))
                .put("freshCoreAgeMs", (System.currentTimeMillis() - jinhakLastCoreVerifiedAtMs).coerceAtLeast(0L))
                .put("globalReauthSkipped", true))
        }
        return quarantined
    }

'''
main = replace_once(main, auth_anchor, auth_helper + auth_anchor, 'auth domain helper')

# If the rendered login detector fires first, second same-target redirect with fresh core proof is local target failure.
main = replace_once(
    main,
    '''        batchRenderedLoginSurfacePauses += 1
        batchPausedForLogin = true
        if (which == ProviderId.JINHAK) noteJinhakTargetAuthRedirectEpisode("rendered-login-surface")
        batchCollecting = false
''',
    '''        batchRenderedLoginSurfacePauses += 1
        batchPausedForLogin = true
        if (which == ProviderId.JINHAK) {
            val cycles = noteJinhakTargetAuthRedirectEpisode("rendered-login-surface")
            if (fastQuarantineRepeatedTargetRedirect(cycles, "rendered-login-surface-fresh-core")) return
        }
        batchCollecting = false
''',
    'rendered login fast quarantine'
)

# If route correction wins the race, apply the same classification before global auth is invalidated.
main = replace_once(
    main,
    '''        if (batchRunning && isProviderLoginUrl(ProviderId.JINHAK, currentUrl) && !batchPausedForLogin) {
            jinhakLoginUrlStateCorrections += 1
            batchPausedForLogin = true
''',
    '''        if (batchRunning && isProviderLoginUrl(ProviderId.JINHAK, currentUrl) && !batchPausedForLogin) {
            jinhakLoginUrlStateCorrections += 1
            val cycles = noteJinhakTargetAuthRedirectEpisode("login-url-state-correction")
            if (fastQuarantineRepeatedTargetRedirect(cycles, "login-url-state-correction-fresh-core")) return
            batchPausedForLogin = true
''',
    'login route correction fast quarantine'
)

# The normal page guard also checks before setting global auth false.
main = replace_once(
    main,
    '''                if (expectedProvider == ProviderId.JINHAK) {
                    noteJinhakTargetAuthRedirectEpisode("login-route-fallback")
                    jinhakAuthVerifiedForBatch = false
                    jinhakCoreBootstrapState = "batch-login-route-wait"
                }
''',
    '''                if (expectedProvider == ProviderId.JINHAK) {
                    val cycles = noteJinhakTargetAuthRedirectEpisode("login-route-fallback")
                    if (fastQuarantineRepeatedTargetRedirect(cycles, "login-route-fallback-fresh-core")) return@probeLoginSurface
                    jinhakAuthVerifiedForBatch = false
                    jinhakCoreBootstrapState = "batch-login-route-wait"
                }
''',
    'page guard fast quarantine'
)

# Mission owner must survive non-ledger report actions. Replay orphaned CLICKED/DEFERRED target instead of generic crawl.
main = replace_once(
    main,
    '''        jinhakActiveMissionTargetId = ledgerTargetIdForAction
        if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markAttempted(ledgerTargetIdForAction)
''',
    '''        val previousMissionOwner = jinhakActiveMissionTargetId
        val nextMissionOwner = JinhakAuthDomainPolicy.preserveMissionOwner(previousMissionOwner, ledgerTargetIdForAction)
        if (ledgerTargetIdForAction == null && previousMissionOwner != null && nextMissionOwner == previousMissionOwner) {
            jinhakActiveOwnerPreservations += 1
        }
        jinhakActiveMissionTargetId = nextMissionOwner
        if (ledgerTargetIdForAction != null) {
            val previousState = jinhakMissionTargetLedger.stateOf(ledgerTargetIdForAction)
            if (previousState == JinhakMissionTargetLedger.State.CLICKED || previousState == JinhakMissionTargetLedger.State.DEFERRED) {
                jinhakOrphanOutstandingRecoveries += 1
                recordRuntimeEvent("jinhak-orphan-outstanding-replay", JSONObject()
                    .put("targetIdHash", ledgerTargetIdForAction.take(24))
                    .put("previousState", previousState.name.lowercase()))
            }
            jinhakMissionTargetLedger.markAttempted(ledgerTargetIdForAction)
        }
''',
    'active owner preservation'
)
main = replace_once(
    main,
    '''            currentMissionKey == null && jinhakMissionTargetLedger.hasActionablePending() ->
                JinhakMissionLaneSequencer.Selection(null, false, "reference")
''',
    '''            currentMissionKey == null && !JinhakAuthDomainPolicy.allowGenericNavigation(jinhakMissionTargetLedger.outstandingCount()) ->
                JinhakMissionLaneSequencer.Selection(null, false, "reference")
''',
    'generic outstanding fence'
)

# Ledger's actionable route includes monotonic CLICKED/DEFERRED states; no state downgrade is performed.
ledger = replace_once(
    ledger,
    '    fun hasActionablePending(): Boolean = targets.values.any { it.state == State.PENDING }\n',
    '    fun hasActionablePending(): Boolean = targets.values.any { it.state == State.PENDING || it.state == State.CLICKED || it.state == State.DEFERRED }\n',
    'ledger actionable outstanding'
)
ledger = replace_once(
    ledger,
    '''    fun originForNextPending(preferredIdentityKey: String? = null): String? {
        val preferred = preferredIdentityKey?.let { key ->
            sortedTargets().firstOrNull { it.identityKey == key && it.state == State.PENDING }
        }
        return preferred?.originRoute ?: sortedTargets().firstOrNull { it.state == State.PENDING }?.originRoute
    }
''',
    '''    fun originForNextPending(preferredIdentityKey: String? = null): String? {
        fun actionable(target: Target): Boolean = target.state == State.PENDING || target.state == State.CLICKED || target.state == State.DEFERRED
        val preferred = preferredIdentityKey?.let { key ->
            sortedTargets().firstOrNull { it.identityKey == key && actionable(it) }
        }
        return preferred?.originRoute ?: sortedTargets().firstOrNull(::actionable)?.originRoute
    }
''',
    'ledger actionable origin'
)
ledger = replace_once(
    ledger,
    '        val sameOrigin = sortedTargets().filter { it.originRoute == originRoute && it.state == State.PENDING }\n',
    '        val sameOrigin = sortedTargets().filter { it.originRoute == originRoute && (it.state == State.PENDING || it.state == State.CLICKED || it.state == State.DEFERRED) }\n',
    'ledger replay candidates'
)

# Diagnose why a rendered login surface did not dispatch a saved-credential attempt.
main = replace_once(
    main,
    '''        if (provider != which) return
        val now = System.currentTimeMillis()
        if (credentialAutoLoginInFlight && now - credentialAutoLoginLastAttemptAtMs < 6_000L) return
        if (now - credentialAutoLoginLastAttemptAtMs < 900L) return
        val credentials = runCatching { credentialVault.load(which.wireName) }.getOrNull() ?: return
''',
    '''        if (provider != which) return
        val now = System.currentTimeMillis()
        if (credentialAutoLoginInFlight && now - credentialAutoLoginLastAttemptAtMs < 6_000L) {
            credentialAutoLoginSuppressedInFlight += 1
            return
        }
        if (now - credentialAutoLoginLastAttemptAtMs < 900L) {
            credentialAutoLoginSuppressedThrottle += 1
            return
        }
        val credentials = runCatching { credentialVault.load(which.wireName) }.getOrNull()
        if (credentials == null) {
            credentialAutoLoginSuppressedNoCredential += 1
            return
        }
''',
    'auto login early diagnostics'
)
main = replace_once(
    main,
    '            if (!probe.optBoolean("detected", false)) return@probeLoginSurface\n            val surfaceKey = which.wireName + "|" + runtimeSafePath(webView.url)\n',
    '            if (!probe.optBoolean("detected", false)) {\n'
    '                credentialAutoLoginSuppressedProbeLost += 1\n'
    '                return@probeLoginSurface\n'
    '            }\n'
    '            val surfaceKey = which.wireName + "|" + runtimeSafePath(webView.url)\n',
    'auto login probe lost diagnostic'
)
main = replace_once(
    main,
    '''            if (credentialLoginSurfaceAttempts >= 2) {
                sessionState.text = "△ ${which.displayName} 자동 로그인 재시도 한도 도달"
                return@probeLoginSurface
            }
''',
    '''            if (credentialLoginSurfaceAttempts >= 2) {
                credentialAutoLoginSuppressedRetryLimit += 1
                sessionState.text = "△ ${which.displayName} 자동 로그인 재시도 한도 도달"
                return@probeLoginSurface
            }
''',
    'auto login retry diagnostic'
)

# Add diagnostics to all relevant JSON summaries without exposing credentials.
main = main.replace(
    '.put("targetAuthRedirectQuarantines", jinhakTargetAuthRedirectQuarantines)\n',
    '.put("targetAuthRedirectQuarantines", jinhakTargetAuthRedirectQuarantines)\n'
    '                    .put("freshCoreFastTargetQuarantines", jinhakFreshCoreFastQuarantines)\n'
    '                    .put("orphanOutstandingRecoveries", jinhakOrphanOutstandingRecoveries)\n'
    '                    .put("activeOwnerPreservations", jinhakActiveOwnerPreservations)\n'
    '                    .put("hubEditsBlockedDuringCollection", hubEditsBlockedDuringCollection)\n'
)
main = main.replace(
    '.put("credentialAutoLoginFailures", credentialAutoLoginFailures)\n',
    '.put("credentialAutoLoginFailures", credentialAutoLoginFailures)\n'
    '                    .put("credentialAutoLoginSuppressedInFlight", credentialAutoLoginSuppressedInFlight)\n'
    '                    .put("credentialAutoLoginSuppressedThrottle", credentialAutoLoginSuppressedThrottle)\n'
    '                    .put("credentialAutoLoginSuppressedNoCredential", credentialAutoLoginSuppressedNoCredential)\n'
    '                    .put("credentialAutoLoginSuppressedProbeLost", credentialAutoLoginSuppressedProbeLost)\n'
    '                    .put("credentialAutoLoginSuppressedRetryLimit", credentialAutoLoginSuppressedRetryLimit)\n'
)

# Reset new counters when mission state is not being deliberately preserved.
main = replace_once(
    main,
    '''            jinhakTargetAuthRedirectQuarantines = 0
            jinhakLastTargetAuthRedirectSafePath = ""
''',
    '''            jinhakTargetAuthRedirectQuarantines = 0
            jinhakFreshCoreFastQuarantines = 0
            jinhakOrphanOutstandingRecoveries = 0
            jinhakActiveOwnerPreservations = 0
            jinhakLastTargetAuthRedirectSafePath = ""
''',
    'auth counter reset'
)

MAIN.write_text(main)
LEDGER.write_text(ledger)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

checks = {
    'version': 'private const val VERSION = "0.10.2"' in main and 'versionCode = 110020' in gradle,
    'policy': POLICY.exists() and 'TARGET_QUARANTINE' in POLICY.read_text(),
    'mission-lab': TEST.exists() and 'secondRedirectWithFreshCoreQuarantinesTarget' in TEST.read_text(),
    'fast-quarantine': 'jinhak-fresh-core-fast-target-quarantine' in main,
    'owner-preserve': 'preserveMissionOwner' in main and 'jinhakActiveOwnerPreservations' in main,
    'orphan-replay': 'State.CLICKED || previousState == JinhakMissionTargetLedger.State.DEFERRED' in main,
    'generic-fence': 'allowGenericNavigation(jinhakMissionTargetLedger.outstandingCount())' in main,
    'selected-six-default': 'startLaunchAwareCollection' in main and 'startPreferredHubCollection' in main,
    'hub-edit-fence': 'hub-publish-blocked-during-collection' in main,
    'auto-login-diagnostics': 'credentialAutoLoginSuppressedProbeLost' in main,
}
failed = [k for k,v in checks.items() if not v]
if failed:
    raise SystemExit('v0.10.2 postcondition failed: ' + ', '.join(failed))
print('v0.10.2 auth domain + mission ownership repair patch applied')
