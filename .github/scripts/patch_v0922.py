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
    'private const val VERSION = "0.9.21"',
    'private const val BUILD_CODE = 109210',
    'jinhakMissionCells.onRendererGone(',
    'JINHAK_SLOW_ESCALATION_MS = 35_000L',
    'slowLanePool.enqueue(task)',
    'private fun collectSnapshotForBatch()',
    'override fun onCreateWindow(',
    'processJournalActive',
    'persistLiveJinhakDiagnostics',
]
missing = [x for x in required if x not in main]
if missing:
    raise SystemExit('v0.9.21 source precondition failed: ' + ', '.join(missing))

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.9.21"', 'private const val VERSION = "0.9.22"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 109210', 'private const val BUILD_CODE = 109220', 'main build code')
gradle = replace_once(gradle, 'versionCode = 109210', 'versionCode = 109220', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.9.21"', 'versionName = "0.9.22"', 'gradle version name')
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.21 Process Resume Journal',
    'Admission Collector v0.9.22 Single-WebView Stability Guard',
    'manifest label'
)

# Runtime stability counters. These are operational diagnostics only.
main = replace_once(
    main,
    '    private var processLastLifecycle = "created"\n',
    '''    private var processLastLifecycle = "created"
    private var jinhakSingleWebViewSlowLaneBypasses = 0
    private var jinhakSnapshotOverlapDeferrals = 0
    private var jinhakSnapshotOverlapDeferralScheduled = false
    private var jinhakPopupWebViewsCreated = 0
    private var jinhakPopupWebViewsDestroyed = 0
    private var jinhakRendererFirstCrashCooldowns = 0
''',
    'stability diagnostics fields'
)

main = replace_once(
    main,
    '        private const val JINHAK_SLOW_ESCALATION_MS = 35_000L\n',
    '''        private const val JINHAK_SLOW_ESCALATION_MS = 35_000L
        private const val JINHAK_SINGLE_WEBVIEW_STABILITY_MODE = true
        private const val JINHAK_SNAPSHOT_OVERLAP_RETRY_MS = 400L
        private const val JINHAK_TRANSIENT_POPUP_TIMEOUT_MS = 5_000L
        private const val JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS = 2_000L
''',
    'stability constants'
)

# Reset per-batch stability counters without touching persisted mission/auth state.
main = replace_once(
    main,
    '        jinhakSlowLaneMaxDurationMs = 0L\n',
    '''        jinhakSlowLaneMaxDurationMs = 0L
        jinhakSingleWebViewSlowLaneBypasses = 0
        jinhakSnapshotOverlapDeferrals = 0
        jinhakSnapshotOverlapDeferralScheduled = false
        jinhakPopupWebViewsCreated = 0
        jinhakPopupWebViewsDestroyed = 0
        jinhakRendererFirstCrashCooldowns = 0
''',
    'stability counter reset'
)

# v0.9.22: the real-device log proved a foreground renderer crash and a hidden slow-lane
# renderer death in the same mission run. Keep Jinhak mission traversal on the foreground
# WebView only. The existing 60s mission fence/lease recovery remains the bounded fallback.
main = replace_once(
    main,
    '            val slowLaneCircuitOpen = ::slowLanePool.isInitialized && slowLanePool.stats().rendererCircuitOpen\n',
    '''            if (JINHAK_SINGLE_WEBVIEW_STABILITY_MODE) {
                jinhakSingleWebViewSlowLaneBypasses += 1
                recordRuntimeEvent("jinhak-single-webview-slow-lane-bypass", JSONObject()
                    .put("targetSafePath", runtimeSafePath(target))
                    .put("currentSafePath", runtimeSafePath(current))
                    .put("elapsedMs", System.currentTimeMillis() - startedAt)
                    .put("missionBound", mission?.identityKey != null)
                    .put("hiddenWebViewCreated", false))
                persistLiveJinhakDiagnostics("single-webview-slow-lane-bypass", force = true)
                status.text = "안정성 모드: 숨김 WebView를 만들지 않고 메인 WebView + mission fence로 계속합니다."
                return@postDelayed
            }
            val slowLaneCircuitOpen = ::slowLanePool.isInitialized && slowLanePool.stats().rendererCircuitOpen
''',
    'disable hidden slow lane escalation'
)

# Do not supersede an already-running snapshot just because the legacy batchCollecting flag
# became false. This removes the exact snapshot overlap observed immediately before the crash.
main = replace_once(
    main,
    '    private fun collectSnapshotForBatch() {\n        if (!batchRunning || batchPausedForLogin || batchCollecting) return\n',
    '''    private fun collectSnapshotForBatch() {
        if (!batchRunning || batchPausedForLogin || batchCollecting) return
        if (provider == ProviderId.JINHAK && jinhakMissionCells.isSnapshotActive()) {
            jinhakSnapshotOverlapDeferrals += 1
            if (!jinhakSnapshotOverlapDeferralScheduled) {
                jinhakSnapshotOverlapDeferralScheduled = true
                handler.postDelayed({
                    jinhakSnapshotOverlapDeferralScheduled = false
                    if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK) {
                        collectSnapshotForBatch()
                    }
                }, JINHAK_SNAPSHOT_OVERLAP_RETRY_MS)
            }
            return
        }
''',
    'snapshot overlap deferral'
)

# On renderer death, cancel any queued overlap retry. The supervisor generation invalidation
# continues to reject late callbacks from the dead renderer.
main = replace_once(
    main,
    '                if (cellInvalidation.snapshotInvalidated) batchCollecting = false\n\n                val deadView = view ?: webView\n',
    '''                if (cellInvalidation.snapshotInvalidated) batchCollecting = false
                jinhakSnapshotOverlapDeferralScheduled = false

                val deadView = view ?: webView
''',
    'renderer snapshot deferral reset'
)

# First Jinhak renderer crash now gets a short blank-page cooldown and resumes from mission
# origin/core rather than immediately hammering the replacement renderer. Adiga behavior is unchanged.
old_recovery = '''                        if (!repeatedJinhakCrash) {
                            batchRunning = wasBatchRunning
                            batchPausedForLogin = wasBatchPausedForLogin
                            recordRuntimeEvent(
                                "webview-renderer-recovered-in-place",
                                JSONObject()
                                    .put("didCrash", didCrash)
                                    .put("batchRunning", batchRunning)
                                    .put("unifiedRunning", unifiedRunning)
                                    .put("resumeSafePath", runtimeSafePath(resumeUrl))
                                    .put("rendererCrashCountInWindow", runtimeRendererCrashCount)
                                    .put("activityRecreated", false)
                            )
                            status.text = "WebView renderer 복구 완료 · 현재 수집 지점에서 재개합니다."
                            replacement.loadUrl(resumeUrl)
                            return@runCatching
                        }
'''
new_recovery = '''                        if (!repeatedJinhakCrash) {
                            batchPausedForLogin = wasBatchPausedForLogin
                            if (provider == ProviderId.JINHAK && wasUnifiedRunning) {
                                batchRunning = false
                                jinhakRendererFirstCrashCooldowns += 1
                                val missionOrigin = jinhakMissionOriginRoute.takeIf { it.isNotBlank() }
                                val safeResume = missionOrigin
                                    ?: JinhakSiteTopology.missionSeeds().firstOrNull()?.takeIf { it.isNotBlank() }
                                    ?: resumeUrl
                                currentBatchTarget = safeResume
                                replacement.loadUrl("about:blank")
                                recordRuntimeEvent(
                                    "webview-renderer-recovered-cooldown",
                                    JSONObject()
                                        .put("didCrash", didCrash)
                                        .put("cooldownMs", JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS)
                                        .put("resumeSafePath", runtimeSafePath(safeResume))
                                        .put("resumeFromMissionOrigin", missionOrigin != null)
                                        .put("rendererCrashCountInWindow", runtimeRendererCrashCount)
                                        .put("activityRecreated", false),
                                    synchronous = true
                                )
                                status.text = "WebView renderer 교체 완료 · 2초 안정화 후 보존된 mission 지점에서 재개합니다."
                                handler.postDelayed({
                                    if (!unifiedRunning || provider != ProviderId.JINHAK || runtimeRendererRecovering) return@postDelayed
                                    batchRunning = wasBatchRunning
                                    batchPausedForLogin = wasBatchPausedForLogin
                                    batchCollecting = false
                                    replacement.loadUrl(safeResume)
                                }, JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS)
                            } else {
                                batchRunning = wasBatchRunning
                                recordRuntimeEvent(
                                    "webview-renderer-recovered-in-place",
                                    JSONObject()
                                        .put("didCrash", didCrash)
                                        .put("batchRunning", batchRunning)
                                        .put("unifiedRunning", unifiedRunning)
                                        .put("resumeSafePath", runtimeSafePath(resumeUrl))
                                        .put("rendererCrashCountInWindow", runtimeRendererCrashCount)
                                        .put("activityRecreated", false)
                                )
                                status.text = "WebView renderer 복구 완료 · 현재 수집 지점에서 재개합니다."
                                replacement.loadUrl(resumeUrl)
                            }
                            return@runCatching
                        }
'''
main = replace_once(main, old_recovery, new_recovery, 'first renderer crash cooldown')

# The old popup bridge created a WebView for every window.open and never destroyed it.
# Keep popup compatibility but make each bridge transient, nested-popup-disabled and bounded.
old_popup = '''            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
                val child = WebView(this@MainActivity)
                child.settings.javaScriptEnabled = true
                child.settings.domStorageEnabled = true
                child.settings.javaScriptCanOpenWindowsAutomatically = true
                child.settings.setSupportMultipleWindows(true)
                child.webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean {
                        webView.loadUrl(request.url.toString())
                        return true
                    }

                    override fun onPageFinished(v: WebView, url: String) {
                        if (url.isNotBlank() && url != "about:blank") webView.loadUrl(url)
                    }
                }
                transport.webView = child
                resultMsg.sendToTarget()
                return true
            }
'''
new_popup = '''            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
                val child = WebView(this@MainActivity)
                if (provider == ProviderId.JINHAK) jinhakPopupWebViewsCreated += 1
                var childDestroyed = false

                fun destroyTransientPopup(reason: String) {
                    if (childDestroyed) return
                    childDestroyed = true
                    runCatching { child.stopLoading() }
                    runCatching { child.removeAllViews() }
                    runCatching { child.destroy() }
                    if (provider == ProviderId.JINHAK) {
                        jinhakPopupWebViewsDestroyed += 1
                        recordRuntimeEvent("jinhak-transient-popup-destroyed", JSONObject()
                            .put("reason", reason.take(80))
                            .put("created", jinhakPopupWebViewsCreated)
                            .put("destroyed", jinhakPopupWebViewsDestroyed))
                    }
                }

                child.settings.apply {
                    javaScriptEnabled = true
                    domStorageEnabled = true
                    databaseEnabled = false
                    javaScriptCanOpenWindowsAutomatically = false
                    setSupportMultipleWindows(false)
                    cacheMode = WebSettings.LOAD_NO_CACHE
                    mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
                }
                child.webViewClient = object : WebViewClient() {
                    private fun handoff(target: String): Boolean {
                        if (target.isBlank() || target == "about:blank") return false
                        if (batchRunning && provider == ProviderId.JINHAK &&
                            !ProviderRegistry.adapter(ProviderId.JINHAK).accepts(target)) {
                            jinhakExternalNavigationsBlocked += 1
                            recordRuntimeEvent("jinhak-popup-external-navigation-blocked", JSONObject()
                                .put("targetSafePath", runtimeSafePath(target)))
                            handler.post { destroyTransientPopup("external-blocked") }
                            return true
                        }
                        webView.loadUrl(target)
                        handler.post { destroyTransientPopup("main-handoff") }
                        return true
                    }

                    override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean =
                        handoff(request.url?.toString().orEmpty())

                    override fun onPageFinished(v: WebView, url: String) {
                        handoff(url)
                    }
                }
                transport.webView = child
                resultMsg.sendToTarget()
                handler.postDelayed({ destroyTransientPopup("timeout") }, JINHAK_TRANSIENT_POPUP_TIMEOUT_MS)
                return true
            }
'''
main = replace_once(main, old_popup, new_popup, 'bounded transient popup bridge')

# v0.9.21 stored process-journal fields in the terminal diagnostics path but the live running
# JINHAK_CRAWL_DIAGNOSTICS export did not contain them. Add both journal and stability evidence
# to the live summary so post-crash exports can diagnose the event after reopening.
main = replace_once(
    main,
    '                .put("legacyBatchCollecting", batchCollecting)\n                .put("cloudRecordCheckpointsQueued", jinhakCloudRecordCheckpointsQueued)\n',
    '''                .put("legacyBatchCollecting", batchCollecting)
                .put("processJournalActive", getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).getBoolean("processJournalActive", false))
                .put("processJournalClean", getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).getBoolean("processJournalClean", true))
                .put("previousUncleanTerminationDetected", processJournalPreviousUncleanTermination)
                .put("processResumeGateRuns", processResumeGateRuns)
                .put("processResumeGatePending", processResumeGatePending)
                .put("processHeartbeatAgeMs", if (processHeartbeatAtMs > 0L) (now - processHeartbeatAtMs).coerceAtLeast(0L) else JSONObject.NULL)
                .put("processLastLifecycle", processLastLifecycle.take(120))
                .put("lastRuntimeEventType", getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).getString("lastRuntimeEventType", "").orEmpty().take(80))
                .put("singleWebViewStabilityMode", JINHAK_SINGLE_WEBVIEW_STABILITY_MODE)
                .put("singleWebViewSlowLaneBypasses", jinhakSingleWebViewSlowLaneBypasses)
                .put("snapshotOverlapDeferrals", jinhakSnapshotOverlapDeferrals)
                .put("popupWebViewsCreated", jinhakPopupWebViewsCreated)
                .put("popupWebViewsDestroyed", jinhakPopupWebViewsDestroyed)
                .put("rendererFirstCrashCooldowns", jinhakRendererFirstCrashCooldowns)
                .put("cloudRecordCheckpointsQueued", jinhakCloudRecordCheckpointsQueued)
''',
    'live process/stability diagnostics'
)

# Add the new stability counters beside the already existing terminal process journal fields too.
main = replace_once(
    main,
    '                        .put("processSessionSecretStored", false)\n                        .put("loginSurfaceDetections", credentialLoginSurfaceDetections)\n',
    '''                        .put("processSessionSecretStored", false)
                        .put("singleWebViewStabilityMode", JINHAK_SINGLE_WEBVIEW_STABILITY_MODE)
                        .put("singleWebViewSlowLaneBypasses", jinhakSingleWebViewSlowLaneBypasses)
                        .put("snapshotOverlapDeferrals", jinhakSnapshotOverlapDeferrals)
                        .put("popupWebViewsCreated", jinhakPopupWebViewsCreated)
                        .put("popupWebViewsDestroyed", jinhakPopupWebViewsDestroyed)
                        .put("rendererFirstCrashCooldowns", jinhakRendererFirstCrashCooldowns)
                        .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
''',
    'terminal stability diagnostics'
)

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('v0.9.22 Single-WebView Stability Guard patch applied')
