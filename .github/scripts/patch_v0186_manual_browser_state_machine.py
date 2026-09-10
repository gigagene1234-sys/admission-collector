from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
STORE = ROOT / "app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def must_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if new in text:
        return text
    actual = text.count(old)
    if actual < count:
        raise SystemExit(f"{label}: expected at least {count} anchor(s), found {actual}")
    return text.replace(old, new, count)


def replace_function(text: str, name_pattern: str, replacement: str, label: str) -> str:
    if replacement.strip() in text:
        return text
    pattern = rf"    private fun {name_pattern}.*?(?=\n    private fun |\n    fun |\n    override fun |\n}}\s*$)"
    updated, count = re.subn(pattern, replacement.rstrip(), text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected one function, found {count}")
    return updated


# ---------------------------------------------------------------------------
# Version truth: APK metadata, runtime export metadata and launcher label agree.
# ---------------------------------------------------------------------------
gradle = GRADLE.read_text()
gradle = must_replace(gradle, 'versionCode = 118500', 'versionCode = 118600', 'gradle-version-code')
gradle = must_replace(gradle, 'versionName = "0.18.5"', 'versionName = "0.18.6"', 'gradle-version-name')
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = must_replace(
    manifest,
    'android:label="Admission Hub v0.18.5 Manual Storage Reports"',
    'android:label="Admission Hub v0.18.6 Manual Browser State Machine"',
    'manifest-label',
)
MANIFEST.write_text(manifest)

text = MAIN.read_text()
if 'import com.admissionhub.collector.jinhak.JinhakManualBrowserStateMachine' not in text:
    text = must_replace(
        text,
        'import com.admissionhub.collector.jinhak.JinhakManualStorageReportPolicy\n',
        'import com.admissionhub.collector.jinhak.JinhakManualStorageReportPolicy\nimport com.admissionhub.collector.jinhak.JinhakManualBrowserStateMachine\n',
        'main-state-machine-import',
    )
text = must_replace(text, 'private const val VERSION = "0.18.4"', 'private const val VERSION = "0.18.6"', 'runtime-version')
text = must_replace(text, 'private const val BUILD_CODE = 118400', 'private const val BUILD_CODE = 118600', 'runtime-build-code')

# ---------------------------------------------------------------------------
# MANUAL_BROWSER: do not intercept any Jinhak navigation before /library.
# Service-worker interception must also be passive because it can otherwise
# cancel assets/redirects required by the provider login flow.
# ---------------------------------------------------------------------------
service_worker_anchor = '''                override fun shouldInterceptRequest(request: WebResourceRequest): WebResourceResponse? {
                    val target = request.url?.toString().orEmpty()
                    if (provider == ProviderId.JINHAK && JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {'''
service_worker_replacement = '''                override fun shouldInterceptRequest(request: WebResourceRequest): WebResourceResponse? {
                    val target = request.url?.toString().orEmpty()
                    if (provider == ProviderId.JINHAK && !batchRunning) return null
                    if (provider == ProviderId.JINHAK && JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {'''
text = must_replace(text, service_worker_anchor, service_worker_replacement, 'manual-service-worker-bypass')

main_intercept_anchor = '''                if (provider == ProviderId.JINHAK) {
                    if (JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {'''
main_intercept_replacement = '''                if (provider == ProviderId.JINHAK) {
                    if (!batchRunning) return super.shouldInterceptRequest(view, request)
                    if (JinhakManualBrowserStateMachine.shouldStopOnly(target, batchRunning)) return super.shouldInterceptRequest(view, request)
                    if (JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {'''
text = must_replace(text, main_intercept_anchor, main_intercept_replacement, 'manual-main-request-bypass')

main_override_anchor = '''            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (provider != ProviderId.JINHAK || target.isBlank()) return false
                if (JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {'''
main_override_replacement = '''            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (provider != ProviderId.JINHAK || target.isBlank()) return false
                if (!batchRunning) return false
                if (JinhakManualBrowserStateMachine.shouldStopOnly(target, batchRunning)) {
                    handler.post {
                        if (provider == ProviderId.JINHAK && batchRunning) {
                            stopBatch("jinhak-left-manual-storage-report-scope")
                            sessionState.text = "○ 직접 탐색 · 수시 저장소 재진입 필요"
                            status.text = "자동 탐색 범위를 벗어났습니다. 페이지 이동은 막지 않습니다. 수시 저장소로 직접 돌아오면 다시 시작합니다."
                        }
                    }
                    return false
                }
                if (JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)) {'''
text = must_replace(text, main_override_anchor, main_override_replacement, 'manual-main-navigation-bypass')

history_anchor = '''                if (provider != ProviderId.JINHAK) return
                if (jinhakUserSessionConfirmed && JinhakStrictHigh3Sandbox.isBenignSameDocumentHistoryAlias(url)) {'''
history_replacement = '''                if (provider != ProviderId.JINHAK) return
                if (!batchRunning) return
                if (JinhakManualBrowserStateMachine.shouldStopOnly(url, batchRunning)) {
                    stopBatch("jinhak-left-manual-storage-report-scope-history")
                    sessionState.text = "○ 직접 탐색 · 수시 저장소 재진입 필요"
                    status.text = "자동 탐색 범위를 벗어났습니다. SPA 이동은 차단하지 않습니다. 수시 저장소로 직접 돌아오면 다시 시작합니다."
                    return
                }
                if (jinhakUserSessionConfirmed && JinhakStrictHigh3Sandbox.isBenignSameDocumentHistoryAlias(url)) {'''
text = must_replace(text, history_anchor, history_replacement, 'manual-spa-history-bypass')

# Main-page callbacks must not feed legacy auth state while the user is logging in/navigating.
page_started_anchor = '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                if (provider == ProviderId.JINHAK) {'''
page_started_replacement = '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                if (provider == ProviderId.JINHAK && !batchRunning) {
                    clearJinhakLegacyAuthState()
                    return
                }
                if (provider == ProviderId.JINHAK) {'''
text = must_replace(text, page_started_anchor, page_started_replacement, 'manual-page-start-bypass')

# Even if a legacy caller reaches these functions, credential autofill is impossible.
text = replace_function(
    text,
    r"beginV0184SingleSurfaceAutofill\(\)",
    '''    private fun beginV0184SingleSurfaceAutofill() {
        // v0.18.6: Jinhak credentials are never read or injected by Admission Hub.
        jinhakV0184AutofillRunning = false
    }
''',
    'neutral-v0184-autofill-entry',
)
text = replace_function(
    text,
    r"attemptV0184SingleSurfaceAutofill\(generation: Int, attempt: Int, username: String, password: String\)",
    '''    private fun attemptV0184SingleSurfaceAutofill(generation: Int, attempt: Int, username: String, password: String) {
        // v0.18.6 compatibility stub. No DOM credential access, submit, retry or login inference.
        jinhakV0184AutofillRunning = false
    }
''',
    'neutral-v0184-autofill-attempt',
)

# Legacy route blocker becomes STOP-only. It cannot invoke auth, redirect, or stop the user's page.
text = replace_function(
    text,
    r"blockJinhakV0174MainFrame\(source: String, target: String, decision: JinhakStrictHigh3Sandbox.MainFrameDecision\)",
    '''    private fun blockJinhakV0174MainFrame(source: String, target: String, decision: JinhakStrictHigh3Sandbox.MainFrameDecision) {
        if (provider != ProviderId.JINHAK) return
        noteJinhakV0174Decision(source, target, decision)
        if (!batchRunning) return
        if (JinhakManualBrowserStateMachine.shouldStopOnly(target, true)) {
            stopBatch("jinhak-left-manual-storage-report-scope:$source")
            sessionState.text = "○ 직접 탐색 · 수시 저장소 재진입 필요"
            status.text = "자동 탐색 범위를 벗어났습니다. 로그인/라우팅 복구는 실행하지 않습니다."
        }
    }
''',
    'neutral-legacy-route-blocker',
)

MAIN.write_text(text)

# ---------------------------------------------------------------------------
# Exact local rebind for six pinned applications.
# Reuse is allowed only when the previous canonical session contains every
# pinned application_identity_key exactly; no name similarity or cross-card inference.
# ---------------------------------------------------------------------------
store = STORE.read_text()
helper_marker = '    private fun canonicalSessionForExactPinnedRebind(sessionId: String): String {'
if helper_marker not in store:
    insertion_anchor = '    fun canonicalHubSummary(sessionId: String): JSONObject {'
    if insertion_anchor not in store:
        raise SystemExit('local-rebind-helper: canonicalHubSummary anchor missing')
    helper = '''    private fun canonicalSessionForExactPinnedRebind(sessionId: String): String {
        if (sessionId.isBlank()) return sessionId
        val pinned = pinnedHubSlotCount()
        if (pinned <= 0) return sessionId
        val matchedCurrent = readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM canonical_applications WHERE session_id=? AND application_identity_key IN (SELECT application_identity_key FROM hub_application_slots WHERE user_pinned=1)",
            arrayOf(sessionId)
        ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        if (matchedCurrent == pinned) return sessionId
        return latestReusableCanonicalSessionId() ?: sessionId
    }

'''
    store = store.replace(insertion_anchor, helper + insertion_anchor, 1)

store = must_replace(
    store,
    '''    fun canonicalHubSummary(sessionId: String): JSONObject {
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val slots = loadHubApplicationSlots()
        val audit = readableDatabase.rawQuery(
            "SELECT audit_json FROM hub_quality_audits WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)''',
    '''    fun canonicalHubSummary(sessionId: String): JSONObject {
        val canonicalEvidenceSessionId = canonicalSessionForExactPinnedRebind(sessionId)
        val candidates = loadCanonicalApplicationCandidates(canonicalEvidenceSessionId)
        val slots = loadHubApplicationSlots()
        val audit = readableDatabase.rawQuery(
            "SELECT audit_json FROM hub_quality_audits WHERE session_id=? LIMIT 1",
            arrayOf(canonicalEvidenceSessionId)''',
    'canonical-hub-exact-rebind',
)
store = must_replace(
    store,
    '.put("candidateGraph", candidates)\n            .put("slots", slots)',
    '.put("candidateGraph", candidates)\n            .put("canonicalEvidenceSessionId", canonicalEvidenceSessionId)\n            .put("slots", slots)',
    'canonical-hub-rebind-diagnostic',
)
store = must_replace(
    store,
    '.put("selectedRecoveryPlan", selectedSixRecoveryPlan(sessionId))',
    '.put("selectedRecoveryPlan", selectedSixRecoveryPlan(canonicalEvidenceSessionId))',
    'canonical-hub-recovery-rebind',
)

score_anchor = '''    fun scoreDecisionSummary(sessionId: String): JSONObject {
        val db = readableDatabase
        val fullProfile = currentStudentScoreProfile()
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val candidateById = (0 until candidates.length()).map { candidates.getJSONObject(it) }.associateBy { it.optString("applicationIdentityKey") }
        val slots = loadHubApplicationSlots()
        val selected = (0 until slots.length()).mapNotNull { slots.optJSONObject(it)?.optString("applicationIdentityKey") }.toSet()'''
score_replacement = '''    fun scoreDecisionSummary(sessionId: String): JSONObject {
        val db = readableDatabase
        val fullProfile = currentStudentScoreProfile()
        val canonicalEvidenceSessionId = canonicalSessionForExactPinnedRebind(sessionId)
        val candidates = loadCanonicalApplicationCandidates(canonicalEvidenceSessionId)
        val candidateById = (0 until candidates.length()).map { candidates.getJSONObject(it) }.associateBy { it.optString("applicationIdentityKey") }
        val slots = loadHubApplicationSlots()
        val selected = (0 until slots.length()).mapNotNull { slots.optJSONObject(it)?.optString("applicationIdentityKey") }.toSet()'''
store = must_replace(store, score_anchor, score_replacement, 'score-summary-exact-rebind')

review_anchor = '                val review = ApplicationReviewEngine.evaluate(candidateById[identity] ?: JSONObject(), loadApplicationReviewInput(identity), fullProfile, prediction, Instant.now())'
review_replacement = '''                val reviewCandidate = candidateById[identity] ?: JSONObject()
                val reviewInput = loadApplicationReviewInput(identity)
                    .put("applicationIdentityKey", identity)
                    .put("academicYear", reviewCandidate.optInt("academicYear", 0))
                val review = ApplicationReviewEngine.evaluate(reviewCandidate, reviewInput, fullProfile, prediction, Instant.now())'''
store = must_replace(store, review_anchor, review_replacement, 'review-identity-year-binding')

STORE.write_text(store)
