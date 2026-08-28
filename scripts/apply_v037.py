from pathlib import Path

ROOT = Path('MainActivity.kt')
APP = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
GRADLE = Path('app/build.gradle.kts')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'missing marker: {label}')
    return text.replace(old, new, 1)


def patch_activity(path: Path) -> None:
    text = path.read_text()
    if 'private const val VERSION = "0.3.7"' in text:
        return

    text = replace_once(
        text,
        '    private var batchSessionSyncRetries = 0\n',
        '    private var batchSessionSyncRetries = 0\n'
        '    private var batchNavigationWatchdogGeneration = 0\n'
        '    private var batchNavigationWatchdogRecovery = false\n',
        'watchdog fields',
    )
    text = replace_once(
        text,
        '        private const val MAX_SESSION_SYNC_RETRIES = 3\n        private const val VERSION = "0.3.6"\n',
        '        private const val MAX_SESSION_SYNC_RETRIES = 3\n'
        '        private const val BATCH_NAVIGATION_TIMEOUT_MS = 15_000L\n'
        '        private const val VERSION = "0.3.7"\n',
        'version constants',
    )

    text = replace_once(
        text,
        '            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n'
        '                if (batchRunning && !batchPausedForLogin) {\n'
        '                    status.text = "수집 엔진 로딩: ${safeDisplayUrl(url)}"\n',
        '            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n'
        '                if (batchRunning && !batchPausedForLogin) {\n'
        '                    armBatchNavigationWatchdog(url)\n'
        '                    status.text = "수집 엔진 로딩: ${safeDisplayUrl(url)}"\n',
        'arm watchdog',
    )

    text = replace_once(
        text,
        '            override fun onPageFinished(view: WebView, url: String) {\n'
        '                CookieManager.getInstance().flush()\n'
        '                if (batchRunning && !batchPausedForLogin) {\n',
        '            override fun onPageFinished(view: WebView, url: String) {\n'
        '                CookieManager.getInstance().flush()\n'
        '                if (batchRunning && !batchPausedForLogin) {\n'
        '                    disarmBatchNavigationWatchdog()\n'
        '                    if (batchNavigationWatchdogRecovery) {\n'
        '                        batchNavigationWatchdogRecovery = false\n'
        '                        return\n'
        '                    }\n',
        'disarm watchdog',
    )

    text = replace_once(
        text,
        '        batchSessionSyncRetries = 0\n        currentBatchTarget = canonicalizeBatchUrl(url)\n',
        '        batchSessionSyncRetries = 0\n'
        '        batchNavigationWatchdogRecovery = false\n'
        '        disarmBatchNavigationWatchdog()\n'
        '        currentBatchTarget = canonicalizeBatchUrl(url)\n',
        'reset watchdog at batch start',
    )

    text = replace_once(
        text,
        '    private fun showBatchCover() {\n',
        '    private fun armBatchNavigationWatchdog(expectedUrl: String) {\n'
        '        val generation = ++batchNavigationWatchdogGeneration\n'
        '        handler.postDelayed({\n'
        '            if (!batchRunning || batchPausedForLogin || generation != batchNavigationWatchdogGeneration) return@postDelayed\n'
        '            val current = webView.url ?: expectedUrl\n'
        '            val sameDocument = canonicalizeBatchUrl(current) == canonicalizeBatchUrl(expectedUrl) || sameBatchDocument(current, expectedUrl)\n'
        '            if (!sameDocument) return@postDelayed\n'
        '            batchNavigationWatchdogRecovery = true\n'
        '            batchNavigationWatchdogGeneration += 1\n'
        '            status.text = "페이지 로딩 지연 감지: 현재 DOM으로 안전하게 계속합니다."\n'
        '            if (::batchCover.isInitialized) {\n'
        '                batchCover.text = "입시정보 수집 계속 중\\n\\n페이지 로딩이 오래 걸려 현재 상태를 평가한 뒤 다음 항목으로 진행합니다.\\n${safeDisplayUrl(current)}"\n'
        '            }\n'
        '            runCatching { webView.stopLoading() }\n'
        '            handler.postDelayed({\n'
        '                if (!batchRunning || batchPausedForLogin || batchCollecting) return@postDelayed\n'
        '                scheduleBatchSnapshot()\n'
        '            }, 250L)\n'
        '        }, BATCH_NAVIGATION_TIMEOUT_MS)\n'
        '    }\n\n'
        '    private fun disarmBatchNavigationWatchdog() {\n'
        '        batchNavigationWatchdogGeneration += 1\n'
        '    }\n\n'
        '    private fun showBatchCover() {\n',
        'watchdog helpers',
    )

    for marker in [
        '        batchRunning = false\n        batchPausedForLogin = false\n        batchCollecting = false\n        webView.stopLoading()\n',
        '        batchPausedForLogin = true\n        batchCollecting = false\n        hideBatchCover()\n',
    ]:
        if marker in text:
            if 'batchNavigationWatchdogRecovery = false' not in marker:
                replacement = marker.replace(
                    '        webView.stopLoading()\n',
                    '        batchNavigationWatchdogRecovery = false\n        disarmBatchNavigationWatchdog()\n        webView.stopLoading()\n',
                ).replace(
                    '        hideBatchCover()\n',
                    '        batchNavigationWatchdogRecovery = false\n        disarmBatchNavigationWatchdog()\n        hideBatchCover()\n',
                )
                text = text.replace(marker, replacement, 1)

    # finishBatch has the same leading state-reset block as stopBatch; patch any remaining occurrence.
    finish_marker = '    private fun finishBatch(reason: String) {\n        batchRunning = false\n        batchPausedForLogin = false\n        batchCollecting = false\n        webView.stopLoading()\n'
    finish_replacement = '    private fun finishBatch(reason: String) {\n        batchRunning = false\n        batchPausedForLogin = false\n        batchCollecting = false\n        batchNavigationWatchdogRecovery = false\n        disarmBatchNavigationWatchdog()\n        webView.stopLoading()\n'
    text = replace_once(text, finish_marker, finish_replacement, 'finish watchdog cleanup')

    path.write_text(text)


for target in (ROOT, APP):
    patch_activity(target)

if ROOT.read_text() != APP.read_text():
    raise SystemExit('MainActivity copies diverged after v0.3.7 patch')

gradle = GRADLE.read_text()
gradle = gradle.replace('versionCode = 13', 'versionCode = 14')
gradle = gradle.replace('versionName = "0.3.6"', 'versionName = "0.3.7"')
GRADLE.write_text(gradle)

print('v0.3.7 navigation watchdog patch applied')
