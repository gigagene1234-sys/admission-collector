from pathlib import Path
import re

p=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s=p.read_text()

# Version identity.
s=s.replace('private const val VERSION = "0.16.2"','private const val VERSION = "0.16.3"',1)
s=s.replace('private const val BUILD_CODE = 116200','private const val BUILD_CODE = 116300',1)

# Recovery constants.
anchor='''        private const val MAX_JINHAK_REAUTH_CYCLES = 3
'''
insert='''        private const val MAX_JINHAK_REAUTH_CYCLES = 3
        private const val MAX_JINHAK_LOWER_GRADE_HIGH3_RECOVERIES = 2
        private const val JINHAK_LOWER_GRADE_RECOVERY_DELAY_MS = 450L
'''
if s.count(anchor)!=1: raise SystemExit('reauth constant anchor mismatch')
s=s.replace(anchor,insert,1)

# Runtime fields.
anchor='''    private var jinhakLowerGradeLoginTerminalStops = 0
    private var jinhakLowerGradeLoginFenceLatched = false
'''
insert='''    private var jinhakLowerGradeLoginTerminalStops = 0
    private var jinhakLowerGradeLoginFenceLatched = false
    private var jinhakLowerGradeHigh3RecoveryAttempts = 0
    private var jinhakLowerGradeHigh3RecoverySuccesses = 0
    private var jinhakLowerGradeRecoveryInFlight = false
    private var jinhakLowerGradeManualGateActive = false
'''
if s.count(anchor)!=1: raise SystemExit('lower grade field anchor mismatch')
s=s.replace(anchor,insert,1)

# Reset the recovery state for each explicit integrated run.
anchor='''        jinhakLowerGradeLoginFenceLatched = false
        jinhakLowerGradeLoginTerminalStops = 0
'''
insert='''        jinhakLowerGradeLoginFenceLatched = false
        jinhakLowerGradeLoginTerminalStops = 0
        jinhakLowerGradeHigh3RecoveryAttempts = 0
        jinhakLowerGradeHigh3RecoverySuccesses = 0
        jinhakLowerGradeRecoveryInFlight = false
        jinhakLowerGradeManualGateActive = false
'''
if s.count(anchor)<1: raise SystemExit('unified reset anchor missing')
s=s.replace(anchor,insert,1)

# Replace v0.16.2 terminal fence with a bounded high3 recovery gate. It no longer ends the Jinhak
# phase merely because the shared login surface was in the lower-grade product context.
pattern=r'''    private fun terminateJinhakLowerGradeLoginLoop\(source: String, detail: JSONObject = JSONObject\(\)\) \{.*?\n    \}\n\n    private fun installJinhakHigh3DomProductFence'''
replacement=r'''    private fun recoverJinhakLowerGradeLoginContext(source: String, detail: JSONObject = JSONObject()) {
        if (provider != ProviderId.JINHAK) return
        if (jinhakLowerGradeRecoveryInFlight) return

        val high3Core = JinhakGradeRouteFence.protectedHigh3Core()
        val canAutoRecover = high3Core.isNotBlank() &&
            jinhakLowerGradeHigh3RecoveryAttempts < MAX_JINHAK_LOWER_GRADE_HIGH3_RECOVERIES

        if (canAutoRecover) {
            jinhakLowerGradeHigh3RecoveryAttempts += 1
            val attempt = jinhakLowerGradeHigh3RecoveryAttempts
            jinhakLowerGradeRecoveryInFlight = true
            jinhakLowerGradeLoginFenceLatched = true

            // Cancel only the competing login callbacks. Do NOT terminate the batch/unified phase.
            ++credentialLoginSurfaceGeneration
            ++jinhakLoginRecoveryGeneration
            credentialAutoLoginInFlight = false
            credentialAwaitingLoginExitProvider = null
            jinhakAuthVerifiedForBatch = false
            jinhakCoreBootstrapState = "lower-grade-high3-recovery"
            jinhakLastAuthEvidence = "lower-grade-login-context-blocked-recovering"
            if (batchRunning) batchPausedForLogin = true

            runCatching { webView.stopLoading() }
            webView.visibility = View.INVISIBLE
            val event = JSONObject(detail.toString())
                .put("source", source.take(80))
                .put("attempt", attempt)
                .put("maxAttempts", MAX_JINHAK_LOWER_GRADE_HIGH3_RECOVERIES)
                .put("high3CoreSafePath", runtimeSafePath(high3Core))
                .put("jinhakPhaseTerminated", false)
                .put("retrySuppressed", false)
                .put("adigaOfficialEvidencePreserved", true)
                .put("probabilityInferred", false)
            batchErrors.put(JSONObject(event.toString()).put("type", "jinhak-lower-grade-high3-recovery"))
            recordRuntimeEvent("jinhak-lower-grade-high3-recovery", event)
            unifiedSessionId?.let { sessionId ->
                localStore.recordSyncState(
                    sessionId,
                    "JINHAK_LOWER_GRADE_HIGH3_RECOVERY",
                    ProviderId.JINHAK.wireName,
                    JSONObject(event.toString()).put("nextAction", "reload-protected-high3-core-and-resume-auth"),
                    false
                )
            }
            sessionState.text = "○ 진학사 고1·2 차단 · 고3·N수 보호경로 복구 $attempt/$MAX_JINHAK_LOWER_GRADE_HIGH3_RECOVERIES"
            status.text = "고1·2 로그인 컨텍스트를 닫고 진학사 고3·N수 보호경로로 즉시 복귀합니다. 인증되면 같은 수집 target을 자동 재개합니다."
            handler.postDelayed({
                if (provider != ProviderId.JINHAK) return@postDelayed
                jinhakLowerGradeLoginFenceLatched = false
                jinhakLowerGradeRecoveryInFlight = false
                webView.visibility = View.INVISIBLE
                webView.loadUrl(high3Core)
            }, JINHAK_LOWER_GRADE_RECOVERY_DELAY_MS)
            return
        }

        // Automatic high3 bounce was exhausted. Keep the integrated Jinhak phase alive and expose
        // only the high3/N수 login surface. This is a user/credential gate, not a terminal state.
        jinhakLowerGradeManualGateActive = true
        jinhakLowerGradeLoginFenceLatched = false
        jinhakLowerGradeRecoveryInFlight = false
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "high3-login-gate"
        jinhakLastAuthEvidence = "high3-login-required-after-lower-grade-block"
        if (batchRunning) batchPausedForLogin = true
        val event = JSONObject(detail.toString())
            .put("source", source.take(80))
            .put("automaticRecoveriesExhausted", jinhakLowerGradeHigh3RecoveryAttempts)
            .put("manualHigh3Gate", true)
            .put("jinhakPhaseTerminated", false)
            .put("adigaOfficialEvidencePreserved", true)
            .put("probabilityInferred", false)
        recordRuntimeEvent("jinhak-high3-login-gate", event)
        unifiedSessionId?.let { sessionId ->
            localStore.recordSyncState(
                sessionId,
                "JINHAK_HIGH3_LOGIN_GATE",
                ProviderId.JINHAK.wireName,
                JSONObject(event.toString()).put("nextAction", "authenticate-on-high3-login-then-resume-crawl"),
                false
            )
        }
        sessionState.text = "○ 진학사 고3·N수 로그인 필요 · 수집 target 보존"
        status.text = "고1·2 이동은 차단했습니다. 진학사 단계는 종료하지 않습니다. 고3·N수 로그인 인증이 끝나면 같은 수집 단계로 자동 복귀합니다."
        // The common login surface is allowed only with the lower-grade selector hidden. If the
        // current page is not the shared login surface, bounce once more through the protected core.
        val current = webView.url.orEmpty()
        if (isProviderLoginUrl(ProviderId.JINHAK, current)) {
            installJinhakHigh3DomProductFence("manual-high3-gate")
            if (credentialVault.has(ProviderId.JINHAK.wireName)) {
                handler.postDelayed({
                    if (provider == ProviderId.JINHAK && jinhakLowerGradeManualGateActive) {
                        attemptSavedCredentialLogin(ProviderId.JINHAK, "manual-high3-gate")
                    }
                }, 850L)
            }
        } else if (high3Core.isNotBlank()) {
            webView.visibility = View.INVISIBLE
            handler.postDelayed({
                if (provider == ProviderId.JINHAK && jinhakLowerGradeManualGateActive) webView.loadUrl(high3Core)
            }, 350L)
        }
    }

    private fun verifyRecoveredJinhakHigh3AndResume(url: String): Boolean {
        if (provider != ProviderId.JINHAK || !JinhakGradeRouteFence.isHigh3(url)) return false
        if (jinhakLowerGradeHigh3RecoveryAttempts <= 0 && !jinhakLowerGradeManualGateActive) return false
        val expectedUrl = url
        checkSessionState { needsLogin, authenticated ->
            if (provider != ProviderId.JINHAK || webView.url.orEmpty() != expectedUrl) return@checkSessionState
            if (!needsLogin && authenticated) {
                jinhakLowerGradeHigh3RecoverySuccesses += 1
                jinhakLowerGradeRecoveryInFlight = false
                jinhakLowerGradeManualGateActive = false
                jinhakLowerGradeLoginFenceLatched = false
                jinhakAuthVerifiedForBatch = true
                jinhakCoreBootstrapState = "protected-core-verified-after-lower-grade-recovery"
                jinhakLastAuthEvidence = "protected-core-stable-after-lower-grade-recovery"
                jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
                runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, url, VERSION) }
                recordRuntimeEvent("jinhak-lower-grade-high3-recovery-success", JSONObject()
                    .put("attempts", jinhakLowerGradeHigh3RecoveryAttempts)
                    .put("batchRunning", batchRunning)
                    .put("transitionGate", jinhakTransitionAuthGateActive))
                sessionState.text = "● 진학사 고3·N수 인증 복구 · 수집 재개"
                when {
                    batchRunning && batchPausedForLogin -> resumeBatchAfterVerifiedJinhakAuth("lower-grade-high3-recovered")
                    unifiedRunning && unifiedPhase == "jinhak" && jinhakTransitionAuthGateActive && !batchRunning -> {
                        jinhakTransitionAuthGateActive = false
                        unifiedPendingJinhakStart = false
                        status.text = "진학사 고3·N수 인증 복구 완료 · 진학사 수집 엔진을 시작합니다."
                        handler.postDelayed({
                            if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
                        }, 220L)
                    }
                    startupLoginPreflightActive -> onStartupProviderAuthenticated(ProviderId.JINHAK, startupLoginPollGeneration)
                    else -> status.text = "진학사 고3·N수 인증이 복구되었습니다."
                }
            } else {
                jinhakCoreBootstrapState = "high3-recovery-auth-required"
                jinhakLastAuthEvidence = "high3-protected-route-still-requires-login"
                status.text = "고3·N수 보호경로가 아직 로그인을 요구합니다. 고1·2는 차단한 채 고3·N수 인증만 계속합니다."
            }
        }
        return true
    }

    private fun installJinhakHigh3DomProductFence'''
ns, n = re.subn(pattern, replacement, s, count=1, flags=re.S)
if n != 1: raise SystemExit('terminal fence function block mismatch')
s=ns

# Rename all call sites from terminal to recovery behavior.
s=s.replace('terminateJinhakLowerGradeLoginLoop(', 'recoverJinhakLowerGradeLoginContext(')

# On page-finished, authenticated high3 recovery gets first chance to resume the existing phase.
anchor='''            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                if (provider == ProviderId.JINHAK) {
'''
insert='''            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                if (provider == ProviderId.JINHAK && verifyRecoveredJinhakHigh3AndResume(url)) {
                    return
                }
                if (provider == ProviderId.JINHAK) {
'''
if s.count(anchor)!=1: raise SystemExit('onPageFinished anchor mismatch')
s=s.replace(anchor,insert,1)

# DOM unsafe context no longer terminalizes the phase after automatic recovery budget is exhausted.
old='''                } else {
                    webView.visibility = View.INVISIBLE
                    status.text = "진학사 고1·2 로그인 컨텍스트 차단 · 해당 로그인 페이지 재시도를 중단합니다."
                    recoverJinhakLowerGradeLoginContext(
                        "unsafe-login-dom",
                        JSONObject(result.toString()).put("currentSafePath", runtimeSafePath(currentUrl))
                    )
                }
'''
new='''                } else {
                    webView.visibility = View.INVISIBLE
                    status.text = "진학사 고1·2 로그인 컨텍스트 차단 · 고3·N수 인증 경로로 복구합니다."
                    recoverJinhakLowerGradeLoginContext(
                        "unsafe-login-dom",
                        JSONObject(result.toString()).put("currentSafePath", runtimeSafePath(currentUrl))
                    )
                }
'''
if s.count(old)!=1: raise SystemExit('unsafe login DOM branch mismatch')
s=s.replace(old,new,1)

# When high3 is confirmed in the shared login DOM, keep the gate alive and attempt saved credential
# submission; manual login remains possible if the stored credential fails.
old='''                if (result.optBoolean("safeHigh3", false)) {
                    webView.visibility = View.VISIBLE
                    status.text = "진학사 고3·N수 로그인 컨텍스트 확인 완료 · 자동 로그인을 계속합니다."
                } else {
'''
new='''                if (result.optBoolean("safeHigh3", false)) {
                    webView.visibility = View.VISIBLE
                    status.text = "진학사 고3·N수 로그인 컨텍스트 확인 완료 · 인증 후 수집을 자동 재개합니다."
                    if (jinhakLowerGradeManualGateActive && credentialVault.has(ProviderId.JINHAK.wireName)) {
                        handler.postDelayed({
                            if (provider == ProviderId.JINHAK && jinhakLowerGradeManualGateActive) {
                                attemptSavedCredentialLogin(ProviderId.JINHAK, "safe-high3-login-gate")
                            }
                        }, 180L)
                    }
                } else {
'''
if s.count(old)!=1: raise SystemExit('safeHigh3 DOM branch mismatch')
s=s.replace(old,new,1)

# The Jinhak auto-login should be blocked only during the tiny navigation latch, not for the entire
# recovery/manual gate.
# Existing line remains correct because latch is released before high3 core/login is reloaded.

# Add recovery diagnostics to live export.
anchor='''.put("lowerGradeNavigationsBlocked", jinhakLowerGradeNavigationsBlocked)'''
insert='''.put("lowerGradeNavigationsBlocked", jinhakLowerGradeNavigationsBlocked)
                        .put("lowerGradeHigh3RecoveryAttempts", jinhakLowerGradeHigh3RecoveryAttempts)
                        .put("lowerGradeHigh3RecoverySuccesses", jinhakLowerGradeHigh3RecoverySuccesses)
                        .put("lowerGradeRecoveryInFlight", jinhakLowerGradeRecoveryInFlight)
                        .put("lowerGradeManualGateActive", jinhakLowerGradeManualGateActive)'''
if anchor not in s: raise SystemExit('diagnostics lower grade anchor missing')
s=s.replace(anchor,insert,1)

p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts')
s=p.read_text().replace('versionCode = 116200','versionCode = 116300',1).replace('versionName = "0.16.2"','versionName = "0.16.3"',1)
p.write_text(s)

p=Path('app/src/main/AndroidManifest.xml')
s=p.read_text().replace('Admission Hub v0.16.2 Jinhak Fail-Closed','Admission Hub v0.16.3 High3 Recover',1)
p.write_text(s)

print('v0.16.3 high3 recovery patch applied')
