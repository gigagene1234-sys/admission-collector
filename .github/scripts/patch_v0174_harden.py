from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
SLOW = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSlowLanePool.kt"


def must_replace(text: str, old: str, new: str, label: str, min_count: int = 1) -> str:
    if new in text and old not in text:
        return text
    count = text.count(old)
    if count < min_count:
        raise SystemExit(f"{label}: expected >= {min_count}, found {count}")
    return text.replace(old, new)


text = MAIN.read_text()

# Every legacy Jinhak home fallback now routes through the one strict app-navigation helper.
text = text.replace(
    "webView.loadUrl(ProviderId.JINHAK.homeUrl)",
    'loadJinhakV0174High3Only(ProviderId.JINHAK.homeUrl, "legacy-jinhak-home-failsafe")'
)

# Known Jinhak core/probe loads are high3 but must still pass through the same central validator.
text = text.replace(
    "webView.loadUrl(coreProbe)",
    'loadJinhakV0174High3Only(coreProbe, "legacy-core-probe")'
)
text = text.replace(
    "if (core.isNotBlank()) webView.loadUrl(core) else openJinhakDirectHigh3Auth(\"startup-no-core\", null)",
    'if (core.isNotBlank()) loadJinhakV0174High3Only(core, "startup-core") else openJinhakV0174StrictEntry("startup-no-core")'
)

# Credential dialog can never construct/open a Jinhak login URL. For Jinhak the user gets only
# the strict high3 entry; server-side redirect may expose the high3-bound member login surface.
text = text.replace(
    "if (!continueAfterSave) webView.loadUrl(providerLoginUrl(which))",
    'if (!continueAfterSave) {\n                    if (which == ProviderId.JINHAK) openJinhakV0174StrictEntry("credential-dialog-direct-login")\n                    else webView.loadUrl(providerLoginUrl(which))\n                }'
)

# All foreground Jinhak recovery/retry paths pass through strict high3 validation before loadUrl.
text = text.replace(
    "if (!retryOrigin.isNullOrBlank() && isProviderUrl(retryOrigin)) webView.loadUrl(retryOrigin)\n                else loadNextBatchPage()",
    'if (!retryOrigin.isNullOrBlank() && JinhakStrictHigh3Sandbox.allowsCollectorNavigation(retryOrigin)) {\n                    loadJinhakV0174High3Only(retryOrigin, "recovery-retry-origin")\n                } else {\n                    jinhakV0174PersistedTargetBlocks += 1\n                    loadNextBatchPage()\n                }'
)
text = text.replace(
    "if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)\n                else loadNextBatchPage()",
    'if (!retry.isNullOrBlank() && provider == ProviderId.JINHAK) {\n                    if (!loadJinhakV0174High3Only(retry, "legacy-retry")) {\n                        jinhakV0174PersistedTargetBlocks += 1\n                        loadNextBatchPage()\n                    }\n                } else if (!retry.isNullOrBlank() && isProviderUrl(retry)) {\n                    webView.loadUrl(retry)\n                } else loadNextBatchPage()'
)
text = text.replace(
    "webView.loadUrl(failedRoute)",
    'loadJinhakV0174High3Only(failedRoute, "bootstrap-failed-route-retry")'
)

# Strictify any Jinhak transition/open-provider generic home calls without changing Adiga.
text = text.replace(
    "webView.loadUrl(which.homeUrl)",
    'if (which == ProviderId.JINHAK) loadJinhakV0174High3Only(which.homeUrl, "provider-home") else webView.loadUrl(which.homeUrl)'
)

# If a legacy generic beginBatch block is ever reached for Jinhak, it cannot directly load a URL.
old_generic_start = """                val startUrl = currentBatchTarget
                if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)
                else loadNextBatchPage()
"""
new_generic_start = """                val startUrl = currentBatchTarget
                if (!startUrl.isNullOrBlank() && provider == ProviderId.JINHAK) {
                    if (!loadJinhakV0174High3Only(startUrl, "legacy-begin-start")) loadNextBatchPage()
                } else if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)
                else loadNextBatchPage()
"""
if old_generic_start in text:
    text = text.replace(old_generic_start, new_generic_start)

# Auto-start/natural high3 transitions are forbidden. Startup user-session entry may open only the
# strict high3 URL and must then wait for explicit approval on a visible high3 page.
old_begin_jinhak = """        if (which == ProviderId.JINHAK) {
            provider = ProviderId.JINHAK
            startupLoginStage = "jinhak-user-owned-session"
            startupLoginOpenAttempted = false
"""
if old_begin_jinhak in text:
    new_begin_jinhak = """        if (which == ProviderId.JINHAK) {
            provider = ProviderId.JINHAK
            startupLoginStage = "jinhak-strict-high3-user-owned-session"
            startupLoginOpenAttempted = false
"""
    text = text.replace(old_begin_jinhak, new_begin_jinhak, 1)

# The legacy provider login URL accessor must be fail-safe for Jinhak if any old call survives.
old_provider_login = '        ProviderId.JINHAK -> JinhakHigh3AuthRoute.sanitizeReturnTarget(currentBatchTarget)\n'
new_provider_login = '        ProviderId.JINHAK -> JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget) ?: JinhakStrictHigh3Sandbox.strictEntryUrl()\n'
if old_provider_login in text:
    text = text.replace(old_provider_login, new_provider_login)

# Extend v0.17.4 decision diagnostics for high3-return login blocking if the strict policy adds it.
old_decision_case = '''            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_GENERIC_LOGIN -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174GenericLoginBlocks += 1 }
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_OTHER_JINHAK -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174OtherJinhakBlocks += 1 }
'''
new_decision_case = '''            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_GENERIC_LOGIN -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174GenericLoginBlocks += 1 }
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174OtherJinhakBlocks += 1 }
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_OTHER_JINHAK -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174OtherJinhakBlocks += 1 }
'''
if old_decision_case in text:
    text = text.replace(old_decision_case, new_decision_case)

MAIN.write_text(text)

# Hidden slow-lane browsers can never present login UI, so they are stricter than the foreground:
# high3-only top-level navigation, lower-grade blocking for every request, and no member/root route.
slow = SLOW.read_text()
if "import android.webkit.WebResourceResponse" not in slow:
    slow = slow.replace(
        "import android.webkit.WebResourceRequest\n",
        "import android.webkit.WebResourceRequest\nimport android.webkit.WebResourceResponse\n"
    )
if "import java.io.ByteArrayInputStream" not in slow:
    slow = slow.replace("import java.util.ArrayDeque\n", "import java.util.ArrayDeque\nimport java.io.ByteArrayInputStream\n")

old_client = '''        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean =
                !isAllowedJinhakUrl(request.url.toString())

            override fun onPageStarted(v: WebView, url: String, favicon: Bitmap?) {
                if (slot.task == null) return
                slot.lastProgressAtMs = System.currentTimeMillis()
                slot.pageFinished = false
                slot.stablePolls = 0
            }
'''
new_client = '''        view.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(v: WebView, request: WebResourceRequest): WebResourceResponse? {
                val target = request.url?.toString().orEmpty()
                if (JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) return blockedResponse("lower-grade-any-request")
                if (request.isForMainFrame && !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(target)) {
                    return blockedResponse("non-high3-main-frame")
                }
                return super.shouldInterceptRequest(v, request)
            }

            override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean =
                !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(request.url.toString())

            override fun onPageStarted(v: WebView, url: String, favicon: Bitmap?) {
                if (slot.task == null) return
                if (!JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) {
                    runCatching { v.stopLoading() }
                    finishFailure(slot, "slow-lane-strict-high3-block")
                    return
                }
                slot.lastProgressAtMs = System.currentTimeMillis()
                slot.pageFinished = false
                slot.stablePolls = 0
            }
'''
if old_client not in slow:
    raise SystemExit("slow-lane WebViewClient anchor missing")
slow = slow.replace(old_client, new_client, 1)

old_allowed = '''    private fun isAllowedJinhakUrl(raw: String): Boolean = try {
        val uri = Uri.parse(raw)
        val host = uri.host.orEmpty().lowercase()
        uri.scheme == "https" && (host == "jinhak.com" || host.endsWith(".jinhak.com"))
    } catch (_: Exception) { false }
'''
new_allowed = '''    private fun blockedResponse(reason: String): WebResourceResponse = WebResourceResponse(
        "text/plain",
        "UTF-8",
        204,
        "No Content",
        mapOf("Cache-Control" to "no-store", "X-Admission-Hub-SlowLane-Fence" to reason),
        ByteArrayInputStream(ByteArray(0))
    )

    private fun isAllowedJinhakUrl(raw: String): Boolean =
        JinhakStrictHigh3Sandbox.allowsCollectorNavigation(raw)
'''
if old_allowed not in slow:
    raise SystemExit("slow-lane isAllowedJinhakUrl anchor missing")
slow = slow.replace(old_allowed, new_allowed, 1)
SLOW.write_text(slow)

print("v0.17.4 hardening applied: remaining foreground retries centralized; slow lane high3-only; member login requires high3 return")
