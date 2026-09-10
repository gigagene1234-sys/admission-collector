from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = MAIN.read_text()


def replace_function(name_pattern: str, replacement: str, label: str) -> None:
    global text
    marker = replacement.strip().splitlines()[0].strip()
    # If the replacement body is already present directly after the function signature, keep it.
    if marker in text and replacement.strip() in text:
        return
    pattern = rf"    private fun {name_pattern}.*?(?=\n    private fun |\n    override fun |\n}}\s*$)"
    updated, count = re.subn(pattern, replacement.rstrip(), text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected one function, found {count}")
    text = updated


replace_function(
    r"enterJinhakUserSessionGate\(reason: String\)",
    '''    private fun enterJinhakUserSessionGate(reason: String) {
        if (provider != ProviderId.JINHAK) return
        clearJinhakLegacyAuthState()
        batchPausedForLogin = false
        if (::authHost.isInitialized) authHost.visibility = View.GONE
        if (::webView.isInitialized) webView.visibility = View.VISIBLE
        sessionState.text = "○ 직접 로그인 · 수시 저장소로 이동"
        status.text = "진학사 로그인/세션은 Admission Hub가 관리하지 않습니다. 직접 로그인하고 수시 저장소까지 이동하세요."
    }
''',
    "neutral-enter-user-session-gate",
)

replace_function(
    r"confirmJinhakUserSessionAndResume\(reason: String\)",
    '''    private fun confirmJinhakUserSessionAndResume(reason: String) {
        if (provider != ProviderId.JINHAK) return
        clearJinhakLegacyAuthState()
        val current = webView.url.orEmpty()
        if (JinhakManualStorageReportPolicy.isStorageEntry(current)) {
            batchPausedForLogin = false
            if (!batchRunning) startBatch() else scheduleBatchSnapshot()
        } else {
            batchPausedForLogin = false
            sessionState.text = "○ 수시 저장소 직접 진입 필요"
            status.text = "현재 페이지에서는 자동 탐색을 시작하지 않습니다. 수시 저장소까지 직접 이동하세요."
        }
    }
''',
    "neutral-confirm-user-session",
)

replace_function(
    r"startV0180DedicatedJinhakAuth\(reason: String, forceManual: Boolean = false\)",
    '''    private fun startV0180DedicatedJinhakAuth(reason: String, forceManual: Boolean = false) {
        if (provider != ProviderId.JINHAK) provider = ProviderId.JINHAK
        clearJinhakLegacyAuthState()
        batchPausedForLogin = false
        if (::authHost.isInitialized) authHost.visibility = View.GONE
        if (::webView.isInitialized) webView.visibility = View.VISIBLE
        sessionState.text = "○ 직접 로그인 · 수시 저장소로 이동"
        status.text = "자동 로그인/인증 검증은 비활성화되어 있습니다. 진학사에서 직접 로그인하고 수시 저장소까지 이동하세요."
    }
''',
    "neutral-start-v0180-auth",
)

replace_function(
    r"completeV0180DedicatedJinhakAuth\(successUrl: String\)",
    '''    private fun completeV0180DedicatedJinhakAuth(successUrl: String) {
        if (provider != ProviderId.JINHAK) return
        clearJinhakLegacyAuthState()
        sessionState.text = "○ 직접 탐색"
        status.text = "로그인 성공 여부를 Admission Hub가 판정하지 않습니다. 수시 저장소가 실제로 열리면 그때 탐색을 시작합니다."
    }
''',
    "neutral-complete-v0180-auth",
)

replace_function(
    r"requestV0182ProtectedSessionProbe\(trigger: String\)",
    '''    private fun requestV0182ProtectedSessionProbe(trigger: String) {
        if (provider != ProviderId.JINHAK) return
        clearJinhakLegacyAuthState()
        sessionState.text = "○ 수시 저장소 직접 진입 대기"
    }
''',
    "neutral-protected-session-probe",
)

replace_function(
    r"markV0182ProtectedSessionVerified\(url: String, trigger: String\)",
    '''    private fun markV0182ProtectedSessionVerified(url: String, trigger: String) {
        if (provider != ProviderId.JINHAK) return
        // v0.18.5 intentionally does not create or persist a Jinhak auth-proof state.
        clearJinhakLegacyAuthState()
    }
''',
    "neutral-protected-session-verification",
)

replace_function(
    r"recreateV0180AuthWebView\(generation: Int\)",
    '''    private fun recreateV0180AuthWebView(generation: Int) {
        // v0.18.5 has no dedicated Jinhak auth WebView.
        clearJinhakLegacyAuthState()
        if (::authHost.isInitialized) authHost.visibility = View.GONE
    }
''',
    "neutral-auth-webview-recreate",
)

replace_function(
    r"startJinhakRealAuthProbe\(autoContinue: Boolean, trigger: String\)",
    '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        provider = ProviderId.JINHAK
        clearJinhakLegacyAuthState()
        sessionState.text = "○ 직접 로그인 · 수시 저장소로 이동"
        status.text = "진학사 인증 probe는 비활성화되어 있습니다. 수시 저장소가 열린 사실만 자동 탐색 시작 신호로 사용합니다."
    }
''',
    "neutral-real-auth-probe",
)

# Even if an old login-surface callback reaches this helper, Jinhak never pauses into an app-owned
# authentication state. It stops traversal and gives control back to the user.
replace_function(
    r"pauseBatchForRenderedLoginSurface\(which: ProviderId, reason: String\)",
    '''    private fun pauseBatchForRenderedLoginSurface(which: ProviderId, reason: String) {
        if (!batchRunning || provider != which) return
        if (which == ProviderId.JINHAK) {
            batchPausedForLogin = false
            stopBatch("jinhak-provider-login-surface")
            clearJinhakLegacyAuthState()
            sessionState.text = "○ 직접 로그인 필요"
            status.text = "진학사 로그인 화면으로 이동했습니다. 직접 로그인하고 수시 저장소까지 돌아오면 새 리포트 탐색을 시작합니다."
            return
        }
        batchRenderedLoginSurfacePauses += 1
        batchPausedForLogin = true
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        hideBatchCover()
        sessionState.text = "○ ${which.displayName} 로그인 화면 감지 · 사용자 로그인 필요"
        status.text = "현재 수집 대상을 보존한 채 로그인 처리를 기다립니다. 로그인 성공 후 같은 대상을 다시 엽니다."
        recordRuntimeEvent(
            "rendered-login-surface-batch-pause",
            JSONObject()
                .put("provider", which.wireName)
                .put("reason", reason.take(40))
                .put("currentTarget", runtimeSafePath(currentBatchTarget))
                .put("proactiveLoginNavigation", false)
        )
    }
''',
    "neutral-rendered-login-pause",
)

MAIN.write_text(text)
