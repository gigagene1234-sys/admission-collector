from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_FILES = [
    ROOT / "MainActivity.kt",
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
]
GRADLE = ROOT / "app/build.gradle.kts"


def once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 match, found {n}")
    return text.replace(old, new, 1)


def replace_function(text: str, name: str, next_name: str, replacement: str) -> str:
    start_marker = f"    private fun {name}"
    end_marker = f"    private fun {next_name}"
    start = text.find(start_marker)
    end = text.find(end_marker, start + 1)
    if start < 0 or end < 0:
        raise SystemExit(f"function markers missing: {name} -> {next_name}")
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:]


def patch_main(path: Path) -> None:
    text = path.read_text()

    text = once(text, 'private const val VERSION = "0.3.5"', 'private const val VERSION = "0.3.6"', f"{path}: version")
    text = once(
        text,
        '    private lateinit var collectorWebView: WebView\n    private lateinit var status: TextView',
        '    private lateinit var status: TextView',
        f"{path}: remove secondary webview field",
    )
    text = once(
        text,
        '    private lateinit var batchButton: Button\n    private lateinit var cloudOffload: CloudOffloadCoordinator',
        '    private lateinit var batchButton: Button\n    private lateinit var batchCover: TextView\n    private lateinit var cloudOffload: CloudOffloadCoordinator',
        f"{path}: batch cover field",
    )
    text = once(
        text,
        '    private var batchCloudPagesScheduled = 0\n    private var batchCloudPagesSkipped = 0',
        '    private var batchCloudPagesScheduled = 0\n    private var batchCloudPagesSkipped = 0\n    private var batchCloudPagesDeferred = 0',
        f"{path}: deferred counter",
    )
    text = once(
        text,
        '    private var batchSessionSyncRetries = 0\n    private var collectorStateSyncInProgress = false\n    private var collectorStateSyncPayload: String? = null\n    private var collectorStateSyncTarget: String? = null',
        '    private var batchSessionSyncRetries = 0',
        f"{path}: remove browser state copy fields",
    )

    old_browser = '''        collectorWebView = WebView(this).apply {
            isFocusable = false
            isClickable = false
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        webView = WebView(this)
        val browserStack = FrameLayout(this).apply {
            addView(collectorWebView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(webView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
        }
'''
    new_browser = '''        webView = WebView(this)
        batchCover = TextView(this).apply {
            text = "수집 대기 중"
            gravity = Gravity.CENTER
            textSize = 18f
            setTextColor(android.graphics.Color.DKGRAY)
            setBackgroundColor(android.graphics.Color.WHITE)
            setPadding(32, 32, 32, 32)
            visibility = View.GONE
            isClickable = true
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        }
        val browserStack = FrameLayout(this).apply {
            addView(webView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(batchCover, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
        }
'''
    text = once(text, old_browser, new_browser, f"{path}: single webview UI")

    text = text.replace('            setAcceptThirdPartyCookies(collectorWebView, true)\n', '')

    collector_settings_start = text.find('        collectorWebView.settings.apply {')
    main_client_start = text.find('        webView.webViewClient = object : WebViewClient() {', collector_settings_start)
    if collector_settings_start < 0 or main_client_start < 0:
        raise SystemExit(f"{path}: collector settings/client block missing")
    text = text[:collector_settings_start] + text[main_client_start:]

    old_client = '''        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                if (!batchRunning) status.text = "불러오는 중: ${safeDisplayUrl(url)}"
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                if (batchPausedForLogin) {
                    checkSessionState { needsLogin, authenticated ->
                        if (!needsLogin && authenticated) {
                            sessionState.text = "● 로그인 상태 복구 감지"
                            resumeAfterLogin()
                        }
                    }
                } else if (!batchRunning) {
                    status.text = "현재 페이지: ${safeDisplayUrl(url)}"
                    checkSessionState()
                }
            }
        }
'''
    new_client = '''        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                if (batchRunning && !batchPausedForLogin) {
                    status.text = "수집 엔진 로딩: ${safeDisplayUrl(url)}"
                    if (::batchCover.isInitialized) {
                        batchCover.text = "입시정보 수집 중\n\n페이지 렌더링은 이 화면 뒤에서 처리됩니다.\n${safeDisplayUrl(url)}"
                    }
                } else if (!batchRunning) {
                    status.text = "불러오는 중: ${safeDisplayUrl(url)}"
                }
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                if (batchRunning && !batchPausedForLogin) {
                    val pending = pendingBatchPageAction
                    if (pending != null && sameBatchDocument(url, pending.baseUrl)) {
                        executePendingBatchPageAction()
                    } else {
                        scheduleBatchSnapshot()
                    }
                    return
                }
                if (batchPausedForLogin) {
                    checkSessionState { needsLogin, authenticated ->
                        if (!needsLogin && authenticated) {
                            sessionState.text = "● 로그인 상태 복구 감지"
                            resumeAfterLogin()
                        }
                    }
                } else {
                    status.text = "현재 페이지: ${safeDisplayUrl(url)}"
                    checkSessionState()
                }
            }
        }
'''
    text = once(text, old_client, new_client, f"{path}: batch-aware authenticated WebView client")

    old_targets = '''        val targets = mutableListOf(webView)
        if (::collectorWebView.isInitialized && batchRunning) targets.add(collectorWebView)
        targets.forEach { target ->
'''
    text = once(text, old_targets, '        listOf(webView).forEach { target ->\n', f"{path}: keepalive single webview")

    text = once(
        text,
        '        batchCloudPagesScheduled = 0\n        batchCloudPagesSkipped = 0\n        batchContextRecoveries = 0\n        batchSessionSyncRetries = 0\n        collectorStateSyncInProgress = false\n        collectorStateSyncPayload = null\n        collectorStateSyncTarget = null',
        '        batchCloudPagesScheduled = 0\n        batchCloudPagesSkipped = 0\n        batchCloudPagesDeferred = 0\n        batchContextRecoveries = 0\n        batchSessionSyncRetries = 0',
        f"{path}: reset single webview counters",
    )
    text = once(
        text,
        '        batchRunning = true\n        startCollectionKeepAlive()',
        '        batchRunning = true\n        showBatchCover()\n        startCollectionKeepAlive()',
        f"{path}: show cover at start",
    )
    text = once(
        text,
        '                        if (!startUrl.isNullOrBlank()) synchronizeCollectorBrowserState(startUrl)\n                        else loadNextBatchPage()',
        '                        if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)\n                        else loadNextBatchPage()',
        f"{path}: initial same-webview load",
    )

    helper_marker = '    private fun confirmStopBatch() {'
    helpers = '''    private fun showBatchCover() {
        if (!::batchCover.isInitialized) return
        batchCover.text = "입시정보 수집 중\n\n로그인된 브라우저 자체가 수집 엔진으로 동작합니다.\n페이지 이동은 이 화면 뒤에서 처리됩니다."
        batchCover.visibility = View.VISIBLE
        batchCover.bringToFront()
    }

    private fun hideBatchCover() {
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
    }

'''
    if helpers not in text:
        idx = text.find(helper_marker)
        if idx < 0:
            raise SystemExit(f"{path}: confirmStopBatch marker missing")
        text = text[:idx] + helpers + text[idx:]

    old_stop = '''        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        collectorStateSyncInProgress = false
        collectorStateSyncPayload = null
        collectorStateSyncTarget = null
        collectorWebView.stopLoading()
        stopCollectionKeepAlive()
'''
    new_stop = '''        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        webView.stopLoading()
        hideBatchCover()
        stopCollectionKeepAlive()
'''
    text = once(text, old_stop, new_stop, f"{path}: stop same-webview batch")

    text = once(
        text,
        '    private fun pauseBatchForLogin(autoOpenLogin: Boolean = true) {\n        batchPausedForLogin = true\n        batchCollecting = false',
        '    private fun pauseBatchForLogin(autoOpenLogin: Boolean = true) {\n        batchPausedForLogin = true\n        batchCollecting = false\n        hideBatchCover()',
        f"{path}: reveal login UI on pause",
    )

    recover = '''    private fun recoverCollectorSessionOrPause() {
        if (!batchRunning) return
        CookieManager.getInstance().flush()
        checkSessionState { needsLogin, authenticated ->
            if (!batchRunning) return@checkSessionState
            batchSessionSyncRetries = 0
            if (needsLogin) {
                pauseBatchForLogin(autoOpenLogin = true)
                return@checkSessionState
            }
            batchPausedForLogin = false
            showBatchCover()
            sessionState.text = if (authenticated) "● 로그인 유지 / 동일 수집 브라우저" else "△ 로그인 판정 미확정 / 동일 브라우저 재시도"
            val retry = currentBatchTarget
            handler.postDelayed({
                if (!batchRunning || batchPausedForLogin) return@postDelayed
                if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)
                else loadNextBatchPage()
            }, 250)
        }
    }'''
    text = replace_function(text, 'recoverCollectorSessionOrPause()', 'resumeAfterLogin()', recover)

    resume = '''    private fun resumeAfterLogin() {
        if (!batchRunning || !batchPausedForLogin) {
            checkSessionState()
            return
        }
        checkSessionState { needsLogin, authenticated ->
            if (needsLogin || !authenticated) {
                Toast.makeText(this, "로그인 상태가 아직 확인되지 않습니다.", Toast.LENGTH_SHORT).show()
                return@checkSessionState
            }
            batchPausedForLogin = false
            showBatchCover()
            sessionState.text = "● 로그인 복구 / 동일 수집 브라우저"
            val retry = currentBatchTarget
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                status.text = "로그인 복구 완료: 중단 지점 재시도"
                webView.loadUrl(retry)
            } else {
                loadNextBatchPage()
            }
        }
    }'''
    # Remove the obsolete storage-copy functions together with replacement of resume.
    resume_start = text.find('    private fun resumeAfterLogin()')
    schedule_start = text.find('    private fun scheduleBatchSnapshot()', resume_start)
    if resume_start < 0 or schedule_start < 0:
        raise SystemExit(f"{path}: resume/schedule markers missing")
    text = text[:resume_start] + resume + "\n\n" + text[schedule_start:]

    # From batch scheduling onward, all crawling happens in the authenticated visible WebView,
    # which is visually covered by batchCover while it works.
    schedule_start = text.find('    private fun scheduleBatchSnapshot()')
    destroy_start = text.find('    override fun onDestroy()', schedule_start)
    if schedule_start < 0 or destroy_start < 0:
        raise SystemExit(f"{path}: schedule/onDestroy markers missing")
    segment = text[schedule_start:destroy_start].replace('collectorWebView', 'webView')
    text = text[:schedule_start] + segment + text[destroy_start:]

    old_cloud_status = '''                    batchCloudResumePlans += 1
                    batchCloudPagesScheduled += pages.size
                    val skipped = (plan.totalPages - 1 - pages.size).coerceAtLeast(0)
                    batchCloudPagesSkipped += skipped
                    status.text = "Cloud resume: ${pages.size}쪽 재수집 / ${skipped}쪽 완료로 건너뜀"
                    enqueuePageActions(baseUrl, plan, pages.sorted())
'''
    new_cloud_status = '''                    val deferred = response.optJSONArray("deferred") ?: JSONArray()
                    batchCloudResumePlans += 1
                    batchCloudPagesScheduled += pages.size
                    batchCloudPagesDeferred += deferred.length()
                    val skipped = (plan.totalPages - 1 - pages.size).coerceAtLeast(0)
                    batchCloudPagesSkipped += skipped
                    status.text = if (deferred.length() > 0) {
                        "Cloud resume: ${pages.size}쪽 재수집 / ${skipped}쪽 건너뜀 / 서버오류 ${deferred.length()}쪽 보류"
                    } else {
                        "Cloud resume: ${pages.size}쪽 재수집 / ${skipped}쪽 완료로 건너뜀"
                    }
                    enqueuePageActions(baseUrl, plan, pages.sorted())
'''
    text = once(text, old_cloud_status, new_cloud_status, f"{path}: deferred resume status")

    old_finish = '''    private fun finishBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        webView.stopLoading()
        stopCollectionKeepAlive()
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        finalizeBatchJson(reason)
        cloudOffload.finish(
            reason = reason,
            summary = JSONObject()
                .put("attemptedPages", batchPageCount)
                .put("successfulPages", batchSnapshots.length())
                .put("errorPages", batchErrors.length())
                .put("records", batchRecords.length())
                .put("paginationRetries", batchPaginationRetries)
                .put("cloudResumePlans", batchCloudResumePlans)
                .put("cloudPagesScheduled", batchCloudPagesScheduled)
                .put("cloudPagesSkipped", batchCloudPagesSkipped)
        )
        status.text = "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"
    }
'''
    new_finish = '''    private fun finishBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        webView.stopLoading()
        hideBatchCover()
        stopCollectionKeepAlive()
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        val effectiveReason = if (reason == "completed" && batchCloudPagesDeferred > 0) "completed-with-deferred-errors" else reason
        finalizeBatchJson(effectiveReason)
        if (batchCloudPagesDeferred == 0) {
            cloudOffload.finish(
                reason = effectiveReason,
                summary = JSONObject()
                    .put("attemptedPages", batchPageCount)
                    .put("successfulPages", batchSnapshots.length())
                    .put("errorPages", batchErrors.length())
                    .put("records", batchRecords.length())
                    .put("paginationRetries", batchPaginationRetries)
                    .put("cloudResumePlans", batchCloudResumePlans)
                    .put("cloudPagesScheduled", batchCloudPagesScheduled)
                    .put("cloudPagesSkipped", batchCloudPagesSkipped)
                    .put("cloudPagesDeferred", batchCloudPagesDeferred)
            )
        }
        status.text = if (batchCloudPagesDeferred > 0) {
            "수집 완료: 서버 오류 ${batchCloudPagesDeferred}쪽은 Cloud에 보류 / 나머지 완료 페이지는 유지됨"
        } else {
            "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"
        }
    }
'''
    text = once(text, old_finish, new_finish, f"{path}: finish with deferred run preservation")

    text = once(
        text,
        '                .put("cloudPagesSkipped", batchCloudPagesSkipped)\n                .put("contextRecoveries", batchContextRecoveries)\n                .put("collectionTransport", "background-webview")',
        '                .put("cloudPagesSkipped", batchCloudPagesSkipped)\n                .put("cloudPagesDeferred", batchCloudPagesDeferred)\n                .put("contextRecoveries", batchContextRecoveries)\n                .put("collectionTransport", "authenticated-webview-covered")',
        f"{path}: summary transport/deferred",
    )

    old_destroy = '''        if (::collectorWebView.isInitialized) {
            collectorWebView.stopLoading()
            collectorWebView.destroy()
        }
        webView.stopLoading()
'''
    text = once(text, old_destroy, '        webView.stopLoading()\n', f"{path}: destroy single webview")

    # Any residual secondary-WebView name belongs to the old v0.3.5 collector.
    text = text.replace('collectorWebView', 'webView')
    text = text.replace('    private var collectorStateSyncInProgress = false\n', '')
    text = text.replace('    private var collectorStateSyncPayload: String? = null\n', '')
    text = text.replace('    private var collectorStateSyncTarget: String? = null\n', '')
    if 'collectorWebView' in text:
        raise SystemExit(f"{path}: obsolete collectorWebView reference remains")
    if 'synchronizeCollectorBrowserState' in text or 'collectorStateSyncInProgress' in text:
        raise SystemExit(f"{path}: obsolete browser-state copy code remains")

    path.write_text(text)


for p in MAIN_FILES:
    patch_main(p)

text = GRADLE.read_text()
text = once(text, 'versionCode = 12', 'versionCode = 13', 'gradle versionCode')
text = once(text, 'versionName = "0.3.5"', 'versionName = "0.3.6"', 'gradle versionName')
GRADLE.write_text(text)

print('v0.3.6 authenticated covered WebView patch applied')
