from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, got {count}: {old[:180]!r}")
    p.write_text(text.replace(old, new, 1))


def replace_all_checked(path: str, old: str, new: str, expected: int) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected exactly {expected} matches, got {count}: {old[:180]!r}")
    p.write_text(text.replace(old, new))


# Version/label.
replace_once(
    "app/build.gradle.kts",
    '        versionCode = 118200\n        versionName = "0.18.2"',
    '        versionCode = 118300\n        versionName = "0.18.3"'
)
replace_once(
    "app/src/main/AndroidManifest.xml",
    'android:label="Admission Hub v0.18.2 Protected Session Bootstrap"',
    'android:label="Admission Hub v0.18.3 Storage Competition Watch"'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '        private const val VERSION = "0.18.2"\n        private const val BUILD_CODE = 118200',
    '        private const val VERSION = "0.18.3"\n        private const val BUILD_CODE = 118300'
)

# Policy import and diagnostics.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    'import com.admissionhub.collector.jinhak.JinhakProtectedSessionPolicy\n',
    'import com.admissionhub.collector.jinhak.JinhakProtectedSessionPolicy\nimport com.admissionhub.collector.jinhak.JinhakStorageCompetitionPolicy\n'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''    private var jinhakV0182RecoveryScopePreparations = 0
''',
    '''    private var jinhakV0182RecoveryScopePreparations = 0
    private var jinhakV0183StorageSnapshots = 0
    private var jinhakV0183CompetitionRecords = 0
    private var jinhakV0183CurrentCompetitionVerifiedRecords = 0
    private var jinhakV0183StorageRefreshes = 0
    private var jinhakV0183StorageWatchGeneration = 0
    private var jinhakV0183NextRefreshAtMs = 0L
'''
)

# Reset watch diagnostics for a new unified run.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        jinhakV0182RecoveryScopePreparations = 0
        jinhakNormalizedMissionSeedContexts.clear()''',
    '''        jinhakV0182RecoveryScopePreparations = 0
        jinhakV0183StorageSnapshots = 0
        jinhakV0183CompetitionRecords = 0
        jinhakV0183CurrentCompetitionVerifiedRecords = 0
        jinhakV0183StorageRefreshes = 0
        jinhakV0183StorageWatchGeneration += 1
        jinhakV0183NextRefreshAtMs = 0L
        jinhakNormalizedMissionSeedContexts.clear()'''
)

# v0.18.3 Jinhak adapter is storage-only. Authentication redirects are handled by the dedicated
# auth surface before normal collection; no reports, recommendation pages, or generic frontier
# targets are admitted to the collector batch.
replace_once(
    "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt",
    'import com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox\n',
    'import com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox\nimport com.admissionhub.collector.jinhak.JinhakStorageCompetitionPolicy\n'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt",
    '    override fun seedUrls(): List<String> = JinhakSiteTopology.missionSeeds()',
    '    override fun seedUrls(): List<String> = listOf(JinhakSiteTopology.protectedCoreProbeUrl())'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt",
    '''    override fun isBatchNavigable(url: String): Boolean {
        if (!accepts(url) || !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) return false
''',
    '''    override fun isBatchNavigable(url: String): Boolean {
        if (!accepts(url) || !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) return false
        if (JinhakStorageCompetitionPolicy.ENABLED && !JinhakStorageCompetitionPolicy.isStorageUrl(url)) return false
'''
)

# Same-card competition evidence. An explicitly qualified current/real-time value may be promoted
# to currentApplicationCompetition. An unlabeled visible value is preserved only as displayedCompetition.
replace_once(
    "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt",
    '''                val cardMetrics = predictionMetrics(evidence)
                mission?.capacity?.let { if (!cardMetrics.has("capacity")) cardMetrics.put("capacity", it) }
''',
    '''                val cardMetrics = predictionMetrics(evidence)
                val competitionReading = if (pageType == "jinhak-early-storage") JinhakStorageCompetitionPolicy.readCompetition(evidence) else null
                competitionReading?.displayedCompetition?.let { cardMetrics.put("displayedCompetition", it) }
                competitionReading?.currentApplicationCompetition?.let { cardMetrics.put("currentApplicationCompetition", it) }
                competitionReading?.let {
                    cardMetrics.put("currentCompetitionSemanticsVerified", it.currentSemanticsVerified)
                    it.evidenceLabel?.let { label -> cardMetrics.put("competitionEvidenceLabel", label) }
                }
                mission?.capacity?.let { if (!cardMetrics.has("capacity")) cardMetrics.put("capacity", it) }
'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt",
    '''                val hasPrimaryPrediction = listOf(
                    "stabilityBars", "predictionProbability", "predictionLabel", "myRank", "predictedCut"
                ).any { cardMetrics.has(it) && !cardMetrics.isNull(it) }
''',
    '''                val hasPrimaryPrediction = listOf(
                    "stabilityBars", "predictionProbability", "predictionLabel", "myRank", "predictedCut",
                    "displayedCompetition", "currentApplicationCompetition"
                ).any { cardMetrics.has(it) && !cardMetrics.isNull(it) }
'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt",
    '''                result.put(record)
                if (mission?.identityKey != null) {
                    result.put(JinhakApplicationMission.missionEvidence(mission, pageType, observedAt, safePath(snapshot.optString("url"))))
                }
''',
    '''                result.put(record)
                if (pageType == "jinhak-early-storage" && mission?.identityKey != null && competitionReading?.displayedCompetition != null) {
                    val competitionMetrics = JSONObject()
                        .put("displayedCompetition", competitionReading.displayedCompetition)
                        .put("currentApplicationCompetition", competitionReading.currentApplicationCompetition ?: JSONObject.NULL)
                        .put("currentCompetitionSemanticsVerified", competitionReading.currentSemanticsVerified)
                        .put("evidenceLabel", competitionReading.evidenceLabel ?: JSONObject.NULL)
                        .put("sourceClass", "jinhak-user-viewed-derived")
                    val competitionRecord = JSONObject()
                        .put("recordType", "jinhak-saved-application-competition-watch")
                        .put("providerPageType", pageType)
                        .put("dataScope", "current-application-competition-observation")
                        .put("year", local.year ?: TARGET_YEAR)
                        .put("university", university ?: JSONObject.NULL)
                        .put("department", department ?: JSONObject.NULL)
                        .put("admission", admission ?: JSONObject.NULL)
                        .put("applicationIdentityKey", mission.identityKey)
                        .put("metrics", competitionMetrics)
                        .put("observedAt", observedAt)
                        .put("cardIndex", i)
                        .put("confidence", if (competitionReading.currentSemanticsVerified) "high" else "raw")
                        .put("sourcePage", safePath(snapshot.optString("url")))
                        .put("rawEvidence", competitionReading.evidenceLabel ?: evidence.take(500))
                    competitionRecord.put("sourceRowFingerprint", fingerprint(competitionRecord, observedAt, preserveSnapshot = true))
                    result.put(competitionRecord)
                }
                if (mission?.identityKey != null) {
                    result.put(JinhakApplicationMission.missionEvidence(mission, pageType, observedAt, safePath(snapshot.optString("url"))))
                }
'''
)

# Disable report/agent mission generation from the saved repository. The repository card itself is
# the entire Jinhak collection scope for this release.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '                val rawMissionCandidates = JinhakAgentNavigator.candidates(snapshot)',
    '                val rawMissionCandidates = if (JinhakStorageCompetitionPolicy.ENABLED) emptyList() else JinhakAgentNavigator.candidates(snapshot)'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''            var jinhakExpansionStateKey: String? = null
            var jinhakExpandOutgoingLinks = true
            var jinhakAllowAgentAction = true
''',
    '''            var jinhakExpansionStateKey: String? = null
            val jinhakStorageOnlySnapshot = provider == ProviderId.JINHAK && JinhakStorageCompetitionPolicy.ENABLED &&
                snapshot.optString("providerPageType") == "jinhak-early-storage"
            var jinhakExpandOutgoingLinks = !jinhakStorageOnlySnapshot
            var jinhakAllowAgentAction = !jinhakStorageOnlySnapshot
'''
)

# Count each persisted storage observation and the competition rows that it produced.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) {
                jinhakConsecutiveStalls = 0
                val pageTypeNow = snapshot.optString("providerPageType")
''',
    '''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) {
                jinhakConsecutiveStalls = 0
                val pageTypeNow = snapshot.optString("providerPageType")
                if (JinhakStorageCompetitionPolicy.ENABLED && pageTypeNow == "jinhak-early-storage") {
                    jinhakV0183StorageSnapshots += 1
                    for (ri in 0 until pageRecords.length()) {
                        val observed = pageRecords.optJSONObject(ri) ?: continue
                        if (observed.optString("recordType") == "jinhak-saved-application-competition-watch") {
                            jinhakV0183CompetitionRecords += 1
                            if (observed.optJSONObject("metrics")?.optBoolean("currentCompetitionSemanticsVerified", false) == true) {
                                jinhakV0183CurrentCompetitionVerifiedRecords += 1
                            }
                        }
                    }
                }
'''
)

# Storage-only watch loop. It does not claim cloud frontier or leave the saved-application page.
# The 15-minute interval is deliberately conservative and is not presented as a Jinhak server TTL.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''    private fun loadNextBatchPage() {
        if (!batchRunning || batchPausedForLogin) return
        if (batchCloudPlansPending > 0) {
''',
    '''    private fun scheduleV0183StorageCompetitionRefresh() {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || !JinhakStorageCompetitionPolicy.ENABLED) return
        val generation = ++jinhakV0183StorageWatchGeneration
        jinhakV0183NextRefreshAtMs = System.currentTimeMillis() + JinhakStorageCompetitionPolicy.REFRESH_INTERVAL_MS
        status.text = "진학사 수시저장소만 추적 중 · 다음 경쟁률 확인 약 15분 후"
        persistLiveJinhakDiagnostics("v0183-storage-watch-scheduled", force = true)
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || generation != jinhakV0183StorageWatchGeneration) return@postDelayed
            jinhakV0183StorageRefreshes += 1
            val storage = JinhakSiteTopology.protectedCoreProbeUrl()
            currentBatchTarget = storage
            status.text = "진학사 수시저장소 경쟁률 새로 확인 중…"
            loadJinhakV0174High3Only(storage, "v0183-periodic-storage-refresh")
        }, JinhakStorageCompetitionPolicy.REFRESH_INTERVAL_MS)
    }

    private fun loadNextBatchPage() {
        if (!batchRunning || batchPausedForLogin) return
        if (provider == ProviderId.JINHAK && JinhakStorageCompetitionPolicy.ENABLED &&
            jinhakV0182ProtectedSessionVerified && batchSnapshots.length() > 0) {
            scheduleV0183StorageCompetitionRefresh()
            return
        }
        if (batchCloudPlansPending > 0) {
'''
)

# Both auth/live diagnostic payloads should expose the same storage-watch state.
replace_all_checked(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''                    .put("v0182RecoveryScopePreparations", jinhakV0182RecoveryScopePreparations)
''',
    '''                    .put("v0182RecoveryScopePreparations", jinhakV0182RecoveryScopePreparations)
                    .put("v0183StorageOnlyMode", JinhakStorageCompetitionPolicy.ENABLED)
                    .put("v0183StorageRefreshIntervalMs", JinhakStorageCompetitionPolicy.REFRESH_INTERVAL_MS)
                    .put("v0183StorageSnapshots", jinhakV0183StorageSnapshots)
                    .put("v0183CompetitionRecords", jinhakV0183CompetitionRecords)
                    .put("v0183CurrentCompetitionVerifiedRecords", jinhakV0183CurrentCompetitionVerifiedRecords)
                    .put("v0183StorageRefreshes", jinhakV0183StorageRefreshes)
                    .put("v0183NextRefreshAtMs", jinhakV0183NextRefreshAtMs)
''',
    expected=2
)

print("v0.18.3 storage-only competition watch patch applied")
