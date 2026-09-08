from pathlib import Path

p=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s=p.read_text()

# Product identity.
s=s.replace('private const val VERSION = "0.16.1"', 'private const val VERSION = "0.16.2"', 1)
s=s.replace('private const val BUILD_CODE = 116100', 'private const val BUILD_CODE = 116200', 1)

# Per-run latch/counter. The latch is the important state-machine fix: once an unsafe lower-grade
# login context is observed, no login recovery callback may reopen or poll that page again.
anchor='''    private var jinhakDomLowerGradeBlocks = 0
'''
insert='''    private var jinhakDomLowerGradeBlocks = 0
    private var jinhakLowerGradeLoginTerminalStops = 0
    private var jinhakLowerGradeLoginFenceLatched = false
'''
if s.count(anchor)!=1: raise SystemExit('counter anchor mismatch')
s=s.replace(anchor,insert,1)

# Direct lower-grade navigation must never bounce back and forth between blocked route and high3.
old='''                if (target.isNotBlank() && jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                    jinhakLowerGradeNavigationsBlocked += 1
                    recordRuntimeEvent("jinhak-lower-grade-navigation-blocked", JSONObject()
                        .put("targetSafePath", runtimeSafePath(target))
                        .put("currentSafePath", runtimeSafePath(view.url.orEmpty()))
                        .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core())))
                    status.text = "진학사 고1·고2 화면 이동 차단 · 고3 세션을 그대로 유지합니다."
                    return true
                }
'''
new='''                if (target.isNotBlank() && jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                    jinhakLowerGradeNavigationsBlocked += 1
                    recordRuntimeEvent("jinhak-lower-grade-navigation-blocked", JSONObject()
                        .put("targetSafePath", runtimeSafePath(target))
                        .put("currentSafePath", runtimeSafePath(view.url.orEmpty()))
                        .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core())))
                    if (jinhakLowerGradeAuthFenceShouldTerminate()) {
                        terminateJinhakLowerGradeLoginLoop("lower-grade-navigation", JSONObject().put("targetSafePath", runtimeSafePath(target)))
                    } else {
                        status.text = "진학사 고1·고2 화면 이동 차단 · 현재 고3 세션을 유지합니다."
                    }
                    return true
                }
'''
if s.count(old)!=1: raise SystemExit('shouldOverride lower-grade anchor mismatch')
s=s.replace(old,new,1)

old='''                if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
                    jinhakLowerGradeNavigationsBlocked += 1
                    view.stopLoading()
                    recordRuntimeEvent("jinhak-lower-grade-redirect-stopped", JSONObject()
                        .put("targetSafePath", runtimeSafePath(url))
                        .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core())))
                    status.text = "진학사 고1·고2 리다이렉트 차단 · 로그인 재시도 없이 고3 보호경로로 복귀합니다."
                    val high3 = JinhakGradeRouteFence.protectedHigh3Core()
                    if (high3.isNotBlank()) handler.postDelayed({
                        if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(webView.url.orEmpty())) {
                            webView.loadUrl(high3)
                        }
                    }, 80L)
                    return
                }
'''
new='''                if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
                    jinhakLowerGradeNavigationsBlocked += 1
                    view.stopLoading()
                    recordRuntimeEvent("jinhak-lower-grade-redirect-stopped", JSONObject()
                        .put("targetSafePath", runtimeSafePath(url))
                        .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core())))
                    if (jinhakLowerGradeAuthFenceShouldTerminate()) {
                        terminateJinhakLowerGradeLoginLoop("lower-grade-redirect", JSONObject().put("targetSafePath", runtimeSafePath(url)))
                    } else {
                        status.text = "진학사 고1·고2 리다이렉트 차단 · 해당 페이지를 열지 않고 현재 고3 세션을 유지합니다."
                    }
                    return
                }
'''
if s.count(old)!=1: raise SystemExit('pageStarted lower-grade anchor mismatch')
s=s.replace(old,new,1)

# Do not start DOM login probing in parallel with the product fence. On Jinhak, fence first, then
# start login-surface detection only if the fail-closed latch did not fire.
old='''                if (provider == ProviderId.JINHAK) installJinhakHigh3DomProductFence("page-finished")
                // Probe only after the high3 DOM product fence is armed. Jinhak's login page can
                // switch the product context without changing /jh/member/login, so URL-only fencing
                // is insufficient on real devices.
                scheduleLoginSurfaceDetection(provider, "page-finished")
'''
new='''                if (provider == ProviderId.JINHAK) {
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
                }
'''
if s.count(old)!=1: raise SystemExit('pageFinished login detection anchor mismatch')
s=s.replace(old,new,1)

# Add terminal auth-fence helpers before DOM fence.
anchor='''    private fun installJinhakHigh3DomProductFence(reason: String) {
'''
helper='''    private fun jinhakLowerGradeAuthFenceShouldTerminate(): Boolean {
        if (provider != ProviderId.JINHAK) return false
        val current = if (::webView.isInitialized) webView.url.orEmpty() else ""
        return isProviderLoginUrl(ProviderId.JINHAK, current) ||
            batchPausedForLogin ||
            jinhakTransitionAuthGateActive ||
            startupLoginPreflightActive ||
            jinhakRealAuthProbeActive ||
            credentialAwaitingLoginExitProvider == ProviderId.JINHAK ||
            (unifiedRunning && unifiedPhase == "jinhak" && !jinhakAuthVerifiedForBatch)
    }

    private fun terminateJinhakLowerGradeLoginLoop(source: String, detail: JSONObject = JSONObject()) {
        if (provider != ProviderId.JINHAK || jinhakLowerGradeLoginFenceLatched) return
        jinhakLowerGradeLoginFenceLatched = true
        jinhakLowerGradeLoginTerminalStops += 1

        // Cancel every producer that can reopen/poll the login route. This is intentionally
        // terminal for the current Jinhak phase; the next explicit unified run resets the latch.
        ++credentialLoginSurfaceGeneration
        ++jinhakLoginRecoveryGeneration
        ++startupLoginPollGeneration
        ++jinhakRealAuthProbeGeneration
        credentialAutoLoginInFlight = false
        credentialAwaitingLoginExitProvider = null
        jinhakTransitionAuthGateActive = false
        startupLoginPreflightActive = false
        startupLoginPreflightVerified = false
        jinhakRealAuthProbeActive = false
        unifiedPendingJinhakStart = false
        batchPausedForLogin = false
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "lower-grade-login-terminal-fence"
        jinhakLastAuthEvidence = "lower-grade-login-context-blocked"

        runCatching { webView.stopLoading() }
        runCatching { webView.loadUrl("about:blank") }
        webView.visibility = View.VISIBLE
        if (::unifiedButton.isInitialized) unifiedButton.isEnabled = true

        val event = JSONObject(detail.toString())
            .put("source", source.take(80))
            .put("retrySuppressed", true)
            .put("loginPageReopenAllowed", false)
            .put("adigaOfficialEvidencePreserved", true)
            .put("jinhakPromotedToOfficial", false)
            .put("probabilityInferred", false)
        batchErrors.put(JSONObject(event.toString()).put("type", "jinhak-lower-grade-login-terminal-fence"))
        recordRuntimeEvent("jinhak-lower-grade-login-terminal-fence", event)
        unifiedSessionId?.let { sessionId ->
            localStore.recordSyncState(
                sessionId,
                "JINHAK_LOWER_GRADE_LOGIN_FENCED",
                ProviderId.JINHAK.wireName,
                JSONObject(event.toString())
                    .put("terminalStops", jinhakLowerGradeLoginTerminalStops)
                    .put("nextAction", "finish-jinhak-phase-without-login-retry"),
                true
            )
        }
        sessionState.text = "△ 진학사 고1·2 로그인 차단 · 진학사 단계 종료"
        status.text = "고1·2 로그인 컨텍스트를 감지해 해당 페이지 재진입을 중단했습니다. 진학사 재시도 없이 어디가 공식자료·저장된 근거 분석을 계속합니다."

        when {
            batchRunning -> handler.post { if (batchRunning) finishBatch("jinhak-lower-grade-login-fenced") }
            unifiedRunning && unifiedPhase == "jinhak" -> handler.post { finishUnifiedCollection("jinhak-lower-grade-login-fenced") }
        }
    }

'''
if s.count(anchor)!=1: raise SystemExit('DOM fence helper anchor mismatch')
s=s.replace(anchor,helper+anchor,1)

# This is the exact loop observed in the uploaded recording: hidden login page + recursive 500 ms
# unsafe-login-recheck forever. Replace it with a terminal state transition.
old='''                } else {
                    webView.visibility = View.INVISIBLE
                    status.text = "진학사 고1·2 로그인 컨텍스트 차단 · 고3·N수 확인 전에는 로그인 화면을 표시하지 않습니다."
                    handler.postDelayed({
                        if (provider == ProviderId.JINHAK && jinhakHigh3FenceActive() && isProviderLoginUrl(ProviderId.JINHAK, webView.url.orEmpty())) {
                            installJinhakHigh3DomProductFence("unsafe-login-recheck")
                        }
                    }, 500L)
                }
'''
new='''                } else {
                    webView.visibility = View.INVISIBLE
                    status.text = "진학사 고1·2 로그인 컨텍스트 차단 · 해당 로그인 페이지 재시도를 중단합니다."
                    terminateJinhakLowerGradeLoginLoop(
                        "unsafe-login-dom",
                        JSONObject(result.toString()).put("currentSafePath", runtimeSafePath(currentUrl))
                    )
                }
'''
if s.count(old)!=1: raise SystemExit('unsafe-login recursive loop anchor mismatch')
s=s.replace(old,new,1)

# Any queued login detector/recovery/credential attempt becomes inert once the terminal latch fires.
old='''    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {
        if (provider != which) return
'''
new='''    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {
        if (provider != which) return
        if (which == ProviderId.JINHAK && jinhakLowerGradeLoginFenceLatched) return
'''
if s.count(old)!=1: raise SystemExit('scheduleLoginSurfaceDetection anchor mismatch')
s=s.replace(old,new,1)

old='''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (provider != which) return
        if (which == ProviderId.JINHAK) installJinhakHigh3DomProductFence("credential:$reason")
'''
new='''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (provider != which) return
        if (which == ProviderId.JINHAK && jinhakLowerGradeLoginFenceLatched) return
        if (which == ProviderId.JINHAK) installJinhakHigh3DomProductFence("credential:$reason")
'''
if s.count(old)!=1: raise SystemExit('credential anchor mismatch')
s=s.replace(old,new,1)

old='''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
'''
new='''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        if (jinhakLowerGradeLoginFenceLatched) return
'''
if s.count(old)!=1: raise SystemExit('scheduleJinhakLoginRecovery anchor mismatch')
s=s.replace(old,new,1)

# Reset only for a new explicit unified run, never from a retry callback.
old='''    private fun startUnifiedCollectionAuthenticated() {
        if (batchRunning) {
            Toast.makeText(this, "현재 개별 수집을 먼저 종료한 뒤 통합 수집을 시작하세요.", Toast.LENGTH_LONG).show()
            return
        }
'''
new='''    private fun startUnifiedCollectionAuthenticated() {
        if (batchRunning) {
            Toast.makeText(this, "현재 개별 수집을 먼저 종료한 뒤 통합 수집을 시작하세요.", Toast.LENGTH_LONG).show()
            return
        }
        jinhakLowerGradeLoginFenceLatched = false
        jinhakLowerGradeLoginTerminalStops = 0
'''
if s.count(old)!=1: raise SystemExit('unified start reset anchor mismatch')
s=s.replace(old,new,1)

p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts')
s=p.read_text().replace('versionCode = 116100','versionCode = 116200',1).replace('versionName = "0.16.1"','versionName = "0.16.2"',1)
p.write_text(s)
p=Path('app/src/main/AndroidManifest.xml')
s=p.read_text().replace('Admission Hub v0.16.1 High3 DOM Fence','Admission Hub v0.16.2 Jinhak Fail-Closed',1)
p.write_text(s)
print('v0.16.2 fail-closed Jinhak auth patch applied')
