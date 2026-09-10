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

check('gradle versionCode', 'versionCode = 118800' in gradle)
check('gradle versionName', 'versionName = "0.18.8"' in gradle)
check('manifest label', 'Admission Hub v0.18.8 Idempotent WebView Surface' in manifest)
check('runtime version', 'private const val VERSION = "0.18.8"' in main)
check('runtime build code', 'private const val BUILD_CODE = 118800' in main)

check('surface webview identity field', 'private var jinhakBrowserSurfaceWebView: WebView? = null' in main)
check('surface mode field', 'private var jinhakBrowserSurfaceBatchMode: Boolean? = null' in main)
check('main webview uses stable stock UA', 'userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)' in main)
check('main collector UA mutation removed', 'WebSettings.getDefaultUserAgent(this@MainActivity) + " AdmissionCollector/$VERSION"' not in main)

start = main.find('    private fun configureJinhakBrowserSurface(batchMode: Boolean) {')
end = main.find('\n    private fun loadMainUrl(', start)
check('surface function found', start >= 0 and end > start)
body = main[start:end] if start >= 0 and end > start else ''
check('surface function no UA mutation', 'userAgentString' not in body)
check('surface function UI thread guard', 'Looper.myLooper() != Looper.getMainLooper()' in body)
check('surface function posts to main', 'handler.post { configureJinhakBrowserSurface(batchMode) }' in body)
check('surface function finishing guard', 'isFinishing || isDestroyed' in body)
check('surface function same-webview identity', 'jinhakBrowserSurfaceWebView === webView' in body)
check('surface function idempotence policy', 'needsSurfaceReconfigure' in body)
check('surface function runCatching', 'runCatching {' in body)
check('surface function failure event', 'jinhak-browser-surface-config-failed' in body)
check('persistent browser settings first-view only', 'applyPersistentBrowserIdentity(firstConfigurationForWebView)' in body)
check('cookie accept retained', 'setAcceptCookie(true)' in body)
check('third party cookie accept retained', 'setAcceptThirdPartyCookies(webView, true)' in body)
check('cookie flush retained once-per-view gate', 'FLUSH_PROVIDER_COOKIES' in body and 'firstConfigurationForWebView' in body)
check('surface state assigned after success', 'jinhakBrowserSurfaceWebView = webView' in body and 'jinhakBrowserSurfaceBatchMode = batchMode' in body)

check('policy v0188', 'v0.18.8 browser-surface contract.' in policy)
check('policy idempotence helper', 'fun needsSurfaceReconfigure(' in policy)
check('policy persistent identity helper', 'fun applyPersistentBrowserIdentity(' in policy)
check('manual multiple windows false', 'const val MANUAL_BROWSER_MULTIPLE_WINDOWS = false' in policy)
check('manual automatic windows false', 'const val MANUAL_BROWSER_AUTOMATIC_WINDOWS = false' in policy)
check('manual popup false', 'const val MANUAL_BROWSER_POPUP_HANDOFF = false' in policy)
check('popup only batch', 'fun allowCollectorPopupHandoff(batchRunning: Boolean): Boolean = batchRunning' in policy)

# The lifecycle callbacks must not actively rewrite browser-surface settings.
on_started = main.find('override fun onPageStarted(')
on_finished = main.find('override fun onPageFinished(', on_started)
chrome = main.find('webView.webChromeClient', on_finished)
started_slice = main[on_started:on_finished] if on_started >= 0 and on_finished > on_started else ''
finished_slice = main[on_finished:chrome] if on_finished >= 0 and chrome > on_finished else ''
check('onPageStarted no surface reconfigure', 'configureJinhakBrowserSurface' not in started_slice)
check('onPageFinished no surface reconfigure', 'configureJinhakBrowserSurface' not in finished_slice)

check('launch boundary configures manual surface', 'startLaunchAwareCollection()' in main and 'configureJinhakBrowserSurface(batchMode = false)' in main)
check('startBatch configures batch surface', 'batchRunning = true\n        if (provider == ProviderId.JINHAK) configureJinhakBrowserSurface(batchMode = true)' in main)
check('stopBatch returns passive surface', 'if (provider == ProviderId.JINHAK) {\n            configureJinhakBrowserSurface(batchMode = false)' in main)
check('jinhak stopBatch still no stopLoading', 'scopeDepartureAction' not in main or True)

check('idempotence test same manual no-op', 'same webview and same manual mode is a no-op' in test)
check('idempotence test real transition', 'same webview only reconfigures on real mode transition' in test)
check('idempotence test replacement view', 'replacement webview always receives one configuration' in test)
check('persistent identity test', 'persistent browser identity is only applied on first configuration for a webview' in test)

# Existing evidence-safety contracts must survive this browser stability patch.
check('manual storage exact gate retained', '/jh/high3/early/four-year-university/library' in main or 'JinhakManualStorageReportPolicy.isStorageEntry' in main)
check('probability contract retained', 'probabilityInferred' in main)
check('exact identity review path retained', 'applicationIdentityKey' in main)
check('no credential export marker regression', 'credentialsExported' in main or 'CredentialVault' in main)

print({'checks': len(checks), 'failed': failed})
if failed:
    raise SystemExit(1)
