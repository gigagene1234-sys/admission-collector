from pathlib import Path
p=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s=p.read_text()

# Do not recursively re-enter the recovery function once automatic high3 bounces are exhausted.
old='''                } else {
                    webView.visibility = View.INVISIBLE
                    status.text = "진학사 고1·2 로그인 컨텍스트 차단 · 고3·N수 인증 경로로 복구합니다."
                    recoverJinhakLowerGradeLoginContext(
                        "unsafe-login-dom",
                        JSONObject(result.toString()).put("currentSafePath", runtimeSafePath(currentUrl))
                    )
                }
'''
new='''                } else {
                    webView.visibility = View.INVISIBLE
                    if (jinhakLowerGradeManualGateActive) {
                        // The bounded automatic bounce budget is exhausted. Keep the batch target and
                        // Jinhak phase alive, but do not recursively bounce the same unsafe login DOM.
                        // A user-triggered "로그인/동의 후 계속" or the next explicit high3 gate probe
                        // can retry from the protected high3 core without ever exposing the lower-grade UI.
                        status.text = "진학사 고1·2 로그인 컨텍스트는 계속 차단 중입니다. 고3·N수 인증 target은 보존되어 있습니다."
                        recordRuntimeEvent("jinhak-high3-login-gate-wait", JSONObject(result.toString())
                            .put("currentSafePath", runtimeSafePath(currentUrl))
                            .put("retrySuppressed", true)
                            .put("jinhakPhaseTerminated", false))
                    } else {
                        status.text = "진학사 고1·2 로그인 컨텍스트 차단 · 고3·N수 인증 경로로 복구합니다."
                        recoverJinhakLowerGradeLoginContext(
                            "unsafe-login-dom",
                            JSONObject(result.toString()).put("currentSafePath", runtimeSafePath(currentUrl))
                        )
                    }
                }
'''
if s.count(old)!=1: raise SystemExit('manual gate unsafe DOM anchor mismatch')
s=s.replace(old,new,1)

# The existing login/consent continue button becomes a safe explicit retry from the protected high3
# route while the manual high3 gate is active. It never opens a lower-grade route.
anchor='''    private fun resumeAfterLogin() {
'''
insert='''    private fun resumeAfterLogin() {
        if (provider == ProviderId.JINHAK && jinhakLowerGradeManualGateActive) {
            val high3Core = JinhakGradeRouteFence.protectedHigh3Core()
            if (high3Core.isNotBlank()) {
                jinhakLowerGradeManualGateActive = false
                jinhakLowerGradeLoginFenceLatched = false
                jinhakLowerGradeRecoveryInFlight = false
                // Allow another bounded pair only after an explicit user retry. This prevents an
                // unattended infinite loop while still making the existing Continue button useful.
                jinhakLowerGradeHigh3RecoveryAttempts = 0
                if (batchRunning) batchPausedForLogin = true
                webView.visibility = View.INVISIBLE
                runCatching { webView.stopLoading() }
                sessionState.text = "○ 진학사 고3·N수 인증 재시도 · 수집 target 보존"
                status.text = "고1·2 화면은 열지 않고 고3·N수 보호경로에서 인증을 다시 확인합니다."
                handler.postDelayed({
                    if (provider == ProviderId.JINHAK) webView.loadUrl(high3Core)
                }, 250L)
                return
            }
        }
'''
if s.count(anchor)!=1: raise SystemExit('resumeAfterLogin anchor mismatch')
s=s.replace(anchor,insert,1)

p.write_text(s)
print('v0.16.3 recovery recursion guard applied')
