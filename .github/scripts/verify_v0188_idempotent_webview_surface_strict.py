from pathlib import Path

checks = []
failed = []

def check(name, condition):
    checks.append(name)
    if not condition:
        failed.append(name)

root = Path('.')
main = (root / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt').read_text()
policy = (root / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakPassiveBrowserSurfacePolicy.kt').read_text()
gradle = (root / 'app/build.gradle.kts').read_text()
manifest = (root / 'app/src/main/AndroidManifest.xml').read_text()
test = (root / 'app/src/test/java/com/admissionhub/collector/jinhak/JinhakIdempotentBrowserSurfacePolicyTest.kt').read_text()

check('versionCode 118800', 'versionCode = 118800' in gradle)
check('versionName 0.18.8', 'versionName = "0.18.8"' in gradle)
check('manifest v0188', 'Admission Hub v0.18.8 Idempotent WebView Surface' in manifest)
check('runtime version v0188', 'private const val VERSION = "0.18.8"' in main)
check('runtime build 118800', 'private const val BUILD_CODE = 118800' in main)

check('surface WebView identity tracked', 'private var jinhakBrowserSurfaceWebView: WebView? = null' in main)
check('surface mode tracked', 'private var jinhakBrowserSurfaceBatchMode: Boolean? = null' in main)
check('main WebView UA fixed to stock', 'userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)' in main)
check('main WebView collector UA suffix absent', 'WebSettings.getDefaultUserAgent(this@MainActivity) + " AdmissionCollector/$VERSION"' not in main)

surface_start = main.find('    private fun configureJinhakBrowserSurface(batchMode: Boolean) {')
surface_end = main.find('\n    private fun loadMainUrl(', surface_start)
check('surface function bounded', surface_start >= 0 and surface_end > surface_start)
surface = main[surface_start:surface_end] if surface_start >= 0 and surface_end > surface_start else ''
check('surface does not mutate UA', 'userAgentString' not in surface)
check('surface main-thread guard', 'Looper.myLooper() != Looper.getMainLooper()' in surface)
check('surface posts to handler when off-main', 'handler.post { configureJinhakBrowserSurface(batchMode) }' in surface)
check('surface lifecycle guard', 'isFinishing || isDestroyed' in surface)
check('surface same-WebView identity check', 'jinhakBrowserSurfaceWebView === webView' in surface)
check('surface idempotence helper used', 'needsSurfaceReconfigure' in surface)
check('surface exception containment', 'runCatching {' in surface and '.onFailure { error ->' in surface)
check('surface failure telemetry', 'jinhak-browser-surface-config-failed' in surface)
check('surface persistent settings first-view gated', 'applyPersistentBrowserIdentity(firstConfigurationForWebView)' in surface)
check('surface cookies accepted', 'setAcceptCookie(true)' in surface)
check('surface third-party cookies accepted', 'setAcceptThirdPartyCookies(webView, true)' in surface)
check('surface cookies flushed only inside first-view gate', surface.find('applyPersistentBrowserIdentity(firstConfigurationForWebView)') < surface.find('FLUSH_PROVIDER_COOKIES') if 'FLUSH_PROVIDER_COOKIES' in surface else False)
check('surface state committed after settings', surface.find('setSupportMultipleWindows') < surface.find('jinhakBrowserSurfaceWebView = webView') if 'setSupportMultipleWindows' in surface else False)

check('policy v0188 comment', 'v0.18.8 browser-surface contract.' in policy)
check('policy needs reconfigure helper', 'fun needsSurfaceReconfigure(' in policy)
check('policy first-view helper', 'fun applyPersistentBrowserIdentity(' in policy)
check('manual windows disabled', 'const val MANUAL_BROWSER_MULTIPLE_WINDOWS = false' in policy)
check('manual automatic windows disabled', 'const val MANUAL_BROWSER_AUTOMATIC_WINDOWS = false' in policy)
check('manual popup disabled', 'const val MANUAL_BROWSER_POPUP_HANDOFF = false' in policy)
check('popup handoff only while batch running', 'fun allowCollectorPopupHandoff(batchRunning: Boolean): Boolean = batchRunning' in policy)

# Verify the first main WebView lifecycle block does not rewrite surface settings.
page_started = main.find('override fun onPageStarted(')
page_finished = main.find('override fun onPageFinished(', page_started)
chrome = main.find('webView.webChromeClient', page_finished)
started_block = main[page_started:page_finished] if page_started >= 0 and page_finished > page_started else ''
finished_block = main[page_finished:chrome] if page_finished >= 0 and chrome > page_finished else ''
check('onPageStarted surface mutation removed', 'configureJinhakBrowserSurface' not in started_block)
check('onPageFinished surface mutation removed', 'configureJinhakBrowserSurface' not in finished_block)

# Explicit transition boundaries remain.
check('manual launch boundary config', 'private fun startLaunchAwareCollection()' in main and 'configureJinhakBrowserSurface(batchMode = false)' in main)
check('batch start boundary config', 'batchRunning = true\n        if (provider == ProviderId.JINHAK) configureJinhakBrowserSurface(batchMode = true)' in main)

stop_start = main.find('    private fun stopBatch(reason: String) {')
stop_end = main.find('\n    private fun pauseBatchForRenderedLoginSurface', stop_start)
check('stopBatch bounded', stop_start >= 0 and stop_end > stop_start)
stop = main[stop_start:stop_end] if stop_start >= 0 and stop_end > stop_start else ''
check('Jinhak stop returns manual surface', 'if (provider == ProviderId.JINHAK) {\n            configureJinhakBrowserSurface(batchMode = false)' in stop)
check('Jinhak stop does not call stopLoading branch', 'if (provider == ProviderId.JINHAK) {\n            configureJinhakBrowserSurface(batchMode = false)\n        } else {\n            webView.stopLoading()\n        }' in stop)

check('same manual no-op unit test', 'same webview and same manual mode is a no-op' in test)
check('mode transition unit test', 'same webview only reconfigures on real mode transition' in test)
check('replacement WebView unit test', 'replacement webview always receives one configuration' in test)
check('first-view persistent identity test', 'persistent browser identity is only applied on first configuration for a webview' in test)

# Existing provider/evidence safety behavior must remain present.
check('storage gate retained', 'JinhakManualStorageReportPolicy.isStorageEntry' in main)
check('same-card report policy retained', 'JinhakManualStorageReportPolicy' in main)
check('probabilityInferred contract retained', 'probabilityInferred' in main)
check('applicationIdentityKey retained', 'applicationIdentityKey' in main)
check('credential vault still explicitly cleared for Jinhak launch', 'credentialVault.clear(ProviderId.JINHAK.wireName)' in main)

print({'checks': len(checks), 'failed': failed})
if failed:
    raise SystemExit(1)
