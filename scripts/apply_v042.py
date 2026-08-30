from pathlib import Path

ROOT = Path('.')
MAIN_PATHS = [
    ROOT / 'MainActivity.kt',
    ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt',
]
BUILD = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'anchor not found: {label}')
    return text.replace(old, new, 1)


for path in MAIN_PATHS:
    s = path.read_text()
    s = replace_once(s,
        '        private const val VERSION = "0.4.1"\n        private const val BUILD_CODE = 10410\n',
        '        private const val VERSION = "0.4.2"\n        private const val BUILD_CODE = 10420\n',
        f'version {path}')

    old_retry = '''    private fun schedulePageActionRetry(action: BatchPageAction, reason: String) {
        val retry = action.copy(retry = action.retry + 1)
        batchPaginationRetries += 1
        batchRetryEvents.put(JSONObject()
            .put("familyKey", action.familyKey)
            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
            .put("page", action.page)
            .put("attempt", retry.retry)
            .put("reason", reason))
        pendingBatchPageAction = retry
        activeBatchPageAction = null
        currentBatchTarget = retry.baseUrl
        status.text = pageActionStatus(retry, "서버 오류 후 재시도 대기")
        val delay = 900L + (retry.retry * 900L)
        handler.postDelayed({
            if (batchRunning && !batchPausedForLogin) webView.loadUrl(retry.baseUrl)
        }, delay)
    }
'''
    new_retry = '''    private fun schedulePageActionRetry(action: BatchPageAction, reason: String) {
        // Central retry circuit-breaker. Every caller, including stale-content recovery,
        // must pass through this guard so one bad page can never pin the whole batch.
        if (action.retry >= MAX_PAGE_RETRIES) {
            recordPaginationFailure(action, reason)
            activeBatchPageAction = null
            pendingBatchPageAction = null
            status.text = pageActionStatus(action, "재시도 상한 도달: 오류로 보존 후 다음 페이지 진행")
            handler.postDelayed({ loadNextBatchPage() }, 250L)
            return
        }

        val retry = action.copy(retry = action.retry + 1)
        batchPaginationRetries += 1
        batchRetryEvents.put(JSONObject()
            .put("familyKey", action.familyKey)
            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
            .put("page", action.page)
            .put("attempt", retry.retry)
            .put("maxAttempts", MAX_PAGE_RETRIES)
            .put("reason", reason))
        pendingBatchPageAction = retry
        activeBatchPageAction = null
        currentBatchTarget = retry.baseUrl
        status.text = pageActionStatus(retry, "재시도 대기 ($reason)")
        val delay = 1200L + (retry.retry * 1000L)
        handler.postDelayed({
            if (batchRunning && !batchPausedForLogin) webView.loadUrl(retry.baseUrl)
        }, delay)
    }
'''
    s = replace_once(s, old_retry, new_retry, f'bounded retry {path}')

    # Give Adiga's AJAX table more time to settle after fnSearch(page). This does not
    # replace stale-content validation; it reduces false stale snapshots caused by a
    # fixed 1.1s capture racing a slow response.
    s = replace_once(s,
        '                }, 1100)\n',
        '                }, 2200)\n',
        f'ajax settle delay {path}')

    # Make the live status explicit that stale content is guarded and bounded.
    s = s.replace(
        'status.text = "페이지 ${activeAction.page} 내용이 기존 ${duplicateOwner}쪽과 동일함: stale 응답으로 판정 후 재시도"',
        'status.text = "페이지 ${activeAction.page} 내용이 기존 ${duplicateOwner}쪽과 동일함: stale 판정 / 최대 $MAX_PAGE_RETRIES회만 재시도"'
    )
    path.write_text(s)

b = BUILD.read_text()
b = replace_once(b, '        versionCode = 10410\n        versionName = "0.4.1"\n',
                 '        versionCode = 10420\n        versionName = "0.4.2"\n', 'gradle version')
BUILD.write_text(b)

m = MANIFEST.read_text()
m = replace_once(m, 'android:label="Admission Collector v0.4.1 Local"',
                 'android:label="Admission Collector v0.4.2 Local"', 'manifest label')
MANIFEST.write_text(m)

print('v0.4.2 bounded retry patch applied')
