from pathlib import Path

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

# -----------------------------------------------------------------------------
# v0.9.16: Target-Specific Auth Redirect Loop Guard
#
# Real-device v0.9.15 evidence showed a bounded but real auth loop:
# target -> /member/login -> protected library verifies authenticated -> retry same
# target -> /member/login again. The provider session itself remained valid, so a
# successful library probe must not imply the repeatedly redirecting target will
# become reachable. This release changes only this target-specific loop behavior.
# -----------------------------------------------------------------------------

field_anchor = '''    private var jinhakMissionOriginSnapshotErrorTotal = 0
    private var jinhakLastMissionOriginSnapshotErrorType = ""
'''
field_new = field_anchor + '''    private val jinhakTargetAuthRedirectCounts = linkedMapOf<String, Int>()
    private val jinhakTargetAuthRedirectQuarantinedKeys = linkedSetOf<String>()
    private var jinhakTargetAuthRedirectEpisodeOpenKey = ""
    private var jinhakTargetAuthRedirectEpisodes = 0
    private var jinhakTargetAuthRedirectQuarantines = 0
    private var jinhakLastTargetAuthRedirectSafePath = ""
'''
if field_anchor not in m:
    raise SystemExit('v0.9.16 field anchor not found')
m = m.replace(field_anchor, field_new, 1)

const_anchor = '''        private const val MAX_JINHAK_MISSION_ORIGIN_ERROR_STREAK = 5
        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L
'''
const_new = '''        private const val MAX_JINHAK_MISSION_ORIGIN_ERROR_STREAK = 5
        private const val MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES = 2
        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L
'''
if const_anchor not in m:
    raise SystemExit('v0.9.16 constant anchor not found')
m = m.replace(const_anchor, const_new, 1)

# Persist the per-target redirect cycle map inside the existing non-sensitive
# mission runtime checkpoint. Keys are SHA-256 hashes of canonical target URLs;
# raw URLs, cookies and credentials are not added.
runtime_store_anchor = '''                .put("missionNeedsReturn", jinhakMissionNeedsReturn)
                .put("reportBridgeContext", jinhakReportBridgeContext?.let { JSONObject(it.toString()) } ?: JSONObject.NULL)
                .put("trigger", trigger.take(60))
'''
runtime_store_new = '''                .put("missionNeedsReturn", jinhakMissionNeedsReturn)
                .put("reportBridgeContext", jinhakReportBridgeContext?.let { JSONObject(it.toString()) } ?: JSONObject.NULL)
                .put("targetAuthRedirectCounts", JSONObject(jinhakTargetAuthRedirectCounts as Map<*, *>))
                .put("targetAuthRedirectEpisodeOpenKey", if (jinhakTargetAuthRedirectEpisodeOpenKey.isBlank()) JSONObject.NULL else jinhakTargetAuthRedirectEpisodeOpenKey)
                .put("trigger", trigger.take(60))
'''
if runtime_store_anchor not in m:
    raise SystemExit('v0.9.16 runtime persistence store anchor not found')
m = m.replace(runtime_store_anchor, runtime_store_new, 1)

runtime_restore_anchor = '''            jinhakReportBridgeContext = runtime.optJSONObject("reportBridgeContext")
            jinhakMissionContext = JinhakReportContextBridge.context(jinhakReportBridgeContext)
'''
runtime_restore_new = '''            jinhakReportBridgeContext = runtime.optJSONObject("reportBridgeContext")
            jinhakMissionContext = JinhakReportContextBridge.context(jinhakReportBridgeContext)
            runtime.optJSONObject("targetAuthRedirectCounts")?.let { persisted ->
                jinhakTargetAuthRedirectCounts.clear()
                val keys = persisted.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    val count = persisted.optInt(key, 0)
                    if (key.isNotBlank() && count > 0) jinhakTargetAuthRedirectCounts[key] = count
                }
            }
            jinhakTargetAuthRedirectEpisodeOpenKey = runtime.optString("targetAuthRedirectEpisodeOpenKey")
                .takeIf { it.isNotBlank() && it != "null" }.orEmpty()
'''
if runtime_restore_anchor not in m:
    raise SystemExit('v0.9.16 runtime persistence restore anchor not found')
m = m.replace(runtime_restore_anchor, runtime_restore_new, 1)

# Target-specific loop helpers. A real logout can use one normal recovery cycle.
# Quarantine happens only after the same non-core target enters a second distinct
# login redirect episode AND the protected core has just re-verified successfully.
helper_anchor = '''    private fun persistJinhakAuthDiagnostics(trigger: String) {
'''
helper = '''    private fun jinhakTargetAuthRedirectKey(rawTarget: String?): String? {
        val target = canonicalizeBatchUrl(rawTarget.orEmpty())
        if (target.isBlank() || isProviderLoginUrl(ProviderId.JINHAK, target)) return null
        val core = canonicalizeBatchUrl(JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty())
        if (core.isNotBlank() && target == core) return null
        return RecordUtils.sha256(target)
    }

    private fun noteJinhakTargetAuthRedirectEpisode(source: String): Int {
        if (provider != ProviderId.JINHAK || !batchRunning) return 0
        val target = canonicalizeBatchUrl(currentBatchTarget.orEmpty())
        val key = jinhakTargetAuthRedirectKey(target) ?: return 0
        if (jinhakTargetAuthRedirectEpisodeOpenKey == key) {
            return jinhakTargetAuthRedirectCounts[key] ?: 0
        }
        jinhakTargetAuthRedirectEpisodeOpenKey = key
        val count = (jinhakTargetAuthRedirectCounts[key] ?: 0) + 1
        jinhakTargetAuthRedirectCounts[key] = count
        jinhakTargetAuthRedirectEpisodes += 1
        jinhakLastTargetAuthRedirectSafePath = runtimeSafePath(target)
        recordRuntimeEvent("jinhak-target-auth-redirect-episode", JSONObject()
            .put("source", source.take(60))
            .put("targetSafePath", jinhakLastTargetAuthRedirectSafePath)
            .put("cycle", count)
            .put("quarantineThreshold", MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES)
            .put("globalAuthFailed", false))
        persistJinhakMissionRuntimeState("target-auth-redirect-episode")
        persistJinhakAuthDiagnostics("target-auth-redirect-episode")
        return count
    }

    private fun clearJinhakTargetAuthRedirectAfterSuccessfulTarget(snapshot: JSONObject) {
        if (provider != ProviderId.JINHAK) return
        val target = canonicalizeBatchUrl(currentBatchTarget.orEmpty())
        val key = jinhakTargetAuthRedirectKey(target) ?: return
        val actual = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        if (actual.isBlank() || actual != target) return
        if (jinhakTargetAuthRedirectCounts.remove(key) != null) {
            if (jinhakTargetAuthRedirectEpisodeOpenKey == key) jinhakTargetAuthRedirectEpisodeOpenKey = ""
            recordRuntimeEvent("jinhak-target-auth-redirect-cleared", JSONObject()
                .put("targetSafePath", runtimeSafePath(target))
                .put("reason", "target-loaded-successfully"))
            persistJinhakMissionRuntimeState("target-auth-redirect-cleared")
        }
    }

    private fun quarantineJinhakTargetSpecificAuthRedirect(retry: String?, reason: String): Boolean {
        if (provider != ProviderId.JINHAK || !batchRunning) return false
        val target = canonicalizeBatchUrl(retry.orEmpty())
        val key = jinhakTargetAuthRedirectKey(target) ?: return false
        val cycles = jinhakTargetAuthRedirectCounts[key] ?: 0
        if (cycles < MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES) return false

        jinhakTargetAuthRedirectEpisodeOpenKey = ""
        if (jinhakTargetAuthRedirectQuarantinedKeys.add(key)) jinhakTargetAuthRedirectQuarantines += 1
        val activeTargetId = jinhakActiveMissionTargetId
        if (activeTargetId != null) {
            jinhakMissionTargetLedger.markFailed(activeTargetId, "target-specific-auth-redirect")
            jinhakActiveMissionTargetId = null
        }
        batchVisited.add(target)
        batchQueued.remove(target)
        batchErrors.put(JSONObject()
            .put("type", "target-specific-auth-redirect")
            .put("targetSafePath", runtimeSafePath(target))
            .put("cycles", cycles)
            .put("protectedCoreVerified", jinhakAuthVerifiedForBatch)
            .put("reason", reason.take(80)))
        localRunId?.let { runId ->
            localStore.markDocument(runId, target, "error", cycles, "target-specific-auth-redirect")
        }
        cloudFrontierTaskIds.remove(target)?.let { taskId ->
            cloudOffload.completeFrontier(taskId, "error", "target-specific-auth-redirect") { ok ->
                if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1
            }
        }

        batchPausedForLogin = false
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchReadinessPolling = false
        pendingBatchPageAction = null
        activeBatchPageAction = null
        jinhakAgentActionInFlight = false
        jinhakMissionNeedsReturn = false
        jinhakReportBridgeContext = null
        jinhakMissionContext = null
        currentBatchTarget = null
        jinhakAbsoluteTargetKey = ""
        ++jinhakAbsoluteTargetGeneration
        ++jinhakStallWatchdogGeneration
        runCatching { webView.stopLoading() }
        showBatchCover()
        sessionState.text = "● 진학사 보호 경로 인증 유지 · 반복 리다이렉트 target만 격리"
        status.text = "동일 target이 로그인 경로로 반복 이동해 해당 target만 오류로 보존하고 다음 지원안으로 진행합니다."
        recordRuntimeEvent("jinhak-target-specific-auth-redirect-quarantined", JSONObject()
            .put("targetSafePath", runtimeSafePath(target))
            .put("cycles", cycles)
            .put("activeMissionTargetFailed", activeTargetId != null)
            .put("globalAuthStillVerified", jinhakAuthVerifiedForBatch))
        persistJinhakMissionRuntimeState("target-auth-redirect-quarantined")
        persistJinhakAuthDiagnostics("target-auth-redirect-quarantined")
        persistLiveJinhakDiagnostics("target-auth-redirect-quarantined", force = true)
        handler.postDelayed({
            if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK) loadNextBatchPage()
        }, 220L)
        return true
    }

''' + helper_anchor
if helper_anchor not in m:
    raise SystemExit('v0.9.16 helper insertion anchor not found')
m = m.replace(helper_anchor, helper, 1)

# Count URL-fallback login episodes exactly when the batch is first paused for the
# login route. The episode latch prevents the DOM detector and URL fallback from
# double-counting the same navigation.
fallback_anchor = '''                if (expectedProvider == ProviderId.JINHAK) {
                    jinhakAuthVerifiedForBatch = false
                    jinhakCoreBootstrapState = "batch-login-route-wait"
                }
                recordRuntimeEvent("login-route-fallback-batch-pause", JSONObject()
'''
fallback_new = '''                if (expectedProvider == ProviderId.JINHAK) {
                    noteJinhakTargetAuthRedirectEpisode("login-route-fallback")
                    jinhakAuthVerifiedForBatch = false
                    jinhakCoreBootstrapState = "batch-login-route-wait"
                }
                recordRuntimeEvent("login-route-fallback-batch-pause", JSONObject()
'''
if fallback_anchor not in m:
    raise SystemExit('v0.9.16 URL fallback pause anchor not found')
m = m.replace(fallback_anchor, fallback_new, 1)

# Count rendered login-form episodes through the same latch.
rendered_anchor = '''        batchRenderedLoginSurfacePauses += 1
        batchPausedForLogin = true
        batchCollecting = false
'''
rendered_new = '''        batchRenderedLoginSurfacePauses += 1
        batchPausedForLogin = true
        if (which == ProviderId.JINHAK) noteJinhakTargetAuthRedirectEpisode("rendered-login-surface")
        batchCollecting = false
'''
if rendered_anchor not in m:
    raise SystemExit('v0.9.16 rendered login pause anchor not found')
m = m.replace(rendered_anchor, rendered_new, 1)

# After the protected core has re-verified, do NOT blindly reload a target that
# has already caused two distinct login redirect cycles. This is the central loop
# breaker. Global auth stays verified and the batch continues with the next target.
resume_old = '''        val retry = currentBatchTarget
        persistJinhakAuthDiagnostics("$reason-resume-target")
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)
            else loadNextBatchPage()
        }, 180L)
'''
resume_new = '''        val retry = currentBatchTarget
        val retryKey = jinhakTargetAuthRedirectKey(retry)
        val redirectCycles = retryKey?.let { jinhakTargetAuthRedirectCounts[it] } ?: 0
        jinhakTargetAuthRedirectEpisodeOpenKey = ""
        persistJinhakMissionRuntimeState("verified-auth-before-target-resume")
        persistJinhakAuthDiagnostics("$reason-resume-target")
        if (redirectCycles >= MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES &&
            quarantineJinhakTargetSpecificAuthRedirect(retry, reason)) {
            return
        }
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)
            else loadNextBatchPage()
        }, 180L)
'''
if resume_old not in m:
    raise SystemExit('v0.9.16 resume target anchor not found')
m = m.replace(resume_old, resume_new, 1)

# A target that subsequently renders and snapshots successfully has proven the
# redirect was transient; clear its target-local counter so future real expiries
# still receive one normal recovery cycle.
success_anchor = '''            batchSessionSyncRetries = 0

            if (provider == ProviderId.JINHAK) {
'''
success_new = '''            batchSessionSyncRetries = 0

            if (provider == ProviderId.JINHAK) {
                clearJinhakTargetAuthRedirectAfterSuccessfulTarget(snapshot)
'''
if success_anchor not in m:
    raise SystemExit('v0.9.16 successful target clear anchor not found')
m = m.replace(success_anchor, success_new, 1)

# Preserve redirect history when resuming the same mission session; reset only for
# a genuinely new Jinhak batch.
reset_anchor = '''        jinhakMissionOriginSnapshotErrorTotal = 0
        jinhakLastMissionOriginSnapshotErrorType = ""
        if (provider == ProviderId.JINHAK && jinhakAuthVerifiedForBatch) {
'''
reset_new = '''        jinhakMissionOriginSnapshotErrorTotal = 0
        jinhakLastMissionOriginSnapshotErrorType = ""
        if (!preserveJinhakMissionState) {
            jinhakTargetAuthRedirectCounts.clear()
            jinhakTargetAuthRedirectQuarantinedKeys.clear()
            jinhakTargetAuthRedirectEpisodeOpenKey = ""
            jinhakTargetAuthRedirectEpisodes = 0
            jinhakTargetAuthRedirectQuarantines = 0
            jinhakLastTargetAuthRedirectSafePath = ""
        }
        if (provider == ProviderId.JINHAK && jinhakAuthVerifiedForBatch) {
'''
if reset_anchor not in m:
    raise SystemExit('v0.9.16 batch reset anchor not found')
m = m.replace(reset_anchor, reset_new, 1)

# Add loop-specific telemetry to every existing auth/diagnostic object that
# already exports loginRouteFallbackPauses. This exports only counts and a safe
# host/path (no query, cookie, token or credential).
diag_anchor = '''                    .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
'''
diag_new = '''                    .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                    .put("targetAuthRedirectEpisodes", jinhakTargetAuthRedirectEpisodes)
                    .put("targetAuthRedirectQuarantines", jinhakTargetAuthRedirectQuarantines)
                    .put("targetAuthRedirectTrackedTargets", jinhakTargetAuthRedirectCounts.size)
                    .put("targetAuthRedirectMaxCycles", jinhakTargetAuthRedirectCounts.values.maxOrNull() ?: 0)
                    .put("targetAuthRedirectThreshold", MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES)
                    .put("lastTargetAuthRedirectSafePath", jinhakLastTargetAuthRedirectSafePath.take(300))
'''
if diag_anchor not in m:
    raise SystemExit('v0.9.16 diagnostic anchor not found')
m = m.replace(diag_anchor, diag_new)

# Version metadata only beyond the single behavior fix.
m = m.replace('private const val VERSION = "0.9.15"', 'private const val VERSION = "0.9.16"', 1)
m = m.replace('private const val BUILD_CODE = 109150', 'private const val BUILD_CODE = 109160', 1)
g = g.replace('versionCode = 109150', 'versionCode = 109160', 1)
g = g.replace('versionName = "0.9.15"', 'versionName = "0.9.16"', 1)
manifest = manifest.replace(
    'Admission Collector v0.9.15 Mission Stall Fence',
    'Admission Collector v0.9.16 Target Auth Redirect Guard',
    1
)

required = {
    'version': 'private const val VERSION = "0.9.16"' in m and 'private const val BUILD_CODE = 109160' in m,
    'threshold': 'MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES = 2' in m,
    'episode-tracking': 'noteJinhakTargetAuthRedirectEpisode' in m and 'jinhakTargetAuthRedirectCounts' in m,
    'target-quarantine': 'target-specific-auth-redirect' in m and 'quarantineJinhakTargetSpecificAuthRedirect' in m,
    'core-auth-preserved': 'protected-core-stable' in m and 'completeJinhakVerifiedAuth' in m,
    'no-global-auth-failure-on-quarantine': '.put("globalAuthStillVerified", jinhakAuthVerifiedForBatch)' in m,
    'persistence': 'targetAuthRedirectCounts' in m and 'targetAuthRedirectEpisodeOpenKey' in m,
    'mission-stall-preserved': 'recoverOrStopJinhakMissionStall' in m,
    'renderer-preserved': 'jinhak-slow-lane-renderer-fallback-main' in m,
    'same-card-preserved': 'MAX_JINHAK_SAME_CARD_REPLAY_ATTEMPTS = 3' in m,
    'privacy': 'credentialExported' in m and 'sessionSecretExported' in m,
}
failed = [k for k, ok in required.items() if not ok]
if failed:
    raise SystemExit('v0.9.16 postcondition failed: ' + ', '.join(failed))

main_path.write_text(m)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('Applied v0.9.16 Target Auth Redirect Loop Guard patch')
