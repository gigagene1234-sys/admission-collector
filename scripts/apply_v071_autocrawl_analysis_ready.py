from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
JINHAK = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
SYNC = ROOT / 'app/src/main/java/com/admissionhub/collector/sync/UnifiedSyncState.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MAIN_WF = ROOT / '.github/workflows/build-admission-collector-main.yml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'missing anchor: {label}')
    if text.count(old) != 1:
        raise SystemExit(f'non-unique anchor {label}: {text.count(old)}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Version bump
# ---------------------------------------------------------------------------
main = MAIN.read_text()
main = replace_once(main, 'private const val VERSION = "0.7.0"', 'private const val VERSION = "0.7.1"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 10700', 'private const val BUILD_CODE = 10710', 'main build')

# ---------------------------------------------------------------------------
# Restore the v0.6.6 autonomous Jinhak batch hand-off.
# Keep v0.7.0 Observation Foundation and all memory/crash guards.
# ---------------------------------------------------------------------------
old_onfinish = '''                if (unifiedRunning && unifiedPhase == "jinhak" && unifiedPendingJinhakStart && provider == ProviderId.JINHAK && !batchRunning) {
                    unifiedPendingJinhakStart = false
                    unifiedJinhakAutoCapture = true
                    status.text = "통합 수집 2/2 · 진학사: 사용자가 직접 여는 입시 데이터 화면만 자동 분석·누적합니다."
                    handler.postDelayed({
                        if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) scheduleUnifiedJinhakAutoCapture(url)
                    }, 450L)
                    return
                }'''
new_onfinish = '''                if (unifiedRunning && unifiedPhase == "jinhak" && unifiedPendingJinhakStart && provider == ProviderId.JINHAK && !batchRunning) {
                    unifiedPendingJinhakStart = false
                    unifiedJinhakAutoCapture = false
                    status.text = "통합 수집 2/2 · 진학사 자동 크롤러 시작: 접근 가능한 진학사 화면을 자율 순회합니다."
                    handler.postDelayed({
                        if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
                    }, 450L)
                    return
                }'''
main = replace_once(main, old_onfinish, new_onfinish, 'jinhak onPageFinished handoff')

old_resume = '''            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = true
            status.text = "이전 중단 감지: 진학사에서 사용자가 직접 여는 입시 화면의 자동 분석·누적을 재개합니다."
            webView.loadUrl(ProviderId.JINHAK.homeUrl)'''
new_resume = '''            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = false
            status.text = "이전 중단 감지: 진학사 자동 크롤러를 체크포인트에서 재개합니다."
            webView.loadUrl(ProviderId.JINHAK.homeUrl)'''
main = replace_once(main, old_resume, new_resume, 'jinhak interrupted resume')

old_transition_state = '''        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY.name, ProviderId.JINHAK.wireName, JSONObject().put("authorizedConnectorActive", false), false)
        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK.name, ProviderId.JINHAK.wireName, JSONObject().put("observationFirst", true), false)'''
new_transition_state = '''        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY.name, ProviderId.JINHAK.wireName, JSONObject().put("authorizedConnectorActive", false), false)
        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL.name, ProviderId.JINHAK.wireName,
            JSONObject().put("observationFirst", true).put("boundedSameProviderTraversal", true).put("maxPages", MAX_JINHAK_AUTONAV_PAGES), false)'''
main = replace_once(main, old_transition_state, new_transition_state, 'jinhak sync state')

old_transition_ui = '''        batchButton.text = "현재 진학사 화면 전체 분석·누적"
        diagnosticButton.text = "진학사 전체 분석 전송"
        unifiedButton.text = "통합 수집 종료"
        status.text = "통합 수집 2/2 · 진학사 분석 대기: 원하는 수시저장소·추천대학·대학정보·리포트 화면을 직접 열면 자동 분석합니다."'''
new_transition_ui = '''        batchButton.text = "진학사 자동 탐색 준비"
        diagnosticButton.text = "진학사 전체 분석 전송"
        unifiedButton.text = "통합 수집 종료"
        status.text = "통합 수집 2/2 · 진학사 자동 크롤러 준비: 로그인 세션을 유지한 채 접근 가능한 화면을 자율 순회합니다."'''
main = replace_once(main, old_transition_ui, new_transition_ui, 'jinhak transition UI')

# Batch captures must preserve v0.7 Observation Evidence too, not only parsed records.
old_batch_store = '''                    localStore.storeUnifiedAnalysisCapture(
                        sessionId = sessionId,
                        provider = ProviderId.JINHAK.wireName,
                        pageKey = pageKey,
                        pageType = snapshot.optString("providerPageType"),
                        payload = digest
                    )
                    localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)'''
new_batch_store = '''                    localStore.storeUnifiedAnalysisCapture(
                        sessionId = sessionId,
                        provider = ProviderId.JINHAK.wireName,
                        pageKey = pageKey,
                        pageType = snapshot.optString("providerPageType"),
                        payload = digest
                    )
                    val batchPageType = snapshot.optString("providerPageType")
                    val batchSession = snapshot.optJSONObject("session") ?: JSONObject()
                    val batchAuthState = when {
                        batchSession.optBoolean("needsLogin", false) -> "auth-required"
                        batchSession.optBoolean("authenticated", false) -> "authenticated"
                        else -> "unknown"
                    }
                    localStore.storeObservationEvidence(
                        sessionId = sessionId,
                        runId = runId,
                        provider = ProviderId.JINHAK.wireName,
                        safeRouteKey = runtimeSafePath(snapshot.optString("url")),
                        pageTypeGuess = batchPageType,
                        pageTypeConfidence = if (batchPageType == "jinhak-other") 0.25 else 0.85,
                        authStateClass = batchAuthState,
                        explicitContext = ObservationEvidence.explicitContextFromDigest(digest),
                        evidence = digest,
                        captureVersion = VERSION
                    )
                    localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)'''
main = replace_once(main, old_batch_store, new_batch_store, 'batch observation persistence')

MAIN.write_text(main)

# ---------------------------------------------------------------------------
# Restore autonomous navigation capability while retaining v0.6.7+ parsers.
# Do not label unparsed pages as valueless: navigation is broad, storage remains
# observation-first. Only unsafe/account/payment/legal/static surfaces are blocked.
# ---------------------------------------------------------------------------
j = JINHAK.read_text()
j = replace_once(j, 'override val supportsBatchCrawl = false', 'override val supportsBatchCrawl = true', 'supportsBatchCrawl')
old_nav = '    override fun isBatchNavigable(url: String): Boolean = false'
new_nav = '''    override fun isBatchNavigable(url: String): Boolean {
        if (!accepts(url)) return false
        return try {
            val uri = URI(url)
            val path = (uri.path ?: "/").lowercase()
            val query = (uri.query ?: "").lowercase()
            val full = "$path?$query"
            // Safety/state-changing surfaces are never auto-opened. Information pages are not
            // discarded merely because the current parser does not understand them yet.
            if (Regex("(?:logout|signout|member|mypage|my-page|account|profile|userinfo|payment|billing|purchase|order|spassdata|coupon|refund|withdraw|customer|faq|qna|event|notice|privacy|terms)").containsMatchIn(full)) return false
            if (Regex("\\\\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|map|woff2?|ttf|eot|zip|hwp|hwpx|pdf)$", RegexOption.IGNORE_CASE).containsMatchIn(path)) return false
            true
        } catch (_: Exception) { false }
    }'''
j = replace_once(j, old_nav, new_nav, 'isBatchNavigable')
JINHAK.write_text(j)

# ---------------------------------------------------------------------------
# Explicit autonomous crawler orchestration state.
# ---------------------------------------------------------------------------
s = SYNC.read_text()
s = replace_once(s, '    JINHAK_AUTHORIZED_SYNC,\n    JINHAK_USER_VIEW_FALLBACK,', '    JINHAK_AUTHORIZED_SYNC,\n    JINHAK_AUTONOMOUS_CRAWL,\n    JINHAK_USER_VIEW_FALLBACK,', 'sync enum')
s = replace_once(
    s,
    '''        UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY to setOf(\n            UnifiedSyncState.JINHAK_AUTHORIZED_SYNC,\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,''',
    '''        UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY to setOf(\n            UnifiedSyncState.JINHAK_AUTHORIZED_SYNC,\n            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,''',
    'capability transition'
)
s = replace_once(
    s,
    '''        UnifiedSyncState.JINHAK_AUTHORIZED_SYNC to setOf(\n            UnifiedSyncState.CANONICAL_MERGE,\n            UnifiedSyncState.AUTH_REQUIRED,\n            UnifiedSyncState.FAILED\n        ),\n        UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK''',
    '''        UnifiedSyncState.JINHAK_AUTHORIZED_SYNC to setOf(\n            UnifiedSyncState.CANONICAL_MERGE,\n            UnifiedSyncState.AUTH_REQUIRED,\n            UnifiedSyncState.FAILED\n        ),\n        UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL to setOf(\n            UnifiedSyncState.CANONICAL_MERGE,\n            UnifiedSyncState.AUTH_REQUIRED,\n            UnifiedSyncState.FAILED\n        ),\n        UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK''',
    'crawler transition block'
)
s = replace_once(s, '            UnifiedSyncState.JINHAK_AUTHORIZED_SYNC,\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,', '            UnifiedSyncState.JINHAK_AUTHORIZED_SYNC,\n            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,', 'auth resume transition')
SYNC.write_text(s)

# ---------------------------------------------------------------------------
# Analysis-ready export contract: no duplicate giant normalized array is created.
# The existing full records + observations remain authoritative; this manifest tells
# downstream analysis (including ChatGPT spreadsheet generation) how to materialize
# a visual workbook without losing provenance.
# ---------------------------------------------------------------------------
store = STORE.read_text()
old_writer = '''        writer.write("{\\\"schemaVersion\\\":3,\\\"type\\\":\\\"admission-unified-two-provider-export\\\",\\\"session\\\":")
        writer.write(status.toString())
        writer.write(",\\\"combinationPolicy\\\":{\\\"officialBaseline\\\":\\\"adiga\\\",\\\"predictionAnalysis\\\":\\\"jinhak\\\",\\\"keepProviderSemanticsSeparate\\\":true,\\\"doNotOverwriteHistoricalWithPrediction\\\":true},\\\"sources\\\":{\\\"adiga\\\":{\\\"runId\\\":")'''
new_writer = '''        writer.write("{\\\"schemaVersion\\\":4,\\\"type\\\":\\\"admission-unified-two-provider-export\\\",\\\"session\\\":")
        writer.write(status.toString())
        writer.write(",\\\"analysisReady\\\":{\\\"contractVersion\\\":1,\\\"purpose\\\":\\\"assistant-xlsx-dashboard-generation\\\",\\\"authoritativeLayers\\\":[\\\"sources.adiga.records\\\",\\\"sources.jinhak.records\\\",\\\"sources.jinhak.pageAnalyses\\\",\\\"observationEvidence\\\"],\\\"recommendedWorkbookSheets\\\":[\\\"Dashboard\\\",\\\"UnifiedRecords\\\",\\\"JinhakPredictions\\\",\\\"HistoricalResults\\\",\\\"Observations\\\",\\\"Coverage\\\",\\\"Errors\\\"],\\\"rowKeyFields\\\":[\\\"provider\\\",\\\"year\\\",\\\"university\\\",\\\"department\\\",\\\"admission\\\",\\\"recordType\\\",\\\"observedAt\\\"],\\\"flattenMetricsForSpreadsheet\\\":true,\\\"preserveRawEvidence\\\":true,\\\"doNotInferMissingBindings\\\":true,\\\"observationFirst\\\":true},\\\"combinationPolicy\\\":{\\\"officialBaseline\\\":\\\"adiga\\\",\\\"predictionAnalysis\\\":\\\"jinhak\\\",\\\"keepProviderSemanticsSeparate\\\":true,\\\"doNotOverwriteHistoricalWithPrediction\\\":true},\\\"sources\\\":{\\\"adiga\\\":{\\\"runId\\\":")'''
store = replace_once(store, old_writer, new_writer, 'streaming analysis-ready manifest')
STORE.write_text(store)

# ---------------------------------------------------------------------------
# Gradle version
# ---------------------------------------------------------------------------
g = GRADLE.read_text()
g = replace_once(g, 'versionCode = 10700', 'versionCode = 10710', 'gradle versionCode')
g = replace_once(g, 'versionName = "0.7.0"', 'versionName = "0.7.1"', 'gradle versionName')
GRADLE.write_text(g)

# ---------------------------------------------------------------------------
# Main CI invariants must follow the new committed source.
# ---------------------------------------------------------------------------
wf = MAIN_WF.read_text()
wf = wf.replace('private const val VERSION = "0.7.0"', 'private const val VERSION = "0.7.1"')
wf = wf.replace('private const val BUILD_CODE = 10700', 'private const val BUILD_CODE = 10710')
wf = wf.replace('versionCode = 10700', 'versionCode = 10710')
wf = wf.replace('versionName = "0.7.0"', 'versionName = "0.7.1"')
wf = wf.replace("grep -q 'override val supportsBatchCrawl = false' app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt", "grep -q 'override val supportsBatchCrawl = true' app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt")
wf = wf.replace("          if 'supportsBatchCrawl = true' in adapter:\n              raise SystemExit('protected Jinhak batch crawler re-enabled')\n", "          if 'supportsBatchCrawl = false' in adapter:\n              raise SystemExit('Jinhak autonomous crawler rollback is not active')\n")
wf = wf.replace("          name: admission-collector-main-v0.7.0-debug", "          name: admission-collector-main-v0.7.1-debug")
wf = wf.replace("grep -q \"versionCode='10700'\" /tmp/badging.txt", "grep -q \"versionCode='10710'\" /tmp/badging.txt")
wf = wf.replace("grep -q \"versionName='0.7.0'\" /tmp/badging.txt", "grep -q \"versionName='0.7.1'\" /tmp/badging.txt")
# Add invariants for this release if not already present.
needle = "          grep -q 'JINHAK_CAPABILITY_DISCOVERY' app/src/main/java/com/admissionhub/collector/sync/UnifiedSyncState.kt\n"
extra = needle + "          grep -q 'JINHAK_AUTONOMOUS_CRAWL' app/src/main/java/com/admissionhub/collector/sync/UnifiedSyncState.kt\n          grep -q 'assistant-xlsx-dashboard-generation' \"$STORE\"\n          grep -q 'storeObservationEvidence' \"$MAIN\"\n"
if needle in wf and 'assistant-xlsx-dashboard-generation' not in wf:
    wf = wf.replace(needle, extra, 1)
MAIN_WF.write_text(wf)

# ---------------------------------------------------------------------------
# Release invariants
# ---------------------------------------------------------------------------
checks = {
    'version': 'private const val VERSION = "0.7.1"' in MAIN.read_text(),
    'build': 'private const val BUILD_CODE = 10710' in MAIN.read_text(),
    'crawler-enabled': 'override val supportsBatchCrawl = true' in JINHAK.read_text(),
    'crawler-state': 'JINHAK_AUTONOMOUS_CRAWL' in SYNC.read_text(),
    'observation-batch': 'batchPageType = snapshot.optString("providerPageType")' in MAIN.read_text(),
    'analysis-contract': 'assistant-xlsx-dashboard-generation' in STORE.read_text(),
    'no-user-view-default': 'JINHAK_USER_VIEW_FALLBACK.name' not in MAIN.read_text(),
}
failed = [k for k,v in checks.items() if not v]
if failed:
    raise SystemExit('failed invariants: ' + ', '.join(failed))
print('v0.7.1 patch applied:', ', '.join(k for k,v in checks.items() if v))
