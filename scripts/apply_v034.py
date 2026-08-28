from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_FILES = [
    ROOT / "MainActivity.kt",
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
]
GRADLE = ROOT / "app/build.gradle.kts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_main(path: Path) -> None:
    text = path.read_text()

    text = replace_once(
        text,
        'private const val VERSION = "0.3.3"',
        'private const val VERSION = "0.3.4"',
        f"{path}: version",
    )

    text = replace_once(
        text,
        'private const val PREVIEW_LIMIT = 16000\n        private const val VERSION = "0.3.4"',
        'private const val PREVIEW_LIMIT = 16000\n        private const val MAX_SESSION_SYNC_RETRIES = 3\n        private const val VERSION = "0.3.4"',
        f"{path}: session sync constant",
    )

    text = replace_once(
        text,
        'private var batchContextRecoveries = 0\n\n    private var lastJson',
        'private var batchContextRecoveries = 0\n    private var batchSessionSyncRetries = 0\n\n    private var lastJson',
        f"{path}: session sync state",
    )

    text = replace_once(
        text,
        'userAgentString = userAgentString + " AdmissionCollectorCrawler/$VERSION"',
        'userAgentString = userAgentString + " AdmissionCollector/$VERSION"',
        f"{path}: collector user agent",
    )

    old_refresh = '''            if (!needsLogin && hasAuthenticatedUi) {
                sessionState.text = "● 로그인 유지됨"
                Toast.makeText(this, "로그인 세션이 유지되고 있습니다.", Toast.LENGTH_SHORT).show()
                return@checkSessionState
            }
'''
    new_refresh = '''            if (!needsLogin && hasAuthenticatedUi) {
                sessionState.text = "● 로그인 유지됨"
                if (batchRunning && batchPausedForLogin) {
                    resumeAfterLogin()
                } else {
                    Toast.makeText(this, "로그인 세션이 유지되고 있습니다.", Toast.LENGTH_SHORT).show()
                }
                return@checkSessionState
            }
'''
    text = replace_once(text, old_refresh, new_refresh, f"{path}: refresh auto resume")

    old_on_finished = '''                    checkSessionState { needsLogin, _ ->
                        if (!needsLogin) {
                            sessionState.text = "● 로그인 상태 복구 감지"
                            resumeAfterLogin()
                        }
                    }
'''
    new_on_finished = '''                    checkSessionState { needsLogin, authenticated ->
                        if (!needsLogin && authenticated) {
                            sessionState.text = "● 로그인 상태 복구 감지"
                            resumeAfterLogin()
                        }
                    }
'''
    text = replace_once(text, old_on_finished, new_on_finished, f"{path}: confirmed resume")

    text = replace_once(
        text,
        'batchContextRecoveries = 0\n        currentBatchTarget = canonicalizeBatchUrl(url)',
        'batchContextRecoveries = 0\n        batchSessionSyncRetries = 0\n        currentBatchTarget = canonicalizeBatchUrl(url)',
        f"{path}: reset session sync",
    )

    old_pause = '''    private fun pauseBatchForLogin() {
        batchPausedForLogin = true
        batchCollecting = false
        sessionState.text = "○ 로그인 갱신 필요"
        status.text = "백그라운드 수집 일시정지: 메인 화면에서 로그인 갱신 후 자동으로 계속합니다."
        batchButton.text = "일괄 수집 중지"
        handler.postDelayed({ refreshSessionOrOpenLogin() }, 150)
    }
'''
    new_pause = '''    private fun pauseBatchForLogin(autoOpenLogin: Boolean = true) {
        batchPausedForLogin = true
        batchCollecting = false
        if (autoOpenLogin) {
            sessionState.text = "○ 로그인 갱신 필요"
            status.text = "백그라운드 수집 일시정지: 메인 로그인 갱신 후 자동으로 계속합니다."
        } else {
            sessionState.text = "△ 수집 세션 재동기화 필요"
            status.text = "수집 세션 자동 동기화 실패: 로그인 세션 확인/갱신 후 계속을 눌러주세요."
        }
        batchButton.text = "일괄 수집 중지"
        if (autoOpenLogin) handler.postDelayed({ refreshSessionOrOpenLogin() }, 150)
    }

    private fun recoverCollectorSessionOrPause() {
        if (!batchRunning) return
        CookieManager.getInstance().flush()
        checkSessionState { needsLogin, authenticated ->
            if (!batchRunning) return@checkSessionState

            if (!needsLogin && authenticated && batchSessionSyncRetries < MAX_SESSION_SYNC_RETRIES) {
                batchSessionSyncRetries += 1
                batchPausedForLogin = false
                batchCollecting = false
                sessionState.text = "● 메인 로그인 유지 / 수집 세션 동기화"
                val retry = currentBatchTarget
                status.text = "백그라운드 수집 세션 재동기화 ${batchSessionSyncRetries}/$MAX_SESSION_SYNC_RETRIES"
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin) return@postDelayed
                    if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                        collectorWebView.loadUrl(retry)
                    } else {
                        loadNextBatchPage()
                    }
                }, 300)
                return@checkSessionState
            }

            if (!needsLogin && authenticated) {
                batchSessionSyncRetries = 0
                pauseBatchForLogin(autoOpenLogin = false)
            } else {
                batchSessionSyncRetries = 0
                pauseBatchForLogin(autoOpenLogin = true)
            }
        }
    }
'''
    text = replace_once(text, old_pause, new_pause, f"{path}: pause/recovery")

    old_session_block = '''            val session = snapshot.optJSONObject("session") ?: JSONObject()
            if (session.optBoolean("needsLogin", false)) {
                if (activeAction != null) {
                    pendingBatchPageAction = activeAction
                    activeBatchPageAction = null
                }
                pauseBatchForLogin()
                return@collectSnapshot
            }

            val plan = if (activeAction == null) currentAdapter().paginationPlan(snapshot) else null
'''
    new_session_block = '''            val session = snapshot.optJSONObject("session") ?: JSONObject()
            if (session.optBoolean("needsLogin", false)) {
                if (activeAction != null) {
                    pendingBatchPageAction = activeAction
                    activeBatchPageAction = null
                }
                recoverCollectorSessionOrPause()
                return@collectSnapshot
            }
            batchSessionSyncRetries = 0

            val plan = if (activeAction == null) currentAdapter().paginationPlan(snapshot) else null
'''
    text = replace_once(text, old_session_block, new_session_block, f"{path}: hidden session recovery")

    old_bootstrap = '''                    webView.evaluateJavascript(
                        "(function(){try{window.fnSearch(1);return true;}catch(e){return false;}})();"
                    ) {
'''
    new_bootstrap = '''                    collectorWebView.evaluateJavascript(
                        "(function(){try{window.fnSearch(1);return true;}catch(e){return false;}})();"
                    ) {
'''
    text = replace_once(text, old_bootstrap, new_bootstrap, f"{path}: hidden bootstrap")

    path.write_text(text)


for main in MAIN_FILES:
    patch_main(main)

text = GRADLE.read_text()
text = replace_once(text, 'versionCode = 10', 'versionCode = 11', 'gradle versionCode')
text = replace_once(text, 'versionName = "0.3.3"', 'versionName = "0.3.4"', 'gradle versionName')
GRADLE.write_text(text)

print("v0.3.4 session synchronization patch applied")
