from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def must_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if new in text:
        return text
    actual = text.count(old)
    if actual < count:
        raise SystemExit(f"{label}: expected at least {count} anchor(s), found {actual}")
    return text.replace(old, new, count)


# Version truth.
gradle = GRADLE.read_text()
gradle = must_replace(gradle, 'versionCode = 118600', 'versionCode = 118700', 'gradle-version-code')
gradle = must_replace(gradle, 'versionName = "0.18.6"', 'versionName = "0.18.7"', 'gradle-version-name')
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = must_replace(
    manifest,
    'android:label="Admission Hub v0.18.6 Manual Browser State Machine"',
    'android:label="Admission Hub v0.18.7 True Passive Manual Browser"',
    'manifest-label',
)
MANIFEST.write_text(manifest)

text = MAIN.read_text()
text = must_replace(
    text,
    'import com.admissionhub.collector.jinhak.JinhakManualBrowserStateMachine\n',
    'import com.admissionhub.collector.jinhak.JinhakManualBrowserStateMachine\nimport com.admissionhub.collector.jinhak.JinhakPassiveBrowserSurfacePolicy\n',
    'passive-surface-import',
)
text = must_replace(text, 'private const val VERSION = "0.18.6"', 'private const val VERSION = "0.18.7"', 'runtime-version')
text = must_replace(text, 'private const val BUILD_CODE = 118600', 'private const val BUILD_CODE = 118700', 'runtime-build-code')

# A single helper owns the actual WebView surface behavior. During manual login the
# collector uses the stock Android WebView UA, one window, provider cookies, and no
# collector popup bridge. Report traversal may re-enable multi-window only while a
# batch is actually active.
helper_anchor = '    private fun loadMainUrl(target: String, source: String = "app-load"): Boolean {'
helper = '''    private fun configureJinhakBrowserSurface(batchMode: Boolean) {
        if (provider != ProviderId.JINHAK || !::webView.isInitialized) return
        webView.settings.apply {
            if (JinhakPassiveBrowserSurfacePolicy.USE_DEFAULT_WEBVIEW_USER_AGENT) {
                userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
            }
            javaScriptCanOpenWindowsAutomatically = JinhakPassiveBrowserSurfacePolicy.automaticWindowsEnabled(batchMode)
            setSupportMultipleWindows(JinhakPassiveBrowserSurfacePolicy.multipleWindowsEnabled(batchMode))
        }
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
            if (JinhakPassiveBrowserSurfacePolicy.FLUSH_PROVIDER_COOKIES) flush()
        }
    }

'''
if 'private fun configureJinhakBrowserSurface(batchMode: Boolean)' not in text:
    if helper_anchor not in text:
        raise SystemExit('browser-surface-helper: loadMainUrl anchor missing')
    text = text.replace(helper_anchor, helper + helper_anchor, 1)

# Any app-originated navigation before /library must bypass the legacy high3 route
# classifier and prepare the passive browser *before* issuing the HTTP request, so
# the request itself uses the provider-normal UA/cookie surface.
load_anchor = '''    private fun loadMainUrl(target: String, source: String = "app-load"): Boolean {
        if (provider != ProviderId.JINHAK) {
            webView.loadUrl(target)
            return true
        }
        val decision = JinhakStrictHigh3Sandbox.decision(target)'''
load_replacement = '''    private fun loadMainUrl(target: String, source: String = "app-load"): Boolean {
        if (provider != ProviderId.JINHAK) {
            webView.loadUrl(target)
            return true
        }
        if (!batchRunning) {
            configureJinhakBrowserSurface(batchMode = false)
            webView.loadUrl(target)
            return true
        }
        val decision = JinhakStrictHigh3Sandbox.decision(target)'''
text = must_replace(text, load_anchor, load_replacement, 'manual-app-navigation-bypass')

# configureWebView can run after renderer replacement. Never accumulate the collector
# UA on Jinhak, and do not arm multi-window behavior while the user is authenticating.
settings_anchor = '''            javaScriptCanOpenWindowsAutomatically = true
            setSupportMultipleWindows(true)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = userAgentString + " AdmissionCollector/$VERSION"'''
settings_replacement = '''            javaScriptCanOpenWindowsAutomatically = provider != ProviderId.JINHAK || batchRunning
            setSupportMultipleWindows(provider != ProviderId.JINHAK || batchRunning)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = if (provider == ProviderId.JINHAK) {
                WebSettings.getDefaultUserAgent(this@MainActivity)
            } else {
                WebSettings.getDefaultUserAgent(this@MainActivity) + " AdmissionCollector/$VERSION"
            }'''
text = must_replace(text, settings_anchor, settings_replacement, 'configure-webview-provider-normal-ua')

# The v0.18.6 regression left the popup client active outside batch mode. This is an
# active route handoff even though the main WebView callbacks are passive. Manual
# browser mode now refuses collector popup ownership; with multiple-windows disabled
# the provider remains on ordinary single-WebView navigation.
popup_anchor = '''            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false'''
popup_replacement = '''            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                if (provider == ProviderId.JINHAK &&
                    !JinhakPassiveBrowserSurfacePolicy.allowCollectorPopupHandoff(batchRunning)) {
                    return false
                }
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false'''
text = must_replace(text, popup_anchor, popup_replacement, 'manual-popup-handoff-disabled')

# page-start is diagnostic-only in manual mode, but also reassert the passive surface
# in case provider scripts or a renderer recreation changed WebView settings.
page_start_anchor = '''                if (provider == ProviderId.JINHAK && !batchRunning) {
                    clearJinhakLegacyAuthState()
                    return
                }'''
page_start_replacement = '''                if (provider == ProviderId.JINHAK && !batchRunning) {
                    clearJinhakLegacyAuthState()
                    configureJinhakBrowserSurface(batchMode = false)
                    return
                }'''
text = must_replace(text, page_start_anchor, page_start_replacement, 'manual-page-start-surface')

# Provider cookies are ordinary WebView browser state. Flushing them persists the
# provider's own login cookie and does not export, inspect, infer or synthesize auth.
text = must_replace(
    text,
    '            override fun onPageFinished(view: WebView, url: String) {\n                if (provider != ProviderId.JINHAK) CookieManager.getInstance().flush()',
    '            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()',
    'jinhak-cookie-flush',
)

storage_anchor = '''                    if (!batchRunning) {
                        if (JinhakManualStorageReportPolicy.isStorageEntry(current)) {
                            batchPausedForLogin = false'''
storage_replacement = '''                    if (!batchRunning) {
                        if (JinhakManualStorageReportPolicy.isStorageEntry(current)) {
                            configureJinhakBrowserSurface(batchMode = false)
                            batchPausedForLogin = false'''
text = must_replace(text, storage_anchor, storage_replacement, 'storage-visible-remains-passive-until-start')

manual_else_anchor = '''                        } else {
                            sessionState.text = "○ 진학사 직접 탐색"
                            status.text = "직접 로그인한 뒤 수시 저장소까지 이동하세요. Admission Hub는 로그인·세션을 건드리지 않습니다."
                        }
                        return'''
manual_else_replacement = '''                        } else {
                            configureJinhakBrowserSurface(batchMode = false)
                            sessionState.text = "○ 진학사 직접 탐색"
                            status.text = "직접 로그인한 뒤 수시 저장소까지 이동하세요. Admission Hub는 로그인·세션을 건드리지 않습니다."
                        }
                        return'''
text = must_replace(text, manual_else_anchor, manual_else_replacement, 'manual-finished-surface')

# Only after startBatch has actually armed the collector may report popup behavior be
# enabled. This prevents the 250 ms /library handoff window from owning auth popups.
batch_start_anchor = '''        batchDuplicateYearViews = JSONArray()
        batchRunning = true
        showBatchCover()'''
batch_start_replacement = '''        batchDuplicateYearViews = JSONArray()
        batchRunning = true
        if (provider == ProviderId.JINHAK) configureJinhakBrowserSurface(batchMode = true)
        showBatchCover()'''
text = must_replace(text, batch_start_anchor, batch_start_replacement, 'report-surface-after-batch-arm')

# STOP_ONLY must truly be stop-only. v0.18.6 still called webView.stopLoading() from
# stopBatch(), so a scope departure could cancel the user's provider navigation even
# though shouldOverrideUrlLoading returned false.
stop_anchor = '''        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("batch-stopped")
        webView.stopLoading()
        hideBatchCover()'''
stop_replacement = '''        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("batch-stopped")
        if (provider == ProviderId.JINHAK) {
            configureJinhakBrowserSurface(batchMode = false)
        } else {
            webView.stopLoading()
        }
        hideBatchCover()'''
text = must_replace(text, stop_anchor, stop_replacement, 'true-stop-only-no-jinhak-stoploading')

# Explicit Jinhak entry helpers establish the passive surface before the user starts
# interacting, covering launch/recovery paths that may not immediately call loadMainUrl.
launch_anchor = '''    private fun startLaunchAwareCollection() {
        provider = ProviderId.JINHAK
        credentialVault.clear(ProviderId.JINHAK.wireName)'''
launch_replacement = '''    private fun startLaunchAwareCollection() {
        provider = ProviderId.JINHAK
        configureJinhakBrowserSurface(batchMode = false)
        credentialVault.clear(ProviderId.JINHAK.wireName)'''
text = must_replace(text, launch_anchor, launch_replacement, 'launch-passive-surface')

auth_stub_anchor = '''    private fun startV0180DedicatedJinhakAuth(reason: String, forceManual: Boolean = false) {
        if (provider != ProviderId.JINHAK) provider = ProviderId.JINHAK
        clearJinhakLegacyAuthState()'''
auth_stub_replacement = '''    private fun startV0180DedicatedJinhakAuth(reason: String, forceManual: Boolean = false) {
        if (provider != ProviderId.JINHAK) provider = ProviderId.JINHAK
        configureJinhakBrowserSurface(batchMode = false)
        clearJinhakLegacyAuthState()'''
text = must_replace(text, auth_stub_anchor, auth_stub_replacement, 'legacy-entry-passive-surface')

probe_anchor = '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        provider = ProviderId.JINHAK
        clearJinhakLegacyAuthState()'''
probe_replacement = '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        provider = ProviderId.JINHAK
        configureJinhakBrowserSurface(batchMode = false)
        clearJinhakLegacyAuthState()'''
text = must_replace(text, probe_anchor, probe_replacement, 'probe-entry-passive-surface')

MAIN.write_text(text)
