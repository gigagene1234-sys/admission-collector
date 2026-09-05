from pathlib import Path

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

# -----------------------------------------------------------------------------
# v0.9.17 — Real Jinhak Auth Gate
#
# Single goal: replace the startup Jinhak home/login preflight ping-pong with a
# bounded auth-only gate that runs against the REAL www.jinhak.com protected Susi
# route in the device WebView. It uses only the existing encrypted CredentialVault
# on-device; no credentials/cookies/tokens/form values are exported.
#
# The prior mission/renderer/stall/same-card logic is intentionally preserved.
# -----------------------------------------------------------------------------

# UI field.
field_anchor = '''    private lateinit var diagnosticButton: Button
    private lateinit var unifiedButton: Button
'''
field_new = '''    private lateinit var diagnosticButton: Button
    private lateinit var unifiedButton: Button
    private lateinit var realJinhakAuthProbeButton: Button
'''
if field_anchor not in m:
    raise SystemExit('v0.9.17 UI field anchor not found')
m = m.replace(field_anchor, field_new, 1)

# Auth-gate runtime state. All stored/exported routes are sanitized host/path only.
auth_field_anchor = '''    private var jinhakLastTargetAuthRedirectSafePath = ""

    companion object {
'''
auth_fields = '''    private var jinhakLastTargetAuthRedirectSafePath = ""
    private var jinhakRealAuthProbeActive = false
    private var jinhakRealAuthProbeAutoContinue = false
    private var jinhakRealAuthProbeGeneration = 0
    private var jinhakRealAuthProbeStartedAtMs = 0L
    private var jinhakRealAuthProbeVerifiedAtMs = 0L
    private var jinhakRealAuthProbeStablePasses = 0
    private var jinhakRealAuthProbeCoreLoads = 0
    private var jinhakRealAuthProbeLoginRoutes = 0
    private var jinhakRealAuthProbeUnexpectedRoutes = 0
    private var jinhakRealAuthProbeCycleDetections = 0
    private var jinhakRealAuthProbeResult = "never-run"
    private var jinhakRealAuthProbeRouteCycleDetected = false
    private var jinhakRealAuthProbeLastSafePath = ""
    private val jinhakRealAuthProbeRouteHistory = ArrayDeque<String>()
    private val jinhakRealAuthProbeRouteCounts = linkedMapOf<String, Int>()
    private var jinhakRealAuthProbeRouteEvents = JSONArray()
    private var jinhakRealAuthProbeBaselineSurfaceDetections = 0
    private var jinhakRealAuthProbeBaselineAutoAttempts = 0
    private var jinhakRealAuthProbeBaselineAutoSubmissions = 0
    private var jinhakRealAuthProbeBaselineAutoSuccesses = 0
    private var jinhakRealAuthProbeBaselineAutoFailures = 0

    companion object {
'''
if auth_field_anchor not in m:
    raise SystemExit('v0.9.17 auth field anchor not found')
m = m.replace(auth_field_anchor, auth_fields, 1)

const_anchor = '''        private const val MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES = 2
        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L
'''
const_new = '''        private const val MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES = 2
        private const val JINHAK_REAL_AUTH_PROBE_TIMEOUT_MS = 90_000L
        private const val JINHAK_REAL_AUTH_PROBE_FRESH_MS = 300_000L
        private const val MAX_JINHAK_REAL_AUTH_ROUTE_TRANSITIONS = 14
        private const val MAX_JINHAK_REAL_AUTH_ROUTE_REVISITS = 4
        private const val MAX_JINHAK_REAL_AUTH_UNEXPECTED_ROUTES = 3
        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L
'''
if const_anchor not in m:
    raise SystemExit('v0.9.17 const anchor not found')
m = m.replace(const_anchor, const_new, 1)

# App launch now starts the bounded real-site auth gate first. Interrupted unified
# sessions still use the existing resume path and are NOT forced through this gate.
launch_old = '''            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {
                handler.postDelayed({ startAutomaticLoginAndCollectionSequence("app-launch") }, 350L)
            } else {
'''
launch_new = '''            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {
                handler.postDelayed({ startJinhakRealAuthProbe(autoContinue = true, trigger = "app-launch") }, 350L)
            } else {
'''
if launch_old not in m:
    raise SystemExit('v0.9.17 launch anchor not found')
m = m.replace(launch_old, launch_new, 1)

# Add a dedicated real-site auth-only diagnostic button. It never starts data
# collection unless autoContinue was explicitly requested by the automatic flow.
actions_anchor = '''        diagnosticButton = Button(this).apply {
            text = "진학사 전체 분석 전송"
            setOnClickListener {
                if (provider == ProviderId.JINHAK) sendLatestJinhakAnalysisDigest() else sendLatestLocalDiagnostic(manual = true)
            }
        }
        actions3.addView(unifiedButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions3.addView(diagnosticButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
'''
actions_new = '''        diagnosticButton = Button(this).apply {
            text = "진학사 전체 분석 전송"
            setOnClickListener {
                if (provider == ProviderId.JINHAK) sendLatestJinhakAnalysisDigest() else sendLatestLocalDiagnostic(manual = true)
            }
        }
        realJinhakAuthProbeButton = Button(this).apply {
            text = "진학사 실제 로그인 진단"
            setOnClickListener {
                if (jinhakRealAuthProbeActive) {
                    finishJinhakRealAuthProbe("user-cancel", success = false)
                } else {
                    startJinhakRealAuthProbe(autoContinue = false, trigger = "manual-auth-probe")
                }
            }
        }
        actions3.addView(unifiedButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions3.addView(diagnosticButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions3.addView(realJinhakAuthProbeButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
'''
if actions_anchor not in m:
    raise SystemExit('v0.9.17 actions anchor not found')
m = m.replace(actions_anchor, actions_new, 1)

# Route-transition capture happens at WebView start, before page-finished logic can
# schedule any auth action. Repeated A-B-A-B transitions are therefore observable.
started_anchor = '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                persistRuntimeCheckpoint()
'''
started_new = '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                if (jinhakRealAuthProbeActive && provider == ProviderId.JINHAK) {
                    noteJinhakRealAuthProbeRoute(url, "page-started")
                }
                persistRuntimeCheckpoint()
'''
if started_anchor not in m:
    raise SystemExit('v0.9.17 onPageStarted anchor not found')
m = m.replace(started_anchor, started_new, 1)

# Existing passive DOM detector still runs. The real-auth gate then owns all other
# navigation decisions until it succeeds/fails; startup/batch state machines cannot
# concurrently redirect the WebView.
finished_anchor = '''                scheduleLoginSurfaceDetection(provider, "page-finished")
                if (startupLoginPreflightActive) {
'''
finished_new = '''                scheduleLoginSurfaceDetection(provider, "page-finished")
                if (jinhakRealAuthProbeActive && provider == ProviderId.JINHAK) {
                    handleJinhakRealAuthProbePageFinished(url)
                    return
                }
                if (startupLoginPreflightActive) {
'''
if finished_anchor not in m:
    raise SystemExit('v0.9.17 onPageFinished anchor not found')
m = m.replace(finished_anchor, finished_new, 1)

# During the real auth probe, the post-submit callback must not enter the normal
# batch/startup Jinhak recovery state machine. The protected core is the only proof.
post_submit_anchor = '''                        if (authenticated) {
                            credentialLoginSurfaceAttempts = 0
                            val url = webView.url.orEmpty()
                            if (url.isNotBlank()) runCatching { sessionVault.captureAuthenticated(which.wireName, url, VERSION) }
                            if (batchRunning && batchPausedForLogin) resumeAfterLogin()
                            if (startupLoginPreflightActive && provider == which) {
                                val generation = startupLoginPollGeneration
                                onStartupProviderAuthenticated(which, generation)
                            }
                        } else if (needsLogin) {
                            scheduleLoginSurfaceDetection(which, "post-submit")
                            if (which == ProviderId.JINHAK) scheduleJinhakLoginRecovery("post-submit-needs-login")
                        } else if (which == ProviderId.JINHAK) {
                            scheduleJinhakLoginRecovery("post-submit-provider-verification")
                        }
'''
post_submit_new = '''                        if (jinhakRealAuthProbeActive && which == ProviderId.JINHAK) {
                            credentialLoginSurfaceAttempts = if (authenticated) 0 else credentialLoginSurfaceAttempts
                            scheduleJinhakRealAuthProbePoll(jinhakRealAuthProbeGeneration, 250L)
                            return@checkSessionState
                        }
                        if (authenticated) {
                            credentialLoginSurfaceAttempts = 0
                            val url = webView.url.orEmpty()
                            if (url.isNotBlank()) runCatching { sessionVault.captureAuthenticated(which.wireName, url, VERSION) }
                            if (batchRunning && batchPausedForLogin) resumeAfterLogin()
                            if (startupLoginPreflightActive && provider == which) {
                                val generation = startupLoginPollGeneration
                                onStartupProviderAuthenticated(which, generation)
                            }
                        } else if (needsLogin) {
                            scheduleLoginSurfaceDetection(which, "post-submit")
                            if (which == ProviderId.JINHAK) scheduleJinhakLoginRecovery("post-submit-needs-login")
                        } else if (which == ProviderId.JINHAK) {
                            scheduleJinhakLoginRecovery("post-submit-provider-verification")
                        }
'''
if post_submit_anchor not in m:
    raise SystemExit('v0.9.17 post-submit anchor not found')
m = m.replace(post_submit_anchor, post_submit_new, 1)

# Full real-site auth probe implementation. No fake server and no proactive login
# URL load: first navigation is the live read-only protected saved-application route.
probe_insert_anchor = '''    private fun startAutomaticLoginAndCollectionSequence(trigger: String) {
'''
probe_impl = r'''    private fun isFreshJinhakRealAuthProbe(): Boolean {
        if (jinhakRealAuthProbeVerifiedAtMs <= 0L || jinhakRealAuthProbeResult != "protected-core-stable") return false
        return System.currentTimeMillis() - jinhakRealAuthProbeVerifiedAtMs <= JINHAK_REAL_AUTH_PROBE_FRESH_MS
    }

    private fun classifyJinhakRealAuthRoute(rawUrl: String): String {
        val canonical = canonicalizeBatchUrl(rawUrl)
        val core = canonicalizeBatchUrl(JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty())
        return when {
            isProviderLoginUrl(ProviderId.JINHAK, rawUrl) -> "login"
            core.isNotBlank() && canonical == core -> "protected-core"
            rawUrl.contains("/jh/high3/", ignoreCase = true) -> "high3"
            rawUrl.contains("/jh/high1/", ignoreCase = true) || rawUrl.contains("/jh/high2/", ignoreCase = true) || rawUrl.contains("/jh/high12/", ignoreCase = true) -> "high12"
            else -> "other"
        }
    }

    private fun noteJinhakRealAuthProbeRoute(rawUrl: String, source: String) {
        if (!jinhakRealAuthProbeActive || provider != ProviderId.JINHAK) return
        val safePath = runtimeSafePath(rawUrl).take(300)
        if (safePath.isBlank() || safePath == jinhakRealAuthProbeLastSafePath) return
        jinhakRealAuthProbeLastSafePath = safePath
        val kind = classifyJinhakRealAuthRoute(rawUrl)
        if (kind == "login") jinhakRealAuthProbeLoginRoutes += 1
        jinhakRealAuthProbeRouteCounts[safePath] = (jinhakRealAuthProbeRouteCounts[safePath] ?: 0) + 1
        jinhakRealAuthProbeRouteHistory.addLast(safePath)
        while (jinhakRealAuthProbeRouteHistory.size > 8) jinhakRealAuthProbeRouteHistory.removeFirst()
        jinhakRealAuthProbeRouteEvents.put(JSONObject()
            .put("elapsedMs", (System.currentTimeMillis() - jinhakRealAuthProbeStartedAtMs).coerceAtLeast(0L))
            .put("safePath", safePath)
            .put("kind", kind)
            .put("source", source.take(40)))

        val history = jinhakRealAuthProbeRouteHistory.toList()
        val n = history.size
        val abab = n >= 4 && history[n - 4] == history[n - 2] && history[n - 3] == history[n - 1] && history[n - 4] != history[n - 3]
        val revisits = jinhakRealAuthProbeRouteCounts[safePath] ?: 0
        val tooManyTransitions = jinhakRealAuthProbeRouteEvents.length() >= MAX_JINHAK_REAL_AUTH_ROUTE_TRANSITIONS
        if (abab || revisits >= MAX_JINHAK_REAL_AUTH_ROUTE_REVISITS || tooManyTransitions) {
            jinhakRealAuthProbeCycleDetections += 1
            jinhakRealAuthProbeRouteCycleDetected = true
            recordRuntimeEvent("jinhak-real-auth-route-cycle", JSONObject()
                .put("safePath", safePath)
                .put("kind", kind)
                .put("abab", abab)
                .put("revisits", revisits)
                .put("transitions", jinhakRealAuthProbeRouteEvents.length())
                .put("actualSite", true))
            finishJinhakRealAuthProbe("auth-route-cycle-detected", success = false)
        }
    }

    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        if (jinhakRealAuthProbeActive) return
        if (unifiedRunning || batchRunning || startupLoginPreflightActive) {
            Toast.makeText(this, "진행 중인 수집/로그인 준비가 있어 실제 진학사 로그인 진단을 시작할 수 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
        if (coreProbe.isBlank()) {
            status.text = "진학사 보호 경로가 정의되지 않아 실제 로그인 진단을 시작할 수 없습니다."
            return
        }
        provider = ProviderId.JINHAK
        jinhakRealAuthProbeActive = true
        jinhakRealAuthProbeAutoContinue = autoContinue
        val generation = ++jinhakRealAuthProbeGeneration
        jinhakRealAuthProbeStartedAtMs = System.currentTimeMillis()
        jinhakRealAuthProbeStablePasses = 0
        jinhakRealAuthProbeCoreLoads = 1
        jinhakRealAuthProbeLoginRoutes = 0
        jinhakRealAuthProbeUnexpectedRoutes = 0
        jinhakRealAuthProbeCycleDetections = 0
        jinhakRealAuthProbeResult = "running"
        jinhakRealAuthProbeRouteCycleDetected = false
        jinhakRealAuthProbeLastSafePath = ""
        jinhakRealAuthProbeRouteHistory.clear()
        jinhakRealAuthProbeRouteCounts.clear()
        jinhakRealAuthProbeRouteEvents = JSONArray()
        jinhakRealAuthProbeBaselineSurfaceDetections = credentialLoginSurfaceDetections
        jinhakRealAuthProbeBaselineAutoAttempts = credentialAutoLoginAttempts
        jinhakRealAuthProbeBaselineAutoSubmissions = credentialAutoLoginSubmissions
        jinhakRealAuthProbeBaselineAutoSuccesses = credentialAutoLoginSuccesses
        jinhakRealAuthProbeBaselineAutoFailures = credentialAutoLoginFailures
        startupCredentialPromptedProvider = null
        credentialLoginSurfaceKey = ""
        credentialLoginSurfaceAttempts = 0
        credentialAwaitingLoginExitProvider = null
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "real-site-auth-probe"
        jinhakLastAuthEvidence = "real-site-probe-pending"
        runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }
        CookieManager.getInstance().flush()
        realJinhakAuthProbeButton.text = "진학사 로그인 진단 중지"
        unifiedButton.isEnabled = false
        sessionState.text = "△ 실제 진학사 보호 경로 인증 확인 중"
        status.text = "실제 www.jinhak.com 수시저장소를 열어 로그인→고3 영역 경로를 진단합니다. 로그인 URL을 강제로 열지 않습니다."
        recordRuntimeEvent("jinhak-real-auth-probe-start", JSONObject()
            .put("trigger", trigger.take(60))
            .put("actualSite", true)
            .put("coreSafePath", runtimeSafePath(coreProbe))
            .put("credentialStored", credentialVault.has(ProviderId.JINHAK.wireName))
            .put("credentialExported", false)
            .put("sessionSecretExported", false))
        webView.loadUrl(coreProbe)
        handler.postDelayed({
            if (jinhakRealAuthProbeActive && generation == jinhakRealAuthProbeGeneration) {
                finishJinhakRealAuthProbe("auth-probe-timeout", success = false)
            }
        }, JINHAK_REAL_AUTH_PROBE_TIMEOUT_MS)
    }

    private fun scheduleJinhakRealAuthProbePoll(generation: Int, delayMs: Long = 1_500L) {
        handler.postDelayed({
            if (!jinhakRealAuthProbeActive || generation != jinhakRealAuthProbeGeneration || provider != ProviderId.JINHAK) return@postDelayed
            handleJinhakRealAuthProbePageFinished(webView.url.orEmpty())
        }, delayMs)
    }

    private fun handleJinhakRealAuthProbePageFinished(url: String) {
        if (!jinhakRealAuthProbeActive || provider != ProviderId.JINHAK) return
        val generation = jinhakRealAuthProbeGeneration
        if (System.currentTimeMillis() - jinhakRealAuthProbeStartedAtMs >= JINHAK_REAL_AUTH_PROBE_TIMEOUT_MS) {
            finishJinhakRealAuthProbe("auth-probe-timeout", success = false)
            return
        }
        val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
        val coreCanonical = canonicalizeBatchUrl(coreProbe)
        val currentCanonical = canonicalizeBatchUrl(url)

        probeLoginSurface(ProviderId.JINHAK) { probe ->
            if (!jinhakRealAuthProbeActive || generation != jinhakRealAuthProbeGeneration) return@probeLoginSurface
            val currentUrl = webView.url.orEmpty()
            val loginRoute = isProviderLoginUrl(ProviderId.JINHAK, currentUrl)
            if (loginRoute || probe.optBoolean("detected", false)) {
                jinhakRealAuthProbeStablePasses = 0
                sessionState.text = "○ 실제 진학사 통합회원 로그인 단계"
                if (credentialVault.has(ProviderId.JINHAK.wireName)) {
                    status.text = "실제 진학사 로그인 폼을 기다리며, 렌더링된 경우에만 기기 저장 계정으로 로그인합니다."
                    if (probe.optBoolean("detected", false)) attemptSavedCredentialLogin(ProviderId.JINHAK, "real-auth-probe")
                    else scheduleLoginSurfaceDetection(ProviderId.JINHAK, "real-auth-probe-login-route")
                } else if (startupCredentialPromptedProvider != ProviderId.JINHAK) {
                    startupCredentialPromptedProvider = ProviderId.JINHAK
                    status.text = "실제 진학사 로그인이 필요합니다. 이 기기에만 암호화 저장할 계정정보를 한 번 입력해주세요."
                    showCredentialDialog(ProviderId.JINHAK, continueAfterSave = true)
                }
                scheduleJinhakRealAuthProbePoll(generation)
                return@probeLoginSurface
            }

            if (currentCanonical.isNotBlank() && currentCanonical == coreCanonical) {
                checkSessionState { needsLogin, _ ->
                    if (!jinhakRealAuthProbeActive || generation != jinhakRealAuthProbeGeneration) return@checkSessionState
                    if (!needsLogin && !isProviderLoginUrl(ProviderId.JINHAK, webView.url.orEmpty())) {
                        jinhakRealAuthProbeStablePasses += 1
                        if (jinhakRealAuthProbeStablePasses >= JINHAK_CORE_AUTH_STABLE_PASSES) {
                            finishJinhakRealAuthProbe("protected-core-stable", success = true)
                        } else {
                            sessionState.text = "△ 실제 수시저장소 접근 확인 · 안정성 재검증 중"
                            scheduleJinhakRealAuthProbePoll(generation, 650L)
                        }
                    } else {
                        jinhakRealAuthProbeStablePasses = 0
                        scheduleJinhakRealAuthProbePoll(generation)
                    }
                }
                return@probeLoginSurface
            }

            // Real Jinhak can land on a high3/high12/general page after login. The auth
            // probe is allowed to return to the protected core only a bounded number of
            // times; route cycling itself is detected separately by page-started history.
            jinhakRealAuthProbeStablePasses = 0
            jinhakRealAuthProbeUnexpectedRoutes += 1
            if (jinhakRealAuthProbeUnexpectedRoutes >= MAX_JINHAK_REAL_AUTH_UNEXPECTED_ROUTES) {
                finishJinhakRealAuthProbe("unexpected-auth-route-loop", success = false)
                return@probeLoginSurface
            }
            if (coreProbe.isNotBlank()) {
                jinhakRealAuthProbeCoreLoads += 1
                status.text = "진학사 로그인 후 다른 영역으로 이동했습니다. 실제 수시저장소 보호 경로로 제한 복귀해 인증 여부를 확인합니다."
                handler.postDelayed({
                    if (jinhakRealAuthProbeActive && generation == jinhakRealAuthProbeGeneration) webView.loadUrl(coreProbe)
                }, 500L)
            }
        }
    }

    private fun finishJinhakRealAuthProbe(result: String, success: Boolean) {
        if (!jinhakRealAuthProbeActive) return
        val autoContinue = jinhakRealAuthProbeAutoContinue
        jinhakRealAuthProbeActive = false
        jinhakRealAuthProbeAutoContinue = false
        ++jinhakRealAuthProbeGeneration
        jinhakRealAuthProbeResult = result.take(80)
        if (success) {
            jinhakRealAuthProbeVerifiedAtMs = System.currentTimeMillis()
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "real-protected-core-verified"
            jinhakLastAuthEvidence = "real-protected-core-stable"
            jinhakLastCoreVerifiedAtMs = jinhakRealAuthProbeVerifiedAtMs
            val current = webView.url.orEmpty()
            if (current.isNotBlank()) runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, current, VERSION) }
        } else {
            jinhakAuthVerifiedForBatch = false
            jinhakCoreBootstrapState = "real-auth-probe-failed"
            jinhakLastAuthEvidence = result.take(80)
            runCatching { webView.stopLoading() }
        }
        realJinhakAuthProbeButton.text = "진학사 실제 로그인 진단"
        unifiedButton.isEnabled = true
        val output = JSONObject()
            .put("schemaVersion", 1)
            .put("type", "jinhak-real-auth-probe")
            .put("collectorVersion", VERSION)
            .put("actualSite", true)
            .put("siteHost", "www.jinhak.com")
            .put("result", result.take(80))
            .put("success", success)
            .put("durationMs", (System.currentTimeMillis() - jinhakRealAuthProbeStartedAtMs).coerceAtLeast(0L))
            .put("protectedCoreStablePasses", jinhakRealAuthProbeStablePasses)
            .put("protectedCoreLoads", jinhakRealAuthProbeCoreLoads)
            .put("loginRouteTransitions", jinhakRealAuthProbeLoginRoutes)
            .put("unexpectedRouteTransitions", jinhakRealAuthProbeUnexpectedRoutes)
            .put("routeCycleDetections", jinhakRealAuthProbeCycleDetections)
            .put("routeCycleDetected", jinhakRealAuthProbeRouteCycleDetected)
            .put("routeTransitions", jinhakRealAuthProbeRouteEvents)
            .put("credentialStored", credentialVault.has(ProviderId.JINHAK.wireName))
            .put("loginSurfaceDetectionsDelta", (credentialLoginSurfaceDetections - jinhakRealAuthProbeBaselineSurfaceDetections).coerceAtLeast(0))
            .put("credentialAutoLoginAttemptsDelta", (credentialAutoLoginAttempts - jinhakRealAuthProbeBaselineAutoAttempts).coerceAtLeast(0))
            .put("credentialAutoLoginSubmissionsDelta", (credentialAutoLoginSubmissions - jinhakRealAuthProbeBaselineAutoSubmissions).coerceAtLeast(0))
            .put("credentialAutoLoginSuccessesDelta", (credentialAutoLoginSuccesses - jinhakRealAuthProbeBaselineAutoSuccesses).coerceAtLeast(0))
            .put("credentialAutoLoginFailuresDelta", (credentialAutoLoginFailures - jinhakRealAuthProbeBaselineAutoFailures).coerceAtLeast(0))
            .put("credentialExported", false)
            .put("cookieExported", false)
            .put("sessionStorageExported", false)
            .put("localStorageExported", false)
            .put("formValuesExported", false)
            .put("routePrivacy", "sanitized-host-path-only-no-query")
        lastJson = output.toString(2)
        showPreview(lastJson)
        recordRuntimeEvent("jinhak-real-auth-probe-finish", JSONObject()
            .put("result", result.take(80))
            .put("success", success)
            .put("actualSite", true)
            .put("routeCycleDetected", jinhakRealAuthProbeRouteCycleDetected)
            .put("transitions", jinhakRealAuthProbeRouteEvents.length())
            .put("credentialExported", false))
        sessionState.text = if (success) "● 실제 진학사 수시저장소 인증 확인 완료" else "△ 실제 진학사 로그인 진단 종료"
        status.text = if (success) {
            "실제 진학사 보호 경로 인증을 확인했습니다. 이후 자동 준비에서는 진학사 홈을 다시 열지 않고 이 최신 인증 증거를 사용합니다."
        } else {
            "진학사 실제 로그인 진단: $result · 전체 수집을 시작하지 않았습니다. JSON 저장으로 짧은 인증 경로 로그를 확인할 수 있습니다."
        }
        if (success && autoContinue) {
            handler.postDelayed({
                if (!unifiedRunning && !batchRunning && !startupLoginPreflightActive) {
                    startAutomaticLoginAndCollectionSequence("real-jinhak-auth-probe")
                }
            }, 250L)
        }
    }

''' + probe_insert_anchor
if probe_insert_anchor not in m:
    raise SystemExit('v0.9.17 probe insertion anchor not found')
m = m.replace(probe_insert_anchor, probe_impl, 1)

# When the startup sequence reaches Jinhak shortly after the real protected-core
# probe, reuse that proof and DO NOT load Jinhak home. This removes the observed
# high3/high12/login landing ping-pong from startup.
begin_provider_anchor = '''        if (which == ProviderId.ADIGA) {
            startupLoginAdigaRestoredLease = lease?.restored == true
        } else {
            startupLoginJinhakRestoredLease = lease?.restored == true
        }
        sessionState.text = if (lease?.restored == true) {
'''
begin_provider_new = '''        if (which == ProviderId.ADIGA) {
            startupLoginAdigaRestoredLease = lease?.restored == true
        } else {
            startupLoginJinhakRestoredLease = lease?.restored == true
        }
        if (which == ProviderId.JINHAK && isFreshJinhakRealAuthProbe()) {
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "real-protected-core-verified"
            jinhakLastAuthEvidence = "real-protected-core-stable"
            jinhakLastCoreVerifiedAtMs = jinhakRealAuthProbeVerifiedAtMs
            recordRuntimeEvent("startup-jinhak-real-auth-proof-reused", JSONObject()
                .put("ageMs", (System.currentTimeMillis() - jinhakRealAuthProbeVerifiedAtMs).coerceAtLeast(0L))
                .put("homeNavigationSkipped", true)
                .put("actualSite", true))
            sessionState.text = "● 실제 진학사 수시저장소 인증 증거 재사용"
            status.text = "진학사 실제 보호 경로 인증이 방금 확인되어 홈/고3 전환 페이지를 다시 열지 않습니다."
            onStartupProviderAuthenticated(which, generation)
            return
        }
        sessionState.text = if (lease?.restored == true) {
'''
if begin_provider_anchor not in m:
    raise SystemExit('v0.9.17 begin provider anchor not found')
m = m.replace(begin_provider_anchor, begin_provider_new, 1)

# Manual unified start also uses the actual-site gate first unless a fresh proof
# already exists.
start_unified_old = '''    private fun startUnifiedCollection() {
        if (!startupLoginPreflightVerified) {
            startAutomaticLoginAndCollectionSequence("manual-start")
            return
        }
        startUnifiedCollectionAuthenticated()
    }
'''
start_unified_new = '''    private fun startUnifiedCollection() {
        if (!startupLoginPreflightVerified) {
            if (isFreshJinhakRealAuthProbe()) {
                startAutomaticLoginAndCollectionSequence("manual-start-fresh-real-auth")
            } else {
                startJinhakRealAuthProbe(autoContinue = true, trigger = "manual-start")
            }
            return
        }
        startUnifiedCollectionAuthenticated()
    }
'''
if start_unified_old not in m:
    raise SystemExit('v0.9.17 start unified anchor not found')
m = m.replace(start_unified_old, start_unified_new, 1)

# PRECHECK carries the real-site proof outcome so a later full export remains
# diagnosable even though the auth-only probe happened before the unified session.
precheck_anchor = '''                    .put("jinhakReauthCycles", jinhakReauthCycles)
                    .put("credentialExported", false)),
'''
precheck_new = '''                    .put("jinhakReauthCycles", jinhakReauthCycles)
                    .put("realJinhakAuthProbeResult", jinhakRealAuthProbeResult.take(80))
                    .put("realJinhakAuthProbeVerified", isFreshJinhakRealAuthProbe())
                    .put("realJinhakAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)
                    .put("realJinhakAuthRouteCycleDetected", jinhakRealAuthProbeRouteCycleDetected)
                    .put("realJinhakAuthRouteTransitions", jinhakRealAuthProbeRouteEvents.length())
                    .put("credentialExported", false)),
'''
if precheck_anchor not in m:
    raise SystemExit('v0.9.17 PRECHECK anchor not found')
m = m.replace(precheck_anchor, precheck_new, 1)

# Keep auth diagnostics aware of the new gate without exporting route queries or
# credentials. This is small boolean/counter telemetry only.
auth_diag_anchor = '''                    .put("lastTargetAuthRedirectSafePath", jinhakLastTargetAuthRedirectSafePath.take(300))
                    .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
'''
auth_diag_new = '''                    .put("lastTargetAuthRedirectSafePath", jinhakLastTargetAuthRedirectSafePath.take(300))
                    .put("realJinhakAuthProbeResult", jinhakRealAuthProbeResult.take(80))
                    .put("realJinhakAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)
                    .put("realJinhakAuthRouteCycleDetected", jinhakRealAuthProbeRouteCycleDetected)
                    .put("realJinhakAuthRouteTransitions", jinhakRealAuthProbeRouteEvents.length())
                    .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
'''
if auth_diag_anchor not in m:
    raise SystemExit('v0.9.17 auth diagnostics anchor not found')
m = m.replace(auth_diag_anchor, auth_diag_new, 1)

# Version metadata only beyond the auth-gate code.
m = m.replace('private const val VERSION = "0.9.16"', 'private const val VERSION = "0.9.17"', 1)
m = m.replace('private const val BUILD_CODE = 109160', 'private const val BUILD_CODE = 109170', 1)
g = g.replace('versionCode = 109160', 'versionCode = 109170', 1)
g = g.replace('versionName = "0.9.16"', 'versionName = "0.9.17"', 1)
manifest = manifest.replace(
    'Admission Collector v0.9.16 Target Auth Redirect Guard',
    'Admission Collector v0.9.17 Real Jinhak Auth Gate',
    1
)

# Postconditions: the new gate exists while all prior safety/stability layers stay.
required = {
    'version': 'private const val VERSION = "0.9.17"' in m and 'private const val BUILD_CODE = 109170' in m,
    'real-core-gate': 'startJinhakRealAuthProbe' in m and 'jinhak-real-auth-probe' in m,
    'no-forced-login': 'webView.loadUrl(providerLoginUrl' not in m,
    'cycle-detection': 'auth-route-cycle-detected' in m and 'MAX_JINHAK_REAL_AUTH_ROUTE_TRANSITIONS' in m,
    'fresh-proof-reuse': 'startup-jinhak-real-auth-proof-reused' in m and 'homeNavigationSkipped' in m,
    'actual-site': '"www.jinhak.com"' in m and 'actualSite' in m,
    'probe-button': '진학사 실제 로그인 진단' in m,
    'privacy': 'sanitized-host-path-only-no-query' in m and '.put("credentialExported", false)' in m,
    'v0916-preserved': 'quarantineJinhakTargetSpecificAuthRedirect' in m and 'MAX_JINHAK_TARGET_AUTH_REDIRECT_CYCLES = 2' in m,
    'mission-stall-preserved': 'recoverOrStopJinhakMissionStall' in m and 'MAX_JINHAK_MISSION_STALL_RECOVERIES = 2' in m,
    'same-card-preserved': 'MAX_JINHAK_SAME_CARD_REPLAY_ATTEMPTS = 3' in m,
    'susi-core-preserved': 'isDefaultSusiCoreTraversalUrl' in m,
}
failed = [k for k, ok in required.items() if not ok]
if failed:
    raise SystemExit('v0.9.17 postcondition failed: ' + ', '.join(failed))
if '.put("username", credentials.username)' in m or '.put("password", credentials.password)' in m:
    raise SystemExit('credential export invariant failed')

main_path.write_text(m)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('Applied v0.9.17 Real Jinhak Auth Gate patch')
