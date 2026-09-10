from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
store = (ROOT / "app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt").read_text()
adapter = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt").read_text()
nav = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakManualStorageReportPolicy.kt").read_text()
state = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakManualBrowserStateMachine.kt").read_text()
gradle = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()


def body(name: str) -> str:
    m = re.search(rf"    private fun {re.escape(name)}(?:\([^\n]*\)|\([^)]*\))\s*\{{.*?(?=\n    private fun |\n    fun |\n    override fun |\n}}\s*$)", main, re.S)
    return m.group(0) if m else ""


autofill_entry = body("beginV0184SingleSurfaceAutofill")
autofill_attempt = body("attemptV0184SingleSurfaceAutofill")
legacy_auth = body("startV0180DedicatedJinhakAuth")
legacy_block = body("blockJinhakV0174MainFrame")
recreate_auth = body("recreateV0180AuthWebView")
protected_probe = body("requestV0182ProtectedSessionProbe")
real_probe = body("startJinhakRealAuthProbe")

required = {
    "apk-version": 'versionName = "0.18.6"' in gradle and 'versionCode = 118600' in gradle,
    "runtime-version": 'private const val VERSION = "0.18.6"' in main and 'private const val BUILD_CODE = 118600' in main,
    "old-runtime-version-gone": 'private const val VERSION = "0.18.4"' not in main and 'private const val BUILD_CODE = 118400' not in main,
    "launcher-label": 'Admission Hub v0.18.6 Manual Browser State Machine' in manifest,
    "state-machine-import": 'import com.admissionhub.collector.jinhak.JinhakManualBrowserStateMachine' in main,
    "manual-phase": 'MANUAL_BROWSER' in state,
    "storage-phase": 'STORAGE_ARMED' in state,
    "report-phase": 'REPORT_TRAVERSAL' in state,
    "stop-only-phase": 'STOP_ONLY' in state,
    "manual-interception-false": 'const val INTERCEPT_MANUAL_BROWSER_NAVIGATION = false' in state,
    "manual-stoploading-false": 'const val STOP_LOADING_IN_MANUAL_BROWSER = false' in state,
    "manual-auth-disabled": all(x in state for x in [
        'const val AUTO_LOGIN = false', 'const val AUTH_PROBE = false',
        'const val SESSION_RESTORE = false', 'const val CREDENTIAL_AUTOFILL = false']),
    "storage-gate": 'const val STORAGE_PATH = "/jh/high3/early/four-year-university/library"' in policy,
    "report-scope": 'const val REPORT_PREFIX = "/jh/high3/early/four-year-university/report/"' in policy,
    "generic-crawl-off": 'const val GENERIC_SITE_CRAWL = false' in policy,
    "same-card-navigator": 'JinhakManualStorageReportPolicy.shouldPromoteAction' in nav,
    "adapter-storage-report-only": 'JinhakManualStorageReportPolicy.isAllowedMissionUrl(url)' in adapter,
    "service-worker-passive-before-batch": 'if (provider == ProviderId.JINHAK && !batchRunning) return null' in main,
    "main-request-passive-before-batch": 'if (!batchRunning) return super.shouldInterceptRequest(view, request)' in main,
    "navigation-passive-before-batch": 'if (!batchRunning) return false' in main,
    "history-passive-before-batch": 'if (provider != ProviderId.JINHAK) return\n                if (!batchRunning) return' in main,
    "page-start-passive-before-batch": 'if (provider == ProviderId.JINHAK && !batchRunning) {\n                    clearJinhakLegacyAuthState()\n                    return' in main,
    "scope-departure-allows-page": '자동 탐색 범위를 벗어났습니다. 페이지 이동은 막지 않습니다.' in main,
    "legacy-block-stop-only": bool(legacy_block) and 'startV0180DedicatedJinhakAuth' not in legacy_block and 'loadUrl(' not in legacy_block and 'stopLoading()' not in legacy_block,
    "legacy-auth-inert": bool(legacy_auth) and 'credentialVault.load' not in legacy_auth and 'loadUrl(' not in legacy_auth and 'beginV0184SingleSurfaceAutofill' not in legacy_auth,
    "autofill-entry-inert": bool(autofill_entry) and 'credentialVault.load' not in autofill_entry and 'evaluateJavascript' not in autofill_entry,
    "autofill-attempt-inert": bool(autofill_attempt) and 'evaluateJavascript' not in autofill_attempt and 'password' not in autofill_attempt.split('{',1)[-1],
    "auth-webview-recreate-inert": bool(recreate_auth) and 'WebView(this)' not in recreate_auth and '.loadUrl(' not in recreate_auth,
    "protected-probe-inert": bool(protected_probe) and '.loadUrl(' not in protected_probe and 'markV0182ProtectedSessionVerified' not in protected_probe,
    "real-probe-inert": bool(real_probe) and 'startV0180DedicatedJinhakAuth' not in real_probe and '.loadUrl(' not in real_probe,
    "no-jinhak-auth-inference": 'val authStateClass = "user-viewed-no-auth-inference"' in main and 'val batchAuthState = "user-viewed-no-auth-inference"' in main,
    "jinhak-session-keepalive-off": 'no Jinhak session keep-alive, measurement, or auth diagnostic exists' in main,
    "jinhak-cookie-flush-not-forced": 'if (which != ProviderId.JINHAK) CookieManager.getInstance().flush()' in main,
    "exact-rebind-helper": 'private fun canonicalSessionForExactPinnedRebind(sessionId: String): String' in store,
    "exact-rebind-query": 'application_identity_key IN (SELECT application_identity_key FROM hub_application_slots WHERE user_pinned=1)' in store,
    "no-similarity-rebind": 'canonicalSessionForExactPinnedRebind' in store and 'latestReusableCanonicalSessionId() ?: sessionId' in store,
    "hub-uses-rebind-session": 'val canonicalEvidenceSessionId = canonicalSessionForExactPinnedRebind(sessionId)' in store and '.put("canonicalEvidenceSessionId", canonicalEvidenceSessionId)' in store,
    "review-uses-rebind-session": store.count('val canonicalEvidenceSessionId = canonicalSessionForExactPinnedRebind(sessionId)') >= 2,
    "review-identity-preserved": '.put("applicationIdentityKey", identity)\n                    .put("academicYear", reviewCandidate.optInt("academicYear", 0))' in store,
    "probability-contract-unchanged": 'probabilityInferred' in (ROOT / "app/src/main/java/com/admissionhub/collector/score/ApplicationReviewEngine.kt").read_text(),
}

failed = [name for name, ok in required.items() if not ok]
print({"checks": len(required), "failed": failed})
if failed:
    raise SystemExit("v0.18.6 contract verification failed: " + ", ".join(failed))
