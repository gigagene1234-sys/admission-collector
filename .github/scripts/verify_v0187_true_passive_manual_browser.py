from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
store = (ROOT / "app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt").read_text()
adapter = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt").read_text()
nav = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakManualStorageReportPolicy.kt").read_text()
state = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakManualBrowserStateMachine.kt").read_text()
surface = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakPassiveBrowserSurfacePolicy.kt").read_text()
gradle = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()


def body(name: str) -> str:
    m = re.search(rf"    private fun {re.escape(name)}(?:\([^\n]*\)|\([^)]*\))\s*(?::[^{{]+)?\{{.*?(?=\n    private fun |\n    fun |\n    override fun |\n}}\s*$)", main, re.S)
    return m.group(0) if m else ""


autofill_entry = body("beginV0184SingleSurfaceAutofill")
autofill_attempt = body("attemptV0184SingleSurfaceAutofill")
legacy_auth = body("startV0180DedicatedJinhakAuth")
legacy_block = body("blockJinhakV0174MainFrame")
recreate_auth = body("recreateV0180AuthWebView")
protected_probe = body("requestV0182ProtectedSessionProbe")
real_probe = body("startJinhakRealAuthProbe")
load_main = body("loadMainUrl")
stop_batch = body("stopBatch")
configure_surface = body("configureJinhakBrowserSurface")

required = {
    "apk-version": 'versionName = "0.18.7"' in gradle and 'versionCode = 118700' in gradle,
    "runtime-version": 'private const val VERSION = "0.18.7"' in main and 'private const val BUILD_CODE = 118700' in main,
    "old-runtime-version-gone": 'private const val VERSION = "0.18.6"' not in main and 'private const val BUILD_CODE = 118600' not in main,
    "launcher-label": 'Admission Hub v0.18.7 True Passive Manual Browser' in manifest,
    "surface-policy-import": 'import com.admissionhub.collector.jinhak.JinhakPassiveBrowserSurfacePolicy' in main,
    "surface-policy-default-ua": 'const val USE_DEFAULT_WEBVIEW_USER_AGENT = true' in surface,
    "surface-policy-cookie-flush": 'const val FLUSH_PROVIDER_COOKIES = true' in surface,
    "surface-policy-manual-single-window": 'const val MANUAL_BROWSER_MULTIPLE_WINDOWS = false' in surface,
    "surface-policy-manual-no-auto-window": 'const val MANUAL_BROWSER_AUTOMATIC_WINDOWS = false' in surface,
    "surface-policy-no-manual-popup-handoff": 'const val MANUAL_BROWSER_POPUP_HANDOFF = false' in surface,
    "surface-policy-popup-only-batch": 'fun allowCollectorPopupHandoff(batchRunning: Boolean): Boolean = batchRunning' in surface,
    "manual-phase": 'MANUAL_BROWSER' in state,
    "storage-phase": 'STORAGE_ARMED' in state,
    "report-phase": 'REPORT_TRAVERSAL' in state,
    "stop-only-phase": 'STOP_ONLY' in state,
    "manual-auth-disabled": all(x in state for x in [
        'const val AUTO_LOGIN = false', 'const val AUTH_PROBE = false',
        'const val SESSION_RESTORE = false', 'const val CREDENTIAL_AUTOFILL = false']),
    "storage-gate": 'const val STORAGE_PATH = "/jh/high3/early/four-year-university/library"' in policy,
    "report-scope": 'const val REPORT_PREFIX = "/jh/high3/early/four-year-university/report/"' in policy,
    "generic-crawl-off": 'const val GENERIC_SITE_CRAWL = false' in policy,
    "same-card-navigator": 'JinhakManualStorageReportPolicy.shouldPromoteAction' in nav,
    "adapter-storage-report-only": 'JinhakManualStorageReportPolicy.isAllowedMissionUrl(url)' in adapter,
    "surface-helper-exists": bool(configure_surface),
    "surface-helper-default-ua": bool(configure_surface) and 'WebSettings.getDefaultUserAgent(this@MainActivity)' in configure_surface,
    "surface-helper-cookie-preserve": bool(configure_surface) and 'setAcceptCookie(true)' in configure_surface and 'setAcceptThirdPartyCookies(webView, true)' in configure_surface and 'flush()' in configure_surface,
    "surface-helper-window-policy": bool(configure_surface) and 'automaticWindowsEnabled(batchMode)' in configure_surface and 'multipleWindowsEnabled(batchMode)' in configure_surface,
    "manual-load-bypasses-strict-before-request": bool(load_main) and 'if (!batchRunning)' in load_main and 'configureJinhakBrowserSurface(batchMode = false)' in load_main and load_main.find('if (!batchRunning)') < load_main.find('JinhakStrictHigh3Sandbox.decision(target)'),
    "manual-main-request-passive": 'if (!batchRunning) return super.shouldInterceptRequest(view, request)' in main,
    "manual-main-navigation-passive": 'if (!batchRunning) return false' in main,
    "manual-history-passive": 'if (provider != ProviderId.JINHAK) return\n                if (!batchRunning) return' in main,
    "manual-page-start-reasserts-surface": 'clearJinhakLegacyAuthState()\n                    configureJinhakBrowserSurface(batchMode = false)\n                    return' in main,
    "manual-popup-client-disabled": '!JinhakPassiveBrowserSurfacePolicy.allowCollectorPopupHandoff(batchRunning)' in main,
    "manual-multiwindow-off-at-configure": 'setSupportMultipleWindows(provider != ProviderId.JINHAK || batchRunning)' in main,
    "manual-auto-window-off-at-configure": 'javaScriptCanOpenWindowsAutomatically = provider != ProviderId.JINHAK || batchRunning' in main,
    "jinhak-default-ua-at-configure": 'userAgentString = if (provider == ProviderId.JINHAK)' in main and 'WebSettings.getDefaultUserAgent(this@MainActivity)' in main,
    "jinhak-page-finished-flushes-cookie": 'override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()' in main,
    "report-window-mode-after-batch-arm": 'batchRunning = true\n        if (provider == ProviderId.JINHAK) configureJinhakBrowserSurface(batchMode = true)' in main,
    "stop-only-no-jinhak-stoploading": bool(stop_batch) and 'if (provider == ProviderId.JINHAK)' in stop_batch and 'configureJinhakBrowserSurface(batchMode = false)' in stop_batch and 'else {\n            webView.stopLoading()' in stop_batch,
    "legacy-block-stop-only": bool(legacy_block) and 'startV0180DedicatedJinhakAuth' not in legacy_block and 'loadUrl(' not in legacy_block and 'stopLoading()' not in legacy_block,
    "legacy-auth-inert": bool(legacy_auth) and 'credentialVault.load' not in legacy_auth and 'loadUrl(' not in legacy_auth and 'beginV0184SingleSurfaceAutofill' not in legacy_auth,
    "legacy-entry-passive-surface": bool(legacy_auth) and 'configureJinhakBrowserSurface(batchMode = false)' in legacy_auth,
    "autofill-entry-inert": bool(autofill_entry) and 'credentialVault.load' not in autofill_entry and 'evaluateJavascript' not in autofill_entry,
    "autofill-attempt-inert": bool(autofill_attempt) and 'evaluateJavascript' not in autofill_attempt and 'password' not in autofill_attempt.split('{',1)[-1],
    "auth-webview-recreate-inert": bool(recreate_auth) and 'WebView(this)' not in recreate_auth and '.loadUrl(' not in recreate_auth,
    "protected-probe-inert": bool(protected_probe) and '.loadUrl(' not in protected_probe and 'markV0182ProtectedSessionVerified' not in protected_probe,
    "real-probe-inert": bool(real_probe) and 'startV0180DedicatedJinhakAuth' not in real_probe and '.loadUrl(' not in real_probe,
    "real-probe-passive-surface": bool(real_probe) and 'configureJinhakBrowserSurface(batchMode = false)' in real_probe,
    "exact-rebind-helper": 'private fun canonicalSessionForExactPinnedRebind(sessionId: String): String' in store,
    "exact-rebind-query": 'application_identity_key IN (SELECT application_identity_key FROM hub_application_slots WHERE user_pinned=1)' in store,
    "hub-uses-rebind-session": 'val canonicalEvidenceSessionId = canonicalSessionForExactPinnedRebind(sessionId)' in store and '.put("canonicalEvidenceSessionId", canonicalEvidenceSessionId)' in store,
    "review-uses-rebind-session": store.count('val canonicalEvidenceSessionId = canonicalSessionForExactPinnedRebind(sessionId)') >= 2,
    "review-identity-preserved": '.put("applicationIdentityKey", identity)\n                    .put("academicYear", reviewCandidate.optInt("academicYear", 0))' in store,
    "probability-contract-unchanged": 'probabilityInferred' in (ROOT / "app/src/main/java/com/admissionhub/collector/score/ApplicationReviewEngine.kt").read_text(),
}

failed = [name for name, ok in required.items() if not ok]
print({"checks": len(required), "failed": failed})
if failed:
    raise SystemExit("v0.18.7 contract verification failed: " + ", ".join(failed))
