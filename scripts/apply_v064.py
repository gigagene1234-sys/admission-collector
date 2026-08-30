from pathlib import Path

ROOT = Path('.')
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

for p in MAIN_FILES:
    m = p.read_text()

    # Imports for renderer recovery and parent removal.
    m = m.replace('import android.view.View\n', 'import android.view.View\nimport android.view.ViewGroup\n', 1)
    m = m.replace('import android.webkit.JsResult\n', 'import android.webkit.JsResult\nimport android.webkit.RenderProcessGoneDetail\n', 1)

    # Runtime/crash/stall state.
    state_anchor = '    private var batchSkipSnapshotUntilMs = 0L\n'
    state_block = '''    private var batchSkipSnapshotUntilMs = 0L\n    private var runtimeLastSafePath = ""\n    private var runtimeRendererRecovering = false\n    private var jinhakStallWatchdogGeneration = 0\n    private var jinhakConsecutiveStalls = 0\n    private var jinhakRecoveredStalls = 0\n'''
    if state_anchor not in m:
        raise SystemExit(f'v064 state anchor missing: {p}')
    m = m.replace(state_anchor, state_block, 1)

    m = m.replace('private const val VERSION = "0.6.3"', 'private const val VERSION = "0.6.4"', 1)
    m = m.replace('private const val BUILD_CODE = 10630', 'private const val BUILD_CODE = 10640', 1)
    const_anchor = '        private const val MAX_JINHAK_AUTONAV_PAGES = 420\n'
    const_block = '''        private const val MAX_JINHAK_AUTONAV_PAGES = 420\n        private const val JINHAK_SOFT_STALL_MS = 12_000L\n        private const val JINHAK_HARD_STALL_MS = 24_000L\n        private const val MAX_JINHAK_CONSECUTIVE_STALLS = 4\n        private const val RUNTIME_PREFS = "collector_runtime_v064"\n'''
    if const_anchor not in m:
        raise SystemExit(f'v064 constants anchor missing: {p}')
    m = m.replace(const_anchor, const_block, 1)

    # Install crash guard before UI work, auto-resume an interrupted unified session, and
    # upload the prior sanitized incident ring after startup.
    old_create = '''    override fun onCreate(savedInstanceState: Bundle?) {\n        super.onCreate(savedInstanceState)\n        cloudOffload = CloudOffloadCoordinator(this)\n        localStore = LocalCollectorStore(this)\n        buildUi()\n        configureWebView()\n        openProvider(ProviderId.JINHAK)\n    }\n'''
    new_create = '''    override fun onCreate(savedInstanceState: Bundle?) {\n        super.onCreate(savedInstanceState)\n        installRuntimeCrashGuard()\n        cloudOffload = CloudOffloadCoordinator(this)\n        localStore = LocalCollectorStore(this)\n        buildUi()\n        configureWebView()\n        val resumed = resumeInterruptedUnifiedSessionIfNeeded()\n        if (!resumed) openProvider(ProviderId.JINHAK)\n        handler.postDelayed({ sendPendingRuntimeEvents() }, 1200L)\n    }\n\n    override fun onTrimMemory(level: Int) {\n        super.onTrimMemory(level)\n        if (level >= TRIM_MEMORY_RUNNING_LOW) {\n            recordRuntimeEvent("memory-trim", JSONObject().put("level", level))\n            if (provider == ProviderId.JINHAK) {\n                // SQLite is authoritative. Do not retain large autonomous-crawl copies in RAM.\n                batchSnapshots = JSONArray()\n                batchRecords = JSONArray()\n                batchResources = JSONArray()\n                lastJinhakDigest = JSONObject()\n                lastJson = ""\n            }\n        }\n    }\n'''
    if old_create not in m:
        raise SystemExit(f'v064 onCreate anchor missing: {p}')
    m = m.replace(old_create, new_create, 1)

    # Persist a cheap sanitized navigation checkpoint before any heavy WebView work.
    page_started_anchor = '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n                if (batchRunning && !batchPausedForLogin) {\n'''
    page_started_new = '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n                runtimeLastSafePath = runtimeSafePath(url)\n                persistRuntimeCheckpoint()\n                if (batchRunning && !batchPausedForLogin) {\n'''
    if page_started_anchor not in m:
        raise SystemExit(f'v064 pageStarted anchor missing: {p}')
    m = m.replace(page_started_anchor, page_started_new, 1)

    # A WebView renderer crash must not take the whole collector down. Persist, remove the
    # dead renderer, and recreate the Activity; the unified-session DB checkpoint resumes it.
    chrome_marker = '        webView.webChromeClient = object : WebChromeClient() {\n'
    renderer_handler = '''        // Renderer failures are separate from app-process exceptions.\n        // Handle them in WebViewClient so a dead renderer cannot crash the whole collector.\n        // The Activity is recreated and resumes from the durable unified/local checkpoint.\n'''
    # Add the override before the closing of WebViewClient, using the exact else/status tail.
    webclient_tail = '''                } else {\n                    status.text = "현재 페이지: ${safeDisplayUrl(url)}"\n                    checkSessionState()\n                }\n            }\n        }\n\n        webView.webChromeClient = object : WebChromeClient() {\n'''
    webclient_new = '''                } else {\n                    status.text = "현재 페이지: ${safeDisplayUrl(url)}"\n                    checkSessionState()\n                }\n            }\n\n            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {\n                if (runtimeRendererRecovering) return true\n                runtimeRendererRecovering = true\n                val didCrash = detail?.didCrash() ?: false\n                recordRuntimeEvent(\n                    "webview-renderer-gone",\n                    JSONObject()\n                        .put("didCrash", didCrash)\n                        .put("priorityAtExit", detail?.rendererPriorityAtExit() ?: -1)\n                        .put("batchRunning", batchRunning)\n                )\n                localRunId?.let { runId ->\n                    val key = currentBatchTarget?.let { canonicalizeBatchUrl(it) }.orEmpty()\n                    if (key.isNotBlank()) localStore.markDocument(runId, key, "error", 0, "webview-renderer-gone")\n                }\n                persistRuntimeCheckpoint(forceResume = unifiedRunning)\n                batchRunning = false\n                batchCollecting = false\n                disarmBatchNavigationWatchdog()\n                runCatching {\n                    (view?.parent as? ViewGroup)?.removeView(view)\n                    view?.destroy()\n                }\n                handler.postDelayed({ recreate() }, 250L)\n                return true\n            }\n        }\n\n        webView.webChromeClient = object : WebChromeClient() {\n'''
    if webclient_tail not in m:
        raise SystemExit(f'v064 WebViewClient tail anchor missing: {p}')
    m = m.replace(webclient_tail, webclient_new, 1)

    # Reset the renderer recovery latch after UI recreation/configuration.
    settings_anchor = '''    private fun configureWebView() {\n        WebView.setWebContentsDebuggingEnabled(false)\n'''
    settings_new = '''    private fun configureWebView() {\n        runtimeRendererRecovering = false\n        WebView.setWebContentsDebuggingEnabled(false)\n'''
    if settings_anchor not in m:
        raise SystemExit(f'v064 configure anchor missing: {p}')
    m = m.replace(settings_anchor, settings_new, 1)

    # Jinhak gets a provider-specific two-stage watchdog. Unlike the old generic watchdog,
    # it does not require the final URL to equal the expected URL, so redirects/SPA loads
    # cannot disable recovery.
    watchdog_anchor = '''    private fun armBatchNavigationWatchdog(expectedUrl: String) {\n        val generation = ++batchNavigationWatchdogGeneration\n'''
    watchdog_new = '''    private fun armBatchNavigationWatchdog(expectedUrl: String) {\n        if (provider == ProviderId.JINHAK) {\n            armJinhakStallWatchdog(expectedUrl)\n            return\n        }\n        val generation = ++batchNavigationWatchdogGeneration\n'''
    if watchdog_anchor not in m:
        raise SystemExit(f'v064 watchdog anchor missing: {p}')
    m = m.replace(watchdog_anchor, watchdog_new, 1)

    disarm_old = '''    private fun disarmBatchNavigationWatchdog() {\n        batchNavigationWatchdogGeneration += 1\n    }\n'''
    disarm_new = '''    private fun disarmBatchNavigationWatchdog() {\n        batchNavigationWatchdogGeneration += 1\n        jinhakStallWatchdogGeneration += 1\n    }\n\n    private fun armJinhakStallWatchdog(expectedUrl: String) {\n        val generation = ++jinhakStallWatchdogGeneration\n        val expectedSafe = runtimeSafePath(expectedUrl)\n        handler.postDelayed({\n            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || generation != jinhakStallWatchdogGeneration) return@postDelayed\n            val probe = """\n                (function(){\n                  try{\n                    var t=String(document.title||'').trim();\n                    var b=(document.body&&document.body.innerText?document.body.innerText:'').replace(/\\s+/g,' ').trim();\n                    var rs=String(document.readyState||'');\n                    var err=/(404\\s*Not\\s*Found|500\\s*(?:Internal\\s*Server\\s*Error)?|웹페이지를\\s*사용할\\s*수\\s*없|net::ERR_|일시적인\\s*오류)/i.test(t+' '+b.slice(0,8000));\n                    return JSON.stringify({readyState:rs,textLength:b.length,error:err,titleLength:t.length});\n                  }catch(e){return JSON.stringify({readyState:'error',textLength:0,error:true,titleLength:0});}\n                })();\n            """.trimIndent()\n            webView.evaluateJavascript(probe) { encoded ->\n                if (!batchRunning || provider != ProviderId.JINHAK || generation != jinhakStallWatchdogGeneration) return@evaluateJavascript\n                val state = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull() ?: JSONObject()\n                val meaningful = state.optInt("textLength", 0) >= 80 || state.optInt("titleLength", 0) >= 3\n                if (meaningful && !state.optBoolean("error", false)) {\n                    jinhakRecoveredStalls += 1\n                    recordRuntimeEvent("jinhak-soft-stall-recovered", JSONObject()\n                        .put("safePath", runtimeSafePath(webView.url ?: expectedUrl))\n                        .put("readyState", state.optString("readyState"))\n                        .put("textLength", state.optInt("textLength")))\n                    status.text = "진학사 로딩 지연 복구: 렌더된 DOM을 수집하고 다음 페이지로 진행합니다."\n                    batchNavigationWatchdogRecovery = true\n                    runCatching { webView.stopLoading() }\n                    handler.postDelayed({\n                        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed\n                        batchNavigationWatchdogRecovery = false\n                        if (!batchCollecting) collectSnapshotForBatch()\n                    }, 220L)\n                }\n            }\n        }, JINHAK_SOFT_STALL_MS)\n\n        handler.postDelayed({\n            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || generation != jinhakStallWatchdogGeneration) return@postDelayed\n            val stalled = canonicalizeBatchUrl(webView.url ?: currentBatchTarget ?: expectedUrl)\n            jinhakConsecutiveStalls += 1\n            jinhakRecoveredStalls += 1\n            recordRuntimeEvent("jinhak-hard-stall-skip", JSONObject()\n                .put("safePath", runtimeSafePath(stalled.ifBlank { expectedUrl }))\n                .put("consecutive", jinhakConsecutiveStalls)\n                .put("expectedSafePath", expectedSafe))\n            localRunId?.let { runId ->\n                if (stalled.isNotBlank()) localStore.markDocument(runId, stalled, "error", 0, "jinhak-navigation-stall")\n            }\n            if (stalled.isNotBlank()) batchVisited.add(stalled)\n            batchErrors.put(JSONObject()\n                .put("type", "jinhak-navigation-stall")\n                .put("safePath", runtimeSafePath(stalled.ifBlank { expectedUrl })))\n            currentBatchTarget = null\n            pendingBatchPageAction = null\n            activeBatchPageAction = null\n            batchCollecting = false\n            batchNavigationWatchdogRecovery = false\n            ++jinhakStallWatchdogGeneration\n            runCatching { webView.stopLoading() }\n            status.text = if (jinhakConsecutiveStalls >= MAX_JINHAK_CONSECUTIVE_STALLS) {\n                "진학사 연속 로딩 지연 ${jinhakConsecutiveStalls}회: 문제 페이지를 격리하고 큐를 계속 진행합니다."\n            } else {\n                "진학사 로딩 중단 페이지 건너뜀: 다음 탐색 대상으로 계속합니다."\n            }\n            handler.postDelayed({ if (batchRunning && !batchPausedForLogin) loadNextBatchPage() }, 280L)\n        }, JINHAK_HARD_STALL_MS)\n    }\n'''
    if disarm_old not in m:
        raise SystemExit(f'v064 disarm anchor missing: {p}')
    m = m.replace(disarm_old, disarm_new, 1)

    # Successful Jinhak capture breaks the consecutive-stall chain.
    success_anchor = '''            val pageRecords = normalizeSnapshot(snapshot)\n            if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {\n'''
    success_new = '''            val pageRecords = normalizeSnapshot(snapshot)\n            if (provider == ProviderId.JINHAK) jinhakConsecutiveStalls = 0\n            if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {\n'''
    if success_anchor not in m:
        raise SystemExit(f'v064 success anchor missing: {p}')
    m = m.replace(success_anchor, success_new, 1)

    # Keep full analysis for true report pages, but navigation/index pages use a much smaller
    # text budget. This materially reduces allocations without dropping report data.
    budget_old = '        val textBudgetLimit = 180_000\n'
    budget_new = '''        val highValuePage = snapshot.optString("providerPageType") in setOf(\n            "jinhak-early-storage", "jinhak-prediction-report", "jinhak-mock-support-report",\n            "jinhak-actual-admit-report", "jinhak-score-calc-report", "jinhak-sat-minimum"\n        )\n        val textBudgetLimit = if (batchRunning && provider == ProviderId.JINHAK && !highValuePage) 32_000 else 180_000\n'''
    if budget_old not in m:
        raise SystemExit(f'v064 digest budget anchor missing: {p}')
    m = m.replace(budget_old, budget_new, 1)

    # Jinhak autonomous crawl is SQLite-first just like large Adiga detail pages. Do not keep
    # hundreds of large snapshots/records in memory in parallel with the WebView renderer.
    records_old = '''            batchSnapshots.put(snapshotForLocalExport(snapshot))\n            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }\n            // University detail records can be large. SQLite is the authoritative local store;\n            // avoid keeping a second in-memory copy during the long detail crawl.\n            if (!(LOCAL_FIRST_BETA && snapshot.optString("providerPageType") == "adiga-university-detail")) {\n                RecordUtils.appendUniqueRecords(batchRecords, pageRecords)\n            }\n'''
    records_new = '''            batchSnapshots.put(snapshotForLocalExport(snapshot))\n            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }\n            // SQLite is authoritative for long crawls. Jinhak pages can be substantially larger\n            // than Adiga list rows, so never duplicate their normalized records in RAM.\n            val keepRecordsInMemory = !(LOCAL_FIRST_BETA && (\n                provider == ProviderId.JINHAK || snapshot.optString("providerPageType") == "adiga-university-detail"\n            ))\n            if (keepRecordsInMemory) RecordUtils.appendUniqueRecords(batchRecords, pageRecords)\n'''
    if records_old not in m:
        raise SystemExit(f'v064 record memory anchor missing: {p}')
    m = m.replace(records_old, records_new, 1)

    snapshot_old = '''    private fun snapshotForLocalExport(snapshot: JSONObject): JSONObject {\n        if (!(LOCAL_FIRST_BETA && provider == ProviderId.ADIGA &&\n                snapshot.optString("providerPageType") == "adiga-university-detail")) {\n            return stripNavigationLinksForExport(snapshot)\n        }\n        // Detailed tables are already normalized into durable SQLite records. Keep only\n        // lightweight diagnostics here to prevent hundreds of university details from\n        // being duplicated in RAM and again in the exported JSON.\n        return JSONObject()\n'''
    snapshot_new = '''    private fun snapshotForLocalExport(snapshot: JSONObject): JSONObject {\n        val lightweight = LOCAL_FIRST_BETA && (\n            provider == ProviderId.JINHAK ||\n                (provider == ProviderId.ADIGA && snapshot.optString("providerPageType") == "adiga-university-detail")\n        )\n        if (!lightweight) return stripNavigationLinksForExport(snapshot)\n        // Full Jinhak analysis is already persisted in unified_analysis_captures and normalized\n        // records are in SQLite. Keep only a tiny batch diagnostic copy in RAM.\n        return JSONObject()\n'''
    if snapshot_old not in m:
        raise SystemExit(f'v064 snapshot memory anchor missing: {p}')
    m = m.replace(snapshot_old, snapshot_new, 1)

    # Runtime crash/event helpers + interrupted-session resume. Insert before startUnifiedCollection.
    unified_marker = '    private fun startUnifiedCollection() {\n'
    runtime_helpers = r'''    private fun runtimeSafePath(url: String?): String {
        if (url.isNullOrBlank()) return ""
        return try {
            val uri = Uri.parse(url)
            val host = uri.host.orEmpty().lowercase()
            val path = uri.path.orEmpty().ifBlank { "/" }
            if (host.isBlank()) path.take(300) else "$host$path".take(300)
        } catch (_: Exception) { "unparseable" }
    }

    private fun persistRuntimeCheckpoint(forceResume: Boolean = unifiedRunning) {
        runCatching {
            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit()
                .putBoolean("resumeUnified", forceResume)
                .putString("provider", provider.wireName)
                .putString("phase", unifiedPhase)
                .putString("safePath", runtimeLastSafePath)
                .putInt("batchPageCount", batchPageCount)
                .putInt("queueSize", batchQueue.size)
                .putInt("errorCount", batchErrors.length())
                .apply()
        }
    }

    private fun recordRuntimeEvent(type: String, detail: JSONObject = JSONObject(), synchronous: Boolean = false) {
        runCatching {
            val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
            val arr = runCatching { JSONArray(prefs.getString("events", "[]")) }.getOrElse { JSONArray() }
            val event = JSONObject()
                .put("at", Instant.now().toString())
                .put("type", type.take(80))
                .put("collectorVersion", VERSION)
                .put("provider", provider.wireName)
                .put("phase", unifiedPhase.take(40))
                .put("safePath", runtimeLastSafePath.take(300))
                .put("batchPageCount", batchPageCount)
                .put("queueSize", batchQueue.size)
                .put("errorCount", batchErrors.length())
                .put("detail", detail)
            arr.put(event)
            while (arr.length() > 40) arr.remove(0)
            val editor = prefs.edit().putString("events", arr.toString())
                .putBoolean("hasPendingEvents", true)
            if (synchronous) editor.commit() else editor.apply()
        }
    }

    private fun installRuntimeCrashGuard() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            runCatching {
                val frames = JSONArray()
                throwable.stackTrace.take(18).forEach { frame ->
                    frames.put("${frame.className}.${frame.methodName}:${frame.lineNumber}".take(220))
                }
                recordRuntimeEvent(
                    "uncaught-exception",
                    JSONObject()
                        .put("exceptionClass", throwable.javaClass.name.take(160))
                        .put("thread", thread.name.take(80))
                        .put("frames", frames),
                    synchronous = true
                )
                persistRuntimeCheckpoint(forceResume = unifiedRunning)
            }
            previous?.uncaughtException(thread, throwable)
        }
    }

    private fun sendPendingRuntimeEvents() {
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        if (!prefs.getBoolean("hasPendingEvents", false)) return
        val arr = runCatching { JSONArray(prefs.getString("events", "[]")) }.getOrElse { JSONArray() }
        if (arr.length() == 0) {
            prefs.edit().putBoolean("hasPendingEvents", false).apply()
            return
        }
        val payload = JSONObject()
            .put("schemaVersion", 1)
            .put("type", "collector-runtime-events")
            .put("collectorVersion", VERSION)
            .put("events", arr)
            .put("privacy", "class-method-stack-and-sanitized-host-path-only-no-query-no-cookie-no-session-token-no-form-values")
        cloudOffload.sendDiagnostic("runtime", VERSION, payload) { result ->
            if (result.isSuccess) {
                prefs.edit().remove("events").putBoolean("hasPendingEvents", false).apply()
            }
        }
    }

    private fun resumeInterruptedUnifiedSessionIfNeeded(): Boolean {
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        val requested = prefs.getBoolean("resumeUnified", false)
        val sessionId = localStore.latestUnifiedSession() ?: return false
        val session = localStore.unifiedStatus(sessionId)
        if (!requested || session.optString("status") != "running") return false

        unifiedSessionId = sessionId
        unifiedRunning = true
        unifiedPhase = session.optString("phase", "jinhak")
        unifiedButton.text = "통합 수집 종료"
        jinhakConsecutiveStalls = 0
        batchRunning = false
        batchCollecting = false

        return if (unifiedPhase == "adiga") {
            provider = ProviderId.ADIGA
            localRunId = session.optJSONObject("adiga")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
                ?: localStore.beginOrResume(ProviderId.ADIGA.wireName, VERSION)
            unifiedPendingAdigaStart = true
            unifiedPendingJinhakStart = false
            status.text = "이전 튕김/중단 감지: 어디가 체크포인트에서 통합 수집을 자동 복구합니다."
            val seed = ProviderRegistry.adapter(ProviderId.ADIGA).seedUrls().firstOrNull() ?: ProviderId.ADIGA.homeUrl
            webView.loadUrl(seed)
            true
        } else {
            provider = ProviderId.JINHAK
            unifiedPhase = "jinhak"
            localRunId = session.optJSONObject("jinhak")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
                ?: localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = true
            status.text = "이전 튕김/중단 감지: 진학사 완료 체크포인트를 건너뛰며 자동 탐색을 재개합니다."
            webView.loadUrl(ProviderId.JINHAK.homeUrl)
            true
        }
    }

'''
    if unified_marker not in m:
        raise SystemExit(f'v064 unified marker missing: {p}')
    m = m.replace(unified_marker, runtime_helpers + unified_marker, 1)

    # Persist resume state at unified start/transition; clear it only on real unified finish.
    start_state_anchor = '        localStore.updateUnifiedSession(sessionId, "adiga", "running", "user-start")\n'
    start_state_new = start_state_anchor + '        persistRuntimeCheckpoint(forceResume = true)\n'
    if start_state_anchor not in m:
        raise SystemExit(f'v064 unified start checkpoint missing: {p}')
    m = m.replace(start_state_anchor, start_state_new, 1)

    transition_anchor = '        localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$adigaReason")\n'
    transition_new = transition_anchor + '        persistRuntimeCheckpoint(forceResume = true)\n'
    if transition_anchor not in m:
        raise SystemExit(f'v064 transition checkpoint missing: {p}')
    m = m.replace(transition_anchor, transition_new, 1)

    finish_anchor = '        localStore.updateUnifiedSession(sessionId, "completed", "completed", reason)\n'
    finish_new = finish_anchor + '        getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit().putBoolean("resumeUnified", false).apply()\n'
    if finish_anchor not in m:
        raise SystemExit(f'v064 finish checkpoint missing: {p}')
    m = m.replace(finish_anchor, finish_new, 1)

    p.write_text(m)

# Gradle + manifest version metadata.
g = GRADLE.read_text()
g = g.replace('versionCode = 10630', 'versionCode = 10640', 1)
g = g.replace('versionName = "0.6.3"', 'versionName = "0.6.4"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text()
mf = mf.replace('Admission Collector v0.6.3 Unified Autonomous Explorer', 'Admission Collector v0.6.4 Crash Guard & Stall Recovery', 1)
MANIFEST.write_text(mf)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirror mismatch after v0.6.4 patch')

print('v0.6.4 crash guard + renderer recovery + Jinhak stall watchdog + RAM reduction applied')
