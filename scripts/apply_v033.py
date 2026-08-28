from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_PATHS = [
    ROOT / "MainActivity.kt",
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_main(text: str) -> str:
    if 'private const val VERSION = "0.3.3"' in text and 'collectorWebView' in text:
        return text
    if 'private const val VERSION = "0.3.2"' not in text:
        raise SystemExit("MainActivity is not the expected v0.3.2 source")

    text = replace_once(text, "import android.view.Gravity\n", "import android.view.Gravity\nimport android.view.View\n", "View import")
    text = replace_once(text, "import android.widget.Button\n", "import android.widget.Button\nimport android.widget.FrameLayout\n", "FrameLayout import")
    text = replace_once(text, "    private lateinit var webView: WebView\n", "    private lateinit var webView: WebView\n    private lateinit var collectorWebView: WebView\n", "collector WebView field")
    text = replace_once(
        text,
        "    private var batchCloudPagesSkipped = 0\n",
        "    private var batchCloudPagesSkipped = 0\n    private var batchContextRecoveries = 0\n",
        "context recovery counter",
    )
    text = replace_once(text, '        private const val VERSION = "0.3.2"\n', '        private const val VERSION = "0.3.3"\n', "version")

    text = replace_once(
        text,
        '''        webView = WebView(this)\n        preview = TextView(this).apply {\n''',
        '''        collectorWebView = WebView(this).apply {\n            isFocusable = false\n            isClickable = false\n            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO\n        }\n        webView = WebView(this)\n        val browserStack = FrameLayout(this).apply {\n            addView(collectorWebView, FrameLayout.LayoutParams(\n                FrameLayout.LayoutParams.MATCH_PARENT,\n                FrameLayout.LayoutParams.MATCH_PARENT\n            ))\n            addView(webView, FrameLayout.LayoutParams(\n                FrameLayout.LayoutParams.MATCH_PARENT,\n                FrameLayout.LayoutParams.MATCH_PARENT\n            ))\n        }\n        preview = TextView(this).apply {\n''',
        "background browser stack",
    )
    text = replace_once(
        text,
        "        root.addView(webView, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 3f))\n",
        "        root.addView(browserStack, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 3f))\n",
        "browser stack layout",
    )

    text = replace_once(
        text,
        '''        CookieManager.getInstance().apply {\n            setAcceptCookie(true)\n            setAcceptThirdPartyCookies(webView, true)\n        }\n''',
        '''        CookieManager.getInstance().apply {\n            setAcceptCookie(true)\n            setAcceptThirdPartyCookies(webView, true)\n            setAcceptThirdPartyCookies(collectorWebView, true)\n        }\n''',
        "shared cookie manager",
    )

    settings_block = '''        webView.settings.apply {\n            javaScriptEnabled = true\n            domStorageEnabled = true\n            databaseEnabled = true\n            cacheMode = WebSettings.LOAD_DEFAULT\n            javaScriptCanOpenWindowsAutomatically = true\n            setSupportMultipleWindows(true)\n            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW\n            userAgentString = userAgentString + " AdmissionCollector/$VERSION"\n        }\n'''
    collector_settings = settings_block + '''\n        collectorWebView.settings.apply {\n            javaScriptEnabled = true\n            domStorageEnabled = true\n            databaseEnabled = true\n            cacheMode = WebSettings.LOAD_DEFAULT\n            javaScriptCanOpenWindowsAutomatically = true\n            setSupportMultipleWindows(false)\n            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW\n            userAgentString = userAgentString + " AdmissionCollectorCrawler/$VERSION"\n        }\n'''
    text = replace_once(text, settings_block, collector_settings, "collector settings")

    old_client = '''        webView.webViewClient = object : WebViewClient() {\n            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false\n\n            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n                status.text = "불러오는 중: ${safeDisplayUrl(url)}"\n            }\n\n            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n                status.text = "현재 페이지: ${safeDisplayUrl(url)}"\n\n                when {\n                    batchPausedForLogin -> checkSessionState { needsLogin, _ ->\n                        if (!needsLogin) {\n                            sessionState.text = "● 로그인 상태 복구 감지"\n                            resumeAfterLogin()\n                        }\n                    }\n                    batchRunning -> {\n                        val pending = pendingBatchPageAction\n                        if (pending != null && canonicalizeBatchUrl(url) == pending.baseUrl) {\n                            executePendingBatchPageAction()\n                        } else {\n                            scheduleBatchSnapshot()\n                        }\n                    }\n                    else -> checkSessionState()\n                }\n            }\n        }\n'''
    new_client = '''        collectorWebView.webViewClient = object : WebViewClient() {\n            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false\n\n            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n                if (batchRunning) status.text = "백그라운드 로딩: ${safeDisplayUrl(url)}"\n            }\n\n            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n                if (!batchRunning || batchPausedForLogin) return\n                val pending = pendingBatchPageAction\n                if (pending != null && sameBatchDocument(url, pending.baseUrl)) {\n                    executePendingBatchPageAction()\n                } else {\n                    scheduleBatchSnapshot()\n                }\n            }\n        }\n\n        webView.webViewClient = object : WebViewClient() {\n            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false\n\n            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n                if (!batchRunning) status.text = "불러오는 중: ${safeDisplayUrl(url)}"\n            }\n\n            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n                if (batchPausedForLogin) {\n                    checkSessionState { needsLogin, _ ->\n                        if (!needsLogin) {\n                            sessionState.text = "● 로그인 상태 복구 감지"\n                            resumeAfterLogin()\n                        }\n                    }\n                } else if (!batchRunning) {\n                    status.text = "현재 페이지: ${safeDisplayUrl(url)}"\n                    checkSessionState()\n                }\n            }\n        }\n'''
    text = replace_once(text, old_client, new_client, "split visible and crawler clients")

    text = replace_once(
        text,
        '''        webView.evaluateJavascript(js) { result ->\n            if (result == "true") {\n                CookieManager.getInstance().flush()\n                sessionState.text = "● 로그인 세션 자동 연장"\n            }\n        }\n    }\n\n    private fun currentAdapter(): ProviderAdapter = ProviderRegistry.adapter(provider)\n''',
        '''        val targets = mutableListOf(webView)\n        if (::collectorWebView.isInitialized && batchRunning) targets.add(collectorWebView)\n        targets.forEach { target ->\n            target.evaluateJavascript(js) { result ->\n                if (result == "true") {\n                    CookieManager.getInstance().flush()\n                    sessionState.text = "● 로그인 세션 자동 연장"\n                }\n            }\n        }\n    }\n\n    private fun currentAdapter(): ProviderAdapter = ProviderRegistry.adapter(provider)\n''',
        "extend session on both browsers",
    )

    text = replace_once(text, "        batchRunning = true\n        batchPausedForLogin = false\n", "        batchRunning = true\n        startCollectionKeepAlive()\n        batchPausedForLogin = false\n", "start foreground keepalive")
    text = replace_once(text, "        batchCloudPagesSkipped = 0\n        currentBatchTarget = url\n", "        batchCloudPagesSkipped = 0\n        batchContextRecoveries = 0\n        currentBatchTarget = canonicalizeBatchUrl(url)\n", "reset stable context")
    text = replace_once(
        text,
        '''                    if (needsLogin) {\n                        pauseBatchForLogin()\n                    } else {\n                        scheduleBatchSnapshot()\n                    }\n''',
        '''                    if (needsLogin) {\n                        pauseBatchForLogin()\n                    } else {\n                        val startUrl = currentBatchTarget\n                        if (!startUrl.isNullOrBlank()) collectorWebView.loadUrl(startUrl)\n                        else loadNextBatchPage()\n                    }\n''',
        "start hidden collector",
    )

    text = replace_once(
        text,
        '''        batchRunning = false\n        batchPausedForLogin = false\n        batchCollecting = false\n        batchQueue.clear()\n''',
        '''        batchRunning = false\n        batchPausedForLogin = false\n        batchCollecting = false\n        collectorWebView.stopLoading()\n        stopCollectionKeepAlive()\n        batchQueue.clear()\n''',
        "stop hidden collector",
    )
    text = replace_once(
        text,
        '''        status.text = "수집 일시정지: 로그인 갱신 후 자동/수동으로 계속할 수 있습니다."\n        batchButton.text = "일괄 수집 중지"\n''',
        '''        status.text = "백그라운드 수집 일시정지: 메인 화면에서 로그인 갱신 후 자동으로 계속합니다."\n        batchButton.text = "일괄 수집 중지"\n        handler.postDelayed({ refreshSessionOrOpenLogin() }, 150)\n''',
        "surface login on visible browser",
    )
    text = replace_once(text, "                webView.loadUrl(retry)\n", "                collectorWebView.loadUrl(retry)\n", "resume collector")

    text = replace_once(text, '        val url = canonicalizeBatchUrl(webView.url ?: "")\n        if (currentAdapter().isDynamicListPage(url)) {\n', '        val url = canonicalizeBatchUrl(collectorWebView.url ?: "")\n        if (currentAdapter().isDynamicListPage(url)) {\n', "batch schedule uses collector")
    text = replace_once(
        text,
        '''        webView.evaluateJavascript(js) { encoded ->\n            if (!batchRunning || batchPausedForLogin || activeBatchPageAction == null) return@evaluateJavascript\n''',
        '''        collectorWebView.evaluateJavascript(js) { encoded ->\n            if (!batchRunning || batchPausedForLogin || activeBatchPageAction == null) return@evaluateJavascript\n''',
        "pagination readiness uses collector",
    )
    text = replace_once(text, '        val current = canonicalizeBatchUrl(webView.url ?: "")\n        if (current != baseUrl) {\n', '        val current = canonicalizeBatchUrl(collectorWebView.url ?: "")\n        if (current != baseUrl && !sameBatchDocument(current, baseUrl)) {\n', "dynamic readiness URL")
    text = replace_once(
        text,
        '''        webView.evaluateJavascript(js) { encoded ->\n            if (!batchRunning || batchPausedForLogin) {\n                batchReadinessPolling = false\n''',
        '''        collectorWebView.evaluateJavascript(js) { encoded ->\n            if (!batchRunning || batchPausedForLogin) {\n                batchReadinessPolling = false\n''',
        "dynamic readiness uses collector",
    )

    text = replace_once(
        text,
        '''        collectSnapshot { snapshot ->\n            batchCollecting = false\n            if (!batchRunning || snapshot == null) return@collectSnapshot\n''',
        '''        collectSnapshot(collectorWebView) { snapshot ->\n            batchCollecting = false\n            if (!batchRunning || snapshot == null) return@collectSnapshot\n            stabilizeBatchSnapshotContext(snapshot)\n''',
        "batch snapshot uses collector and stable context",
    )

    text = replace_once(text, '            val current = canonicalizeBatchUrl(webView.url ?: "")\n            pendingBatchPageAction = action\n', '            val current = canonicalizeBatchUrl(collectorWebView.url ?: "")\n            pendingBatchPageAction = action\n', "page queue current collector")
    text = replace_once(text, "                webView.loadUrl(action.baseUrl)\n", "                collectorWebView.loadUrl(action.baseUrl)\n", "page action base load")
    text = replace_once(text, "            webView.loadUrl(next)\n            return\n        }\n        finishBatch(\"completed\")\n", "            collectorWebView.loadUrl(next)\n            return\n        }\n        finishBatch(\"completed\")\n", "seed load on collector")

    text = replace_once(
        text,
        '''        val js = currentAdapter().paginationScript(action.page)\n        if (js.isNullOrBlank()) {\n''',
        '''        val js = currentAdapter().paginationScript(action.page)\n        if (js.isNullOrBlank()) {\n''',
        "pagination script anchor",
    )
    text = replace_once(
        text,
        '''        activeBatchPageAction = action\n        status.text = pageActionStatus(action, if (action.retry > 0) "재시도 ${action.retry}/$MAX_PAGE_RETRIES" else "이동 중")\n        webView.evaluateJavascript(js) { result ->\n''',
        '''        activeBatchPageAction = action\n        status.text = pageActionStatus(action, if (action.retry > 0) "재시도 ${action.retry}/$MAX_PAGE_RETRIES" else "백그라운드 이동 중")\n        val yearPrelude = action.requestedYear?.let { expectedYear ->\n            """(function(){var n=document.querySelectorAll('[name=searchSyr],#searchSyr');for(var i=0;i<n.length;i++){try{n[i].value='$expectedYear';}catch(e){}}})();"""\n        } ?: ""\n        collectorWebView.evaluateJavascript(yearPrelude + js) { result ->\n''',
        "execute pagination in collector",
    )
    text = replace_once(text, "            if (batchRunning && !batchPausedForLogin) webView.loadUrl(retry.baseUrl)\n", "            if (batchRunning && !batchPausedForLogin) collectorWebView.loadUrl(retry.baseUrl)\n", "retry hidden page")

    text = replace_once(
        text,
        '''    private fun pageActionKey(action: BatchPageAction): String =\n        "${action.baseUrl}|page|${action.page}"\n''',
        '''    private fun pageActionKey(action: BatchPageAction): String =\n        "${action.familyKey}|year=${action.requestedYear ?: "unknown"}|page=${action.page}"\n''',
        "stable page identity",
    )

    helper_marker = '''    private fun canonicalizeBatchUrl(url: String): String {\n'''
    helpers = '''    private fun sameBatchDocument(a: String, b: String): Boolean {\n        return try {\n            val ua = Uri.parse(a)\n            val ub = Uri.parse(b)\n            ua.host.equals(ub.host, ignoreCase = true) && ua.path == ub.path\n        } catch (_: Exception) { false }\n    }\n\n    private fun queryYearFromUrl(url: String?): Int? {\n        if (url.isNullOrBlank()) return null\n        return try { Uri.parse(url).getQueryParameter("searchSyr")?.toIntOrNull() } catch (_: Exception) { null }\n    }\n\n    private fun withQueryParameter(url: String, key: String, value: String): String {\n        return try {\n            val uri = Uri.parse(url)\n            val builder = uri.buildUpon().clearQuery()\n            for (name in uri.queryParameterNames) {\n                if (name == key) continue\n                for (v in uri.getQueryParameters(name)) builder.appendQueryParameter(name, v)\n            }\n            builder.appendQueryParameter(key, value).build().toString()\n        } catch (_: Exception) { url }\n    }\n\n    private fun stabilizeBatchSnapshotContext(snapshot: JSONObject) {\n        if (provider != ProviderId.ADIGA) return\n        val rawUrl = snapshot.optString("url")\n        if (!currentAdapter().isDynamicListPage(rawUrl)) return\n        if (queryYearFromUrl(rawUrl) != null) return\n\n        val expectedYear = activeBatchPageAction?.requestedYear\n            ?: pendingBatchPageAction?.requestedYear\n            ?: queryYearFromUrl(currentBatchTarget)\n        if (expectedYear == null) {\n            snapshot.put("collectionContextError", "missing-searchSyr")\n            return\n        }\n\n        val restoredUrl = withQueryParameter(rawUrl, "searchSyr", expectedYear.toString())\n        snapshot.put("url", restoredUrl)\n        snapshot.put("navigationKey", restoredUrl)\n        snapshot.put("collectionContextRecovered", true)\n        snapshot.put("collectionExpectedYear", expectedYear)\n        currentBatchTarget = restoredUrl\n        batchContextRecoveries += 1\n    }\n\n    private fun startCollectionKeepAlive() {\n        runCatching { startForegroundService(Intent(this, CollectionKeepAliveService::class.java)) }\n    }\n\n    private fun stopCollectionKeepAlive() {\n        runCatching { stopService(Intent(this, CollectionKeepAliveService::class.java)) }\n    }\n\n'''
    text = replace_once(text, helper_marker, helpers + helper_marker, "background helpers")

    text = replace_once(
        text,
        '''        batchRunning = false\n        batchPausedForLogin = false\n        batchCollecting = false\n        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"\n''',
        '''        batchRunning = false\n        batchPausedForLogin = false\n        batchCollecting = false\n        collectorWebView.stopLoading()\n        stopCollectionKeepAlive()\n        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"\n''',
        "finish keepalive",
    )

    text = replace_once(
        text,
        '''                .put("cloudPagesSkipped", batchCloudPagesSkipped)\n                .put("duplicateYearViewsSkipped", batchDuplicateYearViews.length())\n''',
        '''                .put("cloudPagesSkipped", batchCloudPagesSkipped)\n                .put("contextRecoveries", batchContextRecoveries)\n                .put("collectionTransport", "background-webview")\n                .put("duplicateYearViewsSkipped", batchDuplicateYearViews.length())\n''',
        "summary background transport",
    )

    old_collect = '''    private fun collectSnapshot(callback: (JSONObject?) -> Unit) {\n        val js = SnapshotScript.build()\n        webView.evaluateJavascript(js) { encoded ->\n            try {\n                val raw = decodeJsString(encoded)\n                val obj = JSONObject(raw)\n                obj.put("providerPageType", currentAdapter().classify(obj))\n                val session = obj.optJSONObject("session") ?: JSONObject()\n                sessionState.text = when {\n                    session.optBoolean("authenticated", false) -> "● 로그인 유지됨"\n                    session.optBoolean("needsLogin", false) -> "○ 로그인 갱신 필요"\n                    else -> "△ 로그인 상태 미확정"\n                }\n                callback(obj)\n            } catch (e: Exception) {\n                status.text = "수집 실패: ${e.message}"\n                callback(null)\n            }\n        }\n    }\n'''
    new_collect = '''    private fun collectSnapshot(callback: (JSONObject?) -> Unit) = collectSnapshot(webView, callback)\n\n    private fun collectSnapshot(target: WebView, callback: (JSONObject?) -> Unit) {\n        val js = SnapshotScript.build()\n        target.evaluateJavascript(js) { encoded ->\n            try {\n                val raw = decodeJsString(encoded)\n                val obj = JSONObject(raw)\n                obj.put("providerPageType", currentAdapter().classify(obj))\n                val session = obj.optJSONObject("session") ?: JSONObject()\n                sessionState.text = when {\n                    session.optBoolean("authenticated", false) -> "● 로그인 유지됨"\n                    session.optBoolean("needsLogin", false) -> "○ 로그인 갱신 필요"\n                    else -> "△ 로그인 상태 미확정"\n                }\n                callback(obj)\n            } catch (e: Exception) {\n                status.text = "수집 실패: ${e.message}"\n                callback(null)\n            }\n        }\n    }\n'''
    text = replace_once(text, old_collect, new_collect, "snapshot target overload")

    text = replace_once(
        text,
        '''        val planKey = "$baseUrl|${plan.totalItems}|${plan.pageSize}|${plan.totalPages}"\n''',
        '''        val planKey = "${plan.familyKey}|year=${plan.requestedYear ?: "unknown"}|${plan.totalItems}|${plan.pageSize}|${plan.totalPages}"\n''',
        "stable pagination plan key",
    )

    text = replace_once(
        text,
        '''        cloudOffload.shutdown()\n        webView.stopLoading()\n        webView.destroy()\n        super.onDestroy()\n''',
        '''        stopCollectionKeepAlive()\n        cloudOffload.shutdown()\n        if (::collectorWebView.isInitialized) {\n            collectorWebView.stopLoading()\n            collectorWebView.destroy()\n        }\n        webView.stopLoading()\n        webView.destroy()\n        super.onDestroy()\n''',
        "destroy collector WebView",
    )
    return text


def patch_adapter(text: str) -> str:
    if "val requestedYear = queryYear(url) ?: return null" in text:
        return text
    text = replace_once(
        text,
        '''        val meta = snapshot.optJSONObject("listMeta") ?: return null\n''',
        '''        // Dynamic admission lists are year-scoped. A missing year after a login\n        // redirect must never create a second Cloudflare checkpoint namespace (-1).\n        // MainActivity restores the expected year before asking for a plan; if that\n        // recovery fails, skip pagination rather than mislabel data.\n        val requestedYear = queryYear(url) ?: return null\n        val meta = snapshot.optJSONObject("listMeta") ?: return null\n''',
        "require Adiga year context",
    )
    text = replace_once(text, "            requestedYear = queryYear(url),\n", "            requestedYear = requestedYear,\n", "stable Adiga plan year")
    return text


def patch_gradle(text: str) -> str:
    if 'versionName = "0.3.3"' in text:
        return text
    text = replace_once(text, "        versionCode = 9\n        versionName = \"0.3.2\"\n", "        versionCode = 10\n        versionName = \"0.3.3\"\n", "gradle version")
    return text


def patch_manifest(text: str) -> str:
    if "CollectionKeepAliveService" in text:
        return text
    text = replace_once(
        text,
        '    <uses-permission android:name="android.permission.INTERNET" />\n',
        '    <uses-permission android:name="android.permission.INTERNET" />\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />\n',
        "foreground permissions",
    )
    text = replace_once(
        text,
        '''        <activity\n            android:name=".MainActivity"\n''',
        '''        <service\n            android:name=".CollectionKeepAliveService"\n            android:exported="false"\n            android:foregroundServiceType="dataSync" />\n        <activity\n            android:name=".MainActivity"\n''',
        "foreground service manifest",
    )
    return text


for path in MAIN_PATHS:
    path.write_text(patch_main(path.read_text()), encoding="utf-8")

adapter = ROOT / "app/src/main/java/com/admissionhub/collector/provider/AdigaAdapter.kt"
adapter.write_text(patch_adapter(adapter.read_text()), encoding="utf-8")

gradle = ROOT / "app/build.gradle.kts"
gradle.write_text(patch_gradle(gradle.read_text()), encoding="utf-8")

manifest = ROOT / "app/src/main/AndroidManifest.xml"
manifest.write_text(patch_manifest(manifest.read_text()), encoding="utf-8")

print("v0.3.3 background collector patch applied")
