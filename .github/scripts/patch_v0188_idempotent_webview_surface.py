from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing anchor: {label}")
    if text.count(old) != 1:
        raise SystemExit(f"non-unique anchor {label}: {text.count(old)}")
    return text.replace(old, new, 1)

root = Path('.')
gradle = root / 'app/build.gradle.kts'
manifest = root / 'app/src/main/AndroidManifest.xml'
main = root / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
policy = root / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakPassiveBrowserSurfacePolicy.kt'

g = gradle.read_text()
g = replace_once(g, 'versionCode = 118700', 'versionCode = 118800', 'versionCode')
g = replace_once(g, 'versionName = "0.18.7"', 'versionName = "0.18.8"', 'versionName')
gradle.write_text(g)

m = manifest.read_text()
m = replace_once(
    m,
    'android:label="Admission Hub v0.18.7 True Passive Manual Browser"',
    'android:label="Admission Hub v0.18.8 Idempotent WebView Surface"',
    'manifest label',
)
manifest.write_text(m)

p = policy.read_text()
p = replace_once(p, 'v0.18.7 browser-surface contract.', 'v0.18.8 browser-surface contract.', 'policy version')
insert = '''\n    fun needsSurfaceReconfigure(\n        sameWebView: Boolean,\n        previousBatchMode: Boolean?,\n        requestedBatchMode: Boolean\n    ): Boolean = !sameWebView || previousBatchMode != requestedBatchMode\n\n    fun applyPersistentBrowserIdentity(firstConfigurationForWebView: Boolean): Boolean =\n        firstConfigurationForWebView\n'''
p = replace_once(
    p,
    '    fun allowCollectorPopupHandoff(batchRunning: Boolean): Boolean = batchRunning\n',
    insert + '\n    fun allowCollectorPopupHandoff(batchRunning: Boolean): Boolean = batchRunning\n',
    'policy helpers',
)
policy.write_text(p)

s = main.read_text()
s = replace_once(s, 'private const val VERSION = "0.18.7"', 'private const val VERSION = "0.18.8"', 'runtime version')
s = replace_once(s, 'private const val BUILD_CODE = 118700', 'private const val BUILD_CODE = 118800', 'runtime build code')

s = replace_once(
    s,
    '    private var provider: ProviderId = ProviderId.ADIGA\n    private var lastJinhakDigest = JSONObject()\n',
    '    private var provider: ProviderId = ProviderId.ADIGA\n    private var jinhakBrowserSurfaceWebView: WebView? = null\n    private var jinhakBrowserSurfaceBatchMode: Boolean? = null\n    private var lastJinhakDigest = JSONObject()\n',
    'surface state fields',
)

old_fun = '''    private fun configureJinhakBrowserSurface(batchMode: Boolean) {\n        if (provider != ProviderId.JINHAK || !::webView.isInitialized) return\n        webView.settings.apply {\n            if (JinhakPassiveBrowserSurfacePolicy.USE_DEFAULT_WEBVIEW_USER_AGENT) {\n                userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)\n            }\n            javaScriptCanOpenWindowsAutomatically = JinhakPassiveBrowserSurfacePolicy.automaticWindowsEnabled(batchMode)\n            setSupportMultipleWindows(JinhakPassiveBrowserSurfacePolicy.multipleWindowsEnabled(batchMode))\n        }\n        CookieManager.getInstance().apply {\n            setAcceptCookie(true)\n            setAcceptThirdPartyCookies(webView, true)\n            if (JinhakPassiveBrowserSurfacePolicy.FLUSH_PROVIDER_COOKIES) flush()\n        }\n    }\n'''
new_fun = '''    private fun configureJinhakBrowserSurface(batchMode: Boolean) {\n        if (provider != ProviderId.JINHAK || !::webView.isInitialized || isFinishing || isDestroyed) return\n        if (Looper.myLooper() != Looper.getMainLooper()) {\n            handler.post { configureJinhakBrowserSurface(batchMode) }\n            return\n        }\n\n        val sameWebView = jinhakBrowserSurfaceWebView === webView\n        if (!JinhakPassiveBrowserSurfacePolicy.needsSurfaceReconfigure(\n                sameWebView = sameWebView,\n                previousBatchMode = jinhakBrowserSurfaceBatchMode,\n                requestedBatchMode = batchMode\n            )) return\n\n        val firstConfigurationForWebView = !sameWebView\n        runCatching {\n            webView.settings.apply {\n                val automaticWindows = JinhakPassiveBrowserSurfacePolicy.automaticWindowsEnabled(batchMode)\n                if (javaScriptCanOpenWindowsAutomatically != automaticWindows) {\n                    javaScriptCanOpenWindowsAutomatically = automaticWindows\n                }\n                setSupportMultipleWindows(JinhakPassiveBrowserSurfacePolicy.multipleWindowsEnabled(batchMode))\n            }\n            if (JinhakPassiveBrowserSurfacePolicy.applyPersistentBrowserIdentity(firstConfigurationForWebView)) {\n                CookieManager.getInstance().apply {\n                    setAcceptCookie(true)\n                    setAcceptThirdPartyCookies(webView, true)\n                    if (JinhakPassiveBrowserSurfacePolicy.FLUSH_PROVIDER_COOKIES) flush()\n                }\n            }\n            jinhakBrowserSurfaceWebView = webView\n            jinhakBrowserSurfaceBatchMode = batchMode\n        }.onFailure { error ->\n            recordRuntimeEvent(\n                "jinhak-browser-surface-config-failed",\n                JSONObject()\n                    .put("batchMode", batchMode)\n                    .put("error", error.javaClass.simpleName.take(80))\n            )\n        }\n    }\n'''
s = replace_once(s, old_fun, new_fun, 'configureJinhakBrowserSurface')

old_ua = '''            userAgentString = if (provider == ProviderId.JINHAK) {\n                WebSettings.getDefaultUserAgent(this@MainActivity)\n            } else {\n                WebSettings.getDefaultUserAgent(this@MainActivity) + " AdmissionCollector/$VERSION"\n            }\n'''
new_ua = '''            // Keep the main WebView identity stable for its entire lifetime.\n            // Switching UA after a page starts can trigger a reload/reinitialization cycle.\n            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)\n'''
s = replace_once(s, old_ua, new_ua, 'stable main WebView UA')

# Do not reconfigure the WebView from page lifecycle callbacks. Browser-surface
# transitions are owned only by explicit launch/startBatch/stopBatch boundaries.
s = replace_once(
    s,
    '''                if (provider == ProviderId.JINHAK && !batchRunning) {\n                    clearJinhakLegacyAuthState()\n                    configureJinhakBrowserSurface(batchMode = false)\n                    return\n                }\n''',
    '''                if (provider == ProviderId.JINHAK && !batchRunning) {\n                    clearJinhakLegacyAuthState()\n                    return\n                }\n''',
    'onPageStarted surface mutation removal',
)
s = replace_once(
    s,
    '''                        if (JinhakManualStorageReportPolicy.isStorageEntry(current)) {\n                            configureJinhakBrowserSurface(batchMode = false)\n                            batchPausedForLogin = false\n''',
    '''                        if (JinhakManualStorageReportPolicy.isStorageEntry(current)) {\n                            batchPausedForLogin = false\n''',
    'storage page-finished surface mutation removal',
)
s = replace_once(
    s,
    '''                        } else {\n                            configureJinhakBrowserSurface(batchMode = false)\n                            sessionState.text = "○ 진학사 직접 탐색"\n''',
    '''                        } else {\n                            sessionState.text = "○ 진학사 직접 탐색"\n''',
    'manual page-finished surface mutation removal',
)

main.write_text(s)
print('v0.18.8 patch applied')
