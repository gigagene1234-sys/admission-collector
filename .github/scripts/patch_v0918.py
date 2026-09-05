from pathlib import Path

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

# -----------------------------------------------------------------------------
# v0.9.18 — Auth Proof Persistence & Resume Gate
#
# Evidence from the v0.9.17 Galaxy Tab run showed the real Jinhak auth probe and
# protected-core verification succeeded, then process/runtime recreation reset the
# volatile auth fields to their defaults while the SQLite mission ledger survived.
# This patch persists only SAFE auth evidence (timestamps, result strings and
# sanitized host/path), restores it after recreation, and requires a bounded real
# auth probe before resuming a Jinhak mission when no fresh protected-core proof is
# available. Existing mission/same-card/renderer/stall/redirect logic is preserved.
# -----------------------------------------------------------------------------

# Runtime fields used only for safe proof restoration / resume gating.
fields_old = '''    private var jinhakRealAuthProbeBaselineAutoSuccesses = 0
    private var jinhakRealAuthProbeBaselineAutoFailures = 0

    companion object {
'''
fields_new = '''    private var jinhakRealAuthProbeBaselineAutoSuccesses = 0
    private var jinhakRealAuthProbeBaselineAutoFailures = 0
    private var jinhakRealAuthResumeGatePending = false
    private var jinhakAuthProofRestores = 0
    private var jinhakAuthResumeGateRuns = 0

    companion object {
'''
if fields_old not in m:
    raise SystemExit('v0.9.18 runtime field anchor not found')
m = m.replace(fields_old, fields_new, 1)

# Version bump only; preserve all v0.9.17 bounds and safety constants.
version_old = '''        private const val VERSION = "0.9.17"
        private const val BUILD_CODE = 109170
'''
version_new = '''        private const val VERSION = "0.9.18"
        private const val BUILD_CODE = 109180
'''
if version_old not in m:
    raise SystemExit('v0.9.18 version anchor not found')
m = m.replace(version_old, version_new, 1)

# Restore safe proof checkpoint before deciding whether an interrupted unified
# session can resume. Fresh standalone probe proof may also be reused on app launch.
oncreate_old = '''        configureWebView()
        val resumed = resumeInterruptedUnifiedSessionIfNeeded()
        if (!resumed) {
            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {
                handler.postDelayed({ startJinhakRealAuthProbe(autoContinue = true, trigger = "app-launch") }, 350L)
            } else {
                openProvider(ProviderId.JINHAK)
            }
        }
'''
oncreate_new = '''        configureWebView()
        restoreJinhakAuthProofCheckpoint("activity-create")
        val resumed = resumeInterruptedUnifiedSessionIfNeeded()
        if (!resumed) {
            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {
                if (isFreshJinhakRealAuthProbe()) {
                    handler.postDelayed({ startAutomaticLoginAndCollectionSequence("app-launch-restored-real-auth") }, 350L)
                } else {
                    handler.postDelayed({ startJinhakRealAuthProbe(autoContinue = true, trigger = "app-launch") }, 350L)
                }
            } else {
                openProvider(ProviderId.JINHAK)
            }
        }
'''
if oncreate_old not in m:
    raise SystemExit('v0.9.18 onCreate anchor not found')
m = m.replace(oncreate_old, oncreate_new, 1)

# Safe auth-proof checkpoint helpers. No URL query, cookie, token, credential,
# storage, form or session-secret values are persisted here.
checkpoint_anchor = '''    private fun persistRuntimeCheckpoint(forceResume: Boolean = unifiedRunning) {
'''
checkpoint_impl = '''    private fun hasFreshJinhakProtectedCoreProof(): Boolean {
        if (jinhakLastCoreVerifiedAtMs <= 0L) return false
        val age = (System.currentTimeMillis() - jinhakLastCoreVerifiedAtMs).coerceAtLeast(0L)
        if (age > JINHAK_REAL_AUTH_PROBE_FRESH_MS) return false
        return jinhakLastAuthEvidence.startsWith("protected-core-stable") ||
            jinhakLastAuthEvidence.startsWith("real-protected-core-stable")
    }

    private fun persistJinhakAuthProofCheckpoint(synchronous: Boolean = false) {
        runCatching {
            val editor = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit()
                .putString("jinhakAuthProofCollectorVersion", VERSION)
                .putString("jinhakRealAuthProbeResult", jinhakRealAuthProbeResult.take(80))
                .putLong("jinhakRealAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)
                .putLong("jinhakLastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                .putString("jinhakLastAuthEvidence", jinhakLastAuthEvidence.take(80))
                .putString("jinhakAuthProofSafePath", runtimeSafePath(webView.url).take(300))
                .putBoolean("credentialExported", false)
                .putBoolean("sessionSecretExported", false)
            if (synchronous) editor.commit() else editor.apply()
        }
    }

    private fun restoreJinhakAuthProofCheckpoint(trigger: String): Boolean {
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        if (prefs.getString("jinhakAuthProofCollectorVersion", "") != VERSION) return false
        val restoredProbeResult = prefs.getString("jinhakRealAuthProbeResult", "never-run").orEmpty().take(80)
        val restoredProbeAt = prefs.getLong("jinhakRealAuthProbeVerifiedAtMs", 0L)
        val restoredCoreAt = prefs.getLong("jinhakLastCoreVerifiedAtMs", 0L)
        val restoredEvidence = prefs.getString("jinhakLastAuthEvidence", "none").orEmpty().take(80)
        if (restoredProbeAt > jinhakRealAuthProbeVerifiedAtMs) {
            jinhakRealAuthProbeVerifiedAtMs = restoredProbeAt
            jinhakRealAuthProbeResult = restoredProbeResult.ifBlank { "never-run" }
        }
        if (restoredCoreAt > jinhakLastCoreVerifiedAtMs) {
            jinhakLastCoreVerifiedAtMs = restoredCoreAt
            jinhakLastAuthEvidence = restoredEvidence.ifBlank { "none" }
        }
        val fresh = hasFreshJinhakProtectedCoreProof()
        if (fresh) {
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "protected-core-checkpoint-restored"
            jinhakAuthProofRestores += 1
        }
        return fresh
    }

'''
if checkpoint_anchor not in m:
    raise SystemExit('v0.9.18 runtime checkpoint insertion anchor not found')
m = m.replace(checkpoint_anchor, checkpoint_impl + checkpoint_anchor, 1)

# Persist safe proof fields in the normal runtime checkpoint too. apply() remains
# asynchronous here to avoid blocking navigation; successful auth verification also
# performs an explicit synchronous checkpoint below.
persist_old = '''                .putInt("queueSize", batchQueue.size)
                .putInt("errorCount", batchErrors.length())
                .apply()
'''
persist_new = '''                .putInt("queueSize", batchQueue.size)
                .putInt("errorCount", batchErrors.length())
                .putString("jinhakAuthProofCollectorVersion", VERSION)
                .putString("jinhakRealAuthProbeResult", jinhakRealAuthProbeResult.take(80))
                .putLong("jinhakRealAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)
                .putLong("jinhakLastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                .putString("jinhakLastAuthEvidence", jinhakLastAuthEvidence.take(80))
                .putString("jinhakAuthProofSafePath", runtimeSafePath(webView.url).take(300))
                .apply()
'''
if persist_old not in m:
    raise SystemExit('v0.9.18 runtime checkpoint field anchor not found')
m = m.replace(persist_old, persist_new, 1)

# Mirror safe proof into the per-unified-session SQLite runtime checkpoint. This is
# session-scoped and contains no credential/session material.
mission_runtime_old = '''                .put("targetAuthRedirectCounts", JSONObject(jinhakTargetAuthRedirectCounts as Map<*, *>))
                .put("targetAuthRedirectEpisodeOpenKey", if (jinhakTargetAuthRedirectEpisodeOpenKey.isBlank()) JSONObject.NULL else jinhakTargetAuthRedirectEpisodeOpenKey)
                .put("trigger", trigger.take(60))
'''
mission_runtime_new = '''                .put("targetAuthRedirectCounts", JSONObject(jinhakTargetAuthRedirectCounts as Map<*, *>))
                .put("targetAuthRedirectEpisodeOpenKey", if (jinhakTargetAuthRedirectEpisodeOpenKey.isBlank()) JSONObject.NULL else jinhakTargetAuthRedirectEpisodeOpenKey)
                .put("authProofCollectorVersion", VERSION)
                .put("realAuthProbeResult", jinhakRealAuthProbeResult.take(80))
                .put("realAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)
                .put("lastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                .put("lastAuthEvidence", jinhakLastAuthEvidence.take(80))
                .put("authProofSafePath", runtimeSafePath(webView.url).take(300))
                .put("credentialStored", false)
                .put("sessionSecretStored", false)
                .put("trigger", trigger.take(60))
'''
if mission_runtime_old not in m:
    raise SystemExit('v0.9.18 mission runtime anchor not found')
m = m.replace(mission_runtime_old, mission_runtime_new, 1)

# Restore the newest safe session-scoped proof alongside the existing mission state.
restore_runtime_old = '''            jinhakTargetAuthRedirectEpisodeOpenKey = runtime.optString("targetAuthRedirectEpisodeOpenKey")
                .takeIf { it.isNotBlank() && it != "null" }.orEmpty()
        }
'''
restore_runtime_new = '''            jinhakTargetAuthRedirectEpisodeOpenKey = runtime.optString("targetAuthRedirectEpisodeOpenKey")
                .takeIf { it.isNotBlank() && it != "null" }.orEmpty()
            if (runtime.optString("authProofCollectorVersion") == VERSION) {
                val runtimeProbeAt = runtime.optLong("realAuthProbeVerifiedAtMs", 0L)
                val runtimeCoreAt = runtime.optLong("lastCoreVerifiedAtMs", 0L)
                if (runtimeProbeAt > jinhakRealAuthProbeVerifiedAtMs) {
                    jinhakRealAuthProbeVerifiedAtMs = runtimeProbeAt
                    jinhakRealAuthProbeResult = runtime.optString("realAuthProbeResult", "never-run").take(80)
                }
                if (runtimeCoreAt > jinhakLastCoreVerifiedAtMs) {
                    jinhakLastCoreVerifiedAtMs = runtimeCoreAt
                    jinhakLastAuthEvidence = runtime.optString("lastAuthEvidence", "none").take(80)
                }
                if (hasFreshJinhakProtectedCoreProof()) {
                    jinhakAuthVerifiedForBatch = true
                    jinhakCoreBootstrapState = "protected-core-session-checkpoint-restored"
                    jinhakAuthProofRestores += 1
                }
            }
        }
'''
if restore_runtime_old not in m:
    raise SystemExit('v0.9.18 mission restore anchor not found')
m = m.replace(restore_runtime_old, restore_runtime_new, 1)

# Jinhak interrupted-session resume is now auth-gated. A fresh protected-core proof
# gets a short protected-core revalidation before startBatch. If proof is missing or
# stale, the bounded v0.9.17 real-site probe runs first. Never resume via Jinhak home.
resume_old = '''            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = false
            val restoredMissionTargets = restoreJinhakMissionPersistence(sessionId, "activity-resume")
            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()
            status.text = if (lease?.restored == true) {
                "이전 중단 감지: 암호화 로그인 세션과 mission ${restoredMissionTargets}개를 복구하고 진학사 에이전트를 체크포인트에서 재개합니다."
            } else {
                "이전 중단 감지: 저장된 브라우저 세션을 검증한 뒤 진학사 에이전트를 재개합니다."
            }
            webView.loadUrl(ProviderId.JINHAK.homeUrl)
            true
'''
resume_new = '''            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = false
            val restoredMissionTargets = restoreJinhakMissionPersistence(sessionId, "activity-resume")
            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()
            val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
            if (hasFreshJinhakProtectedCoreProof() && coreProbe.isNotBlank()) {
                jinhakAuthVerifiedForBatch = false
                jinhakCoreBootstrapState = "resume-core-revalidate"
                jinhakLastAuthEvidence = "resume-core-revalidation-pending"
                jinhakTransitionAuthGateActive = true
                status.text = "이전 중단 감지: mission ${restoredMissionTargets}개와 최신 보호경로 인증 증거를 복구했습니다. 실제 수시저장소를 재검증한 뒤 재개합니다."
                recordRuntimeEvent("jinhak-resume-auth-proof-restored", JSONObject()
                    .put("restoredMissionTargets", restoredMissionTargets)
                    .put("leaseRestored", lease?.restored == true)
                    .put("proofAgeMs", (System.currentTimeMillis() - jinhakLastCoreVerifiedAtMs).coerceAtLeast(0L))
                    .put("coreSafePath", runtimeSafePath(coreProbe))
                    .put("credentialExported", false)
                    .put("sessionSecretExported", false))
                webView.loadUrl(coreProbe)
            } else {
                unifiedPendingJinhakStart = false
                jinhakRealAuthResumeGatePending = true
                jinhakAuthResumeGateRuns += 1
                status.text = "이전 중단 감지: mission ${restoredMissionTargets}개는 보존됐지만 최신 인증 증거가 없어 실제 진학사 로그인 진단을 먼저 실행합니다."
                recordRuntimeEvent("jinhak-resume-real-auth-gate-required", JSONObject()
                    .put("restoredMissionTargets", restoredMissionTargets)
                    .put("leaseRestored", lease?.restored == true)
                    .put("proofFresh", false)
                    .put("credentialExported", false)
                    .put("sessionSecretExported", false))
                handler.postDelayed({
                    if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning && jinhakRealAuthResumeGatePending) {
                        startJinhakRealAuthProbe(autoContinue = true, trigger = "activity-resume-auth-gate")
                    }
                }, 350L)
            }
            true
'''
if resume_old not in m:
    raise SystemExit('v0.9.18 Jinhak resume anchor not found')
m = m.replace(resume_old, resume_new, 1)

# Permit the auth-only probe during exactly one safe state that v0.9.17 previously
# rejected: a restored unified Jinhak session with batch not yet running.
probe_guard_old = '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        if (jinhakRealAuthProbeActive) return
        if (unifiedRunning || batchRunning || startupLoginPreflightActive) {
            Toast.makeText(this, "진행 중인 수집/로그인 준비가 있어 실제 진학사 로그인 진단을 시작할 수 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
'''
probe_guard_new = '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        if (jinhakRealAuthProbeActive) return
        val restoredResumeGate = jinhakRealAuthResumeGatePending && unifiedRunning &&
            unifiedPhase == "jinhak" && !batchRunning && !startupLoginPreflightActive
        if ((!restoredResumeGate && unifiedRunning) || batchRunning || startupLoginPreflightActive) {
            Toast.makeText(this, "진행 중인 수집/로그인 준비가 있어 실제 진학사 로그인 진단을 시작할 수 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
'''
if probe_guard_old not in m:
    raise SystemExit('v0.9.18 real auth probe guard anchor not found')
m = m.replace(probe_guard_old, probe_guard_new, 1)

# Successful/failed probe state is synchronously checkpointed. Failure invalidates
# any older protected-core proof so it cannot be reused after a failed current probe.
probe_finish_state_old = '''        if (success) {
            jinhakRealAuthProbeVerifiedAtMs = System.currentTimeMillis()
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "real-protected-core-verified"
            jinhakLastAuthEvidence = "real-protected-core-stable"
            jinhakLastCoreVerifiedAtMs = jinhakRealAuthProbeVerifiedAtMs
            val current = webView.url.orEmpty()
            if (current.isNotBlank()) runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, current, VERSION) }
        } else {
            jinhakAuthVerifiedForBatch = false
            jinhakCoreBootstrapState = "real-auth-probe-failed"
            jinhakLastAuthEvidence = result.take(80)
            runCatching { webView.stopLoading() }
        }
'''
probe_finish_state_new = '''        if (success) {
            jinhakRealAuthProbeVerifiedAtMs = System.currentTimeMillis()
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "real-protected-core-verified"
            jinhakLastAuthEvidence = "real-protected-core-stable"
            jinhakLastCoreVerifiedAtMs = jinhakRealAuthProbeVerifiedAtMs
            val current = webView.url.orEmpty()
            if (current.isNotBlank()) runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, current, VERSION) }
        } else {
            jinhakAuthVerifiedForBatch = false
            jinhakCoreBootstrapState = "real-auth-probe-failed"
            jinhakLastAuthEvidence = result.take(80)
            jinhakLastCoreVerifiedAtMs = 0L
            runCatching { webView.stopLoading() }
        }
        persistJinhakAuthProofCheckpoint(synchronous = true)
'''
if probe_finish_state_old not in m:
    raise SystemExit('v0.9.18 probe finish state anchor not found')
m = m.replace(probe_finish_state_old, probe_finish_state_new, 1)

# Resume-gate success continues the same persisted unified session and mission ledger;
# it must not create a fresh unified session. Failure stops after the bounded probe and
# leaves the preserved session paused for a manual retry/stop rather than looping.
probe_autocontinue_old = '''        if (success && autoContinue) {
            handler.postDelayed({
                if (!unifiedRunning && !batchRunning && !startupLoginPreflightActive) {
                    startAutomaticLoginAndCollectionSequence("real-jinhak-auth-probe")
                }
            }, 250L)
        }
'''
probe_autocontinue_new = '''        if (success && autoContinue) {
            if (jinhakRealAuthResumeGatePending && unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) {
                jinhakRealAuthResumeGatePending = false
                unifiedPendingJinhakStart = false
                status.text = "재개 인증 진단 통과 · 보존된 mission ledger에서 진학사 수집을 재개합니다."
                handler.postDelayed({
                    if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
                }, 250L)
            } else {
                handler.postDelayed({
                    if (!unifiedRunning && !batchRunning && !startupLoginPreflightActive) {
                        startAutomaticLoginAndCollectionSequence("real-jinhak-auth-probe")
                    }
                }, 250L)
            }
        }
'''
if probe_autocontinue_old not in m:
    raise SystemExit('v0.9.18 probe auto-continue anchor not found')
m = m.replace(probe_autocontinue_old, probe_autocontinue_new, 1)

# Every successful protected-core verification refreshes a synchronous safe proof
# checkpoint, not only the initial real-auth probe.
verified_old = '''        runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }
        persistJinhakAuthDiagnostics("$reason-auth-verified")
'''
verified_new = '''        runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }
        persistJinhakAuthProofCheckpoint(synchronous = true)
        persistJinhakMissionRuntimeState("protected-core-auth-verified")
        persistJinhakAuthDiagnostics("$reason-auth-verified")
'''
if verified_old not in m:
    raise SystemExit('v0.9.18 verified auth checkpoint anchor not found')
m = m.replace(verified_old, verified_new, 1)

# Add explicit diagnostics so a later export can distinguish probe success, proof
# restore and resume-gate execution instead of collapsing to never-run.
auth_diag_old = '''                    .put("realJinhakAuthRouteTransitions", jinhakRealAuthProbeRouteEvents.length())
                    .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
'''
auth_diag_new = '''                    .put("realJinhakAuthRouteTransitions", jinhakRealAuthProbeRouteEvents.length())
                    .put("authProofRestores", jinhakAuthProofRestores)
                    .put("authResumeGateRuns", jinhakAuthResumeGateRuns)
                    .put("authResumeGatePending", jinhakRealAuthResumeGatePending)
                    .put("freshProtectedCoreProof", hasFreshJinhakProtectedCoreProof())
                    .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
'''
if auth_diag_old not in m:
    raise SystemExit('v0.9.18 auth diagnostic anchor not found')
m = m.replace(auth_diag_old, auth_diag_new, 1)

# The same fields appear in the final aggregate summary. Replace only the first
# matching aggregate diagnostic block after the auth-specific insertion has consumed
# its own occurrence.
aggregate_old = '''                    .put("realJinhakAuthRouteTransitions", jinhakRealAuthProbeRouteEvents.length())
                    .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
'''
aggregate_new = '''                    .put("realJinhakAuthRouteTransitions", jinhakRealAuthProbeRouteEvents.length())
                    .put("authProofRestores", jinhakAuthProofRestores)
                    .put("authResumeGateRuns", jinhakAuthResumeGateRuns)
                    .put("authResumeGatePending", jinhakRealAuthResumeGatePending)
                    .put("freshProtectedCoreProof", hasFreshJinhakProtectedCoreProof())
                    .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
'''
if aggregate_old in m:
    m = m.replace(aggregate_old, aggregate_new, 1)

# Version metadata.
if 'versionCode = 109170' not in g or 'versionName = "0.9.17"' not in g:
    raise SystemExit('v0.9.18 Gradle version anchor not found')
g = g.replace('versionCode = 109170', 'versionCode = 109180', 1)
g = g.replace('versionName = "0.9.17"', 'versionName = "0.9.18"', 1)

old_label = 'Admission Collector v0.9.17 Real Jinhak Auth Gate'
new_label = 'Admission Collector v0.9.18 Auth Proof Resume Gate'
if old_label not in manifest:
    raise SystemExit('v0.9.18 manifest label anchor not found')
manifest = manifest.replace(old_label, new_label, 1)

# Static safety/invariant assertions before writing.
required = [
    'private const val VERSION = "0.9.18"',
    'private const val BUILD_CODE = 109180',
    'persistJinhakAuthProofCheckpoint',
    'restoreJinhakAuthProofCheckpoint',
    'hasFreshJinhakProtectedCoreProof',
    'jinhak-resume-real-auth-gate-required',
    'jinhakRealAuthResumeGatePending',
    'startJinhakRealAuthProbe',
    'auth-route-cycle-detected',
    'quarantineJinhakTargetSpecificAuthRedirect',
    'recoverOrStopJinhakMissionStall',
    'MAX_JINHAK_SAME_CARD_REPLAY_ATTEMPTS = 3',
    'isDefaultSusiCoreTraversalUrl',
]
missing = [x for x in required if x not in m]
if missing:
    raise SystemExit('v0.9.18 required invariant missing: ' + ', '.join(missing))
for forbidden in [
    '.put("username", credentials.username)',
    '.put("password", credentials.password)',
    '.put("cookie",',
    '.put("localStorage",',
    '.put("sessionStorage",',
]:
    if forbidden in m:
        raise SystemExit('v0.9.18 privacy invariant failed: ' + forbidden)

main_path.write_text(m)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('v0.9.18 Auth Proof Persistence & Resume Gate patch applied')
