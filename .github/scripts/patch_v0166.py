from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main_path = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
gradle_path = ROOT / "app/build.gradle.kts"
manifest_path = ROOT / "app/src/main/AndroidManifest.xml"


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 occurrence, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    out, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 regex match, found {count}")
    return out


text = main_path.read_text()

text = once(
    text,
    "import android.webkit.WebResourceRequest\nimport android.webkit.WebSettings",
    "import android.webkit.WebResourceRequest\nimport android.webkit.WebResourceResponse\nimport android.webkit.WebSettings",
    "WebResourceResponse import",
)
text = once(
    text,
    "import java.time.Instant\nimport java.util.ArrayDeque",
    "import java.io.ByteArrayInputStream\nimport java.time.Instant\nimport java.util.ArrayDeque",
    "ByteArrayInputStream import",
)

text = once(
    text,
    "    private var jinhakV0165ProbeCompletedFromProtectedCore = 0\n    private var jinhakPostMissionClosureFences = 0",
    "    private var jinhakV0165ProbeCompletedFromProtectedCore = 0\n"
    "    private var jinhakV0166LowerGradeRequestsIntercepted = 0\n"
    "    private var jinhakV0166LowerGradeNavigationsHardBlocked = 0\n"
    "    private var jinhakV0166LowerGradeRecoveryDispatches = 0\n"
    "    private var jinhakV0166LowerGradeRecoveryPending = false\n"
    "    private var jinhakPostMissionClosureFences = 0",
    "v0166 counters",
)

# Hard network fence: a lower-grade main-frame URL is answered locally before WebView reaches it.
text = once(
    text,
    "        webView.webViewClient = object : WebViewClient() {\n            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {",
    "        webView.webViewClient = object : WebViewClient() {\n"
    "            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {\n"
    "                val target = request.url?.toString().orEmpty()\n"
    "                if (provider == ProviderId.JINHAK && request.isForMainFrame && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {\n"
    "                    handler.post {\n"
    "                        if (provider == ProviderId.JINHAK) {\n"
    "                            jinhakV0166LowerGradeRequestsIntercepted += 1\n"
    "                            hardBlockJinhakLowerGradeNavigation(\"network-intercept\", target)\n"
    "                        }\n"
    "                    }\n"
    "                    return blockedJinhakLowerGradeResponse()\n"
    "                }\n"
    "                return super.shouldInterceptRequest(view, request)\n"
    "            }\n\n"
    "            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {",
    "main WebView network intercept",
)

old_override = '''                if (target.isNotBlank() && jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                    jinhakLowerGradeNavigationsBlocked += 1
                    recordRuntimeEvent("jinhak-lower-grade-navigation-blocked", JSONObject()
                        .put("targetSafePath", runtimeSafePath(target))
                        .put("currentSafePath", runtimeSafePath(view.url.orEmpty()))
                        .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core())))
                    if (jinhakLowerGradeAuthFenceShouldTerminate()) {
                        recoverJinhakLowerGradeLoginContext("lower-grade-navigation", JSONObject().put("targetSafePath", runtimeSafePath(target)))
                    } else {
                        status.text = "진학사 고1·고2 화면 이동 차단 · 현재 고3 세션을 유지합니다."
                    }
                    return true
                }'''
new_override = '''                if (target.isNotBlank() && provider == ProviderId.JINHAK && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                    hardBlockJinhakLowerGradeNavigation("navigation-override", target)
                    return true
                }'''
text = once(text, old_override, new_override, "main lower-grade navigation override")

old_started = '''                if (provider == ProviderId.JINHAK && (
                        isProviderLoginUrl(ProviderId.JINHAK, url) ||
                            (jinhakAuthCompatibilityWindowActive() && JinhakGradeRouteFence.isBlockedLowerGrade(url))
                        )) {
                    view.visibility = View.INVISIBLE
                    status.text = "진학사 인증 전환 처리 중 · 고1·2 화면은 표시하지 않고 기존 로그인 흐름을 유지합니다."
                }
                if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
                    jinhakLowerGradeNavigationsBlocked += 1
                    view.stopLoading()
                    recordRuntimeEvent("jinhak-lower-grade-redirect-stopped", JSONObject()
                        .put("targetSafePath", runtimeSafePath(url))
                        .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core())))
                    if (jinhakLowerGradeAuthFenceShouldTerminate()) {
                        recoverJinhakLowerGradeLoginContext("lower-grade-redirect", JSONObject().put("targetSafePath", runtimeSafePath(url)))
                    } else {
                        status.text = "진학사 고1·고2 리다이렉트 차단 · 해당 페이지를 열지 않고 현재 고3 세션을 유지합니다."
                    }
                    return
                }'''
new_started = '''                if (provider == ProviderId.JINHAK && JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
                    view.visibility = View.INVISIBLE
                    runCatching { view.stopLoading() }
                    hardBlockJinhakLowerGradeNavigation("page-started", url)
                    return
                }
                if (provider == ProviderId.JINHAK && isProviderLoginUrl(ProviderId.JINHAK, url)) {
                    // v0.16.6: the shared Jinhak login page is a legitimate user-owned surface.
                    // Never hide it merely because an auth compatibility window is active.
                    view.visibility = View.VISIBLE
                    sessionState.text = "○ 진학사 고3 사이트 로그인 화면"
                    status.text = "진학사 고3 로그인 화면입니다. 고1·고2 경로는 네트워크 단계에서 차단되며 이 화면만 사용자 로그인용으로 유지합니다."
                }'''
text = once(text, old_started, new_started, "page-started lower-grade/login handling")

# Popup WebViews get the same pre-network hard fence and never hand lower-grade routes to the main WebView.
text = once(
    text,
    "                child.webViewClient = object : WebViewClient() {\n                    private fun handoff(target: String): Boolean {",
    "                child.webViewClient = object : WebViewClient() {\n"
    "                    override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {\n"
    "                        val target = request.url?.toString().orEmpty()\n"
    "                        if (provider == ProviderId.JINHAK && request.isForMainFrame && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {\n"
    "                            handler.post {\n"
    "                                if (provider == ProviderId.JINHAK) {\n"
    "                                    jinhakV0166LowerGradeRequestsIntercepted += 1\n"
    "                                    hardBlockJinhakLowerGradeNavigation(\"popup-network-intercept\", target)\n"
    "                                    destroyTransientPopup(\"lower-grade-network-blocked\")\n"
    "                                }\n"
    "                            }\n"
    "                            return blockedJinhakLowerGradeResponse()\n"
    "                        }\n"
    "                        return super.shouldInterceptRequest(view, request)\n"
    "                    }\n\n"
    "                    private fun handoff(target: String): Boolean {",
    "popup network intercept",
)
text = text.replace(
    "if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {",
    "if (provider == ProviderId.JINHAK && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {",
)

# Insert the route-isolation helpers directly before legacy auth-fence helpers.
marker = "    private fun jinhakLowerGradeAuthFenceShouldTerminate(): Boolean {"
helpers = r'''    private fun blockedJinhakLowerGradeResponse(): WebResourceResponse = WebResourceResponse(
        "text/plain",
        "UTF-8",
        403,
        "Blocked by Admission Hub high3 route isolation",
        mapOf("Cache-Control" to "no-store", "X-Admission-Hub-Route-Fence" to "high3-only"),
        ByteArrayInputStream(ByteArray(0))
    )

    private fun hardBlockJinhakLowerGradeNavigation(source: String, target: String) {
        if (provider != ProviderId.JINHAK || !JinhakGradeRouteFence.isBlockedLowerGrade(target)) return
        jinhakLowerGradeNavigationsBlocked += 1
        jinhakV0166LowerGradeNavigationsHardBlocked += 1
        runCatching { webView.stopLoading() }
        webView.visibility = View.INVISIBLE
        recordRuntimeEvent(
            "jinhak-v0166-lower-grade-hard-block",
            JSONObject()
                .put("source", source.take(80))
                .put("targetSafePath", runtimeSafePath(target))
                .put("currentSafePath", runtimeSafePath(webView.url.orEmpty()))
                .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core()))
                .put("networkRequestAllowed", false)
                .put("followLowerGrade", false)
                .put("batchTerminated", false)
        )
        scheduleJinhakHigh3RouteIsolationRecovery(source)
    }

    private fun scheduleJinhakHigh3RouteIsolationRecovery(source: String) {
        if (provider != ProviderId.JINHAK || jinhakV0166LowerGradeRecoveryPending) return
        val high3Core = JinhakGradeRouteFence.protectedHigh3Core()
        if (high3Core.isBlank() || JinhakGradeRouteFence.isBlockedLowerGrade(high3Core)) return
        jinhakV0166LowerGradeRecoveryPending = true
        jinhakV0166LowerGradeRecoveryDispatches += 1
        handler.postDelayed({
            jinhakV0166LowerGradeRecoveryPending = false
            if (provider != ProviderId.JINHAK) return@postDelayed
            val current = webView.url.orEmpty()
            if (JinhakGradeRouteFence.isBlockedLowerGrade(current) || current.isBlank() || current == "about:blank") {
                webView.visibility = View.INVISIBLE
                recordRuntimeEvent("jinhak-v0166-return-to-protected-high3", JSONObject()
                    .put("source", source.take(80))
                    .put("coreSafePath", runtimeSafePath(high3Core))
                    .put("automaticLowerGradeFollow", false))
                webView.loadUrl(high3Core)
            } else if (isProviderLoginUrl(ProviderId.JINHAK, current)) {
                // Login is user-owned. Do not create another automatic core/login loop here.
                webView.visibility = View.VISIBLE
                status.text = "진학사 고3 로그인 화면을 유지합니다. 로그인 완료 후 '사이트 로그인·동의 완료 후 계속'을 누르세요."
            }
        }, 160L)
    }

'''
if marker not in text:
    raise SystemExit("route helper marker missing")
text = text.replace(marker, helpers + marker, 1)

# v0.9.12 compatibility must never treat high1/high2 as a valid hidden authentication transition.
text = regex_once(
    text,
    r'''    private fun handleJinhakV0912AuthCompatibilityPage\(url: String\): Boolean \{.*?\n    \}\n\n    private fun recoverJinhakLowerGradeLoginContext''',
    r'''    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {
        if (provider != ProviderId.JINHAK || !jinhakAuthCompatibilityWindowActive()) return false
        val lowerGradeTransition = JinhakGradeRouteFence.isBlockedLowerGrade(url)
        if (lowerGradeTransition) {
            // v0.16.6: lower-grade is not an auth transition. It is a forbidden route.
            hardBlockJinhakLowerGradeNavigation("v0912-compatibility-route", url)
            return true
        }
        val loginRoute = isProviderLoginUrl(ProviderId.JINHAK, url)
        if (!loginRoute) return false

        jinhakV0912AuthCompatibilityTransitions += 1
        webView.visibility = View.VISIBLE
        checkSessionState { needsLogin, authenticated ->
            if (provider != ProviderId.JINHAK) return@checkSessionState
            if (authenticated && !needsLogin) {
                val high3Core = JinhakGradeRouteFence.protectedHigh3Core()
                credentialAwaitingLoginExitProvider = null
                jinhakReauthCycles = 0
                jinhakCoreBootstrapState = "v0166-authenticated-handoff-to-protected-high3"
                jinhakLastAuthEvidence = "session-authenticated-before-protected-core"
                jinhakV0912ProtectedCoreHandoffs += 1
                if (high3Core.isNotBlank() && !JinhakGradeRouteFence.isBlockedLowerGrade(high3Core)) {
                    webView.visibility = View.INVISIBLE
                    recordRuntimeEvent("jinhak-v0166-protected-core-handoff", JSONObject()
                        .put("sourceSafePath", runtimeSafePath(url))
                        .put("coreSafePath", runtimeSafePath(high3Core))
                        .put("handoff", jinhakV0912ProtectedCoreHandoffs)
                        .put("lowerGradeFollowed", false))
                    webView.loadUrl(high3Core)
                }
            } else {
                webView.visibility = View.VISIBLE
                installJinhakHigh3DomProductFence("v0166-shared-login-visual-fence")
                scheduleLoginSurfaceDetection(ProviderId.JINHAK, "v0166-shared-login")
                scheduleJinhakLoginRecovery("v0166-shared-login-wait")
            }
        }
        return true
    }

    private fun recoverJinhakLowerGradeLoginContext''',
    "v0912 compatibility function",
)

text = regex_once(
    text,
    r'''    private fun recoverJinhakLowerGradeLoginContext\(source: String, detail: JSONObject = JSONObject\(\)\) \{.*?\n    \}\n\n    private fun verifyRecoveredJinhakHigh3AndResume''',
    r'''    private fun recoverJinhakLowerGradeLoginContext(source: String, detail: JSONObject = JSONObject()) {
        if (provider != ProviderId.JINHAK) return
        val target = detail.optString("targetUrl").takeIf { it.isNotBlank() }
            ?: webView.url.orEmpty()
        if (JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
            hardBlockJinhakLowerGradeNavigation(source, target)
        }
    }

    private fun verifyRecoveredJinhakHigh3AndResume''',
    "legacy lower-grade recovery function",
)

# Login recovery itself may never consume/follow a lower-grade URL.
text = once(
    text,
    "        val v0165Current = webView.url.orEmpty()\n        val v0165HasLocalCredential = credentialVault.load(ProviderId.JINHAK.wireName) != null",
    "        val v0165Current = webView.url.orEmpty()\n"
    "        if (JinhakGradeRouteFence.isBlockedLowerGrade(v0165Current)) {\n"
    "            hardBlockJinhakLowerGradeNavigation(\"login-recovery-entry\", v0165Current)\n"
    "            return\n"
    "        }\n"
    "        val v0165HasLocalCredential = credentialVault.load(ProviderId.JINHAK.wireName) != null",
    "login recovery hard gate",
)
text = once(
    text,
    "        val currentUrl = webView.url.orEmpty()\n        if (isProviderLoginUrl(ProviderId.JINHAK, currentUrl)) {",
    "        val currentUrl = webView.url.orEmpty()\n"
    "        if (JinhakGradeRouteFence.isBlockedLowerGrade(currentUrl)) {\n"
    "            hardBlockJinhakLowerGradeNavigation(\"login-recovery-poll\", currentUrl)\n"
    "            return\n"
    "        }\n"
    "        if (isProviderLoginUrl(ProviderId.JINHAK, currentUrl)) {",
    "login recovery poll hard gate",
)

# A stale lower-grade target is skipped, never retried after protected-core verification.
text = once(
    text,
    "            if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)\n            else loadNextBatchPage()",
    "            if (!retry.isNullOrBlank() && isProviderUrl(retry) && !JinhakGradeRouteFence.isBlockedLowerGrade(retry)) webView.loadUrl(retry)\n"
    "            else loadNextBatchPage()",
    "verified auth retry fence",
)

# A new/unclassified high3 route is allowed to be observed instead of being stopped solely because
# the page taxonomy changed. Known non-core lanes remain excluded.
text = once(
    text,
    '''    private fun isJinhakDefaultCoreQueueUrl(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return true
        val allowed = JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)
        if (!allowed) recordJinhakCoreScopeBlock(url)
        return allowed
    }''',
    '''    private fun isJinhakDefaultCoreQueueUrl(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return true
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
            recordJinhakCoreScopeBlock(url)
            return false
        }
        val lane = JinhakSiteTopology.lane(url)
        val allowed = JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url) ||
            (JinhakGradeRouteFence.isHigh3(url) && lane == JinhakMissionLane.UNKNOWN)
        if (!allowed) recordJinhakCoreScopeBlock(url)
        return allowed
    }''',
    "high3 unknown-page fail-open queue",
)

# Renderer recovery must never reload a forbidden route from browser history/current URL.
text = once(
    text,
    '''                val resumeUrl = currentBatchTarget?.takeIf { it.isNotBlank() }
                    ?: runCatching { deadView.url }.getOrNull()?.takeIf { !it.isNullOrBlank() }
                    ?: when (provider) {
                        ProviderId.JINHAK -> ProviderId.JINHAK.homeUrl
                        ProviderId.ADIGA -> ProviderId.ADIGA.homeUrl
                    }''',
    '''                val rawResumeUrl = currentBatchTarget?.takeIf { it.isNotBlank() }
                    ?: runCatching { deadView.url }.getOrNull()?.takeIf { !it.isNullOrBlank() }
                    ?: when (provider) {
                        ProviderId.JINHAK -> ProviderId.JINHAK.homeUrl
                        ProviderId.ADIGA -> ProviderId.ADIGA.homeUrl
                    }
                val resumeUrl = if (provider == ProviderId.JINHAK && JinhakGradeRouteFence.isBlockedLowerGrade(rawResumeUrl)) {
                    JinhakGradeRouteFence.protectedHigh3Core().ifBlank { ProviderId.JINHAK.homeUrl }
                } else rawResumeUrl''',
    "renderer resume lower-grade sanitation",
)

# Reset and diagnostics for the new hard-route counters.
text = once(
    text,
    "        jinhakV0165ProbeCompletedFromProtectedCore = 0\n        // Restore both domain leases",
    "        jinhakV0165ProbeCompletedFromProtectedCore = 0\n"
    "        jinhakV0166LowerGradeRequestsIntercepted = 0\n"
    "        jinhakV0166LowerGradeNavigationsHardBlocked = 0\n"
    "        jinhakV0166LowerGradeRecoveryDispatches = 0\n"
    "        jinhakV0166LowerGradeRecoveryPending = false\n"
    "        // Restore both domain leases",
    "v0166 reset counters",
)
text = once(
    text,
    '''                    .put("jinhakV0165ProbeCompletedFromProtectedCore", jinhakV0165ProbeCompletedFromProtectedCore)
                        .put("jinhakPostMissionClosureFences", jinhakPostMissionClosureFences)''',
    '''                    .put("jinhakV0165ProbeCompletedFromProtectedCore", jinhakV0165ProbeCompletedFromProtectedCore)
                    .put("jinhakV0166LowerGradeRequestsIntercepted", jinhakV0166LowerGradeRequestsIntercepted)
                    .put("jinhakV0166LowerGradeNavigationsHardBlocked", jinhakV0166LowerGradeNavigationsHardBlocked)
                    .put("jinhakV0166LowerGradeRecoveryDispatches", jinhakV0166LowerGradeRecoveryDispatches)
                    .put("jinhakV0166LowerGradeRecoveryPending", jinhakV0166LowerGradeRecoveryPending)
                        .put("jinhakPostMissionClosureFences", jinhakPostMissionClosureFences)''',
    "v0166 diagnostics counters",
)

text = once(text, '        private const val VERSION = "0.16.5"\n        private const val BUILD_CODE = 116500', '        private const val VERSION = "0.16.6"\n        private const val BUILD_CODE = 116600', "MainActivity version")

# The old compatibility path must no longer advertise lower-grade as a valid hidden auth transition.
for forbidden in [
    '.put("blockedBeforeAuth", false)',
    'jinhak-v0912-hidden-auth-transition',
    'Authentication transitions are handled by the v0.9.12 compatibility path above.',
]:
    if forbidden in text:
        raise SystemExit(f"forbidden legacy lower-grade compatibility token still present: {forbidden}")

main_path.write_text(text)

gradle = gradle_path.read_text()
gradle = once(gradle, "versionCode = 116500", "versionCode = 116600", "Gradle versionCode")
gradle = once(gradle, 'versionName = "0.16.5"', 'versionName = "0.16.6"', "Gradle versionName")
gradle_path.write_text(gradle)

manifest = manifest_path.read_text()
manifest = once(
    manifest,
    'android:label="Admission Hub v0.16.5 Login Handoff + Dashboard Gates"',
    'android:label="Admission Hub v0.16.6 High3 Route Isolation"',
    "manifest label",
)
manifest_path.write_text(manifest)

print("v0.16.6 hard high3 route isolation patch applied")
