from pathlib import Path

ROOT = Path('.')
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
JINHAK = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# -----------------------------------------------------------------------------
# v0.6.2 goals
# 1) One unified run must autonomously traverse both providers.
# 2) Jinhak navigation remains same-origin, bounded, and excludes account/payment areas.
# 3) Jinhak hub/menu pages are traversal surfaces, not accepted admission records.
# 4) Adiga site JavaScript error dialogs must never block the crawler UI again.
# -----------------------------------------------------------------------------

for p in MAIN_FILES:
    m = p.read_text()

    m = m.replace('import android.webkit.WebChromeClient\n', 'import android.webkit.WebChromeClient\nimport android.webkit.JsResult\n', 1)
    m = m.replace('private const val VERSION = "0.6.1"', 'private const val VERSION = "0.6.2"', 1)
    m = m.replace('private const val BUILD_CODE = 10610', 'private const val BUILD_CODE = 10620', 1)

    # New bounded autonomous Jinhak phase and anti-dialog state.
    state_anchor = '''    private var unifiedPendingAdigaStart = false\n    private var unifiedJinhakAutoCapture = false\n    private val unifiedJinhakCapturedPages = linkedSetOf<String>()\n    private var unifiedAutoCaptureScheduled = false\n'''
    state_new = '''    private var unifiedPendingAdigaStart = false\n    private var unifiedPendingJinhakStart = false\n    private var unifiedJinhakAutoCapture = false\n    private val unifiedJinhakCapturedPages = linkedSetOf<String>()\n    private var unifiedAutoCaptureScheduled = false\n    private var batchSkipSnapshotUntilMs = 0L\n'''
    if state_anchor not in m:
        raise SystemExit(f'v0.6.2 unified state anchor missing: {p}')
    m = m.replace(state_anchor, state_new, 1)

    const_anchor = '        private const val BATCH_NAVIGATION_TIMEOUT_MS = 15_000L\n'
    const_new = '''        private const val BATCH_NAVIGATION_TIMEOUT_MS = 15_000L\n        private const val MAX_JINHAK_AUTONAV_PAGES = 420\n'''
    if const_anchor not in m:
        raise SystemExit(f'v0.6.2 constant anchor missing: {p}')
    m = m.replace(const_anchor, const_new, 1)

    # The Jinhak phase now starts the regular queue engine automatically instead of
    # waiting for the user to open each page manually.
    page_finished_anchor = '''                if (!batchRunning && unifiedRunning && unifiedPhase == "jinhak" && provider == ProviderId.JINHAK && unifiedJinhakAutoCapture) {\n                    scheduleUnifiedJinhakAutoCapture(url)\n                }\n                if (batchRunning && !batchPausedForLogin) {\n'''
    page_finished_new = '''                if (unifiedRunning && unifiedPhase == "jinhak" && unifiedPendingJinhakStart && provider == ProviderId.JINHAK && !batchRunning) {\n                    unifiedPendingJinhakStart = false\n                    handler.postDelayed({\n                        if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()\n                    }, 450L)\n                    return\n                }\n                if (!batchRunning && unifiedRunning && unifiedPhase == "jinhak" && provider == ProviderId.JINHAK && unifiedJinhakAutoCapture) {\n                    scheduleUnifiedJinhakAutoCapture(url)\n                }\n                if (batchRunning && !batchPausedForLogin) {\n'''
    if page_finished_anchor not in m:
        raise SystemExit(f'v0.6.2 Jinhak page-finished anchor missing: {p}')
    m = m.replace(page_finished_anchor, page_finished_new, 1)

    # Intercept site alert/confirm dialogs during Adiga automation. The external site
    # can still fail, but a JavaScript dialog can no longer pin the WebView forever.
    chrome_anchor = '''        webView.webChromeClient = object : WebChromeClient() {\n            override fun onCreateWindow(\n'''
    chrome_new = '''        webView.webChromeClient = object : WebChromeClient() {\n            override fun onJsAlert(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {\n                if (batchRunning && provider == ProviderId.ADIGA) {\n                    result?.confirm()\n                    if (isAdigaBlockingErrorMessage(message)) {\n                        handleAdigaBlockingDialog(message)\n                    } else {\n                        status.text = "어디가 안내창 자동 확인 후 수집 계속"\n                    }\n                    return true\n                }\n                return super.onJsAlert(view, url, message, result)\n            }\n\n            override fun onJsConfirm(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {\n                if (batchRunning && provider == ProviderId.ADIGA && isAdigaBlockingErrorMessage(message)) {\n                    result?.confirm()\n                    handleAdigaBlockingDialog(message)\n                    return true\n                }\n                return super.onJsConfirm(view, url, message, result)\n            }\n\n            override fun onCreateWindow(\n'''
    if chrome_anchor not in m:
        raise SystemExit(f'v0.6.2 WebChromeClient anchor missing: {p}')
    m = m.replace(chrome_anchor, chrome_new, 1)

    # Transition into an autonomous Jinhak crawl. The manual auto-capture helper is
    # kept as a fallback for pages the user opens after an interrupted run.
    transition_old = '''        unifiedPhase = "jinhak"\n        unifiedPendingAdigaStart = false\n        unifiedJinhakAutoCapture = true\n        unifiedAutoCaptureScheduled = false\n        unifiedJinhakCapturedPages.clear()\n'''
    transition_new = '''        unifiedPhase = "jinhak"\n        unifiedPendingAdigaStart = false\n        unifiedPendingJinhakStart = true\n        unifiedJinhakAutoCapture = false\n        unifiedAutoCaptureScheduled = false\n        unifiedJinhakCapturedPages.clear()\n'''
    if transition_old not in m:
        raise SystemExit(f'v0.6.2 transition state anchor missing: {p}')
    m = m.replace(transition_old, transition_new, 1)

    transition_status_old = '''        batchButton.text = "현재 진학사 화면 전체 분석·누적"\n        diagnosticButton.text = "진학사 전체 분석 전송"\n        unifiedButton.text = "통합 수집 종료"\n        status.text = "통합 수집 2/2 · 진학사 단계: 로그인 후 필요한 화면을 열기만 하면 자동 분석·누적됩니다."\n        webView.loadUrl(ProviderId.JINHAK.homeUrl)\n'''
    transition_status_new = '''        batchButton.text = "진학사 자동 탐색 준비"\n        diagnosticButton.text = "진학사 전체 분석 전송"\n        unifiedButton.text = "통합 수집 종료"\n        status.text = "통합 수집 2/2 · 진학사 안전 자동 탐색 준비: 동일 도메인의 입시정보 링크를 스스로 순회합니다."\n        webView.loadUrl(ProviderId.JINHAK.homeUrl)\n'''
    if transition_status_old not in m:
        raise SystemExit(f'v0.6.2 transition UI anchor missing: {p}')
    m = m.replace(transition_status_old, transition_status_new, 1)

    # Reset the pending Jinhak state when a new unified run begins/ends.
    m = m.replace('''        unifiedPendingAdigaStart = true\n        unifiedJinhakAutoCapture = false\n''', '''        unifiedPendingAdigaStart = true\n        unifiedPendingJinhakStart = false\n        unifiedJinhakAutoCapture = false\n''', 1)
    m = m.replace('''        unifiedJinhakAutoCapture = false\n        unifiedPendingAdigaStart = false\n        unifiedAutoCaptureScheduled = false\n''', '''        unifiedJinhakAutoCapture = false\n        unifiedPendingAdigaStart = false\n        unifiedPendingJinhakStart = false\n        unifiedAutoCaptureScheduled = false\n''', 1)

    # Jinhak now uses the same Local-First completion verifier; no Cloud queue is
    # required merely to decide whether traversal completed.
    completion_old = '''        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) verifyLocalCompletionOrFinish()\n        else verifyCloudCompletionOrFinish()\n'''
    completion_new = '''        if (LOCAL_FIRST_BETA && (provider == ProviderId.ADIGA || provider == ProviderId.JINHAK)) verifyLocalCompletionOrFinish()\n        else verifyCloudCompletionOrFinish()\n'''
    if completion_old not in m:
        raise SystemExit(f'v0.6.2 local completion anchor missing: {p}')
    m = m.replace(completion_old, completion_new, 1)

    # Bound Jinhak discovery independently from the much larger Adiga crawl.
    enqueue_anchor = '''    private fun enqueueDiscoveredUrl(url: String) {\n        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return\n        if (batchVisited.contains(url)) return\n'''
    enqueue_new = '''    private fun enqueueDiscoveredUrl(url: String) {\n        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return\n        if (provider == ProviderId.JINHAK && batchQueued.size + batchVisited.size >= MAX_JINHAK_AUTONAV_PAGES) return\n        if (batchVisited.contains(url)) return\n'''
    if enqueue_anchor not in m:
        raise SystemExit(f'v0.6.2 enqueue bound anchor missing: {p}')
    m = m.replace(enqueue_anchor, enqueue_new, 1)

    # Reset anti-dialog timing at every batch start.
    start_reset_anchor = '''        batchPersistedPageSignatureOwners.clear()\n        disarmBatchNavigationWatchdog()\n'''
    start_reset_new = '''        batchPersistedPageSignatureOwners.clear()\n        batchSkipSnapshotUntilMs = 0L\n        disarmBatchNavigationWatchdog()\n'''
    if start_reset_anchor not in m:
        raise SystemExit(f'v0.6.2 batch reset anchor missing: {p}')
    m = m.replace(start_reset_anchor, start_reset_new, 1)

    # If a stale callback arrives immediately after an intercepted site error dialog,
    # postpone it rather than collecting the just-failed DOM or racing the next page.
    schedule_anchor = '''    private fun scheduleBatchSnapshot() {\n        if (!batchRunning || batchPausedForLogin || batchCollecting) return\n\n'''
    schedule_new = '''    private fun scheduleBatchSnapshot() {\n        if (!batchRunning || batchPausedForLogin || batchCollecting) return\n        val skipWait = batchSkipSnapshotUntilMs - System.currentTimeMillis()\n        if (skipWait > 0L) {\n            handler.postDelayed({ scheduleBatchSnapshot() }, skipWait + 80L)\n            return\n        }\n\n'''
    if schedule_anchor not in m:
        raise SystemExit(f'v0.6.2 scheduleBatchSnapshot anchor missing: {p}')
    m = m.replace(schedule_anchor, schedule_new, 1)

    # Every autonomously visited Jinhak page gets its privacy-sanitized full-screen
    # analysis bundle stored under the unified session, not only normalized records.
    page_records_anchor = '''            val pageRecords = normalizeSnapshot(snapshot)\n            if (activeAction != null && LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {\n'''
    page_records_new = '''            val pageRecords = normalizeSnapshot(snapshot)\n            if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {\n                val sessionId = unifiedSessionId\n                val runId = localRunId ?: localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION).also { localRunId = it }\n                if (sessionId != null) {\n                    localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId)\n                    val capturedAt = Instant.now().toString()\n                    val digest = buildJinhakDigest(snapshot, pageRecords, runId, capturedAt)\n                    lastJinhakDigest = digest\n                    val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))\n                    val pageKey = RecordUtils.sha256(navKey)\n                    localStore.storeUnifiedAnalysisCapture(\n                        sessionId = sessionId,\n                        provider = ProviderId.JINHAK.wireName,\n                        pageKey = pageKey,\n                        pageType = snapshot.optString("providerPageType"),\n                        payload = digest\n                    )\n                    localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)\n                }\n            }\n            if (activeAction != null && LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {\n'''
    if page_records_anchor not in m:
        raise SystemExit(f'v0.6.2 Jinhak batch analysis anchor missing: {p}')
    m = m.replace(page_records_anchor, page_records_new, 1)

    # After Jinhak's autonomous queue drains, close the same unified session and build
    # one two-source export automatically.
    transition_call = '''        if (unifiedRunning && unifiedPhase == "adiga" && provider == ProviderId.ADIGA) {\n            val sessionId = unifiedSessionId\n            if (sessionId != null) {\n                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.ADIGA.wireName, runId) }\n                localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$effectiveReason")\n            }\n            handler.postDelayed({ transitionUnifiedToJinhak(effectiveReason) }, 350L)\n        }\n'''
    transition_call_new = transition_call + '''        else if (unifiedRunning && unifiedPhase == "jinhak" && provider == ProviderId.JINHAK) {\n            val sessionId = unifiedSessionId\n            if (sessionId != null) {\n                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId) }\n                localStore.updateUnifiedSession(sessionId, "jinhak", "running", "jinhak:$effectiveReason")\n            }\n            handler.postDelayed({ finishUnifiedCollection("jinhak:$effectiveReason") }, 350L)\n        }\n'''
    if transition_call not in m:
        raise SystemExit(f'v0.6.2 finish unified anchor missing: {p}')
    m = m.replace(transition_call, transition_call_new, 1)

    # Insert the Adiga dialog helper immediately before the existing batch start.
    start_marker = '    private fun startBatch() {\n'
    dialog_helpers = r'''    private fun isAdigaBlockingErrorMessage(message: String?): Boolean {
        val text = message?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
        if (text.isBlank()) return false
        return Regex("(페이지.{0,12}오류|오류.{0,12}발생|일시적.{0,12}오류|처리.{0,12}오류|서버.{0,12}오류|500|server\\s*error|internal\\s*server\\s*error)", RegexOption.IGNORE_CASE)
            .containsMatchIn(text)
    }

    private fun handleAdigaBlockingDialog(message: String?) {
        if (!batchRunning || provider != ProviderId.ADIGA) return
        val compactMessage = message?.replace(Regex("\\s+"), " ")?.trim()?.take(180).orEmpty()
        val action = activeBatchPageAction ?: pendingBatchPageAction
        activeBatchPageAction = null
        pendingBatchPageAction = null
        batchSkipSnapshotUntilMs = System.currentTimeMillis() + 1800L

        if (action != null) {
            val key = pageActionKey(action)
            batchPageActionQueued.remove(key)
            batchPageActionFailed.add(key)
            batchErrors.put(JSONObject()
                .put("url", action.baseUrl)
                .put("type", "site-blocking-dialog")
                .put("page", action.page)
                .put("totalPages", action.totalPages)
                .put("familyKey", action.familyKey)
                .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
                .put("retryCount", action.retry)
                .put("message", compactMessage))
            localRunId?.let { runId ->
                localStore.markPage(
                    runId, action.familyKey, action.requestedYear,
                    action.page, action.totalPages, "error", action.retry, "site-blocking-dialog"
                )
                localStore.markDocument(runId, canonicalizeBatchUrl(action.baseUrl), "error", action.retry, "site-blocking-dialog")
            }
        } else {
            val navKey = canonicalizeBatchUrl(webView.url ?: currentBatchTarget.orEmpty())
            if (navKey.isNotBlank()) {
                batchVisited.add(navKey)
                batchErrors.put(JSONObject()
                    .put("url", navKey)
                    .put("type", "site-blocking-dialog")
                    .put("message", compactMessage))
                localRunId?.let { runId ->
                    localStore.markDocument(runId, navKey, "error", 0, "site-blocking-dialog")
                }
            }
        }
        status.text = "어디가 페이지 오류창 자동 차단: 오류를 체크포인트에 남기고 다음 페이지로 진행합니다."
        handler.postDelayed({
            if (batchRunning && !batchPausedForLogin) loadNextBatchPage()
        }, 220L)
    }

'''
    if start_marker not in m:
        raise SystemExit(f'v0.6.2 startBatch marker missing: {p}')
    m = m.replace(start_marker, dialog_helpers + start_marker, 1)

    p.write_text(m)

# ---- Jinhak adapter: bounded same-origin autonomous traversal + hub false-positive guard. ----
j = JINHAK.read_text()
j = j.replace('override val supportsBatchCrawl = false', 'override val supportsBatchCrawl = true', 1)

old_nav = '''    override fun isBatchNavigable(url: String): Boolean = false\n\n'''
new_nav = r'''    override fun seedUrls(): List<String> = listOf("https://www.jinhak.com/")

    override fun isBatchNavigable(url: String): Boolean {
        if (!accepts(url)) return false
        return try {
            val uri = URI(url)
            val path = (uri.path ?: "/").lowercase()
            val query = (uri.query ?: "").lowercase()
            val full = "$path?$query"
            if (Regex("(?:logout|signout|member|mypage|my-page|account|payment|pay|coupon|refund|withdraw|profile|userinfo|customer|faq|qna|event|notice|privacy|terms)").containsMatchIn(full)) return false
            if (Regex("\\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|map|woff2?|ttf|eot|zip|hwp|hwpx|pdf)$", RegexOption.IGNORE_CASE).containsMatchIn(path)) return false
            true
        } catch (_: Exception) { false }
    }

'''
if old_nav not in j:
    raise SystemExit('v0.6.2 Jinhak navigation anchor missing')
j = j.replace(old_nav, new_nav, 1)

# Home page is a navigation hub. It must never inherit a random article/table context
# and become an accepted university/department record.
classify_anchor = '''        val url = snapshot.optString("url").lowercase()\n        val text = GenericAdmissionParser.collectText(snapshot)\n        val hasPrediction = text.contains("합격예측") || text.contains("모의지원") || Regex("[0-9]{1,2}\\\\s*칸").containsMatchIn(text)\n        val hasActual = text.contains("실제합격자") ||\n            (text.contains("입시결과") && Regex("(최종등록|합격자|충원|70%|50%)").containsMatchIn(text))\n'''
classify_new = '''        val url = snapshot.optString("url").lowercase()\n        val text = GenericAdmissionParser.collectText(snapshot)\n        val path = runCatching { URI(snapshot.optString("url")).path?.lowercase() ?: "/" }.getOrDefault("/")\n        val rootPage = path.isBlank() || path == "/" || path.endsWith("/index") || path.endsWith("/index.html")\n        val hasPrediction = text.contains("합격예측") || text.contains("모의지원") || Regex("[0-9]{1,2}\\\\s*칸").containsMatchIn(text)\n        val hasActual = Regex("(실제합격자\\\\s*(?:리포트|사례)|합격자\\\\s*리포트|전년도\\\\s*입시결과\\\\s*(?:리포트|상세))").containsMatchIn(text) ||\n            Regex("(actual|admitreport|resultreport|passcase)").containsMatchIn(url)\n'''
if classify_anchor not in j:
    raise SystemExit('v0.6.2 Jinhak classify anchor missing')
j = j.replace(classify_anchor, classify_new, 1)

when_anchor = '''        return when {\n            Regex("(login|signin|member/login)").containsMatchIn(url) || text.contains("로그인") && text.contains("비밀번호") -> "jinhak-login"\n            earlyStorage -> "jinhak-early-storage"\n'''
when_new = '''        return when {\n            Regex("(login|signin|member/login)").containsMatchIn(url) || text.contains("로그인") && text.contains("비밀번호") -> "jinhak-login"\n            rootPage -> "jinhak-home"\n            earlyStorage -> "jinhak-early-storage"\n'''
if when_anchor not in j:
    raise SystemExit('v0.6.2 Jinhak classify when anchor missing')
j = j.replace(when_anchor, when_new, 1)

# Navigation/reference surfaces are retained in the full-screen analysis bundle but do
# not emit page-wide accepted records. This fixes the v0.6.1 home-page false positives.
guard_anchor = '''            return RecordUtils.dedupe(result)\n        }\n\n        val metrics = JSONObject()\n'''
guard_new = '''            return RecordUtils.dedupe(result)\n        }\n\n        if (pageType == "jinhak-home" || pageType == "jinhak-university-search" || pageType == "jinhak-curation" || pageType == "jinhak-other") {\n            return result\n        }\n\n        val metrics = JSONObject()\n'''
if guard_anchor not in j:
    raise SystemExit('v0.6.2 Jinhak normalization guard anchor missing')
j = j.replace(guard_anchor, guard_new, 1)

# Explicit data-scope marker for the new hub classification.
j = j.replace('''        "jinhak-score-calc-report", "jinhak-student-basic" -> "student-profile"\n        else -> "reference"\n''', '''        "jinhak-score-calc-report", "jinhak-student-basic" -> "student-profile"\n        "jinhak-home", "jinhak-university-search", "jinhak-curation" -> "reference-navigation"\n        else -> "reference"\n''', 1)

JINHAK.write_text(j)

# ---- Version metadata ----
g = GRADLE.read_text()
g = g.replace('versionCode = 10610', 'versionCode = 10620', 1)
g = g.replace('versionName = "0.6.1"', 'versionName = "0.6.2"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text()
mf = mf.replace('Admission Collector v0.6.1 Unified Two-Site Collector', 'Admission Collector v0.6.2 Unified Autonomous Explorer', 1)
MANIFEST.write_text(mf)

# Mirror invariant.
if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirror mismatch after v0.6.2 patch')

print('v0.6.2 autonomous Jinhak explorer + Adiga blocking-dialog recovery patch applied')
