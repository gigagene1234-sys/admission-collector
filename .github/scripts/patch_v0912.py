from pathlib import Path

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
snapshot_path = Path('app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
s = snapshot_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

# -----------------------------------------------------------------------------
# v0.9.12: Jinhak bootstrap recovery + persistence diagnostics.
# Real-device v0.9.11 completed its Jinhak phase with 3/3 snapshot errors,
# 0 successful snapshots, 0 mission targets and no exported missionPersistence.
# This patch is intentionally bounded to making the bootstrap observable/recoverable
# so the v0.9.11 persistence fix can actually be exercised on-device.
# -----------------------------------------------------------------------------

# 1) Eliminate false-positive server-error detection from a bare visible "500" value.
old_server = "  var serverError=/(500\\s*(?:Internal\\s*Server\\s*Error)?|서비스\\s*처리\\s*중\\s*오류|일시적인\\s*오류가\\s*발생)/i.test(titleText+' '+bodyText);"
new_server = """  var titleServerError=/^(?:500(?:\\s+Internal\\s+Server\\s+Error)?|HTTP\\s+ERROR\\s+500)$/i.test(titleText);\n  var bodyServerError=/(?:\\b500\\s+Internal\\s+Server\\s+Error\\b|\\bHTTP\\s+ERROR\\s+500\\b|서비스\\s*처리\\s*중\\s*오류|일시적인\\s*오류가\\s*발생)/i.test(bodyText);\n  var serverError=titleServerError||bodyServerError;"""
if old_server not in s:
    raise SystemExit('SnapshotScript server-error anchor not found')
s = s.replace(old_server, new_server, 1)

# 2) Runtime counters for bounded bootstrap recovery and exact error-class visibility.
field_anchor = '    private var jinhakNormalizedAmbiguousBindings = 0\n'
field_insert = field_anchor + '''    private val jinhakBootstrapRetryCounts = linkedMapOf<String, Int>()
    private val jinhakPageStateErrorTypes = linkedMapOf<String, Int>()
    private var jinhakBootstrapRetryAttempts = 0
    private var jinhakBootstrapFatalNoSuccess = 0
'''
if field_anchor not in m:
    raise SystemExit('MainActivity bootstrap field anchor not found')
m = m.replace(field_anchor, field_insert, 1)

const_anchor = '        private const val JINHAK_CORE_AUTH_STABLE_PASSES = 2\n'
const_insert = const_anchor + '        private const val MAX_JINHAK_BOOTSTRAP_PAGE_RETRIES = 2\n'
if const_anchor not in m:
    raise SystemExit('MainActivity bootstrap retry constant anchor not found')
m = m.replace(const_anchor, const_insert, 1)

# 3) Jinhak must own a Jinhak local run BEFORE the first snapshot/error.
start_anchor = '''        if (provider == ProviderId.JINHAK) {
            jinhakBatchStartCount += 1
            recordRuntimeEvent("jinhak-batch-start", JSONObject()
                .put("count", jinhakBatchStartCount)
                .put("preserveMissionState", preserveJinhakMissionState))
        }
'''
start_new = '''        if (provider == ProviderId.JINHAK) {
            localRunId = localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
            unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->
                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId) }
            }
            jinhakBatchStartCount += 1
            recordRuntimeEvent("jinhak-batch-start", JSONObject()
                .put("count", jinhakBatchStartCount)
                .put("preserveMissionState", preserveJinhakMissionState)
                .put("providerRunInitializedBeforeSnapshot", localRunId != null))
        }
'''
if start_anchor not in m:
    raise SystemExit('MainActivity Jinhak batch start anchor not found')
m = m.replace(start_anchor, start_new, 1)

# Reset only bootstrap-segment diagnostics; persisted mission state is intentionally untouched.
reset_anchor = '''        jinhakCoreScopeBlockedUrls = 0
        jinhakCoreScopeBlockedLaneCounts.clear()
'''
reset_new = reset_anchor + '''        jinhakBootstrapRetryCounts.clear()
        jinhakPageStateErrorTypes.clear()
        jinhakBootstrapRetryAttempts = 0
        jinhakBootstrapFatalNoSuccess = 0
'''
if reset_anchor not in m:
    raise SystemExit('MainActivity Jinhak diagnostics reset anchor not found')
m = m.replace(reset_anchor, reset_new, 1)

# 4) A core Jinhak bootstrap page gets two bounded retries before the frontier moves on.
error_anchor = '''            if (pageState.optBoolean("isError", false)) {
                val errorType = pageState.optString("errorType", "page-error")
                if (activeAction != null && activeAction.retry < MAX_PAGE_RETRIES) {
'''
error_new = '''            if (pageState.optBoolean("isError", false)) {
                val errorType = pageState.optString("errorType", "page-error")
                if (provider == ProviderId.JINHAK) {
                    jinhakPageStateErrorTypes[errorType] = (jinhakPageStateErrorTypes[errorType] ?: 0) + 1
                    val failedRoute = canonicalizeBatchUrl(
                        snapshot.optString("navigationKey", snapshot.optString("url", currentBatchTarget.orEmpty()))
                    )
                    recordRuntimeEvent("jinhak-page-state-error", JSONObject()
                        .put("errorType", errorType.take(80))
                        .put("safePath", runtimeSafePath(failedRoute))
                        .put("pageTitle", snapshot.optString("title").take(120))
                        .put("successfulSnapshotsBeforeError", batchSnapshots.length()))
                    val bootstrapUnpopulated = batchSnapshots.length() == 0 &&
                        jinhakMissionTargetLedger.summary().optInt("targets", 0) == 0
                    val retryableCoreRoute = failedRoute.isNotBlank() &&
                        JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(failedRoute)
                    if (bootstrapUnpopulated && retryableCoreRoute) {
                        val prior = jinhakBootstrapRetryCounts[failedRoute] ?: 0
                        if (prior < MAX_JINHAK_BOOTSTRAP_PAGE_RETRIES) {
                            val nextAttempt = prior + 1
                            jinhakBootstrapRetryCounts[failedRoute] = nextAttempt
                            jinhakBootstrapRetryAttempts += 1
                            if (navigationKey.isNotBlank()) batchVisited.remove(navigationKey)
                            batchVisited.remove(failedRoute)
                            currentBatchTarget = failedRoute
                            status.text = "진학사 핵심 수시 화면 오류 감지: ${nextAttempt}/${MAX_JINHAK_BOOTSTRAP_PAGE_RETRIES}회 제한 재시도"
                            recordRuntimeEvent("jinhak-bootstrap-core-retry", JSONObject()
                                .put("errorType", errorType.take(80))
                                .put("attempt", nextAttempt)
                                .put("maxAttempts", MAX_JINHAK_BOOTSTRAP_PAGE_RETRIES)
                                .put("safePath", runtimeSafePath(failedRoute)))
                            handler.postDelayed({
                                if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK) {
                                    webView.loadUrl(failedRoute)
                                }
                            }, 700L + nextAttempt * 500L)
                            return@collectSnapshot
                        }
                    }
                }
                if (activeAction != null && activeAction.retry < MAX_PAGE_RETRIES) {
'''
if error_anchor not in m:
    raise SystemExit('MainActivity pageState error anchor not found')
m = m.replace(error_anchor, error_new, 1)

# 5) Never report a zero-success Jinhak bootstrap as "completed".
verify_anchor = '''    private fun verifyLocalCompletionOrFinish() {
        if (!batchRunning || batchPausedForLogin) return
        if (provider == ProviderId.JINHAK && jinhakMissionTargetLedger.outstandingCount() > 0) {
'''
verify_new = '''    private fun verifyLocalCompletionOrFinish() {
        if (!batchRunning || batchPausedForLogin) return
        if (provider == ProviderId.JINHAK && batchSnapshots.length() == 0) {
            jinhakBootstrapFatalNoSuccess += 1
            val persistence = unifiedSessionId?.let { localStore.jinhakMissionPersistenceSummary(it) } ?: JSONObject()
            batchErrors.put(JSONObject()
                .put("type", "jinhak-bootstrap-no-success")
                .put("attemptedSnapshots", batchPageCount)
                .put("errorTypes", JSONObject(jinhakPageStateErrorTypes as Map<*, *>))
                .put("bootstrapRetryAttempts", jinhakBootstrapRetryAttempts)
                .put("persistedTargets", persistence.optInt("persistedTargets", 0)))
            recordRuntimeEvent("jinhak-bootstrap-no-success", JSONObject()
                .put("attemptedSnapshots", batchPageCount)
                .put("errorTypes", JSONObject(jinhakPageStateErrorTypes as Map<*, *>))
                .put("bootstrapRetryAttempts", jinhakBootstrapRetryAttempts)
                .put("persistence", persistence))
            finishBatch("jinhak-bootstrap-no-success")
            return
        }
        if (provider == ProviderId.JINHAK && jinhakMissionTargetLedger.outstandingCount() > 0) {
'''
if verify_anchor not in m:
    raise SystemExit('MainActivity verifyLocalCompletionOrFinish anchor not found')
m = m.replace(verify_anchor, verify_new, 1)

# 6) Final unified diagnostics must contain the persistence summary, not only live diagnostics.
final_diag_anchor = '''                        .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
                        .put("missionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                        .put("missionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                        .put("cloudFrontierPublished", cloudFrontierPublished)
'''
final_diag_new = '''                        .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
                        .put("missionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                        .put("missionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                        .put("missionPersistence", localStore.jinhakMissionPersistenceSummary(sessionId))
                        .put("jinhakBootstrapRetryAttempts", jinhakBootstrapRetryAttempts)
                        .put("jinhakBootstrapFatalNoSuccess", jinhakBootstrapFatalNoSuccess)
                        .put("jinhakPageStateErrorTypes", JSONObject(jinhakPageStateErrorTypes as Map<*, *>))
                        .put("cloudFrontierPublished", cloudFrontierPublished)
'''
if final_diag_anchor not in m:
    raise SystemExit('MainActivity final diagnostics anchor not found')
m = m.replace(final_diag_anchor, final_diag_new, 1)

# Batch JSON gets the same aggregate evidence for local/manual inspection.
finalize_anchor = '''                .put("jinhakMissionTargetLedger", jinhakMissionTargetLedger.summary())
                .put("jinhakMissionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                .put("jinhakMissionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("jinhakApplicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
'''
finalize_new = '''                .put("jinhakMissionTargetLedger", jinhakMissionTargetLedger.summary())
                .put("jinhakMissionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                .put("jinhakMissionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("jinhakMissionPersistence", unifiedSessionId?.let { localStore.jinhakMissionPersistenceSummary(it) } ?: JSONObject())
                .put("jinhakBootstrapRetryAttempts", jinhakBootstrapRetryAttempts)
                .put("jinhakBootstrapFatalNoSuccess", jinhakBootstrapFatalNoSuccess)
                .put("jinhakPageStateErrorTypes", JSONObject(jinhakPageStateErrorTypes as Map<*, *>))
                .put("jinhakApplicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
'''
if finalize_anchor not in m:
    raise SystemExit('MainActivity finalize diagnostics anchor not found')
m = m.replace(finalize_anchor, finalize_new, 1)

# Version metadata.
for old, new in [
    ('private const val VERSION = "0.9.11"', 'private const val VERSION = "0.9.12"'),
    ('private const val BUILD_CODE = 109110', 'private const val BUILD_CODE = 109120'),
]:
    if old not in m:
        raise SystemExit(f'MainActivity version anchor not found: {old}')
    m = m.replace(old, new, 1)

for old, new in [
    ('versionCode = 109110', 'versionCode = 109120'),
    ('versionName = "0.9.11"', 'versionName = "0.9.12"'),
]:
    if old not in g:
        raise SystemExit(f'Gradle version anchor not found: {old}')
    g = g.replace(old, new, 1)

old_label = 'Admission Collector v0.9.11 Mission State Persistence'
new_label = 'Admission Collector v0.9.12 Jinhak Bootstrap Recovery'
if old_label not in manifest:
    raise SystemExit('Manifest label anchor not found')
manifest = manifest.replace(old_label, new_label, 1)

main_path.write_text(m)
snapshot_path.write_text(s)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('v0.9.12 patch applied')
