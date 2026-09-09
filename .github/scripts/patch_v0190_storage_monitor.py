#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(text: str, old: str, new: str, name: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{name}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)

# Version metadata.
gradle = ROOT / "app/build.gradle.kts"
g = gradle.read_text()
g = replace_once(g, 'versionCode = 118200', 'versionCode = 119000', 'versionCode')
g = replace_once(g, 'versionName = "0.18.2"', 'versionName = "0.19.0"', 'versionName')
gradle.write_text(g)

manifest = ROOT / "app/src/main/AndroidManifest.xml"
m = manifest.read_text()
m = replace_once(
    m,
    'android:label="Admission Hub v0.18.2 Protected Session Bootstrap"',
    'android:label="Admission Hub v0.19 Storage Competition Monitor"',
    'manifest label'
)
manifest.write_text(m)

# Strict current-competition semantics are injected into the existing same-card parser.
mission = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakApplicationMission.kt"
s = mission.read_text()
s = replace_once(s, 'const val SEMANTICS_VERSION = 3', 'const val SEMANTICS_VERSION = 4', 'metric semantics version')
anchor = '''        number(text, Regex("""(?:실시간\\s*수시\\s*)?모의지원\\s*경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)""")).let { match ->
'''
# Source uses safe-call before let; patch on the following stable block instead.
old = '''        number(text, Regex("""(?:실시간\\s*수시\\s*)?모의지원\\s*경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)"""))?.let {
            out.put("mockCompetition", it)
        }
        number(text, Regex("""모의지원자\\s*(?:수|인원)\\s*[:：]?\\s*([0-9,]+)"""))?.toInt()?.let {
'''
new = '''        number(text, Regex("""(?:실시간\\s*수시\\s*)?모의지원\\s*경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)"""))?.let {
            out.put("mockCompetition", it)
        }
        val liveCompetition = JinhakStorageCompetitionMonitor.extract(text)
        liveCompetition.currentApplicationCompetition?.let {
            out.put("currentApplicationCompetition", it)
            out.put("currentApplicationCompetitionSource", liveCompetition.currentSource ?: "explicit-current")
            out.put("currentApplicationCompetitionDerived", liveCompetition.derivedFromExplicitCounts)
        }
        liveCompetition.ambiguousGenericCompetition?.let {
            out.put("genericCompetitionUnresolved", it)
            out.put("currentApplicationCompetitionAmbiguous", true)
        }
        out.put("competitionSourceClass", "jinhak-user-viewed-storage")
        out.put("competitionOfficial", false)
        number(text, Regex("""모의지원자\\s*(?:수|인원)\\s*[:：]?\\s*([0-9,]+)"""))?.toInt()?.let {
'''
s = replace_once(s, old, new, 'competition semantic insertion')
mission.write_text(s)

# Ensure the exact library is classified as storage and competition-only cards remain normalized.
adapter = ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt"
a = adapter.read_text()
a = replace_once(
    a,
    'import com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox\n',
    'import com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox\nimport com.admissionhub.collector.jinhak.JinhakStorageOnlyPolicy\n',
    'adapter storage policy import'
)
a = replace_once(
    a,
    'val earlyStorage = Regex("(storage|save)").containsMatchIn(url) || Regex("(수시|정시)?\\\\s*저장소|저장대학").containsMatchIn(headingText)',
    'val earlyStorage = JinhakStorageOnlyPolicy.isLibrary(rawUrl) || Regex("(storage|save)").containsMatchIn(url) || Regex("(수시|정시)?\\\\s*저장소|저장대학").containsMatchIn(headingText)',
    'exact storage classification'
)
a = replace_once(
    a,
    'listOf("mockCompetition", "predictionProbability", "myRank", "predictedCut", "mockApplicants", "applicants")',
    'listOf("currentApplicationCompetition", "genericCompetitionUnresolved", "mockCompetition", "predictionProbability", "myRank", "predictedCut", "mockApplicants", "applicants")',
    'rich storage metric list'
)
a = replace_once(
    a,
    '''                val hasPrimaryPrediction = listOf(
                    "stabilityBars", "predictionProbability", "predictionLabel", "myRank", "predictedCut"
                ).any { cardMetrics.has(it) && !cardMetrics.isNull(it) }
''',
    '''                val hasPrimaryPrediction = listOf(
                    "currentApplicationCompetition", "genericCompetitionUnresolved",
                    "stabilityBars", "predictionProbability", "predictionLabel", "myRank", "predictedCut"
                ).any { cardMetrics.has(it) && !cardMetrics.isNull(it) }
''',
    'competition-only card preservation'
)
adapter.write_text(a)

main = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
t = main.read_text()
t = replace_once(
    t,
    'import com.admissionhub.collector.jinhak.JinhakProtectedSessionPolicy\n',
    'import com.admissionhub.collector.jinhak.JinhakProtectedSessionPolicy\nimport com.admissionhub.collector.jinhak.JinhakStorageOnlyPolicy\n',
    'MainActivity storage policy import'
)

# Runtime monitor state. No credential/cookie/form value is persisted or exported.
t = replace_once(
    t,
    '    private var jinhakNoProgressFences = 0\n',
    '''    private var jinhakNoProgressFences = 0
    private var jinhakStorageMonitorActive = false
    private var jinhakStorageMonitorGeneration = 0
    private var jinhakStorageRefreshes = 0
    private var jinhakStorageCompetitionSnapshots = 0
    private var jinhakStorageCompetitionChanges = 0
    private var jinhakStorageLoginPauses = 0
    private var jinhakStorageNaturalResumes = 0
    private var jinhakStorageNonLibraryNavigationsBlocked = 0
    private var jinhakStorageLoginEpisodeOpen = false
    private var jinhakStorageLastRefreshAtMs = 0L
    private var jinhakStorageNextRefreshAtMs = 0L
    private val jinhakStorageTrackedIdentityKeys = linkedSetOf<String>()
    private val jinhakStorageLatestCompetition = linkedMapOf<String, Double>()
''',
    'storage monitor state'
)

# Primary WebView login surfaces are site-owned. Do not divert them to the dedicated auth WebView.
old = '''                        if (JinhakDedicatedAuthPolicy.isLoginSurface(target)) {
                            handler.post {
                                jinhakV0180CollectorLoginRouteLoads += 1
                                startV0180DedicatedJinhakAuth("collector-network-login")
                            }
                            return jinhakV0174BlockedResponse("dedicated-auth-route")
                        }
                        val decision = JinhakStrictHigh3Sandbox.decision(target)
'''
new = '''                        if (JinhakStorageOnlyPolicy.isSiteLogin(target)) {
                            handler.post { pauseJinhakStorageForSiteLogin("network-login", target) }
                            return super.shouldInterceptRequest(view, request)
                        }
                        if (!jinhakStorageLoginEpisodeOpen && !JinhakStorageOnlyPolicy.isLibrary(target) && target != "about:blank") {
                            handler.post {
                                jinhakStorageNonLibraryNavigationsBlocked += 1
                                persistJinhakAuthDiagnostics("v0190-storage-non-library-network-block")
                            }
                            return jinhakV0174BlockedResponse("v0190-storage-only")
                        }
                        val decision = JinhakStrictHigh3Sandbox.decision(target)
'''
t = replace_once(t, old, new, 'network login natural handoff')

old = '''                if (JinhakDedicatedAuthPolicy.isLoginSurface(target)) {
                    jinhakV0180CollectorLoginRouteLoads += 1
                    startV0180DedicatedJinhakAuth("collector-navigation-login")
                    return true
                }
                val decision = JinhakStrictHigh3Sandbox.decision(target)
'''
new = '''                if (JinhakStorageOnlyPolicy.isSiteLogin(target)) {
                    pauseJinhakStorageForSiteLogin("navigation-login", target)
                    return false
                }
                if (!jinhakStorageLoginEpisodeOpen && !JinhakStorageOnlyPolicy.isLibrary(target) && target != "about:blank") {
                    jinhakStorageNonLibraryNavigationsBlocked += 1
                    persistJinhakAuthDiagnostics("v0190-storage-non-library-navigation-block")
                    return true
                }
                val decision = JinhakStrictHigh3Sandbox.decision(target)
'''
t = replace_once(t, old, new, 'navigation login natural handoff')

old = '''                    if (JinhakDedicatedAuthPolicy.isLoginSurface(url) == true) {
                        jinhakV0180CollectorLoginRouteLoads += 1
                        runCatching { view.stopLoading() }
                        startV0180DedicatedJinhakAuth("collector-page-started-login")
                        return
                    }
'''
new = '''                    if (JinhakStorageOnlyPolicy.isSiteLogin(url)) {
                        pauseJinhakStorageForSiteLogin("page-started-login", url)
                        return
                    }
'''
t = replace_once(t, old, new, 'page-started login natural handoff')

old = '''                if (provider == ProviderId.JINHAK) {
                    if (JinhakProtectedSessionPolicy.isProtectedProofUrl(url)) {
                        markV0182ProtectedSessionVerified(url, "collector-page-finished-protected")
                    }
                    if (JinhakDedicatedAuthPolicy.isLoginSurface(url)) {
                        jinhakV0180CollectorLoginRouteLoads += 1
                        startV0180DedicatedJinhakAuth("collector-page-finished-login")
                        return
                    }
                    val visible = webView.url.orEmpty()
'''
new = '''                if (provider == ProviderId.JINHAK) {
                    if (JinhakStorageOnlyPolicy.isSiteLogin(url)) {
                        pauseJinhakStorageForSiteLogin("page-finished-login", url)
                        return
                    }
                    if (JinhakStorageOnlyPolicy.isLibrary(url)) {
                        val wasLoginEpisode = jinhakStorageLoginEpisodeOpen || batchPausedForLogin
                        markV0182ProtectedSessionVerified(url, "v0190-library-page-finished")
                        jinhakUserSessionConfirmed = true
                        jinhakAuthVerifiedForBatch = true
                        jinhakStorageLoginEpisodeOpen = false
                        batchPausedForLogin = false
                        jinhakTransitionAuthGateActive = false
                        jinhakCoreBootstrapState = "v0190-storage-protected-session-verified"
                        jinhakLastAuthEvidence = "protected-early-storage-page-finished"
                        if (wasLoginEpisode) jinhakStorageNaturalResumes += 1
                        if (!batchRunning && jinhakStorageMonitorActive) {
                            handler.postDelayed({
                                if (provider == ProviderId.JINHAK && !batchRunning && jinhakStorageMonitorActive && JinhakStorageOnlyPolicy.isLibrary(webView.url.orEmpty())) startBatch()
                            }, 120L)
                            return
                        }
                    }
                    val visible = webView.url.orEmpty()
'''
t = replace_once(t, old, new, 'page-finished protected storage handoff')

# Start Jinhak from exactly one protected route. A server login redirect stays visible in the same WebView.
old_start = '''        if (provider == ProviderId.JINHAK) {
            activateV0181PinnedSixFocus("start-batch")
            if (!jinhakUserSessionConfirmed) {
                enterJinhakUserSessionGate("start-batch")
                return
            }
            if (!jinhakV0182ProtectedSessionVerified) {
                jinhakAuthVerifiedForBatch = false
                requestV0182ProtectedSessionProbe("start-batch")
                return
            }
            val visibleHigh3 = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)
            if (!jinhakUserSessionConfirmed || visibleHigh3 == null) {
                jinhakV0174PersistedTargetBlocks += 1
                enterJinhakUserSessionGate("v0174-start-batch-requires-visible-high3")
                return
            }
            currentBatchTarget = canonicalizeBatchUrl(visibleHigh3)
            jinhakAuthVerifiedForBatch = false
            jinhakCoreBootstrapState = "v0182-user-approved-high3-awaiting-protected-proof"
            jinhakLastAuthEvidence = "user-approved-public-high3-not-auth-proof"
            jinhakLastCoreVerifiedAtMs = 0L
        }
'''
new_start = '''        if (provider == ProviderId.JINHAK) {
            activateV0181PinnedSixFocus("v0190-storage-start-batch")
            jinhakStorageMonitorActive = true
            val current = webView.url.orEmpty()
            if (JinhakStorageOnlyPolicy.isSiteLogin(current)) {
                pauseJinhakStorageForSiteLogin("start-batch-login-visible", current)
                return
            }
            if (!JinhakStorageOnlyPolicy.isLibrary(current)) {
                jinhakAuthVerifiedForBatch = false
                jinhakV0182ProtectedSessionVerified = false
                jinhakCoreBootstrapState = "v0190-loading-protected-storage"
                jinhakLastAuthEvidence = "awaiting-protected-storage-or-site-login"
                currentBatchTarget = canonicalizeBatchUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
                status.text = "진학사 수시 저장소만 엽니다. 로그인이 필요하면 같은 화면의 진학사 로그인으로 자연 전환됩니다."
                webView.loadUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
                return
            }
            markV0182ProtectedSessionVerified(current, "v0190-start-batch-library-visible")
            jinhakUserSessionConfirmed = true
            jinhakAuthVerifiedForBatch = true
            jinhakV0182ProtectedSessionVerified = true
            jinhakCoreBootstrapState = "v0190-storage-protected-session-verified"
            jinhakLastAuthEvidence = "protected-early-storage-visible"
            currentBatchTarget = canonicalizeBatchUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
        }
'''
t = replace_once(t, old_start, new_start, 'storage-only startBatch')

old_begin = '''        if (provider == ProviderId.JINHAK) {
            val visible = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)
            val target = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget)
            if (!jinhakUserSessionConfirmed || visible == null) {
                batchPausedForLogin = true
                hideBatchCover()
                enterJinhakUserSessionGate("v0174-begin-navigation-visible-high3-required")
                return
            }
            currentBatchTarget = canonicalizeBatchUrl(visible)
            if (target == null || canonicalizeBatchUrl(target) == canonicalizeBatchUrl(visible)) {
                scheduleBatchSnapshot()
            } else {
                loadJinhakV0174High3Only(target, "begin-batch-navigation")
            }
            return
        }
'''
new_begin = '''        if (provider == ProviderId.JINHAK) {
            jinhakStorageMonitorActive = true
            val visible = webView.url.orEmpty()
            currentBatchTarget = canonicalizeBatchUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
            when {
                JinhakStorageOnlyPolicy.isSiteLogin(visible) -> pauseJinhakStorageForSiteLogin("begin-navigation-login", visible)
                JinhakStorageOnlyPolicy.isLibrary(visible) -> scheduleBatchSnapshot()
                else -> webView.loadUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
            }
            return
        }
'''
t = replace_once(t, old_begin, new_begin, 'storage-only begin navigation')

# Transition from Adiga directly to the one protected storage route; no public-high3 confirmation gate.
old_transition = '''        enterJinhakUserSessionGate("unified-transition")
        val current = webView.url.orEmpty()
        if (!isProviderUrl(current)) {
            loadJinhakV0174High3Only(ProviderId.JINHAK.homeUrl, "legacy-jinhak-home-failsafe")
        }
'''
new_transition = '''        jinhakStorageMonitorActive = true
        jinhakStorageLoginEpisodeOpen = false
        jinhakCoreBootstrapState = "v0190-loading-protected-storage"
        jinhakLastAuthEvidence = "awaiting-protected-storage-or-site-login"
        currentBatchTarget = canonicalizeBatchUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
        status.text = "통합 수집 2/2 · 진학사 수시 저장소 단일 경로로 전환합니다. 로그인은 진학사 사이트가 같은 WebView에서 처리합니다."
        webView.loadUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
'''
t = replace_once(t, old_transition, new_transition, 'unified transition direct storage')

# Disable all collector-owned Jinhak credential submission entry points. Existing dedicated-auth
# implementation remains unreachable for backward source compatibility only.
t = replace_once(
    t,
    '''    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {
        if (provider != ProviderId.JINHAK) return
        startV0180DedicatedJinhakAuth("legacy-entry:$reason")
    }
''',
    '''    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {
        if (provider != ProviderId.JINHAK) return
        persistJinhakAuthDiagnostics("v0190-collector-owned-login-disabled:$reason")
    }
''',
    'disable legacy Jinhak credential entry'
)
t = replace_once(
    t,
    '''        if (which == ProviderId.JINHAK) {
            provider = ProviderId.JINHAK
            startV0180DedicatedJinhakAuth("saved-credential:$reason")
            return
        }
''',
    '''        if (which == ProviderId.JINHAK) {
            provider = ProviderId.JINHAK
            persistJinhakAuthDiagnostics("v0190-saved-credential-submit-disabled:$reason")
            return
        }
''',
    'disable Jinhak saved credential submit'
)

# Dedicated auth must not be launched by route-block compatibility handling either.
t = replace_once(
    t,
    '''        if (JinhakDedicatedAuthPolicy.isLoginSurface(target)) {
            jinhakV0180CollectorLoginRouteLoads += 1
            handler.post { startV0180DedicatedJinhakAuth("collector-route:$source") }
        }
''',
    '''        if (JinhakStorageOnlyPolicy.isSiteLogin(target)) {
            handler.post { pauseJinhakStorageForSiteLogin("route-block:$source", target) }
        }
''',
    'disable route-block dedicated auth'
)

# Add monitor helpers before batch snapshot collection.
helpers_anchor = '    private fun collectSnapshotForBatch() {\n'
helpers = '''    private fun pauseJinhakStorageForSiteLogin(source: String, url: String) {
        if (provider != ProviderId.JINHAK) return
        jinhakStorageMonitorActive = true
        if (!jinhakStorageLoginEpisodeOpen) {
            jinhakStorageLoginEpisodeOpen = true
            jinhakStorageLoginPauses += 1
        }
        batchPausedForLogin = batchRunning
        jinhakAuthVerifiedForBatch = false
        jinhakV0182ProtectedSessionVerified = false
        jinhakCoreBootstrapState = "v0190-site-login-visible"
        jinhakLastAuthEvidence = "site-owned-login-redirect-visible"
        disarmBatchNavigationWatchdog()
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
        sessionState.text = "○ 진학사 수시 저장소 로그인 대기"
        status.text = "진학사 사이트가 로그인 화면으로 전환했습니다. 이 화면에서 로그인하면 수시 저장소로 자연 복귀할 때 자동 재개합니다."
        recordRuntimeEvent("jinhak-v0190-storage-login-pause", JSONObject()
            .put("source", source.take(80))
            .put("safePath", runtimeSafePath(url))
            .put("dedicatedAuthStarted", false)
            .put("credentialSubmit", false))
        persistJinhakAuthDiagnostics("v0190-storage-login-pause:$source")
    }

    private fun appendJinhakStorageCompetitionSnapshots(records: JSONArray): Int {
        val additions = JSONArray()
        var added = 0
        for (i in 0 until records.length()) {
            val source = records.optJSONObject(i) ?: continue
            if (source.optString("recordType") != "jinhak-saved-application-prediction") continue
            val metrics = source.optJSONObject("metrics") ?: continue
            val hasCurrent = metrics.has("currentApplicationCompetition") && !metrics.isNull("currentApplicationCompetition")
            val hasUnresolved = metrics.has("genericCompetitionUnresolved") && !metrics.isNull("genericCompetitionUnresolved")
            if (!hasCurrent && !hasUnresolved) continue
            val identity = source.optString("applicationIdentityKey").takeIf { it.isNotBlank() && it != "null" }
            if (identity != null) jinhakStorageTrackedIdentityKeys.add(identity)
            val observedAt = source.optString("observedAt", Instant.now().toString())
            val current = if (hasCurrent) metrics.optDouble("currentApplicationCompetition") else Double.NaN
            val unresolved = if (hasUnresolved) metrics.optDouble("genericCompetitionUnresolved") else Double.NaN
            if (identity != null && hasCurrent && !current.isNaN()) {
                val prior = jinhakStorageLatestCompetition.put(identity, current)
                if (prior != null && java.lang.Double.compare(prior, current) != 0) {
                    jinhakStorageCompetitionChanges += 1
                }
            }
            val record = JSONObject()
                .put("recordType", "jinhak-competition-snapshot")
                .put("providerPageType", "jinhak-early-storage")
                .put("dataScope", "current-application-competition-monitor")
                .put("year", source.opt("year") ?: JSONObject.NULL)
                .put("university", source.opt("university") ?: JSONObject.NULL)
                .put("department", source.opt("department") ?: JSONObject.NULL)
                .put("admission", source.opt("admission") ?: JSONObject.NULL)
                .put("applicationIdentityKey", identity ?: JSONObject.NULL)
                .put("observedAt", observedAt)
                .put("sourceClass", "jinhak-user-viewed-storage")
                .put("official", false)
                .put("probabilityInferred", false)
                .put("metrics", JSONObject()
                    .put("currentApplicationCompetition", if (hasCurrent) current else JSONObject.NULL)
                    .put("currentApplicationCompetitionSource", metrics.opt("currentApplicationCompetitionSource") ?: JSONObject.NULL)
                    .put("currentApplicationCompetitionDerived", metrics.optBoolean("currentApplicationCompetitionDerived", false))
                    .put("genericCompetitionUnresolved", if (hasUnresolved) unresolved else JSONObject.NULL)
                    .put("currentApplicationCompetitionAmbiguous", hasUnresolved && !hasCurrent))
            record.put("sourceRowFingerprint", RecordUtils.sha256(listOf(
                identity ?: "unbound", observedAt, if (hasCurrent) current.toString() else "null",
                if (hasUnresolved) unresolved.toString() else "null"
            ).joinToString("|")))
            additions.put(record)
            added += 1
        }
        for (i in 0 until additions.length()) records.put(additions.optJSONObject(i))
        jinhakStorageCompetitionSnapshots += added
        if (added > 0) {
            recordRuntimeEvent("jinhak-v0190-competition-snapshot", JSONObject()
                .put("added", added)
                .put("trackedApplications", jinhakStorageTrackedIdentityKeys.size)
                .put("changes", jinhakStorageCompetitionChanges))
        }
        return added
    }

    private fun scheduleJinhakStorageRefresh(source: String) {
        if (provider != ProviderId.JINHAK || !batchRunning || !jinhakStorageMonitorActive) return
        disarmBatchNavigationWatchdog()
        val generation = ++jinhakStorageMonitorGeneration
        jinhakStorageLastRefreshAtMs = System.currentTimeMillis()
        jinhakStorageNextRefreshAtMs = jinhakStorageLastRefreshAtMs + JinhakStorageOnlyPolicy.MONITOR_INTERVAL_MS
        sessionState.text = "● 진학사 수시 저장소 경쟁률 추적 중 · 15분 주기"
        status.text = "수시 저장소 스냅샷 저장 완료 · 다음 갱신은 약 15분 후입니다."
        persistJinhakAuthDiagnostics("v0190-storage-refresh-scheduled:$source")
        handler.postDelayed({
            if (generation != jinhakStorageMonitorGeneration || !batchRunning || !jinhakStorageMonitorActive || provider != ProviderId.JINHAK) return@postDelayed
            val current = webView.url.orEmpty()
            if (JinhakStorageOnlyPolicy.isSiteLogin(current) || jinhakStorageLoginEpisodeOpen) {
                pauseJinhakStorageForSiteLogin("periodic-refresh-login-visible", current)
                return@postDelayed
            }
            jinhakStorageRefreshes += 1
            jinhakStorageLastRefreshAtMs = System.currentTimeMillis()
            currentBatchTarget = canonicalizeBatchUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
            recordRuntimeEvent("jinhak-v0190-storage-periodic-refresh", JSONObject()
                .put("refresh", jinhakStorageRefreshes)
                .put("intervalMs", JinhakStorageOnlyPolicy.MONITOR_INTERVAL_MS))
            webView.loadUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)
        }, JinhakStorageOnlyPolicy.MONITOR_INTERVAL_MS)
    }

'''
t = replace_once(t, helpers_anchor, helpers + helpers_anchor, 'storage monitor helpers')

# Create standalone competition history records immediately after storage normalization.
t = replace_once(
    t,
    '''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) {
''',
    '''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK && JinhakStorageOnlyPolicy.isLibrary(snapshot.optString("url"))) {
                appendJinhakStorageCompetitionSnapshots(pageRecords)
            }
            if (provider == ProviderId.JINHAK) {
''',
    'append competition snapshots'
)

# Never create report-click ledger targets or autonomous actions in storage-only mode.
t = replace_once(
    t,
    '''                val ledgerAdded = if (pageTypeNow == "jinhak-recommended-university") {
''',
    '''                val ledgerAdded = if (JinhakStorageOnlyPolicy.isLibrary(snapshot.optString("url"))) {
                    0
                } else if (pageTypeNow == "jinhak-recommended-university") {
''',
    'suppress storage report ledger'
)
t = replace_once(
    t,
    '            if (provider == ProviderId.JINHAK && activeAction == null && jinhakAllowAgentAction && maybeExecuteJinhakAgentAction(snapshot, jinhakExpansionStateKey)) {\n',
    '            if (provider == ProviderId.JINHAK && activeAction == null && !JinhakStorageOnlyPolicy.isLibrary(snapshot.optString("url")) && jinhakAllowAgentAction && maybeExecuteJinhakAgentAction(snapshot, jinhakExpansionStateKey)) {\n',
    'suppress storage agent actions'
)

# Replace normal crawl completion with the periodic storage refresh state.
end_anchor = '''            if (batchPageCount >= MAX_BATCH_PAGES) {
                finishBatch("page-limit")
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 350)
            }
'''
end_new = '''            if (provider == ProviderId.JINHAK && JinhakStorageOnlyPolicy.isLibrary(snapshot.optString("url"))) {
                scheduleJinhakStorageRefresh("snapshot-complete")
                return@collectSnapshot
            }
            if (batchPageCount >= MAX_BATCH_PAGES) {
                finishBatch("page-limit")
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 350)
            }
'''
t = replace_once(t, end_anchor, end_new, 'periodic storage refresh scheduling')

# Export the new architecture and tracker counters in auth diagnostics.
diag_anchor = '                    .put("jinhakAuthModel", "dedicated-auth-webview-autologin-v0180")\n'
diag_new = '''                    .put("jinhakAuthModel", "single-webview-site-owned-storage-only-v0190")
                    .put("jinhakCollectionMode", JinhakStorageOnlyPolicy.MODE)
                    .put("storageMonitorIntervalMs", JinhakStorageOnlyPolicy.MONITOR_INTERVAL_MS)
                    .put("storageMonitorActive", jinhakStorageMonitorActive)
                    .put("storageRefreshes", jinhakStorageRefreshes)
                    .put("storageCompetitionSnapshots", jinhakStorageCompetitionSnapshots)
                    .put("storageCompetitionChanges", jinhakStorageCompetitionChanges)
                    .put("storageTrackedApplications", jinhakStorageTrackedIdentityKeys.size)
                    .put("storageLoginPauses", jinhakStorageLoginPauses)
                    .put("storageNaturalResumes", jinhakStorageNaturalResumes)
                    .put("storageNonLibraryNavigationsBlocked", jinhakStorageNonLibraryNavigationsBlocked)
                    .put("storageLastRefreshAtMs", jinhakStorageLastRefreshAtMs)
                    .put("storageNextRefreshAtMs", jinhakStorageNextRefreshAtMs)
                    .put("collectorOwnedJinhakLogin", false)
                    .put("dedicatedAuthUsedByV0190", false)
'''
t = replace_once(t, diag_anchor, diag_new, 'v0190 diagnostics')

main.write_text(t)
print('v0.19.0 storage-only competition monitor patch applied')
