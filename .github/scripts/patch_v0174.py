from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
ADAPTER = ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt"
BUILD = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and new in text:
        return text
    raise SystemExit(f"{label}: expected one old token, found {count}")


def replace_member(text: str, name: str, replacement: str) -> str:
    marker = f"    private fun {name}"
    start = text.find(marker)
    if start < 0:
        if replacement.strip() in text:
            return text
        raise SystemExit(f"member missing: {name}")
    search_start = start + len(marker)
    candidates = []
    for token in [
        "\n    private fun ", "\n    private val ", "\n    private var ",
        "\n    private data class ", "\n    private class ", "\n    private object ",
        "\n    override fun ",
    ]:
        idx = text.find(token, search_start)
        if idx >= 0:
            candidates.append(idx)
    end = min(candidates) if candidates else len(text)
    return text[:start] + replacement.rstrip() + "\n" + text[end + (1 if end < len(text) else 0):]


def replace_adapter_member(text: str, name: str, replacement: str) -> str:
    marker = f"    override fun {name}"
    start = text.find(marker)
    if start < 0:
        if replacement.strip() in text:
            return text
        raise SystemExit(f"adapter member missing: {name}")
    search_start = start + len(marker)
    candidates = []
    for token in ["\n    override fun ", "\n    private fun ", "\n    private val ", "\n    private const val "]:
        idx = text.find(token, search_start)
        if idx >= 0:
            candidates.append(idx)
    end = min(candidates) if candidates else len(text)
    return text[:start] + replacement.rstrip() + "\n" + text[end + (1 if end < len(text) else 0):]


# -----------------------------------------------------------------------------
# Metadata
# -----------------------------------------------------------------------------
build = BUILD.read_text()
build = replace_once(build, "versionCode = 117300", "versionCode = 117400", "versionCode")
build = replace_once(build, 'versionName = "0.17.3"', 'versionName = "0.17.4"', "versionName")
BUILD.write_text(build)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Hub v0.17.3 Natural High3 Handoff"',
    'android:label="Admission Hub v0.17.4 Strict High3 Sandbox"',
    "manifest label",
)
MANIFEST.write_text(manifest)

# -----------------------------------------------------------------------------
# Jinhak adapter: automated traversal is high3-only even before WebView transport.
# -----------------------------------------------------------------------------
adapter = ADAPTER.read_text()
if "import com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox" not in adapter:
    adapter = replace_once(
        adapter,
        "import com.admissionhub.collector.jinhak.JinhakReportYearGuard\n",
        "import com.admissionhub.collector.jinhak.JinhakReportYearGuard\nimport com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox\n",
        "adapter strict import",
    )
adapter = replace_adapter_member(adapter, "isBatchNavigable", '''    override fun isBatchNavigable(url: String): Boolean {
        if (!accepts(url) || !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) return false
        return try {
            val uri = URI(url)
            val path = (uri.path ?: "/").lowercase()
            val query = (uri.query ?: "").lowercase()
            val full = "$path?$query"
            if (Regex("(?:logout|signout|member|mypage|my-page|account|profile|userinfo|payment|billing|purchase|order|spassdata|coupon|refund|withdraw|customer|faq|qna|event|notice|privacy|terms)").containsMatchIn(full)) return false
            if (Regex("\\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|map|woff2?|ttf|eot|zip|hwp|hwpx|pdf)$", RegexOption.IGNORE_CASE).containsMatchIn(path)) return false
            true
        } catch (_: Exception) { false }
    }''')
ADAPTER.write_text(adapter)

# -----------------------------------------------------------------------------
# MainActivity strict sandbox.
# -----------------------------------------------------------------------------
text = MAIN.read_text()
text = replace_once(text, 'private const val VERSION = "0.17.3"', 'private const val VERSION = "0.17.4"', "VERSION")
text = replace_once(text, 'private const val BUILD_CODE = 117300', 'private const val BUILD_CODE = 117400', "BUILD_CODE")

# Imports for service-worker request fencing and strict sandbox.
if "import android.os.Build\n" not in text:
    text = replace_once(text, "import android.os.Bundle\n", "import android.os.Bundle\nimport android.os.Build\n", "Build import")
if "import android.webkit.ServiceWorkerClient\n" not in text:
    text = replace_once(
        text,
        "import android.webkit.RenderProcessGoneDetail\n",
        "import android.webkit.RenderProcessGoneDetail\nimport android.webkit.ServiceWorkerClient\nimport android.webkit.ServiceWorkerController\n",
        "service worker imports",
    )
if "import com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox\n" not in text:
    text = replace_once(
        text,
        "import com.admissionhub.collector.jinhak.JinhakUserSessionPolicy\n",
        "import com.admissionhub.collector.jinhak.JinhakUserSessionPolicy\nimport com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox\n",
        "strict sandbox import",
    )

# Defense-in-depth counters.
state_anchor = "    private var jinhakV0173ActualLoginReturns = 0\n"
state_extra = state_anchor + '''    private var jinhakV0174StrictMainFrameBlocks = 0
    private var jinhakV0174LowerGradeAnyRequestBlocks = 0
    private var jinhakV0174ServiceWorkerLowerGradeBlocks = 0
    private var jinhakV0174PopupBlocks = 0
    private var jinhakV0174HistoryBlocks = 0
    private var jinhakV0174AppNavigationBlocks = 0
    private var jinhakV0174RendererResumeBlocks = 0
    private var jinhakV0174PersistedTargetBlocks = 0
    private var jinhakV0174SharedRootBlocks = 0
    private var jinhakV0174GenericLoginBlocks = 0
    private var jinhakV0174OtherJinhakBlocks = 0
    private var jinhakV0174ExternalBlocks = 0
    private var jinhakV0174MemberLoginAllows = 0
    private var jinhakV0174High3Allows = 0
    private var jinhakV0174ExplicitHigh3Confirmations = 0
    private var jinhakV0174StrictEntryRequests = 0
    private var jinhakV0174ForbiddenPageStartsStopped = 0
    private var jinhakV0174ForbiddenPageFinishesObserved = 0
'''
if "jinhakV0174StrictMainFrameBlocks" not in text:
    text = replace_once(text, state_anchor, state_extra, "v0174 counters")

# UI semantics: one button either enters strict high3 or confirms the currently-visible high3 page.
text = text.replace(
    'text = "진학사 로그인 완료 · 탐색 시작/재개"',
    'text = "진학사 고3 전용 진입 / 현재 고3 탐색 시작"'
)

# User back history is also fail-closed for Jinhak.
text = replace_once(
    text,
    "setOnClickListener { if (webView.canGoBack()) webView.goBack() }",
    "setOnClickListener { if (provider == ProviderId.JINHAK) safeJinhakV0174Back() else if (webView.canGoBack()) webView.goBack() }",
    "back button strict history",
)

# Strict helpers are inserted before WebView configuration.
configure_marker = '    @Suppress("SetJavaScriptEnabled")\n    private fun configureWebView() {'
if "private fun loadJinhakV0174High3Only" not in text:
    helpers = r'''    private fun jinhakV0174BlockedResponse(reason: String): WebResourceResponse = WebResourceResponse(
        "text/plain",
        "UTF-8",
        204,
        "No Content",
        mapOf(
            "Cache-Control" to "no-store",
            "X-Admission-Hub-Strict-High3" to reason.take(80)
        ),
        ByteArrayInputStream(ByteArray(0))
    )

    private fun noteJinhakV0174Decision(source: String, target: String, decision: JinhakStrictHigh3Sandbox.MainFrameDecision) {
        if (provider != ProviderId.JINHAK) return
        when (decision) {
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> jinhakV0174High3Allows += 1
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> jinhakV0174MemberLoginAllows += 1
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_SHARED_ROOT -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174SharedRootBlocks += 1 }
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_GENERIC_LOGIN -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174GenericLoginBlocks += 1 }
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_OTHER_JINHAK -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174OtherJinhakBlocks += 1 }
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_EXTERNAL,
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_INVALID -> { jinhakV0174StrictMainFrameBlocks += 1; jinhakV0174ExternalBlocks += 1 }
            JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_LOWER_GRADE -> jinhakV0174StrictMainFrameBlocks += 1
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK -> Unit
        }
        recordRuntimeEvent(
            "jinhak-v0174-route-decision",
            JSONObject()
                .put("source", source.take(80))
                .put("targetSafePath", runtimeSafePath(target))
                .put("decision", JinhakStrictHigh3Sandbox.reason(decision))
                .put("strictHigh3Only", true)
                .put("sharedRootAllowed", false)
                .put("genericLoginAllowed", false)
                .put("lowerGradeAllowed", false)
        )
    }

    private fun blockJinhakV0174MainFrame(source: String, target: String, decision: JinhakStrictHigh3Sandbox.MainFrameDecision) {
        if (provider != ProviderId.JINHAK) return
        noteJinhakV0174Decision(source, target, decision)
        jinhakUserSessionConfirmed = false
        jinhakAuthVerifiedForBatch = false
        if (batchRunning) batchPausedForLogin = true
        currentBatchTarget = currentBatchTarget?.takeIf { JinhakStrictHigh3Sandbox.allowsCollectorNavigation(it) }
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
        if (::slowLaneHost.isInitialized) slowLaneHost.visibility = View.GONE
        if (::jinhakSessionConfirmButton.isInitialized) {
            jinhakSessionConfirmButton.isEnabled = true
            jinhakSessionConfirmButton.text = "진학사 고3 전용 화면 다시 열기"
        }
        if (::sessionState.isInitialized) sessionState.text = "○ 고3 전용 샌드박스가 비허용 경로를 차단함"
        if (::status.isInitialized) status.text = "진학사 고3·정확한 회원 로그인 화면 외의 최상위 이동을 차단했습니다. 버튼을 눌러 고3 전용 진입점만 다시 여세요."
        persistJinhakAuthDiagnostics("v0174-strict-block:$source")
    }

    private fun loadJinhakV0174High3Only(target: String?, reason: String): Boolean {
        if (provider != ProviderId.JINHAK) return false
        val safe = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(target)
        if (safe == null) {
            jinhakV0174AppNavigationBlocks += 1
            val raw = target.orEmpty()
            noteJinhakV0174Decision(reason, raw, JinhakStrictHigh3Sandbox.decision(raw))
            status.text = "앱 내부 진학사 이동이 고3 전용 규칙을 통과하지 못해 실행하지 않았습니다."
            return false
        }
        currentBatchTarget = safe
        recordRuntimeEvent(
            "jinhak-v0174-app-high3-navigation",
            JSONObject().put("reason", reason.take(80)).put("targetSafePath", runtimeSafePath(safe)).put("high3Only", true)
        )
        webView.loadUrl(safe)
        return true
    }

    private fun openJinhakV0174StrictEntry(reason: String) {
        if (provider != ProviderId.JINHAK) provider = ProviderId.JINHAK
        jinhakV0174StrictEntryRequests += 1
        jinhakUserSessionConfirmed = false
        jinhakAuthVerifiedForBatch = false
        batchPausedForLogin = batchRunning
        loadJinhakV0174High3Only(JinhakStrictHigh3Sandbox.strictEntryUrl(), "strict-entry:$reason")
        sessionState.text = "○ 진학사 고3 전용 진입"
        status.text = "고3 전용 주소만 열었습니다. 로그인이 필요하면 진학사 서버가 정확한 회원 로그인 화면을 표시할 수 있으며, 공통 루트·고1·고2·고12·공용 로그인 라우터는 차단됩니다."
    }

    private fun safeJinhakV0174Back() {
        if (!webView.canGoBack()) return
        val list = webView.copyBackForwardList()
        val index = list.currentIndex - 1
        if (index < 0) return
        val target = list.getItemAtIndex(index)?.url.orEmpty()
        val decision = JinhakStrictHigh3Sandbox.decision(target)
        if (decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 ||
            decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN ||
            decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK) {
            webView.goBack()
        } else {
            jinhakV0174HistoryBlocks += 1
            noteJinhakV0174Decision("history-back", target, decision)
            Toast.makeText(this, "고3 전용 샌드박스 밖의 이전 페이지라 뒤로가기를 차단했습니다.", Toast.LENGTH_SHORT).show()
        }
    }

    private fun installJinhakV0174ServiceWorkerFence() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return
        runCatching {
            ServiceWorkerController.getInstance().setServiceWorkerClient(object : ServiceWorkerClient() {
                override fun shouldInterceptRequest(request: WebResourceRequest): WebResourceResponse? {
                    val target = request.url?.toString().orEmpty()
                    if (provider == ProviderId.JINHAK && JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {
                        handler.post {
                            jinhakV0174ServiceWorkerLowerGradeBlocks += 1
                            jinhakV0174LowerGradeAnyRequestBlocks += 1
                            noteJinhakV0174Decision("service-worker", target, JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_LOWER_GRADE)
                        }
                        return jinhakV0174BlockedResponse("lower-grade-service-worker")
                    }
                    return null
                }
            })
        }
    }

'''
    text = replace_once(text, configure_marker, helpers + configure_marker, "insert strict helpers")

# Install service-worker fence each time the WebView is configured/replaced.
configure_start = '''        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        webView.settings.apply {
'''
configure_new = '''        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }
        installJinhakV0174ServiceWorkerFence()

        webView.settings.apply {
'''
text = replace_once(text, configure_start, configure_new, "install service worker fence")

# Main-frame and all-request transport fencing.
old_intercept = '''            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val target = request.url?.toString().orEmpty()
                if (provider == ProviderId.JINHAK && request.isForMainFrame) {
                    when (JinhakHigh3AuthRoute.decision(target)) {
                        JinhakHigh3AuthRoute.MainFrameDecision.BLOCK_LOWER_GRADE -> {
                            handler.post {
                                if (provider == ProviderId.JINHAK) {
                                    jinhakV0166LowerGradeRequestsIntercepted += 1
                                    hardBlockJinhakLowerGradeNavigation("network-intercept", target)
                                }
                            }
                            return blockedJinhakLowerGradeResponse()
                        }
                        JinhakHigh3AuthRoute.MainFrameDecision.REWRITE_GENERIC_LOGIN -> {
                            handler.post {
                                if (provider == ProviderId.JINHAK) {
                                    jinhakV0167GenericLoginRewrites += 1
                                    openJinhakDirectHigh3Auth("generic-login-network-rewrite", currentBatchTarget)
                                }
                            }
                            return blockedJinhakLowerGradeResponse()
                        }
                        else -> Unit
                    }
                }
                return super.shouldInterceptRequest(view, request)
            }
'''
new_intercept = '''            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val target = request.url?.toString().orEmpty()
                if (provider == ProviderId.JINHAK) {
                    if (JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {
                        handler.post {
                            if (provider == ProviderId.JINHAK) {
                                jinhakV0166LowerGradeRequestsIntercepted += 1
                                jinhakV0174LowerGradeAnyRequestBlocks += 1
                                hardBlockJinhakLowerGradeNavigation("v0174-any-request-intercept", target)
                            }
                        }
                        return jinhakV0174BlockedResponse("lower-grade-any-request")
                    }
                    if (request.isForMainFrame) {
                        val decision = JinhakStrictHigh3Sandbox.decision(target)
                        when (decision) {
                            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3,
                            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN,
                            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK -> {
                                handler.post { noteJinhakV0174Decision("network-main-allow", target, decision) }
                            }
                            else -> {
                                handler.post { blockJinhakV0174MainFrame("network-main-block", target, decision) }
                                return jinhakV0174BlockedResponse(JinhakStrictHigh3Sandbox.reason(decision))
                            }
                        }
                    }
                }
                return super.shouldInterceptRequest(view, request)
            }
'''
text = replace_once(text, old_intercept, new_intercept, "strict shouldInterceptRequest")

old_override = '''            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (target.isNotBlank() && provider == ProviderId.JINHAK) {
                    when (JinhakHigh3AuthRoute.decision(target)) {
                        JinhakHigh3AuthRoute.MainFrameDecision.BLOCK_LOWER_GRADE -> {
                            hardBlockJinhakLowerGradeNavigation("navigation-override", target)
                            return true
                        }
                        JinhakHigh3AuthRoute.MainFrameDecision.REWRITE_GENERIC_LOGIN -> {
                            jinhakV0167GenericLoginRewrites += 1
                            openJinhakDirectHigh3Auth("generic-login-navigation-rewrite", currentBatchTarget)
                            return true
                        }
                        else -> Unit
                    }
                }
                if (batchRunning && provider == ProviderId.JINHAK && target.isNotBlank() && !ProviderRegistry.adapter(ProviderId.JINHAK).accepts(target)) {
                    jinhakExternalNavigationsBlocked += 1
                    recordRuntimeEvent("jinhak-external-navigation-blocked", JSONObject()
                        .put("targetSafePath", runtimeSafePath(target))
                        .put("currentTargetSafePath", runtimeSafePath(currentBatchTarget)))
                    return true
                }
                return false
            }
'''
new_override = '''            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (provider != ProviderId.JINHAK || target.isBlank()) return false
                if (JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {
                    jinhakV0174LowerGradeAnyRequestBlocks += 1
                    hardBlockJinhakLowerGradeNavigation("v0174-navigation-override", target)
                    return true
                }
                if (!request.isForMainFrame) return false
                val decision = JinhakStrictHigh3Sandbox.decision(target)
                return when (decision) {
                    JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3,
                    JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN,
                    JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK -> {
                        noteJinhakV0174Decision("navigation-main-allow", target, decision)
                        false
                    }
                    else -> {
                        blockJinhakV0174MainFrame("navigation-main-block", target, decision)
                        true
                    }
                }
            }
'''
text = replace_once(text, old_override, new_override, "strict shouldOverrideUrlLoading")

# Page-start fence catches history/POST/JS/server cases even if override/intercept was bypassed.
old_started = '''                if (provider == ProviderId.JINHAK) {
                    when (JinhakHigh3AuthRoute.decision(url)) {
                        JinhakHigh3AuthRoute.MainFrameDecision.BLOCK_LOWER_GRADE -> {
                            runCatching { view.stopLoading() }
                            hardBlockJinhakLowerGradeNavigation("page-started-invariant-breach", url)
                            return
                        }
                        JinhakHigh3AuthRoute.MainFrameDecision.REWRITE_GENERIC_LOGIN -> {
                            runCatching { view.stopLoading() }
                            jinhakV0167GenericLoginRewrites += 1
                            openJinhakDirectHigh3Auth("generic-login-page-start-rewrite", currentBatchTarget)
                            return
                        }
                        JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_CANONICAL_AUTH -> {
                            markJinhakDirectAuthWait("member-login-page-started", url)
                        }
                        else -> Unit
                    }
                }
'''
new_started = '''                if (provider == ProviderId.JINHAK) {
                    val decision = JinhakStrictHigh3Sandbox.decision(url)
                    when (decision) {
                        JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> {
                            noteJinhakV0174Decision("page-started-high3", url, decision)
                        }
                        JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> {
                            noteJinhakV0174Decision("page-started-member-login", url, decision)
                            enterJinhakUserSessionGate("v0174-member-login-page-started")
                        }
                        JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK -> Unit
                        else -> {
                            jinhakV0174ForbiddenPageStartsStopped += 1
                            runCatching { view.stopLoading() }
                            blockJinhakV0174MainFrame("page-started-strict-stop", url, decision)
                            return
                        }
                    }
                }
'''
text = replace_once(text, old_started, new_started, "strict onPageStarted")

# Page-finished no longer invokes legacy auth compatibility or natural auto-resume.
old_finished_prefix = '''                CookieManager.getInstance().flush()
                if (provider == ProviderId.JINHAK && handleJinhakV0912AuthCompatibilityPage(url)) {
                    return
                }
                if (provider == ProviderId.JINHAK && verifyRecoveredJinhakHigh3AndResume(url)) {
                    return
                }
                if (provider == ProviderId.JINHAK) {
                    when {
                        JinhakHigh3AuthRoute.isMemberLoginSurface(url) -> {
                            markJinhakDirectAuthWait("member-login-page-finished", url)
                            scheduleLoginSurfaceDetection(ProviderId.JINHAK, "member-login-one-shot")
                            return
                        }
                        JinhakHigh3AuthRoute.isGenericProductLogin(url) -> {
                            jinhakV0167GenericLoginRewrites += 1
                            openJinhakDirectHigh3Auth("generic-login-page-finished-rewrite", currentBatchTarget)
                            return
                        }
                        JinhakGradeRouteFence.isBlockedLowerGrade(url) -> {
                            hardBlockJinhakLowerGradeNavigation("page-finished-invariant-breach", url)
                            return
                        }
                    }
                } else {
                    scheduleLoginSurfaceDetection(provider, "page-finished")
                }
'''
new_finished_prefix = '''                CookieManager.getInstance().flush()
                if (provider == ProviderId.JINHAK) {
                    val visible = webView.url.orEmpty()
                    if (JinhakUserSessionPolicy.shouldIgnoreStaleLoginCallback(url, visible)) {
                        jinhakV0173StaleLoginCallbacksIgnored += 1
                        recordRuntimeEvent("jinhak-v0174-stale-member-login-callback-ignored", JSONObject()
                            .put("callbackSafePath", runtimeSafePath(url))
                            .put("currentSafePath", runtimeSafePath(visible)))
                    } else {
                        val decision = JinhakStrictHigh3Sandbox.decision(url)
                        when (decision) {
                            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> {
                                enterJinhakUserSessionGate("v0174-member-login-page-finished")
                                return
                            }
                            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> {
                                noteJinhakV0174Decision("page-finished-high3", url, decision)
                                if (!jinhakUserSessionConfirmed) {
                                    batchPausedForLogin = batchRunning
                                    if (::batchCover.isInitialized) batchCover.visibility = View.GONE
                                    jinhakSessionConfirmButton.text = "현재 고3 화면에서 탐색 시작/재개"
                                    sessionState.text = "● 고3 화면 확인 · 사용자 탐색 시작 승인 대기"
                                    status.text = "고3 화면에 도착했습니다. 자동 재개하지 않습니다. 현재 고3 화면을 직접 확인한 뒤 버튼을 눌러야 탐색을 시작합니다."
                                    return
                                }
                            }
                            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK -> return
                            else -> {
                                jinhakV0174ForbiddenPageFinishesObserved += 1
                                blockJinhakV0174MainFrame("page-finished-strict-block", url, decision)
                                return
                            }
                        }
                    }
                } else {
                    scheduleLoginSurfaceDetection(provider, "page-finished")
                }
'''
text = replace_once(text, old_finished_prefix, new_finished_prefix, "strict onPageFinished prefix")

# Paused Jinhak never polls/reloads; explicit high3 confirmation is required.
old_paused = '''                if (batchPausedForLogin) {
                    if (provider == ProviderId.JINHAK) {
                        scheduleJinhakLoginRecovery("batch-paused-page-finished")
                    } else {
                        checkSessionState { needsLogin, authenticated ->
                            if (!needsLogin && authenticated) {
                                sessionState.text = "● 로그인 상태 복구 감지"
                                resumeAfterLogin()
                            }
                        }
                    }
                } else {
'''
new_paused = '''                if (batchPausedForLogin) {
                    if (provider == ProviderId.JINHAK) {
                        sessionState.text = "○ 진학사 수집 일시정지 · 현재 고3 화면 사용자 승인 대기"
                        persistJinhakAuthDiagnostics("v0174-paused-no-auto-recovery")
                    } else {
                        checkSessionState { needsLogin, authenticated ->
                            if (!needsLogin && authenticated) {
                                sessionState.text = "● 로그인 상태 복구 감지"
                                resumeAfterLogin()
                            }
                        }
                    }
                } else {
'''
text = replace_once(text, old_paused, new_paused, "disable Jinhak paused auto recovery")

# Exact explicit confirmation semantics. Login/shared/other pages can never become confirmed.
text = replace_member(text, "confirmJinhakUserSessionAndResume", '''    private fun confirmJinhakUserSessionAndResume(reason: String) {
        if (provider != ProviderId.JINHAK) {
            Toast.makeText(this, "진학사 화면에서만 사용할 수 있습니다.", Toast.LENGTH_SHORT).show()
            return
        }
        val current = webView.url.orEmpty()
        when (JinhakStrictHigh3Sandbox.decision(current)) {
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> {
                jinhakUserSessionConfirmed = false
                jinhakAuthVerifiedForBatch = false
                batchPausedForLogin = batchRunning
                jinhakSessionConfirmButton.text = "로그인 완료 후 고3 화면에서 다시 누르기"
                sessionState.text = "○ 진학사 회원 로그인은 사용자 관리"
                status.text = "현재는 정확한 진학사 회원 로그인 화면입니다. 로그인 절차를 완료하세요. 앱은 로그인 성공을 판정하거나 다음 주소를 자동으로 열지 않습니다."
                return
            }
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> {
                jinhakUserSessionConfirmed = true
                jinhakUserSessionConfirmations += 1
                jinhakAuthVerifiedForBatch = true // compatibility flag == explicit user approval on visible high3 only
                jinhakV0174ExplicitHigh3Confirmations += 1
                jinhakV0173ResumeArmed = false
                batchPausedForLogin = false
                jinhakTransitionAuthGateActive = false
                currentBatchTarget = canonicalizeBatchUrl(current)
                jinhakCoreBootstrapState = "v0174-explicit-visible-high3-confirmed"
                jinhakLastAuthEvidence = "user-explicitly-approved-current-visible-high3"
                jinhakSessionConfirmButton.text = "고3 탐색 승인됨 · 필요 시 다시 확인"
                sessionState.text = "● 현재 고3 화면 사용자 승인 완료"
                status.text = "현재 보이는 고3 화면에서만 탐색 권한을 열었습니다. 공통 루트·공용 로그인·고1·고2·고12·기타 제품 경로는 계속 차단됩니다."
                recordRuntimeEvent("jinhak-v0174-explicit-high3-confirmed", JSONObject()
                    .put("reason", reason.take(80))
                    .put("safePath", runtimeSafePath(current))
                    .put("collectorVerifiedLogin", false)
                    .put("autoResume", false)
                    .put("strictHigh3Only", true))
                persistJinhakAuthDiagnostics("v0174-explicit-high3-confirmed:$reason")
                when {
                    startupLoginPreflightActive -> {
                        startupLoginJinhakAuthenticated = true
                        startupLoginPreflightActive = false
                        startupLoginPreflightVerified = true
                        startupLoginVerifiedAtMs = System.currentTimeMillis()
                        startupLoginStage = "jinhak-user-explicit-high3"
                        startupLoginPollGeneration += 1
                        handler.postDelayed({ if (!unifiedRunning && !batchRunning && jinhakUserSessionConfirmed) startUnifiedCollectionAuthenticated() }, 120L)
                    }
                    unifiedRunning && unifiedPhase == "jinhak" && !batchRunning -> {
                        unifiedPendingJinhakStart = false
                        handler.postDelayed({ if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning && jinhakUserSessionConfirmed) startBatch() }, 120L)
                    }
                    batchRunning -> {
                        handler.postDelayed({
                            if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK && jinhakUserSessionConfirmed) {
                                currentBatchTarget = canonicalizeBatchUrl(webView.url.orEmpty())
                                scheduleBatchSnapshot()
                            }
                        }, 120L)
                    }
                    else -> startBatch()
                }
            }
            else -> {
                jinhakUserSessionConfirmed = false
                jinhakAuthVerifiedForBatch = false
                openJinhakV0174StrictEntry("user-button:$reason")
            }
        }
    }''')

# Auto handoff is impossible in v0.17.4; only explicit high3 button approval activates collection.
text = replace_member(text, "scheduleJinhakV0173StableHigh3Handoff", '''    private fun scheduleJinhakV0173StableHigh3Handoff(rawUrl: String, reason: String) {
        if (provider == ProviderId.JINHAK) {
            persistJinhakAuthDiagnostics("v0174-auto-high3-handoff-disabled:$reason")
        }
    }''')
text = replace_member(text, "activateJinhakV0173StableHigh3", '''    private fun activateJinhakV0173StableHigh3(reason: String, rawUrl: String) {
        if (provider == ProviderId.JINHAK) {
            persistJinhakAuthDiagnostics("v0174-auto-high3-activation-disabled:$reason")
        }
    }''')

# Legacy auth compatibility entry points cannot navigate/resume Jinhak anymore.
text = replace_member(text, "openJinhakDirectHigh3Auth", '''    private fun openJinhakDirectHigh3Auth(reason: String, requestedTarget: String?) {
        if (provider != ProviderId.JINHAK) return
        val target = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(requestedTarget ?: currentBatchTarget)
        if (target == null) {
            jinhakV0174AppNavigationBlocks += 1
            persistJinhakAuthDiagnostics("v0174-legacy-auth-navigation-blocked:$reason")
            return
        }
        if (!jinhakUserSessionConfirmed) {
            persistJinhakAuthDiagnostics("v0174-legacy-auth-navigation-awaits-user:$reason")
            return
        }
        loadJinhakV0174High3Only(target, "legacy-high3-only:$reason")
    }''')
text = replace_member(text, "handleJinhakV0912AuthCompatibilityPage", '''    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {
        // v0.17.4 WebView transport policy is authoritative. Legacy compatibility routing is disabled.
        return false
    }''')
text = replace_member(text, "verifyRecoveredJinhakHigh3AndResume", '''    private fun verifyRecoveredJinhakHigh3AndResume(url: String): Boolean {
        // v0.17.4 never auto-resumes from a route observation. User must approve the visible high3 page.
        return false
    }''')
text = replace_member(text, "scheduleJinhakLoginRecovery", '''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        persistJinhakAuthDiagnostics("v0174-auto-login-recovery-disabled:$reason")
    }''')
text = replace_member(text, "completeJinhakVerifiedAuth", '''    private fun completeJinhakVerifiedAuth(reason: String) {
        if (provider != ProviderId.JINHAK) return
        persistJinhakAuthDiagnostics("v0174-legacy-verified-auth-disabled:$reason")
    }''')
text = replace_member(text, "resumeBatchAfterVerifiedJinhakAuth", '''    private fun resumeBatchAfterVerifiedJinhakAuth(reason: String) {
        if (provider != ProviderId.JINHAK) return
        persistJinhakAuthDiagnostics("v0174-legacy-auth-resume-disabled:$reason")
    }''')
text = replace_member(text, "handleJinhakTransitionAuthGate", '''    private fun handleJinhakTransitionAuthGate(url: String) {
        if (provider != ProviderId.JINHAK) return
        when (JinhakStrictHigh3Sandbox.decision(url)) {
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> enterJinhakUserSessionGate("v0174-transition-member-login")
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> {
                jinhakTransitionAuthGateActive = false
                jinhakSessionConfirmButton.text = "현재 고3 화면에서 탐색 시작/재개"
                sessionState.text = "● 고3 화면 확인 · 사용자 승인 대기"
                status.text = "고3 화면이 보이지만 자동 탐색은 시작하지 않습니다. 현재 화면을 확인한 뒤 버튼을 누르세요."
            }
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK -> Unit
            else -> blockJinhakV0174MainFrame("transition-strict-block", url, JinhakStrictHigh3Sandbox.decision(url))
        }
    }''')

# Rendered login guard no longer probes the Jinhak DOM. URL sandbox + explicit approval is enough.
text = replace_member(text, "continueBatchAfterRenderedLoginGuard", '''    private fun continueBatchAfterRenderedLoginGuard(url: String, attempt: Int) {
        if (!batchRunning || batchPausedForLogin) return
        if (provider == ProviderId.JINHAK) {
            val current = webView.url.orEmpty()
            when (JinhakStrictHigh3Sandbox.decision(current)) {
                JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> {
                    if (!jinhakUserSessionConfirmed) {
                        batchPausedForLogin = true
                        hideBatchCover()
                        jinhakSessionConfirmButton.text = "현재 고3 화면에서 탐색 시작/재개"
                        sessionState.text = "● 고3 화면 확인 · 사용자 승인 대기"
                    } else {
                        scheduleBatchSnapshot()
                    }
                }
                JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> enterJinhakUserSessionGate("v0174-batch-member-login")
                JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK -> {
                    batchPausedForLogin = true
                    hideBatchCover()
                }
                else -> blockJinhakV0174MainFrame("v0174-batch-rendered-guard", current, JinhakStrictHigh3Sandbox.decision(current))
            }
            return
        }
        val expectedProvider = provider
        probeLoginSurface(expectedProvider) { probe ->
            if (!batchRunning || batchPausedForLogin || provider != expectedProvider) return@probeLoginSurface
            if (probe.optBoolean("detected", false)) {
                pauseBatchForRenderedLoginSurface(expectedProvider, "rendered-login:$attempt")
            } else {
                scheduleBatchSnapshot()
            }
        }
    }''')

# Jinhak batch may start only from an explicitly approved visible strict-high3 page.
start_guard = '''        if (provider == ProviderId.JINHAK) {
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "v0172-user-confirmed-login-assumed"
            jinhakLastAuthEvidence = "user-confirmed-login-assumed-no-app-verification"
            jinhakLastCoreVerifiedAtMs = 0L
        }
'''
start_guard_new = '''        if (provider == ProviderId.JINHAK) {
            val visibleHigh3 = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)
            if (!jinhakUserSessionConfirmed || visibleHigh3 == null) {
                jinhakV0174PersistedTargetBlocks += 1
                enterJinhakUserSessionGate("v0174-start-batch-requires-visible-high3")
                return
            }
            currentBatchTarget = canonicalizeBatchUrl(visibleHigh3)
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "v0174-explicit-visible-high3-confirmed"
            jinhakLastAuthEvidence = "user-explicitly-approved-current-visible-high3"
            jinhakLastCoreVerifiedAtMs = 0L
        }
'''
text = replace_once(text, start_guard, start_guard_new, "startBatch visible high3 guard")

# Persisted/current target after reset must also be strict high3.
assign_anchor = '''        currentBatchTarget = if (provider == ProviderId.JINHAK && preserveJinhakMissionState && !currentBatchTarget.isNullOrBlank()) {
            currentBatchTarget
        } else if (provider == ProviderId.JINHAK) {
            val visible = webView.url.orEmpty().takeIf { JinhakGradeRouteFence.isHigh3(it) && !JinhakUserSessionPolicy.isLoginSurface(it) }
            canonicalizeBatchUrl(visible ?: url)
        } else canonicalizeBatchUrl(url)
'''
assign_new = '''        currentBatchTarget = if (provider == ProviderId.JINHAK && preserveJinhakMissionState && !currentBatchTarget.isNullOrBlank()) {
            currentBatchTarget
        } else if (provider == ProviderId.JINHAK) {
            JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)?.let(::canonicalizeBatchUrl)
        } else canonicalizeBatchUrl(url)
        if (provider == ProviderId.JINHAK) {
            val strict = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget)
                ?: JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)
            if (strict == null) {
                jinhakV0174PersistedTargetBlocks += 1
                batchRunning = false
                hideBatchCover()
                enterJinhakUserSessionGate("v0174-invalid-persisted-or-visible-target")
                return
            }
            currentBatchTarget = canonicalizeBatchUrl(strict)
        }
'''
text = replace_once(text, assign_anchor, assign_new, "strict currentBatchTarget after reset")

# beginBatchNavigation never loads a non-high3 Jinhak target.
text = replace_member(text, "beginBatchNavigation", '''    private fun beginBatchNavigation(runId: String?) {
        if (provider == ProviderId.JINHAK) {
            armJinhakProgressFence()
            armJinhakHardCellLeaseWatchdog()
        }
        enqueueProviderSeeds()
        cloudOffload.probeFrontier { available ->
            runOnUiThread {
                if (available) status.text = "Cloud frontier 연결됨: 링크 계획·중복제거·재시도를 클라우드와 동기화합니다."
            }
        }
        if (runId != null && batchPageActions.isEmpty()) {
            status.text = "Cloud 체크포인트 연결: ${runId.take(8)}… / 기본 정보영역 ${batchQueue.size}개 탐색"
        } else if (runId == null) {
            status.text = "로컬 안전모드: 기본 정보영역 ${batchQueue.size}개 탐색"
        }
        if (provider == ProviderId.JINHAK) {
            val visible = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)
            val target = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget)
            if (!jinhakUserSessionConfirmed || visible == null) {
                batchPausedForLogin = true
                hideBatchCover()
                enterJinhakUserSessionGate("v0174-begin-navigation-visible-high3-required")
                return
            }
            currentBatchTarget = canonicalizeBatchUrl(visible)
            if (target == null || canonicalizeBatchUrl(target) == canonicalizeBatchUrl(visible)) {
                scheduleBatchSnapshot()
            } else {
                loadJinhakV0174High3Only(target, "begin-batch-navigation")
            }
            return
        }
        checkSessionState { needsLogin, _ ->
            if (needsLogin) {
                pauseBatchForLogin()
            } else if (batchPageActions.isNotEmpty()) {
                loadNextBatchPage()
            } else {
                val startUrl = currentBatchTarget
                if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)
                else loadNextBatchPage()
            }
        }
    }''')

# Queue/filter layer: no root/member/other-product target can enter Jinhak crawl.
old_seed_filter = '''            if (url.isBlank() || !isProviderUrl(url) || batchVisited.contains(url) || batchQueued.contains(url)) continue
            if (provider == ProviderId.JINHAK && !isJinhakDefaultCoreQueueUrl(url)) continue
'''
new_seed_filter = '''            if (url.isBlank() || !isProviderUrl(url) || batchVisited.contains(url) || batchQueued.contains(url)) continue
            if (provider == ProviderId.JINHAK && !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) continue
            if (provider == ProviderId.JINHAK && !isJinhakDefaultCoreQueueUrl(url)) continue
'''
text = replace_once(text, old_seed_filter, new_seed_filter, "seed strict filter")

old_core_start = '''    private fun isJinhakDefaultCoreQueueUrl(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return true
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
'''
new_core_start = '''    private fun isJinhakDefaultCoreQueueUrl(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return true
        if (!JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) {
            recordJinhakCoreScopeBlock(url)
            return false
        }
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
'''
text = replace_once(text, old_core_start, new_core_start, "default core strict high3")

old_enqueue_discovered = '''    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) return
'''
new_enqueue_discovered = '''    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (provider == ProviderId.JINHAK && !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) return
        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) return
'''
text = replace_once(text, old_enqueue_discovered, new_enqueue_discovered, "discovered strict high3")

# Cloud frontier handoff also requires strict high3.
old_frontier_filter = '''                        if (url.isBlank() || taskId.isBlank() || !isBatchNavigableProviderUrl(url)) continue
                        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) {
'''
new_frontier_filter = '''                        if (url.isBlank() || taskId.isBlank() || !isBatchNavigableProviderUrl(url)) continue
                        if (provider == ProviderId.JINHAK && !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) continue
                        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) {
'''
text = replace_once(text, old_frontier_filter, new_frontier_filter, "cloud frontier strict filter")

# Every queue-origin app load uses the strict helper when Jinhak is active.
text = text.replace(
    '''                    } else {
                        webView.loadUrl(canonicalOrigin)
                    }
''',
    '''                    } else {
                        if (provider == ProviderId.JINHAK) loadJinhakV0174High3Only(canonicalOrigin, "ledger-origin")
                        else webView.loadUrl(canonicalOrigin)
                    }
'''
)
text = text.replace(
    '''            if (current == action.baseUrl) {
                executePendingBatchPageAction()
            } else {
                webView.loadUrl(action.baseUrl)
            }
''',
    '''            if (current == action.baseUrl) {
                executePendingBatchPageAction()
            } else if (provider == ProviderId.JINHAK) {
                if (!loadJinhakV0174High3Only(action.baseUrl, "batch-page-action")) {
                    pendingBatchPageAction = null
                    jinhakV0174PersistedTargetBlocks += 1
                    handler.postDelayed({ loadNextBatchPage() }, 80L)
                }
            } else {
                webView.loadUrl(action.baseUrl)
            }
'''
)
text = text.replace(
    '''            status.text = "다음 입시정보 페이지 탐색: ${safeDisplayUrl(next)}"
            webView.loadUrl(next)
            return
''',
    '''            status.text = "다음 입시정보 페이지 탐색: ${safeDisplayUrl(next)}"
            if (provider == ProviderId.JINHAK) {
                if (!loadJinhakV0174High3Only(next, "batch-queue")) {
                    jinhakV0174PersistedTargetBlocks += 1
                    continue
                }
            } else {
                webView.loadUrl(next)
            }
            return
'''
)

# Mission return cannot use history or an unvalidated origin.
text = replace_member(text, "maybeReturnToJinhakMissionOrigin", '''    private fun maybeReturnToJinhakMissionOrigin(snapshot: JSONObject): Boolean {
        val mission = jinhakMissionContext ?: return false
        if (!jinhakMissionNeedsReturn || mission.identityKey == null || jinhakMissionOriginRoute.isBlank()) return false
        val origin = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(jinhakMissionOriginRoute)
        if (origin == null) {
            jinhakV0174PersistedTargetBlocks += 1
            jinhakMissionNeedsReturn = false
            jinhakActiveMissionTargetId = null
            recordRuntimeEvent("jinhak-v0174-invalid-mission-origin-blocked", JSONObject()
                .put("applicationIdentityHash", mission.identityKey.take(24))
                .put("originSafePath", runtimeSafePath(jinhakMissionOriginRoute)))
            handler.postDelayed({ loadNextBatchPage() }, 80L)
            return true
        }
        val current = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        jinhakApplicationMissionReturns += 1
        handler.post { maybeSealJinhakCoreCoverage("mission-return") }
        recordRuntimeEvent("jinhak-application-mission-return", JSONObject()
            .put("applicationIdentityHash", mission.identityKey.take(24))
            .put("fromSafePath", runtimeSafePath(current))
            .put("toSafePath", runtimeSafePath(origin))
            .put("coverageLanes", jinhakMissionCoverage[mission.identityKey]?.size ?: 0))
        val returningTargetId = jinhakActiveMissionTargetId
        if (returningTargetId != null && jinhakMissionTargetLedger.stateOf(returningTargetId) == JinhakMissionTargetLedger.State.CLICKED) {
            jinhakMissionTargetLedger.markFailed(returningTargetId, "report-unconfirmed")
        }
        jinhakActiveMissionTargetId = null
        jinhakReportBridgeContext = null
        jinhakMissionNeedsReturn = false
        currentBatchTarget = origin
        status.text = "지원안 리포트 탐색 종료: 고3 수시저장소 origin으로만 복귀합니다."
        handler.postDelayed({
            if (batchRunning && !batchPausedForLogin) loadJinhakV0174High3Only(origin, "mission-origin-return")
        }, 180L)
        return true
    }''')

# Popup/new-window handoff is high3/member-login only; root/other/external is destroyed.
old_popup_handoff = '''                    private fun handoff(target: String): Boolean {
                        if (target.isBlank() || target == "about:blank") return false
                        if (provider == ProviderId.JINHAK && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                            jinhakLowerGradeNavigationsBlocked += 1
                            recordRuntimeEvent("jinhak-popup-lower-grade-navigation-blocked", JSONObject()
                                .put("targetSafePath", runtimeSafePath(target)))
                            handler.post { destroyTransientPopup("lower-grade-blocked") }
                            return true
                        }
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
'''
new_popup_handoff = '''                    private fun handoff(target: String): Boolean {
                        if (target.isBlank() || target == "about:blank") return false
                        if (provider == ProviderId.JINHAK) {
                            val decision = JinhakStrictHigh3Sandbox.decision(target)
                            when (decision) {
                                JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> loadJinhakV0174High3Only(target, "popup-handoff")
                                JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> webView.loadUrl(target)
                                else -> {
                                    jinhakV0174PopupBlocks += 1
                                    noteJinhakV0174Decision("popup-block", target, decision)
                                }
                            }
                            handler.post { destroyTransientPopup("v0174-strict-popup") }
                            return true
                        }
                        webView.loadUrl(target)
                        handler.post { destroyTransientPopup("main-handoff") }
                        return true
                    }
'''
text = replace_once(text, old_popup_handoff, new_popup_handoff, "strict popup handoff")

# Renderer recovery can never fall back to root/member/other product state.
old_resume = '''                val rawResumeUrl = currentBatchTarget?.takeIf { it.isNotBlank() }
                    ?: runCatching { deadView.url }.getOrNull()?.takeIf { !it.isNullOrBlank() }
                    ?: when (provider) {
                        ProviderId.JINHAK -> ProviderId.JINHAK.homeUrl
                        ProviderId.ADIGA -> ProviderId.ADIGA.homeUrl
                    }
                val resumeUrl = if (provider == ProviderId.JINHAK && JinhakGradeRouteFence.isBlockedLowerGrade(rawResumeUrl)) {
                    JinhakGradeRouteFence.protectedHigh3Core().ifBlank { ProviderId.JINHAK.homeUrl }
                } else rawResumeUrl
'''
new_resume = '''                val rawResumeUrl = currentBatchTarget?.takeIf { it.isNotBlank() }
                    ?: runCatching { deadView.url }.getOrNull()?.takeIf { !it.isNullOrBlank() }
                    ?: when (provider) {
                        ProviderId.JINHAK -> JinhakStrictHigh3Sandbox.strictEntryUrl()
                        ProviderId.ADIGA -> ProviderId.ADIGA.homeUrl
                    }
                val resumeUrl = if (provider == ProviderId.JINHAK) {
                    JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(rawResumeUrl) ?: "about:blank"
                } else rawResumeUrl
                if (provider == ProviderId.JINHAK && resumeUrl == "about:blank") jinhakV0174RendererResumeBlocks += 1
'''
text = replace_once(text, old_resume, new_resume, "renderer strict resume base")

# Both renderer safeResume fallbacks must filter mission origins.
text = text.replace(
    '''                                val missionOrigin = jinhakMissionOriginRoute.takeIf { it.isNotBlank() }
                                val safeResume = missionOrigin
                                    ?: JinhakSiteTopology.protectedCoreProbeUrl().takeIf { it.isNotBlank() }
                                    ?: resumeUrl
''',
    '''                                val missionOrigin = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(jinhakMissionOriginRoute)
                                val safeResume = missionOrigin ?: JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(resumeUrl) ?: "about:blank"
'''
)

# Any actual Jinhak renderer resume load is strict-high3 only; blank means user must re-enter.
text = text.replace(
    '''                                    replacement.loadUrl(safeResume)
                                }, JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS)
''',
    '''                                    if (safeResume == "about:blank") {
                                        jinhakV0174RendererResumeBlocks += 1
                                        replacement.loadUrl("about:blank")
                                        enterJinhakUserSessionGate("v0174-renderer-resume-needs-user")
                                    } else {
                                        replacement.loadUrl(safeResume)
                                    }
                                }, JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS)
'''
)
text = text.replace(
    '''                            replacement.loadUrl(safeResume)
                        }, JINHAK_RENDERER_CIRCUIT_COOLDOWN_MS)
''',
    '''                            if (safeResume == "about:blank") {
                                jinhakV0174RendererResumeBlocks += 1
                                replacement.loadUrl("about:blank")
                                enterJinhakUserSessionGate("v0174-renderer-circuit-needs-user")
                            } else {
                                replacement.loadUrl(safeResume)
                            }
                        }, JINHAK_RENDERER_CIRCUIT_COOLDOWN_MS)
'''
)

# openProvider Jinhak entry is high3-only by fail-safe ProviderId.homeUrl, and generic root is never used.
# Real-auth diagnostic button is converted to a strict-entry helper rather than an auth probe.
text = replace_member(text, "startJinhakRealAuthProbe", '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        if (batchRunning) {
            Toast.makeText(this, "진행 중인 진학사 수집이 있습니다. 현재 화면에서 세션을 관리하세요.", Toast.LENGTH_LONG).show()
            return
        }
        provider = ProviderId.JINHAK
        jinhakRealAuthProbeActive = false
        jinhakRealAuthProbeAutoContinue = false
        jinhakRealAuthProbeResult = "disabled-strict-high3-sandbox-v0174"
        enterJinhakUserSessionGate("v0174-manual-strict-entry:$trigger")
        openJinhakV0174StrictEntry("manual-button:$trigger")
        status.text = "진학사 인증 진단 대신 고3 전용 진입점만 엽니다. 로그인 후 고3 화면을 직접 확인하고 탐색 시작 버튼을 누르세요."
    }''')

# Diagnostics expose strict sandbox counters and retain source/probability safety.
diag_anchor = '''                    .put("v0173AutoBootstrapNavigations", 0)
                    .put("collectorVerifiesLogin", false)
'''
diag_new = '''                    .put("v0173AutoBootstrapNavigations", 0)
                    .put("jinhakAuthModel", "user-owned-session-explicit-high3-strict-sandbox-v0174")
                    .put("v0174StrictHigh3Sandbox", true)
                    .put("v0174StrictMainFrameBlocks", jinhakV0174StrictMainFrameBlocks)
                    .put("v0174LowerGradeAnyRequestBlocks", jinhakV0174LowerGradeAnyRequestBlocks)
                    .put("v0174ServiceWorkerLowerGradeBlocks", jinhakV0174ServiceWorkerLowerGradeBlocks)
                    .put("v0174PopupBlocks", jinhakV0174PopupBlocks)
                    .put("v0174HistoryBlocks", jinhakV0174HistoryBlocks)
                    .put("v0174AppNavigationBlocks", jinhakV0174AppNavigationBlocks)
                    .put("v0174RendererResumeBlocks", jinhakV0174RendererResumeBlocks)
                    .put("v0174PersistedTargetBlocks", jinhakV0174PersistedTargetBlocks)
                    .put("v0174SharedRootBlocks", jinhakV0174SharedRootBlocks)
                    .put("v0174GenericLoginBlocks", jinhakV0174GenericLoginBlocks)
                    .put("v0174OtherJinhakBlocks", jinhakV0174OtherJinhakBlocks)
                    .put("v0174ExternalBlocks", jinhakV0174ExternalBlocks)
                    .put("v0174MemberLoginAllows", jinhakV0174MemberLoginAllows)
                    .put("v0174High3Allows", jinhakV0174High3Allows)
                    .put("v0174ExplicitHigh3Confirmations", jinhakV0174ExplicitHigh3Confirmations)
                    .put("v0174StrictEntryRequests", jinhakV0174StrictEntryRequests)
                    .put("v0174ForbiddenPageStartsStopped", jinhakV0174ForbiddenPageStartsStopped)
                    .put("v0174ForbiddenPageFinishesObserved", jinhakV0174ForbiddenPageFinishesObserved)
                    .put("v0174SharedRootAllowed", false)
                    .put("v0174GenericLoginAllowed", false)
                    .put("v0174AutoHigh3Resume", false)
                    .put("collectorVerifiesLogin", false)
'''
# Replace only the first diagnostics occurrence; verification requires at least one authoritative export block.
text = replace_once(text, diag_anchor, diag_new, "v0174 diagnostics")
# Normalize the older auth-model label if it remains in the same diagnostics chain.
text = text.replace('.put("jinhakAuthModel", "user-owned-session-natural-high3-handoff-v0173")\n', '')

MAIN.write_text(text)
print("v0.17.4 strict high3 sandbox patch applied")
