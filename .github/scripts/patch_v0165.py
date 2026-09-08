from pathlib import Path

MAIN = Path("app/src/main/java/com/admissionhub/collector/MainActivity.kt")
s = MAIN.read_text()


def replace_once(old: str, new: str, label: str):
    global s
    if old not in s:
        raise SystemExit(f"{label} anchor missing")
    s = s.replace(old, new, 1)


replace_once('private const val VERSION = "0.16.4"', 'private const val VERSION = "0.16.5"', "version")
replace_once('private const val BUILD_CODE = 116400', 'private const val BUILD_CODE = 116500', "build code")

# Real-device evidence in the supplied recording: the Jinhak form stayed visible while the
# collector continued its recovery cycle. If there is no Collector-local credential, the site
# login surface must own navigation until the user completes the site's own login flow.
counter_anchor = "    private var jinhakV0912ProtectedCoreVerified = 0\n"
replace_once(counter_anchor, counter_anchor + """    private var jinhakV0165ManualLoginWaits = 0
    private var jinhakV0165ManualLoginVerifiedHandoffs = 0
    private var jinhakV0165ProbeCompletedFromProtectedCore = 0
""", "v0165 counters")

recovery_head = """    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
"""
recovery_new = """    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val v0165Current = webView.url.orEmpty()
        val v0165HasLocalCredential = credentialVault.load(ProviderId.JINHAK.wireName) != null
        if (isProviderLoginUrl(ProviderId.JINHAK, v0165Current) &&
            !v0165HasLocalCredential &&
            credentialAwaitingLoginExitProvider != ProviderId.JINHAK) {
            jinhakV0165ManualLoginWaits += 1
            webView.visibility = View.VISIBLE
            installJinhakHigh3DomProductFence("v0165-manual-login-stable-surface")
            sessionState.text = "○ 진학사 사이트 로그인 필요"
            status.text = "진학사 로그인 화면을 유지합니다. 기기 자동완성/Samsung Pass 등을 사용해 사이트 로그인을 끝낸 뒤 '사이트 로그인·동의 완료 후 계속'을 누르세요."
            persistJinhakAuthDiagnostics("v0165-manual-login-wait")
            return
        }
"""
replace_once(recovery_head, recovery_new, "recovery manual gate")

credential_old = """        if (credential == null) {
            credentialAutoLoginSuppressedNoCredential += 1
            if (startupCredentialPromptedProvider != ProviderId.JINHAK) {
                startupCredentialPromptedProvider = ProviderId.JINHAK
                showCredentialDialog(ProviderId.JINHAK, continueAfterSave = true)
            }
            return
        }
"""
credential_new = """        if (credential == null) {
            credentialAutoLoginSuppressedNoCredential += 1
            jinhakV0165ManualLoginWaits += 1
            webView.visibility = View.VISIBLE
            installJinhakHigh3DomProductFence("v0165-no-local-credential")
            sessionState.text = "○ 진학사 사이트 로그인 필요"
            status.text = "Collector에 저장된 로그인 정보가 없습니다. 진학사 로그인 화면 자체에서 기기 자동완성/Samsung Pass 등을 사용해 로그인하세요. 입력값은 Collector 진단/JSON/GitHub로 내보내지 않습니다."
            persistJinhakAuthDiagnostics("v0165-no-local-credential-manual-login")
            return
        }
"""
replace_once(credential_old, credential_new, "credential-null manual gate")

# The v0.16.4 protected-core verifier did not explicitly close an active real-site login probe.
# That left the probe's timeout armed even after the only acceptable verification point was reached.
probe_when_old = """                when {
                    batchRunning && batchPausedForLogin -> resumeBatchAfterVerifiedJinhakAuth("v0912-protected-core-verified")
                    unifiedRunning && unifiedPhase == "jinhak" && jinhakTransitionAuthGateActive && !batchRunning -> {
"""
probe_when_new = """                when {
                    batchRunning && batchPausedForLogin -> resumeBatchAfterVerifiedJinhakAuth("v0912-protected-core-verified")
                    jinhakRealAuthProbeActive -> {
                        jinhakV0165ProbeCompletedFromProtectedCore += 1
                        finishJinhakRealAuthProbe("protected-core-verified-v0165", success = true)
                    }
                    unifiedRunning && unifiedPhase == "jinhak" && jinhakTransitionAuthGateActive && !batchRunning -> {
"""
replace_once(probe_when_old, probe_when_new, "probe completion from protected core")

# Make the existing continue button describe its actual contract: the website login/consent must
# be completed first; the app then verifies the protected high3 route and resumes collection.
replace_once('            text = "로그인/동의 후 계속"\n', '            text = "사이트 로그인·동의 완료 후 계속"\n', "resume button label")

resume_head = """    private fun resumeAfterLogin() {
        if (provider == ProviderId.JINHAK && jinhakLowerGradeManualGateActive) {
"""
resume_new = """    private fun resumeAfterLogin() {
        if (provider == ProviderId.JINHAK && isProviderLoginUrl(ProviderId.JINHAK, webView.url.orEmpty())) {
            val expected = webView.url.orEmpty()
            checkSessionState { needsLogin, authenticated ->
                if (provider != ProviderId.JINHAK || webView.url.orEmpty() != expected) return@checkSessionState
                if (authenticated && !needsLogin) {
                    val core = JinhakGradeRouteFence.protectedHigh3Core()
                    if (core.isNotBlank()) {
                        jinhakV0165ManualLoginVerifiedHandoffs += 1
                        webView.visibility = View.INVISIBLE
                        status.text = "진학사 세션 확인 · 고3·N수 보호경로에서 최종 검증합니다."
                        webView.loadUrl(core)
                    }
                } else {
                    webView.visibility = View.VISIBLE
                    sessionState.text = "○ 진학사 사이트 로그인 미완료"
                    status.text = "아직 진학사 로그인 화면입니다. 사이트의 로그인 절차를 먼저 완료한 뒤 다시 계속을 누르세요."
                }
                persistJinhakAuthDiagnostics("v0165-manual-login-resume-check")
            }
            return
        }
        if (provider == ProviderId.JINHAK && jinhakLowerGradeManualGateActive) {
"""
replace_once(resume_head, resume_new, "resume manual login verification")

# Reset and export only non-secret progress counters.
reset_anchor = """        jinhakV0912ProtectedCoreVerified = 0
"""
replace_once(reset_anchor, reset_anchor + """        jinhakV0165ManualLoginWaits = 0
        jinhakV0165ManualLoginVerifiedHandoffs = 0
        jinhakV0165ProbeCompletedFromProtectedCore = 0
""", "counter reset")

diag_anchor = """                    .put("jinhakV0912ProtectedCoreVerified", jinhakV0912ProtectedCoreVerified)
"""
replace_once(diag_anchor, diag_anchor + """                    .put("jinhakV0165ManualLoginWaits", jinhakV0165ManualLoginWaits)
                    .put("jinhakV0165ManualLoginVerifiedHandoffs", jinhakV0165ManualLoginVerifiedHandoffs)
                    .put("jinhakV0165ProbeCompletedFromProtectedCore", jinhakV0165ProbeCompletedFromProtectedCore)
""", "diagnostic export")

MAIN.write_text(s)

p = Path("app/build.gradle.kts")
g = p.read_text().replace("versionCode = 116400", "versionCode = 116500", 1).replace('versionName = "0.16.4"', 'versionName = "0.16.5"', 1)
p.write_text(g)

p = Path("app/src/main/AndroidManifest.xml")
m = p.read_text().replace("Admission Hub v0.16.4 v0.9.12 Auth Baseline", "Admission Hub v0.16.5 Login Handoff + Dashboard Gates", 1)
p.write_text(m)

print("v0.16.5 stable-site-login handoff patch applied")
