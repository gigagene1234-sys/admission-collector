from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, label: str) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 regex match, found {count}")
    return out


def function_block(text: str, start: str, next_start: str, replacement: str, label: str) -> str:
    pattern = re.escape(start) + r".*?(?=" + re.escape(next_start) + r")"
    return regex_once(text, pattern, replacement.rstrip() + "\n\n", label)


text = MAIN.read_text()

text = once(
    text,
    "import com.admissionhub.collector.jinhak.JinhakAuthDomainPolicy\nimport com.admissionhub.collector.jinhak.JinhakGradeRouteFence",
    "import com.admissionhub.collector.jinhak.JinhakAuthDomainPolicy\nimport com.admissionhub.collector.jinhak.JinhakGradeRouteFence\nimport com.admissionhub.collector.jinhak.JinhakHigh3AuthRoute",
    "high3 auth import",
)

text = once(
    text,
    "    private var jinhakV0166LowerGradeRecoveryPending = false\n    private var jinhakPostMissionClosureFences = 0",
    "    private var jinhakV0166LowerGradeRecoveryPending = false\n"
    "    private var jinhakV0167CanonicalAuthEntries = 0\n"
    "    private var jinhakV0167GenericLoginRewrites = 0\n"
    "    private var jinhakV0167LowerGradeTransportDrops = 0\n"
    "    private var jinhakV0167AuthWaitEntries = 0\n"
    "    private var jinhakV0167AuthWaitDuplicateSuppressions = 0\n"
    "    private var jinhakV0167AuthExitsToHigh3 = 0\n"
    "    private var jinhakV0167AuthWaitActive = false\n"
    "    private var jinhakV0167AuthReturnTarget = \"\"\n"
    "    private var jinhakPostMissionClosureFences = 0",
    "v0167 state",
)

# Keepalive may observe the login surface, but it must never own navigation while the identity
# provider is waiting for the user. This removes the unbounded transition-auth poll source.
old_keepalive = '''                if (provider == ProviderId.JINHAK) {
                    val current = webView.url.orEmpty()
                    if (batchPausedForLogin || jinhakTransitionAuthGateActive || isProviderLoginUrl(ProviderId.JINHAK, current)) {
                        scheduleJinhakLoginRecovery("session-keepalive")
                    } else if (batchRunning) {
                        checkSessionState { needsLogin, _ ->
                            if (batchRunning && provider == ProviderId.JINHAK && needsLogin) {
                                batchPausedForLogin = true
                                jinhakAuthVerifiedForBatch = false
                                jinhakCoreBootstrapState = "keepalive-login-recovery"
                                jinhakReauthCycles += 1
                                persistJinhakAuthDiagnostics("keepalive-needs-login")
                                scheduleJinhakLoginRecovery("keepalive-needs-login")
                            }
                        }
                    }
                    persistJinhakAuthDiagnostics("session-keepalive")
                }'''
new_keepalive = '''                if (provider == ProviderId.JINHAK) {
                    val current = webView.url.orEmpty()
                    when {
                        JinhakGradeRouteFence.isBlockedLowerGrade(current) -> {
                            hardBlockJinhakLowerGradeNavigation("session-keepalive", current)
                        }
                        JinhakHigh3AuthRoute.isGenericProductLogin(current) -> {
                            jinhakV0167GenericLoginRewrites += 1
                            openJinhakDirectHigh3Auth("session-keepalive-generic-login", currentBatchTarget)
                        }
                        JinhakHigh3AuthRoute.isMemberLoginSurface(current) -> {
                            markJinhakDirectAuthWait("session-keepalive-member-login", current)
                        }
                        JinhakGradeRouteFence.isHigh3(current) &&
                            (batchPausedForLogin || jinhakTransitionAuthGateActive || startupLoginPreflightActive) -> {
                            verifyRecoveredJinhakHigh3AndResume(current)
                        }
                        batchRunning -> {
                            checkSessionState { needsLogin, _ ->
                                if (batchRunning && provider == ProviderId.JINHAK && needsLogin) {
                                    batchPausedForLogin = true
                                    jinhakAuthVerifiedForBatch = false
                                    jinhakCoreBootstrapState = "keepalive-direct-auth-required"
                                    jinhakReauthCycles += 1
                                    persistJinhakAuthDiagnostics("keepalive-needs-login")
                                    openJinhakDirectHigh3Auth("keepalive-needs-login", currentBatchTarget)
                                }
                            }
                        }
                    }
                    persistJinhakAuthDiagnostics("session-keepalive")
                }'''
text = once(text, old_keepalive, new_keepalive, "session keepalive")

# Main-frame transport policy. No DOM masking and no visibility mutation is used to enforce grade.
old_intercept = '''            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val target = request.url?.toString().orEmpty()
                if (provider == ProviderId.JINHAK && request.isForMainFrame && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                    handler.post {
                        if (provider == ProviderId.JINHAK) {
                            jinhakV0166LowerGradeRequestsIntercepted += 1
                            hardBlockJinhakLowerGradeNavigation("network-intercept", target)
                        }
                    }
                    return blockedJinhakLowerGradeResponse()
                }
                return super.shouldInterceptRequest(view, request)
            }'''
new_intercept = '''            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
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
            }'''
text = once(text, old_intercept, new_intercept, "main intercept")

old_override = '''                if (target.isNotBlank() && provider == ProviderId.JINHAK && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                    hardBlockJinhakLowerGradeNavigation("navigation-override", target)
                    return true
                }'''
new_override = '''                if (target.isNotBlank() && provider == ProviderId.JINHAK) {
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
                }'''
text = once(text, old_override, new_override, "main navigation override")

old_started = '''                if (provider == ProviderId.JINHAK && JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
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
new_started = '''                if (provider == ProviderId.JINHAK) {
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
                }'''
text = once(text, old_started, new_started, "page started auth route")

old_finished_jinhak = '''                if (provider == ProviderId.JINHAK) {
                    installJinhakHigh3DomProductFence("page-finished")
                    // Product verification is asynchronous. Do not launch a competing login probe
                    // until the lower-grade fail-closed latch had a chance to terminate this auth attempt.
                    handler.postDelayed({
                        if (provider == ProviderId.JINHAK && !jinhakLowerGradeLoginFenceLatched) {
                            scheduleLoginSurfaceDetection(ProviderId.JINHAK, "page-finished-after-product-fence")
                        }
                    }, 180L)
                } else {
                    scheduleLoginSurfaceDetection(provider, "page-finished")
                }'''
new_finished_jinhak = '''                if (provider == ProviderId.JINHAK) {
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
                }'''
text = once(text, old_finished_jinhak, new_finished_jinhak, "page finished no DOM fence")

# Provider login entry is the identity-provider page with an explicit high3 ReturnURL. The generic
# www.jinhak.com product-selector login wrapper is never a collector bootstrap again.
old_provider = '''    private fun providerLoginUrl(which: ProviderId): String = when (which) {
        ProviderId.JINHAK -> "https://www.jinhak.com/jh/member/login"
        ProviderId.ADIGA -> "https://www.adiga.kr/mbs/log/mbsLogView.do?menuId=PCMBSLOG1000"
    }

    private fun isProviderLoginUrl(which: ProviderId, rawUrl: String): Boolean {
        val url = rawUrl.lowercase()
        if (url.isBlank()) return false
        return when (which) {
            ProviderId.JINHAK -> url.contains("jinhak.com/") && (url.contains("/member/login") || url.contains("signin") || url.contains("login"))
            ProviderId.ADIGA -> url.contains("adiga.kr/") && (url.contains("/mbs/log/") || url.contains("mbslogview") || url.contains("login"))
        }
    }'''
new_provider = '''    private fun providerLoginUrl(which: ProviderId): String = when (which) {
        ProviderId.JINHAK -> JinhakHigh3AuthRoute.canonicalLoginUrl(currentBatchTarget)
        ProviderId.ADIGA -> "https://www.adiga.kr/mbs/log/mbsLogView.do?menuId=PCMBSLOG1000"
    }

    private fun isProviderLoginUrl(which: ProviderId, rawUrl: String): Boolean {
        val url = rawUrl.lowercase()
        if (url.isBlank()) return false
        return when (which) {
            ProviderId.JINHAK -> JinhakHigh3AuthRoute.isMemberLoginSurface(rawUrl) || JinhakHigh3AuthRoute.isGenericProductLogin(rawUrl)
            ProviderId.ADIGA -> url.contains("adiga.kr/") && (url.contains("/mbs/log/") || url.contains("mbslogview") || url.contains("login"))
        }
    }'''
text = once(text, old_provider, new_provider, "provider login route")

# Jinhak login surface detection is a single observation. It may submit a locally stored credential
# once, but it never opens Collector's credential dialog or starts a repeated login/navigation loop.
text = once(
    text,
    "        val delays = longArrayOf(100L, 420L, 1_050L, 2_300L)",
    "        val delays = if (which == ProviderId.JINHAK) longArrayOf(250L) else longArrayOf(100L, 420L, 1_050L, 2_300L)",
    "login surface one shot delays",
)
old_dialog = '''                    if (credentialVault.has(which.wireName)) {
                        attemptSavedCredentialLogin(which, reason)
                    } else if (startupCredentialPromptedProvider != which) {
                        startupCredentialPromptedProvider = which
                        showCredentialDialog(which, continueAfterSave = true)
                    }'''
new_dialog = '''                    if (credentialVault.has(which.wireName)) {
                        attemptSavedCredentialLogin(which, reason)
                    } else if (which == ProviderId.JINHAK) {
                        status.text = "진학사 회원 로그인 화면입니다. 사이트 자체 자동완성/Samsung Pass로 로그인하면 high3 ReturnURL로 복귀하며 Collector는 학년 선택 UI를 조작하지 않습니다."
                    } else if (startupCredentialPromptedProvider != which) {
                        startupCredentialPromptedProvider = which
                        showCredentialDialog(which, continueAfterSave = true)
                    }'''
text = once(text, old_dialog, new_dialog, "no Jinhak custom credential dialog")

# Replace v0.16.6 hard-block/recovery helpers. A blocked grade route is dropped, not hidden and not
# followed by an automatic high3 load. Generic login wrapper rewrite is a separate one-shot action.
start = "    private fun blockedJinhakLowerGradeResponse(): WebResourceResponse = WebResourceResponse("
next_start = "    private fun jinhakLowerGradeAuthFenceShouldTerminate(): Boolean {"
helpers = '''    private fun blockedJinhakLowerGradeResponse(): WebResourceResponse = WebResourceResponse(
        "text/plain",
        "UTF-8",
        204,
        "No Content",
        mapOf("Cache-Control" to "no-store", "X-Admission-Hub-Route-Fence" to "high3-transport-drop"),
        ByteArrayInputStream(ByteArray(0))
    )

    private fun hardBlockJinhakLowerGradeNavigation(source: String, target: String) {
        if (provider != ProviderId.JINHAK || !JinhakGradeRouteFence.isBlockedLowerGrade(target)) return
        jinhakLowerGradeNavigationsBlocked += 1
        jinhakV0166LowerGradeNavigationsHardBlocked += 1
        jinhakV0167LowerGradeTransportDrops += 1
        recordRuntimeEvent(
            "jinhak-v0167-lower-grade-transport-drop",
            JSONObject()
                .put("source", source.take(80))
                .put("targetSafePath", runtimeSafePath(target))
                .put("currentSafePath", runtimeSafePath(webView.url.orEmpty()))
                .put("networkRequestAllowed", false)
                .put("followLowerGrade", false)
                .put("visibilityMutation", false)
                .put("recoveryNavigationScheduled", false)
                .put("batchTerminated", false)
        )
        persistJinhakAuthDiagnostics("v0167-lower-grade-drop")
    }

    private fun openJinhakDirectHigh3Auth(reason: String, requestedTarget: String?) {
        if (provider != ProviderId.JINHAK) return
        val target = JinhakHigh3AuthRoute.sanitizeReturnTarget(
            requestedTarget?.takeIf { it.isNotBlank() } ?: currentBatchTarget
        )
        if (target.isBlank() || JinhakGradeRouteFence.isBlockedLowerGrade(target)) return
        val login = JinhakHigh3AuthRoute.canonicalLoginUrl(target)
        val current = webView.url.orEmpty()
        if (jinhakV0167AuthWaitActive && JinhakHigh3AuthRoute.isMemberLoginSurface(current)) {
            jinhakV0167AuthWaitDuplicateSuppressions += 1
            persistJinhakAuthDiagnostics("v0167-auth-wait-duplicate-suppressed")
            return
        }
        jinhakV0167CanonicalAuthEntries += 1
        jinhakV0167AuthWaitActive = true
        jinhakV0167AuthReturnTarget = target
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "v0167-direct-member-auth"
        jinhakLastAuthEvidence = "direct-member-auth-awaiting-high3-return"
        sessionState.text = "○ 진학사 고3 전용 회원 로그인 대기"
        status.text = "진학사 회원 로그인으로 이동합니다. 성공 시 high3 ReturnURL로 직접 복귀하며 Collector는 고1·2 선택 UI를 숨기거나 클릭하지 않습니다."
        recordRuntimeEvent(
            "jinhak-v0167-direct-member-auth-open",
            JSONObject()
                .put("reason", reason.take(80))
                .put("returnTargetSafePath", runtimeSafePath(target))
                .put("genericProductLoginUsed", false)
                .put("uiMaskUsed", false)
        )
        webView.loadUrl(login)
        persistJinhakAuthDiagnostics("v0167-direct-member-auth-open")
    }

    private fun markJinhakDirectAuthWait(reason: String, url: String) {
        if (provider != ProviderId.JINHAK || !JinhakHigh3AuthRoute.isMemberLoginSurface(url)) return
        if (!jinhakV0167AuthWaitActive) jinhakV0167AuthWaitEntries += 1
        jinhakV0167AuthWaitActive = true
        val returnTarget = JinhakHigh3AuthRoute.returnUrl(url)
        if (!returnTarget.isNullOrBlank() && JinhakHigh3AuthRoute.isAllowedHigh3Target(returnTarget)) {
            jinhakV0167AuthReturnTarget = returnTarget
        }
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "v0167-direct-member-auth-wait"
        jinhakLastAuthEvidence = "direct-member-auth-page-visible"
        sessionState.text = "○ 진학사 고3 전용 회원 로그인 대기"
        status.text = "사이트 회원 로그인 완료를 기다립니다. 로그인 후 서버 ReturnURL이 high3 보호경로로 복귀할 때만 인증을 검증합니다."
        recordRuntimeEvent(
            "jinhak-v0167-direct-member-auth-wait",
            JSONObject()
                .put("reason", reason.take(80))
                .put("loginSafePath", runtimeSafePath(url))
                .put("returnTargetSafePath", runtimeSafePath(jinhakV0167AuthReturnTarget))
                .put("navigationPolling", false)
                .put("uiMaskUsed", false)
        )
        persistJinhakAuthDiagnostics("v0167-direct-member-auth-wait")
    }'''
text = function_block(text, start, next_start, helpers, "transport helper block")

# Compatibility page handling is now only route classification. No login-page session polling, no
# DOM grade selector fence, and no automatic core retry from the login page.
compat = '''    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {
        if (provider != ProviderId.JINHAK || !jinhakAuthCompatibilityWindowActive()) return false
        return when (JinhakHigh3AuthRoute.decision(url)) {
            JinhakHigh3AuthRoute.MainFrameDecision.BLOCK_LOWER_GRADE -> {
                hardBlockJinhakLowerGradeNavigation("v0167-compatibility-lower-grade", url)
                true
            }
            JinhakHigh3AuthRoute.MainFrameDecision.REWRITE_GENERIC_LOGIN -> {
                jinhakV0167GenericLoginRewrites += 1
                openJinhakDirectHigh3Auth("v0167-compatibility-generic-login", currentBatchTarget)
                true
            }
            JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_CANONICAL_AUTH -> {
                jinhakV0912AuthCompatibilityTransitions += 1
                markJinhakDirectAuthWait("v0167-compatibility-member-login", url)
                true
            }
            else -> false
        }
    }'''
text = function_block(
    text,
    "    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {",
    "    private fun recoverJinhakLowerGradeLoginContext(source: String, detail: JSONObject = JSONObject()) {",
    compat,
    "compatibility handler",
)

# A protected high3 page is the only place where authentication may be promoted. Failure starts one
# direct member login; it does not hide the WebView or recursively poll/navigation-retry.
verify = '''    private fun verifyRecoveredJinhakHigh3AndResume(url: String): Boolean {
        if (provider != ProviderId.JINHAK || !JinhakGradeRouteFence.isHigh3(url)) return false
        val authGateOwned = jinhakAuthCompatibilityWindowActive() || batchPausedForLogin || jinhakTransitionAuthGateActive || startupLoginPreflightActive || jinhakV0167AuthWaitActive
        if (!authGateOwned) return false
        val expectedUrl = url
        checkSessionState { needsLogin, authenticated ->
            if (provider != ProviderId.JINHAK || webView.url.orEmpty() != expectedUrl) return@checkSessionState
            if (!needsLogin && authenticated) {
                jinhakV0912ProtectedCoreVerified += 1
                jinhakV0167AuthExitsToHigh3 += 1
                jinhakV0167AuthWaitActive = false
                jinhakV0167AuthReturnTarget = ""
                credentialAwaitingLoginExitProvider = null
                jinhakLowerGradeHigh3RecoverySuccesses += 1
                jinhakLowerGradeRecoveryInFlight = false
                jinhakLowerGradeManualGateActive = false
                jinhakLowerGradeLoginFenceLatched = false
                jinhakAuthVerifiedForBatch = true
                jinhakReauthCycles = 0
                jinhakCoreBootstrapState = "v0167-protected-high3-verified"
                jinhakLastAuthEvidence = "protected-high3-stable-v0167"
                jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
                runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, url, VERSION) }
                recordRuntimeEvent("jinhak-v0167-protected-high3-verified", JSONObject()
                    .put("verifiedCount", jinhakV0912ProtectedCoreVerified)
                    .put("authExitsToHigh3", jinhakV0167AuthExitsToHigh3)
                    .put("batchRunning", batchRunning)
                    .put("batchPausedForLogin", batchPausedForLogin)
                    .put("transitionGate", jinhakTransitionAuthGateActive)
                    .put("uiMaskUsed", false))
                sessionState.text = "● 진학사 고3·N수 보호경로 인증 확인 · 수집 재개"
                when {
                    batchRunning && batchPausedForLogin -> resumeBatchAfterVerifiedJinhakAuth("v0167-protected-high3-verified")
                    jinhakRealAuthProbeActive -> {
                        jinhakV0165ProbeCompletedFromProtectedCore += 1
                        finishJinhakRealAuthProbe("protected-core-verified-v0167", success = true)
                    }
                    unifiedRunning && unifiedPhase == "jinhak" && jinhakTransitionAuthGateActive && !batchRunning -> {
                        jinhakTransitionAuthGateActive = false
                        unifiedPendingJinhakStart = false
                        status.text = "진학사 고3·N수 인증 확인 완료 · 진학사 수집을 시작합니다."
                        handler.postDelayed({
                            if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
                        }, 180L)
                    }
                    startupLoginPreflightActive -> onStartupProviderAuthenticated(ProviderId.JINHAK, startupLoginPollGeneration)
                    else -> status.text = "진학사 고3·N수 보호경로 인증이 확인되었습니다."
                }
            } else {
                jinhakAuthVerifiedForBatch = false
                jinhakCoreBootstrapState = "v0167-protected-high3-login-required"
                jinhakLastAuthEvidence = "protected-high3-login-required-v0167"
                openJinhakDirectHigh3Auth("protected-high3-login-required", url)
            }
        }
        return true
    }'''
text = function_block(
    text,
    "    private fun verifyRecoveredJinhakHigh3AndResume(url: String): Boolean {",
    "    private fun installJinhakHigh3DomProductFence(reason: String) {",
    verify,
    "protected high3 verifier",
)

# Delete the DOM/UI grade fence completely. There must be no display:none/aria-hidden/click
# interception based on 고1·2 labels anywhere in the runtime authentication path.
text = function_block(
    text,
    "    private fun installJinhakHigh3DomProductFence(reason: String) {",
    "    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {",
    "",
    "remove DOM product fence",
)

# Strip any remaining calls to the removed visual fence. These calls were UI-only and must not be
# replaced by another hiding implementation.
text = re.sub(r'^\s*installJinhakHigh3DomProductFence\([^\n]*\)\s*\n', '', text, flags=re.M)

# v0.9.12 saved credential path may submit once on the actual member login form. It must then wait
# for the server ReturnURL rather than polling session state and forcing page transitions.
start_marker = "    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {"
end_marker = "    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {"
s = text.index(start_marker)
e = text.index(end_marker, s)
block = text[s:e]
block = block.replace(
    '''            webView.visibility = View.VISIBLE
            sessionState.text = "○ 진학사 사이트 로그인 필요"''',
    '''            sessionState.text = "○ 진학사 고3 전용 회원 로그인 필요"'''
)
callback_pattern = r'''        webView\.evaluateJavascript\(js\) \{ raw ->.*?            persistJinhakAuthDiagnostics\("credential-auto-login-v0912-baseline"\)\n        \}\n'''
callback_repl = '''        webView.evaluateJavascript(js) { raw ->
            credentialAutoLoginInFlight = false
            val decoded = runCatching { JSONTokener(raw).nextValue() as? String }.getOrNull().orEmpty()
            val result = runCatching { JSONObject(decoded) }.getOrDefault(JSONObject())
            if (result.optBoolean("submitted", false)) {
                credentialAutoLoginSubmissions += 1
                jinhakV0912PassiveLoginSubmissions += 1
                credentialAwaitingLoginExitProvider = ProviderId.JINHAK
                credentialAutoLoginLastResult = "v0167-submitted-awaiting-server-high3-return"
                jinhakV0167AuthWaitActive = true
                jinhakCoreBootstrapState = "v0167-login-submitted-awaiting-returnurl"
                jinhakLastAuthEvidence = "login-submit-awaiting-server-returnurl"
                status.text = "진학사 로그인 제출 완료 · Collector는 이동을 강제하지 않고 서버의 high3 ReturnURL 복귀를 기다립니다."
                persistJinhakAuthDiagnostics("v0167-credential-submit-awaiting-returnurl")
            } else {
                credentialAutoLoginLastResult = "v0167-not-submitted-${result.optString("reason", "unknown")}"
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                status.text = "자동 입력이 제출되지 않았습니다. 현재 진학사 회원 로그인 화면에서 직접 로그인하면 됩니다. 반복 이동이나 학년 UI 조작은 수행하지 않습니다."
                persistJinhakAuthDiagnostics("v0167-credential-not-submitted")
            }
        }
'''
block2, n = re.subn(callback_pattern, callback_repl, block, count=1, flags=re.S)
if n != 1:
    raise SystemExit(f"v0912 callback: expected 1, found {n}")
text = text[:s] + block2 + text[e:]

text = once(
    text,
    '''        if (which == ProviderId.JINHAK) {
            installJinhakHigh3DomProductFence("credential-visual-only:$reason")
            attemptSavedCredentialLoginV0912Baseline(reason)
            return
        }''',
    '''        if (which == ProviderId.JINHAK) {
            attemptSavedCredentialLoginV0912Baseline(reason)
            return
        }''',
    "Jinhak credential no visual fence",
)

# Replace the old recursive login recovery state machine with a single-shot router. The legacy poll
# function is removed entirely; transition auth therefore cannot exceed a limit only because batch
# has not started yet (the v0.16.6 164-poll failure).
recovery = '''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val current = webView.url.orEmpty()
        when {
            JinhakGradeRouteFence.isBlockedLowerGrade(current) -> {
                hardBlockJinhakLowerGradeNavigation("single-shot-recovery:$reason", current)
            }
            JinhakHigh3AuthRoute.isGenericProductLogin(current) -> {
                jinhakV0167GenericLoginRewrites += 1
                openJinhakDirectHigh3Auth("single-shot-generic-rewrite:$reason", currentBatchTarget)
            }
            JinhakHigh3AuthRoute.isMemberLoginSurface(current) -> {
                markJinhakDirectAuthWait("single-shot-member-wait:$reason", current)
            }
            JinhakGradeRouteFence.isHigh3(current) -> {
                verifyRecoveredJinhakHigh3AndResume(current)
            }
            startupLoginPreflightActive || jinhakTransitionAuthGateActive ||
                (batchRunning && batchPausedForLogin) || jinhakRealAuthProbeActive -> {
                openJinhakDirectHigh3Auth("single-shot-auth-entry:$reason", currentBatchTarget)
            }
            else -> persistJinhakAuthDiagnostics("single-shot-no-navigation:$reason")
        }
    }'''
text = function_block(
    text,
    "    private fun scheduleJinhakLoginRecovery(reason: String) {",
    "    private fun completeJinhakVerifiedAuth(reason: String) {",
    recovery,
    "remove recursive login recovery poller",
)

# Old v0.16.6 route recovery state is now permanently unused.
text = text.replace("jinhakV0166LowerGradeRecoveryPending = false", "jinhakV0166LowerGradeRecoveryPending = false")

# Add diagnostic fields next to v0.16.6 diagnostics.
diag_anchor = '''                    .put("jinhakV0166LowerGradeRecoveryDispatches", jinhakV0166LowerGradeRecoveryDispatches)
                    .put("jinhakV0166LowerGradeRecoveryPending", jinhakV0166LowerGradeRecoveryPending)'''
diag_new = diag_anchor + '''
                    .put("jinhakV0167CanonicalAuthEntries", jinhakV0167CanonicalAuthEntries)
                    .put("jinhakV0167GenericLoginRewrites", jinhakV0167GenericLoginRewrites)
                    .put("jinhakV0167LowerGradeTransportDrops", jinhakV0167LowerGradeTransportDrops)
                    .put("jinhakV0167AuthWaitEntries", jinhakV0167AuthWaitEntries)
                    .put("jinhakV0167AuthWaitDuplicateSuppressions", jinhakV0167AuthWaitDuplicateSuppressions)
                    .put("jinhakV0167AuthExitsToHigh3", jinhakV0167AuthExitsToHigh3)
                    .put("jinhakV0167AuthWaitActive", jinhakV0167AuthWaitActive)
                    .put("jinhakV0167AuthReturnTargetSafePath", runtimeSafePath(jinhakV0167AuthReturnTarget))
                    .put("jinhakV0167GenericProductLoginBootstrap", false)
                    .put("jinhakV0167DomGradeUiMask", false)
                    .put("jinhakV0167RecursiveLoginPolling", false)'''
text = once(text, diag_anchor, diag_new, "v0167 diagnostics")

# Reset v0.16.7 counters wherever the v0.16.6 run counters are reset.
reset_anchor = '''        jinhakV0166LowerGradeRequestsIntercepted = 0
        jinhakV0166LowerGradeNavigationsHardBlocked = 0
        jinhakV0166LowerGradeRecoveryDispatches = 0
        jinhakV0166LowerGradeRecoveryPending = false'''
if reset_anchor in text:
    reset_new = reset_anchor + '''
        jinhakV0167CanonicalAuthEntries = 0
        jinhakV0167GenericLoginRewrites = 0
        jinhakV0167LowerGradeTransportDrops = 0
        jinhakV0167AuthWaitEntries = 0
        jinhakV0167AuthWaitDuplicateSuppressions = 0
        jinhakV0167AuthExitsToHigh3 = 0
        jinhakV0167AuthWaitActive = false
        jinhakV0167AuthReturnTarget = ""'''
    text = text.replace(reset_anchor, reset_new)

# No v0.16.7 code path may still call the deleted DOM grade fence or recursive poller.
if "installJinhakHigh3DomProductFence" in text:
    raise SystemExit("DOM grade UI fence call/function remains")
if "pollJinhakLoginRecovery(" in text:
    raise SystemExit("recursive login recovery poller remains")
if "__admissionVisualLowerGradeFenceInstalled" in text:
    raise SystemExit("visual lower-grade click fence remains")

text = text.replace('private const val VERSION = "0.16.6"', 'private const val VERSION = "0.16.7"')
text = text.replace('private const val BUILD_CODE = 116600', 'private const val BUILD_CODE = 116700')
MAIN.write_text(text)

gradle = GRADLE.read_text()
gradle = once(gradle, 'versionCode = 116600', 'versionCode = 116700', 'gradle versionCode')
gradle = once(gradle, 'versionName = "0.16.6"', 'versionName = "0.16.7"', 'gradle versionName')
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = once(
    manifest,
    'android:label="Admission Hub v0.16.6 High3 Route Isolation"',
    'android:label="Admission Hub v0.16.7 Direct High3 Auth"',
    'manifest label',
)
MANIFEST.write_text(manifest)

print("v0.16.7 direct-high3-auth patch applied")
