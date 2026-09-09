from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
BUILD = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and text.count(new) >= 1:
        return text
    raise SystemExit(f"{label}: expected one old token, found {count}")


def replace_all(text: str, old: str, new: str, label: str, min_count: int = 1) -> str:
    count = text.count(old)
    if count == 0 and new in text:
        return text
    if count < min_count:
        raise SystemExit(f"{label}: expected at least {min_count}, found {count}")
    return text.replace(old, new)


def replace_member(text: str, name: str, replacement: str) -> str:
    marker = f"    private fun {name}"
    start = text.find(marker)
    if start < 0:
        if replacement.strip() in text:
            return text
        raise SystemExit(f"member not found: {name}")
    tail = text[start + len(marker):]
    match = re.search(r"\n    private\s+(?:fun|val|var|data\s+class|class|object)\b", tail)
    if not match:
        raise SystemExit(f"next member not found after: {name}")
    end = start + len(marker) + match.start()
    return text[:start] + replacement.rstrip() + "\n" + text[end:]


def inject_after_function_open(text: str, name: str, code: str, guard_marker: str) -> str:
    if guard_marker in text:
        return text
    marker = f"    private fun {name}"
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"function not found for injection: {name}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"function open brace not found: {name}")
    return text[:brace+1] + "\n" + code.rstrip() + text[brace+1:]


# -----------------------------------------------------------------------------
# Metadata
# -----------------------------------------------------------------------------
build = BUILD.read_text()
build = replace_once(build, "versionCode = 117000", "versionCode = 117100", "versionCode")
build = replace_once(build, 'versionName = "0.17.0"', 'versionName = "0.17.1"', "versionName")
BUILD.write_text(build)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Hub v0.17.0 Server-Owned Auth"',
    'android:label="Admission Hub v0.17.1 User-Owned Jinhak Session"',
    "manifest label",
)
MANIFEST.write_text(manifest)

text = MAIN.read_text()
text = replace_once(text, 'private const val VERSION = "0.17.0"', 'private const val VERSION = "0.17.1"', "VERSION")
text = replace_once(text, 'private const val BUILD_CODE = 117000', 'private const val BUILD_CODE = 117100', "BUILD_CODE")

# Explicit policy import.
import_anchor = "import com.admissionhub.collector.jinhak.JinhakAuthEventState\n"
if "import com.admissionhub.collector.jinhak.JinhakUserSessionPolicy\n" not in text:
    text = replace_once(
        text,
        import_anchor,
        import_anchor + "import com.admissionhub.collector.jinhak.JinhakUserSessionPolicy\n",
        "JinhakUserSessionPolicy import",
    )

# UI field and user-session state.
field_anchor = "    private lateinit var realJinhakAuthProbeButton: Button\n"
if "private lateinit var jinhakSessionConfirmButton: Button" not in text:
    text = replace_once(
        text,
        field_anchor,
        field_anchor + "    private lateinit var jinhakSessionConfirmButton: Button\n",
        "session confirm button field",
    )

state_anchor = "    private var jinhakAuthVerifiedForBatch = false\n"
if "private var jinhakUserSessionConfirmed = false" not in text:
    text = replace_once(
        text,
        state_anchor,
        state_anchor
        + "    private var jinhakUserSessionConfirmed = false\n"
        + "    private var jinhakUserSessionGateEntries = 0\n"
        + "    private var jinhakUserSessionConfirmations = 0\n"
        + "    private var jinhakUserSessionPauses = 0\n",
        "user session state",
    )

# -----------------------------------------------------------------------------
# Jinhak keep-alive: zero session ownership. Adiga behavior is preserved.
# -----------------------------------------------------------------------------
keep_start = text.find("    private val sessionKeepAlive = object : Runnable {")
keep_end = text.find("    private data class BatchPageAction(", keep_start)
if keep_start < 0 or keep_end < 0:
    raise SystemExit("sessionKeepAlive block not found")
new_keep = '''    private val sessionKeepAlive = object : Runnable {
        override fun run() {
            val active = unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive
            if (active && provider != ProviderId.JINHAK) {
                attemptSessionExtension()
            } else if (active && provider == ProviderId.JINHAK) {
                // v0.17.1: Jinhak session ownership belongs entirely to the user/browser.
                // This timer records liveness only. It never checks, extends, rewrites, clicks,
                // restores, captures, or otherwise changes the Jinhak authentication session.
                jinhakSessionKeepAliveTicks += 1
                if (!hasWindowFocus()) jinhakSessionKeepAliveBackgroundTicks += 1
                persistJinhakAuthDiagnostics("user-owned-session-liveness-only")
            }
            handler.postDelayed(this, 45_000L)
        }
    }
'''
text = text[:keep_start] + new_keep + text[keep_end:]

# -----------------------------------------------------------------------------
# Browser UI: move the real WebView out of the collapsed advanced panel and make
# it a large, always-visible surface directly under the dashboard.
# -----------------------------------------------------------------------------
text = text.replace("        hubAdvancedPanel.addView(status)\n", "")
text = text.replace(
    "        hubAdvancedPanel.addView(browserStack, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(320)))\n",
    "",
)

confirm_anchor = '        hubAdvancedToggle = Button(this).apply { text = "고급 도구" }\n'
if "jinhakSessionConfirmButton = Button(this).apply" not in text:
    text = replace_once(
        text,
        confirm_anchor,
        '''        jinhakSessionConfirmButton = Button(this).apply {
            text = "진학사 로그인 완료 · 탐색 시작/재개"
            setOnClickListener { confirmJinhakUserSessionAndResume("dashboard-browser-button") }
        }
''' + confirm_anchor,
        "create user session confirm button",
    )

root_anchor = '        root.addView(hubDecisionSummary, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))\n'
if 'text = "사이트 탐색 / 로그인"' not in text:
    expanded = root_anchor + '''        root.addView(TextView(this).apply {
            text = "사이트 탐색 / 로그인"
            textSize = 17f
            setPadding(dp(6), dp(10), dp(6), dp(4))
        })
        root.addView(status, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        val expandedBrowserHeight = maxOf(dp(720), (resources.displayMetrics.heightPixels * 0.68f).toInt())
        root.addView(browserStack, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, expandedBrowserHeight))
        root.addView(jinhakSessionConfirmButton, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
'''
    text = replace_once(text, root_anchor, expanded, "expanded browser under dashboard")

# Make browser content use the full available width. This changes viewport behavior only,
# not site content or login state.
web_anchor = "        webView = WebView(this)\n"
if "webView.settings.useWideViewPort = true" not in text:
    text = replace_once(
        text,
        web_anchor,
        web_anchor
        + "        webView.settings.useWideViewPort = true\n"
        + "        webView.settings.loadWithOverviewMode = false\n",
        "wide browser viewport",
    )

# -----------------------------------------------------------------------------
# User-owned session gate. No Jinhak authentication verdict exists in the app.
# jinhakAuthVerifiedForBatch remains only as a compatibility flag and means
# "the user explicitly said login is complete", never app verification.
# -----------------------------------------------------------------------------
start_batch_marker = "    private fun startBatch() {\n"
if "private fun enterJinhakUserSessionGate(" not in text:
    gate_functions = '''    private fun enterJinhakUserSessionGate(reason: String) {
        if (provider != ProviderId.JINHAK) provider = ProviderId.JINHAK
        jinhakUserSessionGateEntries += 1
        if (batchRunning) {
            batchPausedForLogin = true
            jinhakUserSessionPauses += 1
        }
        jinhakUserSessionConfirmed = false
        jinhakAuthVerifiedForBatch = false
        jinhakTransitionAuthGateActive = false
        jinhakCoreBootstrapState = "v0171-user-session-gate"
        jinhakLastAuthEvidence = "user-owned-session-awaiting-explicit-confirmation"
        jinhakLastCoreVerifiedAtMs = 0L
        jinhakReauthCycles = 0
        jinhakAuthVerificationFailures = 0
        jinhakLoginRecoveryPolls = 0
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
        if (::slowLaneHost.isInitialized) slowLaneHost.visibility = View.GONE
        if (::webView.isInitialized) webView.visibility = View.VISIBLE
        if (::jinhakSessionConfirmButton.isInitialized) {
            jinhakSessionConfirmButton.isEnabled = true
            jinhakSessionConfirmButton.text = "진학사 로그인 완료 · 탐색 시작/재개"
        }
        if (::sessionState.isInitialized) sessionState.text = "○ 진학사 로그인·세션은 사용자 관리"
        if (::status.isInitialized) {
            status.text = "아래 진학사 화면에서 직접 로그인 상태를 확인하세요. 앱은 ID/PW·쿠키·로그인 여부·세션 연장을 건드리지 않습니다. 로그인 완료 후 버튼을 누르면 로그인 완료 상태라고 가정하고 탐색합니다."
        }
        recordRuntimeEvent(
            "jinhak-v0171-user-session-gate",
            JSONObject()
                .put("reason", reason.take(100))
                .put("safePath", runtimeSafePath(webView.url))
                .put("sessionAuthority", "user")
                .put("collectorVerifiedLogin", false)
                .put("collectorSessionExtension", false)
                .put("collectorCredentialRead", false)
                .put("collectorCredentialSubmit", false)
                .put("collectorLoginNavigation", false)
        )
        persistJinhakAuthDiagnostics("v0171-user-session-gate:$reason")
    }

    private fun confirmJinhakUserSessionAndResume(reason: String) {
        if (provider != ProviderId.JINHAK) {
            Toast.makeText(this, "진학사 화면에서만 사용할 수 있습니다.", Toast.LENGTH_SHORT).show()
            return
        }
        jinhakUserSessionConfirmed = true
        jinhakUserSessionConfirmations += 1
        // Compatibility-only flag: this is a USER ASSERTION, not Collector authentication proof.
        jinhakAuthVerifiedForBatch = true
        jinhakTransitionAuthGateActive = false
        jinhakCoreBootstrapState = "v0171-user-confirmed-login-assumed"
        jinhakLastAuthEvidence = "user-confirmed-login-assumed-no-app-verification"
        jinhakLastCoreVerifiedAtMs = 0L
        jinhakReauthCycles = 0
        jinhakAuthVerificationFailures = 0
        jinhakLoginRecoveryPolls = 0
        val wasPaused = batchRunning && batchPausedForLogin
        batchPausedForLogin = false
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
        if (::slowLaneHost.isInitialized) slowLaneHost.visibility = View.GONE
        webView.visibility = View.VISIBLE
        jinhakSessionConfirmButton.text = "진학사 로그인 완료 확인됨 · 다시 확인/재개"
        sessionState.text = "● 사용자 확인 완료 · 진학사 로그인 완료 상태로 탐색"
        status.text = "사용자가 로그인 완료를 확인했습니다. Collector는 별도 인증 검사 없이 현재 WebView 세션을 그대로 사용해 진학사 탐색을 실행합니다."
        recordRuntimeEvent(
            "jinhak-v0171-user-session-confirmed",
            JSONObject()
                .put("reason", reason.take(100))
                .put("safePath", runtimeSafePath(webView.url))
                .put("sessionAuthority", "user")
                .put("userConfirmed", true)
                .put("collectorVerifiedLogin", false)
                .put("collectorSessionExtension", false)
                .put("collectorCredentialRead", false)
        )
        persistJinhakAuthDiagnostics("v0171-user-session-confirmed:$reason")

        when {
            startupLoginPreflightActive -> {
                startupLoginJinhakAuthenticated = true
                startupLoginPreflightActive = false
                startupLoginPreflightVerified = true
                startupLoginVerifiedAtMs = System.currentTimeMillis()
                startupLoginStage = "jinhak-user-confirmed"
                startupLoginPollGeneration += 1
                unifiedButton.text = "통합 수집 시작 중"
                handler.postDelayed({
                    if (!unifiedRunning && !batchRunning && jinhakUserSessionConfirmed) startUnifiedCollectionAuthenticated()
                }, 180L)
            }
            unifiedRunning && unifiedPhase == "jinhak" && !batchRunning -> {
                unifiedPendingJinhakStart = false
                handler.postDelayed({
                    if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning && jinhakUserSessionConfirmed) startBatch()
                }, 120L)
            }
            wasPaused && batchRunning -> {
                val retry = currentBatchTarget
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || !jinhakUserSessionConfirmed) return@postDelayed
                    if (!retry.isNullOrBlank() && isProviderUrl(retry) && !JinhakGradeRouteFence.isBlockedLowerGrade(retry)) {
                        webView.loadUrl(retry)
                    } else {
                        loadNextBatchPage()
                    }
                }, 120L)
            }
            !batchRunning -> startBatch()
        }
    }

'''
    text = replace_once(text, start_batch_marker, gate_functions + start_batch_marker, "insert user session gate")

# startBatch cannot run Jinhak until the user says login is complete.
start_guard = '''    private fun startBatch() {
        if (provider == ProviderId.JINHAK && !jinhakUserSessionConfirmed) {
            enterJinhakUserSessionGate("start-batch")
            return
        }
        if (provider == ProviderId.JINHAK) {
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "v0171-user-confirmed-login-assumed"
            jinhakLastAuthEvidence = "user-confirmed-login-assumed-no-app-verification"
            jinhakLastCoreVerifiedAtMs = 0L
        }
'''
if start_guard not in text:
    text = replace_once(text, start_batch_marker, start_guard, "startBatch user gate")

# -----------------------------------------------------------------------------
# Unified transition: show Jinhak itself and wait for explicit user confirmation.
# Never probe a protected path to decide whether login exists.
# -----------------------------------------------------------------------------
text = replace_member(text, "transitionUnifiedToJinhak", '''    private fun transitionUnifiedToJinhak(adigaReason: String) {
        if (!unifiedRunning || unifiedPhase != "adiga") return
        val sessionId = unifiedSessionId ?: return
        unifiedPhase = "jinhak"
        unifiedPendingAdigaStart = false
        unifiedPendingJinhakStart = true
        unifiedJinhakAutoCapture = false
        unifiedAutoCaptureScheduled = false
        unifiedJinhakCapturedPages.clear()
        jinhakBatchStartCount = 0
        jinhakNormalizedMissionSeedContexts.clear()
        jinhakNormalizedIdentitySeedKeys.clear()
        jinhakNormalizedCandidateBindingKeys.clear()
        jinhakNormalizedAmbiguousBindings = 0
        jinhakTransitionAuthGateActive = false
        jinhakUserSessionConfirmed = false
        jinhakAuthVerifiedForBatch = false
        jinhakProtectedCoreStablePasses = 0
        jinhakCoreBootstrapState = "v0171-user-session-gate"
        jinhakLastAuthEvidence = "user-owned-session-awaiting-explicit-confirmation"
        jinhakLastCoreVerifiedAtMs = 0L
        jinhakLoginRecoveryGeneration += 1
        jinhakReauthCycles = 0

        provider = ProviderId.JINHAK
        localRunId = localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
        localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId) }
        localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$adigaReason")
        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY.name, ProviderId.JINHAK.wireName,
            JSONObject().put("authorizedConnectorActive", false).put("sessionAuthority", "user"), false)
        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_USER_SESSION_MISSION.name, ProviderId.JINHAK.wireName,
            JSONObject()
                .put("observationFirst", true)
                .put("userStartedSessionMission", true)
                .put("boundedSameProviderTraversal", true)
                .put("maxPages", MAX_JINHAK_AUTONAV_PAGES)
                .put("loginAssumption", "user-confirms-before-exploration")
                .put("collectorVerifiesLogin", false)
                .put("collectorExtendsSession", false), false)
        persistRuntimeCheckpoint(forceResume = true)
        CookieManager.getInstance().flush()
        batchButton.text = "진학사 탐색 · 사용자 로그인 확인 대기"
        diagnosticButton.text = "진학사 전체 분석 전송"
        unifiedButton.text = "통합 수집 종료"
        currentBatchTarget = canonicalizeBatchUrl(JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty())
        enterJinhakUserSessionGate("unified-transition")
        val current = webView.url.orEmpty()
        if (!isProviderUrl(current)) {
            webView.loadUrl(ProviderId.JINHAK.homeUrl)
        }
    }''')

# -----------------------------------------------------------------------------
# All legacy Jinhak auth/recovery entry points become passive user-session gates.
# -----------------------------------------------------------------------------
text = replace_member(text, "markJinhakDirectAuthWait", '''    private fun markJinhakDirectAuthWait(reason: String, url: String) {
        if (provider != ProviderId.JINHAK) return
        jinhakV0170ServerLoginRedirects += 1
        enterJinhakUserSessionGate("site-login-surface:$reason")
    }''')

text = replace_member(text, "handleJinhakV0912AuthCompatibilityPage", '''    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return false
        return when (JinhakUserSessionPolicy.decision(url)) {
            JinhakUserSessionPolicy.NavigationDecision.DROP_LOWER_GRADE -> {
                hardBlockJinhakLowerGradeNavigation("v0171-lower-grade-drop", url)
                true
            }
            JinhakUserSessionPolicy.NavigationDecision.PAUSE_FOR_USER_SESSION -> {
                enterJinhakUserSessionGate("v0171-login-surface")
                true
            }
            JinhakUserSessionPolicy.NavigationDecision.ALLOW_ASSUMING_USER_LOGIN -> false
        }
    }''')

text = replace_member(text, "scheduleJinhakLoginRecovery", '''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val current = webView.url.orEmpty()
        if (JinhakGradeRouteFence.isBlockedLowerGrade(current)) {
            hardBlockJinhakLowerGradeNavigation("v0171-lower-grade:$reason", current)
            return
        }
        // No automatic Jinhak recovery. If a login surface exists, the user owns it.
        if (JinhakHigh3AuthRoute.isMemberLoginSurface(current) || JinhakHigh3AuthRoute.isGenericProductLogin(current)) {
            enterJinhakUserSessionGate("recovery-request:$reason")
        } else {
            persistJinhakAuthDiagnostics("v0171-recovery-suppressed:$reason")
        }
    }''')

text = replace_member(text, "verifyRecoveredJinhakHigh3AndResume", '''    private fun verifyRecoveredJinhakHigh3AndResume(url: String): Boolean {
        if (provider != ProviderId.JINHAK || !JinhakGradeRouteFence.isHigh3(url)) return false
        // High3 navigation is not authentication proof in v0.17.1. Only the user can confirm.
        if (!jinhakUserSessionConfirmed) {
            persistJinhakAuthDiagnostics("v0171-high3-observed-awaiting-user-confirmation")
        }
        return false
    }''')

text = replace_member(text, "completeJinhakVerifiedAuth", '''    private fun completeJinhakVerifiedAuth(reason: String) {
        if (provider != ProviderId.JINHAK) return
        // Legacy callback intentionally cannot verify or resume Jinhak authentication.
        if (!jinhakUserSessionConfirmed) enterJinhakUserSessionGate("legacy-verified-auth-suppressed:$reason")
        else persistJinhakAuthDiagnostics("v0171-legacy-auth-callback-ignored:$reason")
    }''')

text = replace_member(text, "handleJinhakTransitionAuthGate", '''    private fun handleJinhakTransitionAuthGate(url: String) {
        if (provider != ProviderId.JINHAK) return
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
            hardBlockJinhakLowerGradeNavigation("v0171-transition-lower-grade", url)
            return
        }
        if (JinhakHigh3AuthRoute.isMemberLoginSurface(url) || JinhakHigh3AuthRoute.isGenericProductLogin(url)) {
            enterJinhakUserSessionGate("transition-login-surface")
        }
    }''')

text = replace_member(text, "openJinhakDirectHigh3Auth", '''    private fun openJinhakDirectHigh3Auth(reason: String, requestedTarget: String?) {
        if (provider != ProviderId.JINHAK) return
        val current = webView.url.orEmpty()
        if (JinhakGradeRouteFence.isBlockedLowerGrade(current)) {
            hardBlockJinhakLowerGradeNavigation("v0171-lower-grade:$reason", current)
            return
        }
        if (JinhakHigh3AuthRoute.isMemberLoginSurface(current) || JinhakHigh3AuthRoute.isGenericProductLogin(current) || !jinhakUserSessionConfirmed) {
            enterJinhakUserSessionGate("legacy-auth-navigation-suppressed:$reason")
            return
        }
        // Under explicit user confirmation this compatibility entry point may only continue to
        // the requested high3 mission target; it never constructs a login URL.
        val target = JinhakHigh3AuthRoute.sanitizeReturnTarget(requestedTarget ?: currentBatchTarget)
        if (target.isNotBlank() && !JinhakGradeRouteFence.isBlockedLowerGrade(target)) webView.loadUrl(target)
    }''')

# The diagnostic button no longer performs authentication. It simply exposes the user-owned browser.
text = replace_member(text, "startJinhakRealAuthProbe", '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        if (batchRunning) {
            Toast.makeText(this, "진행 중인 진학사 수집이 있습니다. 현재 화면에서 세션을 관리하세요.", Toast.LENGTH_LONG).show()
            return
        }
        provider = ProviderId.JINHAK
        jinhakRealAuthProbeActive = false
        jinhakRealAuthProbeAutoContinue = false
        jinhakRealAuthProbeResult = "disabled-user-owned-session-v0171"
        enterJinhakUserSessionGate("manual-session-screen:$trigger")
        if (!isProviderUrl(webView.url.orEmpty())) webView.loadUrl(ProviderId.JINHAK.homeUrl)
        status.text = "v0.17.1은 진학사 로그인 진단을 하지 않습니다. 아래 사이트에서 사용자가 로그인 상태를 직접 관리한 뒤 로그인 완료 버튼을 누르세요."
    }''')

text = replace_member(text, "isFreshJinhakRealAuthProbe", '''    private fun isFreshJinhakRealAuthProbe(): Boolean = false''')
text = replace_member(text, "hasFreshJinhakProtectedCoreProof", '''    private fun hasFreshJinhakProtectedCoreProof(): Boolean = false''')
text = replace_member(text, "hasFreshProtectedCoreProofForTargetRedirect", '''    private fun hasFreshProtectedCoreProofForTargetRedirect(): Boolean = false''')

# Login redirects are never treated as target failures in a user-owned session model.
text = replace_member(text, "noteJinhakTargetAuthRedirectEpisode", '''    private fun noteJinhakTargetAuthRedirectEpisode(source: String): Int {
        if (provider != ProviderId.JINHAK || !batchRunning) return 0
        jinhakTargetAuthRedirectEpisodes += 1
        enterJinhakUserSessionGate("target-login-redirect:$source")
        return 1
    }''')
text = replace_member(text, "quarantineJinhakTargetSpecificAuthRedirect", '''    private fun quarantineJinhakTargetSpecificAuthRedirect(retry: String?, reason: String): Boolean {
        // A login redirect means user-session control, not a failed admission target.
        return false
    }''')

# Explicit resume button is the user assertion itself for Jinhak.
resume_marker = "    private fun resumeAfterLogin() {\n"
resume_guard = '''    private fun resumeAfterLogin() {
        if (provider == ProviderId.JINHAK) {
            confirmJinhakUserSessionAndResume("legacy-resume-button")
            return
        }
'''
if resume_guard not in text:
    text = replace_once(text, resume_marker, resume_guard, "resumeAfterLogin user assertion")

# Startup preflight may still be used for Adiga, but Jinhak immediately transfers control to user.
begin_marker = "    private fun beginStartupLoginProvider(which: ProviderId) {\n        if (!startupLoginPreflightActive) return\n"
begin_new = begin_marker + '''        if (which == ProviderId.JINHAK) {
            provider = ProviderId.JINHAK
            startupLoginStage = "jinhak-user-owned-session"
            startupLoginOpenAttempted = false
            startupAuthIndeterminatePolls = 0
            startupLoginPollGeneration += 1
            startupLoginJinhakRestoredLease = false
            localRunId = localStore.latestResumableRun(which.wireName)
            CookieManager.getInstance().flush()
            enterJinhakUserSessionGate("startup-provider")
            if (!isProviderUrl(webView.url.orEmpty())) webView.loadUrl(which.homeUrl)
            return
        }
'''
if begin_new not in text:
    text = replace_once(text, begin_marker, begin_new, "beginStartupLoginProvider Jinhak gate")

# No Jinhak route/DOM auth evaluation during startup.
text = replace_member(text, "evaluateStartupLoginState", '''    private fun evaluateStartupLoginState(expectedProvider: ProviderId, generation: Int) {
        if (expectedProvider == ProviderId.JINHAK) {
            if (startupLoginPreflightActive && provider == ProviderId.JINHAK && generation == startupLoginPollGeneration) {
                enterJinhakUserSessionGate("startup-evaluation-suppressed")
            }
            return
        }
        evaluateStartupLoginStateLegacyAdiga(expectedProvider, generation)
    }''')

# A legacy Jinhak-authenticated callback can no longer approve the session.
on_auth_marker = "    private fun onStartupProviderAuthenticated(expectedProvider: ProviderId, generation: Int) {\n"
on_auth_guard = on_auth_marker + '''        if (expectedProvider == ProviderId.JINHAK) {
            enterJinhakUserSessionGate("legacy-startup-auth-callback-suppressed")
            return
        }
'''
if on_auth_guard not in text:
    text = replace_once(text, on_auth_marker, on_auth_guard, "onStartupProviderAuthenticated Jinhak guard")

# Any stored credential auto-login call for Jinhak is rejected before vault access or JS submission.
text = inject_after_function_open(
    text,
    "attemptSavedCredentialLogin",
    '''        if (which == ProviderId.JINHAK) {
            enterJinhakUserSessionGate("saved-credential-login-disabled:$reason")
            return
        }''',
    "saved-credential-login-disabled:$reason",
)

# Generic provider switches may restore Adiga lease metadata, never Jinhak lease metadata.
text = replace_all(
    text,
    "        val restoredLease = runCatching { sessionVault.restore(which.wireName) }.getOrNull()\n",
    "        val restoredLease = if (which == ProviderId.JINHAK) null else runCatching { sessionVault.restore(which.wireName) }.getOrNull()\n",
    "generic Jinhak lease restore suppression",
)

# Direct Jinhak lease restores are disabled in automatic bootstrap / process-resume paths.
text = text.replace(
    "        val storedJinhak = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()\n",
    "        val storedJinhak: SecureSessionVault.SessionLeaseSummary? = null\n",
)
text = text.replace(
    "        val restoredJinhak = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()\n",
    "        val restoredJinhak: SecureSessionVault.SessionLeaseSummary? = null\n",
)
text = text.replace(
    "            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()\n",
    "            val lease: SecureSessionVault.SessionLeaseSummary? = null\n",
)

# Never capture Jinhak auth-lease metadata. Adiga capture remains unchanged.
text = text.replace(
    "        if (currentUrl.isNotBlank()) runCatching { sessionVault.captureAuthenticated(expectedProvider.wireName, currentUrl, VERSION) }\n",
    "        if (expectedProvider == ProviderId.ADIGA && currentUrl.isNotBlank()) runCatching { sessionVault.captureAuthenticated(expectedProvider.wireName, currentUrl, VERSION) }\n",
)
# Any direct legacy capture is removed.
text = text.replace(
    "        runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }\n",
    "        // v0.17.1: Jinhak auth/session lease capture disabled; user owns the browser session.\n",
)

# startUnified bootstrap does not restore Jinhak lease and starts with no app auth assertion.
text = text.replace(
    "        startupLoginJinhakRestoredLease = restoredJinhak?.restored == true\n",
    "        startupLoginJinhakRestoredLease = false\n",
)
text = text.replace(
    "        startupLoginJinhakRestoredLease = storedJinhak?.restored == true\n",
    "        startupLoginJinhakRestoredLease = false\n",
)

# Selected-six recovery must also wait for the user's explicit session assertion instead of probing core.
selected_old = '''        jinhakTransitionAuthGateActive = true
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "selected-six-recovery-auth-gate"
'''
selected_new = '''        jinhakTransitionAuthGateActive = false
        jinhakUserSessionConfirmed = false
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "v0171-selected-six-user-session-gate"
'''
text = text.replace(selected_old, selected_new)
selected_status = '        status.text = "선택한 6장 중 누락된 report lane만 보강하기 위해 진학사 보호경로 인증을 확인합니다."\n'
if selected_status in text and "selected-six-recovery-user-session" not in text:
    text = text.replace(
        selected_status,
        '''        status.text = "선택한 6장 보강도 사용자 진학사 로그인 세션만 사용합니다. 아래 사이트에서 로그인 완료 후 버튼을 누르세요."
        enterJinhakUserSessionGate("selected-six-recovery-user-session")
        if (!isProviderUrl(webView.url.orEmpty())) webView.loadUrl(ProviderId.JINHAK.homeUrl)
        return
''',
        1,
    )

# Diagnostics explicitly distinguish compatibility auth flag from user authority.
diag_old = '                    .put("jinhakAuthModel", "server-owned-no-dom-probe-v0170")\n'
diag_new = '''                    .put("jinhakAuthModel", "user-owned-session-login-assumed-v0171")
                    .put("jinhakSessionAuthority", "user")
                    .put("userSessionConfirmed", jinhakUserSessionConfirmed)
                    .put("userSessionGateEntries", jinhakUserSessionGateEntries)
                    .put("userSessionConfirmations", jinhakUserSessionConfirmations)
                    .put("userSessionPauses", jinhakUserSessionPauses)
                    .put("collectorVerifiesLogin", false)
                    .put("collectorRestoresJinhakAuthLease", false)
                    .put("collectorCapturesJinhakAuthLease", false)
                    .put("collectorExtendsJinhakSession", false)
'''
text = text.replace(diag_old, diag_new)

# Compatibility strings in status/diagnostic metadata should not claim app verification.
text = text.replace("server-owned-no-dom-probe-v0170", "user-owned-session-login-assumed-v0171")

MAIN.write_text(text)
print("v0.17.1 user-owned Jinhak session + expanded browser patch applied")
