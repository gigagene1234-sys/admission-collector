from pathlib import Path

main_p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
ledger_p = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionTargetLedger.kt')
seq_p = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionLaneSequencer.kt')
topo_p = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt')
gradle_p = Path('app/build.gradle.kts')
manifest_p = Path('app/src/main/AndroidManifest.xml')

main = main_p.read_text()
ledger = ledger_p.read_text()
seq = seq_p.read_text()
topo = topo_p.read_text()
gradle = gradle_p.read_text()
manifest = manifest_p.read_text()

def must_replace(text, old, new, label, count=1):
    if old not in text:
        raise SystemExit(f'missing replacement anchor: {label}')
    return text.replace(old, new, count)

# Version metadata.
main = must_replace(main, 'private const val VERSION = "0.9.8"', 'private const val VERSION = "0.9.9"', 'version')
main = must_replace(main, 'private const val BUILD_CODE = 10980', 'private const val BUILD_CODE = 10990', 'build')
gradle = must_replace(gradle, 'versionCode = 10980', 'versionCode = 10990', 'gradle-code')
gradle = must_replace(gradle, 'versionName = "0.9.8"', 'versionName = "0.9.9"', 'gradle-name')
manifest = must_replace(manifest, 'Admission Collector v0.9.8 Auth Recovery KeepAlive', 'Admission Collector v0.9.9 Mission Ledger Routing', 'manifest-label')

# Diagnostics for the new routing fixes.
state_anchor = '''    private var jinhakSessionExtensionClicks = 0
    private var jinhakBatchStartCount = 0
'''
state_new = '''    private var jinhakSessionExtensionClicks = 0
    private var jinhakOriginInferredMissionTargets = 0
    private var jinhakExternalNavigationsBlocked = 0
    private var jinhakBatchStartCount = 0
'''
main = must_replace(main, state_anchor, state_new, 'v099-state')

reset_anchor = '''        jinhakSessionKeepAliveTicks = 0
        jinhakSessionKeepAliveBackgroundTicks = 0
        jinhakSessionExtensionClicks = 0

        // v0.9.2: restore the encrypted provider session bundles first.
'''
reset_new = '''        jinhakSessionKeepAliveTicks = 0
        jinhakSessionKeepAliveBackgroundTicks = 0
        jinhakSessionExtensionClicks = 0
        jinhakOriginInferredMissionTargets = 0
        jinhakExternalNavigationsBlocked = 0

        // v0.9.2: restore the encrypted provider session bundles first.
'''
main = must_replace(main, reset_anchor, reset_new, 'v099-reset')

# Block external-domain navigations during autonomous Jinhak collection. The real-device v0.9.8
# run reached YouTube even though the URL frontier itself is provider-scoped; clicks can bypass the
# frontier, so enforce the provider boundary at the WebView navigation layer as well.
nav_old = '''        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
'''
nav_new = '''        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (batchRunning && provider == ProviderId.JINHAK && target.isNotBlank() && !ProviderRegistry.adapter(ProviderId.JINHAK).accepts(target)) {
                    jinhakExternalNavigationsBlocked += 1
                    recordRuntimeEvent("jinhak-external-navigation-blocked", JSONObject()
                        .put("targetSafePath", runtimeSafePath(target))
                        .put("currentTargetSafePath", runtimeSafePath(currentBatchTarget)))
                    return true
                }
                return false
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
'''
main = must_replace(main, nav_old, nav_new, 'provider-boundary-navigation')

# The real storage UI exposes the application report action as the generic label "리포트".
# v0.9.8 parsed 30 application-bound anchors but laneForLabel returned reference, causing the
# ledger to drop every target. Infer current-prediction only when that generic report label is
# inside the verified early-storage origin; no cross-card or nearest-card inference is introduced.
ledger_call_old = '''                val ledgerOrigin = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                val ledgerAdded = if (pageTypeNow == "jinhak-recommended-university") {
'''
ledger_call_new = '''                val ledgerOrigin = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                val originInferred = parsedMissionCandidates.count { candidate ->
                    JinhakMissionLaneSequencer.laneForLabel(candidate.label, candidate.kind) == "reference" &&
                        JinhakMissionLaneSequencer.laneForCandidateAtOrigin(candidate.label, candidate.kind, ledgerOrigin, pageTypeNow) != "reference" &&
                        candidate.applicationContext?.identityKey != null
                }
                if (originInferred > 0) jinhakOriginInferredMissionTargets += originInferred
                val ledgerAdded = if (pageTypeNow == "jinhak-recommended-university") {
'''
main = must_replace(main, ledger_call_old, ledger_call_new, 'origin-lane-inference-counter')
main = must_replace(main, 'jinhakMissionTargetLedger.capture(ledgerOrigin, parsedMissionCandidates)', 'jinhakMissionTargetLedger.capture(ledgerOrigin, parsedMissionCandidates, pageTypeNow)', 'ledger-capture-page-type')

# Seed loading must obey the same Susi-core allowlist as discovered and Cloud-frontier URLs.
seed_old = '''            val url = canonicalizeBatchUrl(rawUrl)
            if (url.isBlank() || !isProviderUrl(url) || batchVisited.contains(url) || batchQueued.contains(url)) continue
            val runId = localRunId
'''
seed_new = '''            val url = canonicalizeBatchUrl(rawUrl)
            if (url.isBlank() || !isProviderUrl(url) || batchVisited.contains(url) || batchQueued.contains(url)) continue
            if (provider == ProviderId.JINHAK && !isJinhakDefaultCoreQueueUrl(url)) continue
            val runId = localRunId
'''
main = must_replace(main, seed_old, seed_new, 'seed-core-filter')

# Surface the exact routing counters in live/final diagnostics and batch summary.
main = main.replace('.put("normalizedApplicationAmbiguousBindings", jinhakNormalizedAmbiguousBindings)\n', '.put("normalizedApplicationAmbiguousBindings", jinhakNormalizedAmbiguousBindings)\n                        .put("originInferredMissionTargets", jinhakOriginInferredMissionTargets)\n                        .put("externalNavigationsBlocked", jinhakExternalNavigationsBlocked)\n')
main = main.replace('.put("jinhakReferenceRepeatSkips", jinhakReferenceRepeatSkips)\n', '.put("jinhakReferenceRepeatSkips", jinhakReferenceRepeatSkips)\n                .put("jinhakOriginInferredMissionTargets", jinhakOriginInferredMissionTargets)\n                .put("jinhakExternalNavigationsBlocked", jinhakExternalNavigationsBlocked)\n')

# Mission lane sequencer: preserve the existing label classifier, but add a route/page-aware
# fallback for the exact generic report control observed on the saved-application cards.
seq_anchor = '''    fun laneRank(lane: String): Int {
'''
seq_new = '''    fun laneForCandidateAtOrigin(label: String, kind: String, originRoute: String, pageType: String): String {
        val direct = laneForLabel(label, kind)
        if (direct != "reference") return direct
        val normalizedLabel = label.replace(Regex("\\\\s+"), " ").trim()
        val savedOrigin = pageType == "jinhak-early-storage" || originRoute.contains("/four-year-university/library")
        return if (savedOrigin && Regex("^리포트(?:\\\\s*보기)?$").matches(normalizedLabel)) {
            "current-prediction"
        } else {
            "reference"
        }
    }

    fun laneRank(lane: String): Int {
'''
seq = must_replace(seq, seq_anchor, seq_new, 'origin-aware-lane')

# Ledger captures with the origin-aware classifier. The application identity must still already be
# bound by same-card/unique-container logic; this does not infer identity from neighbouring cards.
ledger_sig_old = '''    fun capture(originRoute: String, candidates: List<JinhakAgentNavigator.Candidate>): Int {
'''
ledger_sig_new = '''    fun capture(originRoute: String, candidates: List<JinhakAgentNavigator.Candidate>, pageType: String = ""): Int {
'''
ledger = must_replace(ledger, ledger_sig_old, ledger_sig_new, 'ledger-signature')
ledger = must_replace(ledger, 'val lane = JinhakMissionLaneSequencer.laneForLabel(candidate.label, candidate.kind)', 'val lane = JinhakMissionLaneSequencer.laneForCandidateAtOrigin(candidate.label, candidate.kind, originRoute, pageType)', 'ledger-origin-lane')

# Route topology: map the actual report routes observed on-device to real lanes, and stop treating
# every /early/ or /univ-major/ reference route as default Susi-core traversal.
topo_anchor = '''        return when {
            path.contains("/four-year-university/library") || Regex("(수시|정시)?\\\\s*저장소").containsMatchIn(text) ->
                JinhakMissionLane.SAVED_APPLICATIONS
            Regex("(actual|actual-admit|admitreport|resultreport|passcase|실제합격자)").containsMatchIn(text) ->
'''
topo_new = '''        return when {
            path.contains("/four-year-university/library") || Regex("(수시|정시)?\\\\s*저장소").containsMatchIn(text) ->
                JinhakMissionLane.SAVED_APPLICATIONS
            path.contains("/four-year-university/report/pass-predict") ->
                JinhakMissionLane.CURRENT_PREDICTION
            path.contains("/four-year-university/report/actual-admission") ->
                JinhakMissionLane.ACTUAL_ADMIT
            path.contains("/four-year-university/report/admission-result") ->
                JinhakMissionLane.UNIVERSITY_RESULT
            Regex("(actual|actual-admit|admitreport|resultreport|passcase|실제합격자)").containsMatchIn(text) ->
'''
topo = must_replace(topo, topo_anchor, topo_new, 'observed-report-route-map')

topo_core_old = '''        JinhakMissionLane.UNIVERSITY_RESULT,
        JinhakMissionLane.SCORE_ANALYSIS,
        JinhakMissionLane.REFERENCE -> true
        JinhakMissionLane.RECOMMENDATION,
'''
topo_core_new = '''        JinhakMissionLane.UNIVERSITY_RESULT,
        JinhakMissionLane.SCORE_ANALYSIS -> true
        JinhakMissionLane.REFERENCE,
        JinhakMissionLane.RECOMMENDATION,
'''
topo = must_replace(topo, topo_core_old, topo_core_new, 'reference-out-of-default-core')

main_p.write_text(main)
ledger_p.write_text(ledger)
seq_p.write_text(seq)
topo_p.write_text(topo)
gradle_p.write_text(gradle)
manifest_p.write_text(manifest)
print('v0.9.9 patch applied')
