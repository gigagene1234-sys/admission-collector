from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, got {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


def replace_all_checked(path: str, old: str, new: str, minimum: int = 1) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f"{path}: expected at least {minimum} matches, got {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new))


replace_once(
    "app/build.gradle.kts",
    '        versionCode = 118000\n        versionName = "0.18.0"',
    '        versionCode = 118100\n        versionName = "0.18.1"'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '        private const val VERSION = "0.18.0"\n        private const val BUILD_CODE = 118000',
    '        private const val VERSION = "0.18.1"\n        private const val BUILD_CODE = 118100'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    'import com.admissionhub.collector.jinhak.JinhakDedicatedAuthPolicy\n',
    'import com.admissionhub.collector.jinhak.JinhakDedicatedAuthPolicy\nimport com.admissionhub.collector.jinhak.JinhakFocusedSixPolicy\n'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '    private var jinhakV0180CollectorLoginRouteLoads = 0\n    private var jinhakV0180LowerGradeBlocks = 0\n    private var jinhakV0180AuthLastReason = ""\n    private var jinhakV0180AuthLastSafePath = ""\n',
    '    private var jinhakV0180CollectorLoginRouteLoads = 0\n    private var jinhakV0180LowerGradeBlocks = 0\n    private var jinhakV0180AuthLastReason = ""\n    private var jinhakV0180AuthLastSafePath = ""\n    private var jinhakV0181FocusedSixMode = false\n    private val jinhakV0181PinnedIdentityKeys = linkedSetOf<String>()\n    private var jinhakV0181PinnedIdentitySeeds = 0\n    private var jinhakV0181GenericRoutesSuppressed = 0\n    private var jinhakV0181GenericActionsSuppressed = 0\n    private var jinhakV0181ProtectedCoreStarts = 0\n'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '        private const val V0180_AUTH_MAX_FILL_ATTEMPTS = 3',
    '        private const val V0180_AUTH_MAX_FILL_ATTEMPTS = 12'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '                    val delay = when (next) { 1 -> 350L; else -> 900L }',
    '                    val delay = when { next <= 2 -> 350L; next <= 5 -> 700L; else -> 1_200L }'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        val target = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget)
            ?: JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(successUrl)
            ?: JinhakStrictHigh3Sandbox.strictEntryUrl()
        currentBatchTarget = target
        loadJinhakV0174High3Only(target, "v0180-auth-success-handoff")''',
    '''        val target = JinhakSiteTopology.protectedCoreProbeUrl()
        jinhakV0181ProtectedCoreStarts += 1
        currentBatchTarget = target
        loadJinhakV0174High3Only(target, "v0181-auth-success-protected-core")'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '    private fun startBatch() {\n',
    '''    private fun activateV0181PinnedSixFocus(trigger: String): Boolean {
        if (provider != ProviderId.JINHAK) return false
        val slots = localStore.loadHubApplicationSlots()
        val rows = mutableListOf<Pair<Boolean, String>>()
        for (i in 0 until slots.length()) {
            val row = slots.optJSONObject(i) ?: continue
            rows += row.optBoolean("occupied", false) to row.optString("applicationIdentityKey")
        }
        val keys = JinhakFocusedSixPolicy.pinnedIdentityKeys(rows)
        jinhakV0181PinnedIdentityKeys.clear()
        jinhakV0181PinnedIdentityKeys.addAll(keys)
        jinhakV0181FocusedSixMode = keys.size == JinhakFocusedSixPolicy.REQUIRED_PINNED_APPLICATIONS
        if (jinhakV0181FocusedSixMode) {
            jinhakV0181PinnedIdentitySeeds = keys.size
            keys.forEach { identity -> jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() } }
            recordRuntimeEvent("jinhak-v0181-focused-six-activated", JSONObject()
                .put("trigger", trigger.take(80))
                .put("pinnedIdentityCount", keys.size)
                .put("genericNavigationAllowed", false))
        }
        return jinhakV0181FocusedSixMode
    }

    private fun startBatch() {
'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''    private fun startBatch() {
        if (provider == ProviderId.JINHAK && !jinhakUserSessionConfirmed) {
            enterJinhakUserSessionGate("start-batch")
            return
        }
        if (provider == ProviderId.JINHAK) {
''',
    '''    private fun startBatch() {
        if (provider == ProviderId.JINHAK && !jinhakUserSessionConfirmed) {
            enterJinhakUserSessionGate("start-batch")
            return
        }
        if (provider == ProviderId.JINHAK) {
            activateV0181PinnedSixFocus("start-batch")
'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''    private fun currentExpectedJinhakMissionIdentities(): Set<String> = when {
        selectedSixRecoveryMode && selectedSixRecoveryIdentityKeys.isNotEmpty() -> selectedSixRecoveryIdentityKeys.toSet()
        jinhakNormalizedIdentitySeedKeys.isNotEmpty() -> jinhakNormalizedIdentitySeedKeys.toSet()
        jinhakMissionCoverage.isNotEmpty() -> jinhakMissionCoverage.keys.toSet()
        else -> emptySet()
    }''',
    '''    private fun currentExpectedJinhakMissionIdentities(): Set<String> = when {
        jinhakV0181FocusedSixMode && jinhakV0181PinnedIdentityKeys.isNotEmpty() -> jinhakV0181PinnedIdentityKeys.toSet()
        selectedSixRecoveryMode && selectedSixRecoveryIdentityKeys.isNotEmpty() -> selectedSixRecoveryIdentityKeys.toSet()
        jinhakNormalizedIdentitySeedKeys.isNotEmpty() -> jinhakNormalizedIdentitySeedKeys.toSet()
        jinhakMissionCoverage.isNotEmpty() -> jinhakMissionCoverage.keys.toSet()
        else -> emptySet()
    }'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        val lane = JinhakSiteTopology.lane(url)
        val allowed = JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url) ||
            (JinhakGradeRouteFence.isHigh3(url) && lane == com.admissionhub.collector.jinhak.JinhakMissionLane.UNKNOWN)
        if (!allowed) recordJinhakCoreScopeBlock(url)
        return allowed''',
    '''        val allowed = if (jinhakV0181FocusedSixMode) {
            JinhakFocusedSixPolicy.isFocusedCoreUrl(url)
        } else {
            JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)
        }
        if (!allowed) {
            jinhakV0181GenericRoutesSuppressed += 1
            recordJinhakCoreScopeBlock(url)
        }
        return allowed'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) return
        if (provider == ProviderId.JINHAK && batchQueued.size + batchVisited.size >= MAX_JINHAK_AUTONAV_PAGES) return''',
    '''        if (provider == ProviderId.JINHAK && jinhakV0181FocusedSixMode && !JinhakFocusedSixPolicy.isFocusedCoreUrl(url)) {
            jinhakV0181GenericRoutesSuppressed += 1
            return
        }
        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) return
        if (provider == ProviderId.JINHAK && batchQueued.size + batchVisited.size >= MAX_JINHAK_AUTONAV_PAGES) return'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''                    val genericPool = candidates.filter { it.applicationContext?.identityKey == null }
                    val generic = JinhakMissionLaneSequencer.choose(genericPool, null, emptySet(), false)
                    JinhakMissionLaneSequencer.Selection(generic.candidate, true, generic.requestedLane)''',
    '''                    val genericPool = candidates.filter { it.applicationContext?.identityKey == null }
                    if (jinhakV0181FocusedSixMode) {
                        jinhakV0181GenericActionsSuppressed += genericPool.size
                        JinhakMissionLaneSequencer.Selection(null, true, "reference")
                    } else {
                        val generic = JinhakMissionLaneSequencer.choose(genericPool, null, emptySet(), false)
                        JinhakMissionLaneSequencer.Selection(generic.candidate, true, generic.requestedLane)
                    }'''
)
replace_all_checked(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''                    .put("v0180LowerGradeBlocks", jinhakV0180LowerGradeBlocks)
                    .put("v0180RecursiveAuthPolling", false)''',
    '''                    .put("v0180LowerGradeBlocks", jinhakV0180LowerGradeBlocks)
                    .put("v0181FocusedSixMode", jinhakV0181FocusedSixMode)
                    .put("v0181PinnedIdentitySeeds", jinhakV0181PinnedIdentitySeeds)
                    .put("v0181GenericRoutesSuppressed", jinhakV0181GenericRoutesSuppressed)
                    .put("v0181GenericActionsSuppressed", jinhakV0181GenericActionsSuppressed)
                    .put("v0181ProtectedCoreStarts", jinhakV0181ProtectedCoreStarts)
                    .put("v0180RecursiveAuthPolling", false)''',
    minimum=1
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt",
    '''    fun missionSeeds(): List<String> = listOf(
        userSessionBootstrapUrl(),
        protectedCoreProbeUrl(),
        "$ROOT/jh/high3/early/four-year-university/university-major-predict",
        "$ROOT/jh/high3/univ-major/univ-info/univ-search",
        "$ROOT/jh/high3/ipsi-analysis/ipsi-strategy"
    )''',
    '''    fun missionSeeds(): List<String> = listOf(
        protectedCoreProbeUrl(),
        "$ROOT/jh/high3/early/four-year-university/university-major-predict"
    )'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt",
    '''        JinhakMissionLane.SCORE_ANALYSIS,
        JinhakMissionLane.STRATEGY,
        JinhakMissionLane.ADMISSION_KNOWLEDGE -> true
        JinhakMissionLane.REFERENCE,''',
    '''        JinhakMissionLane.SCORE_ANALYSIS -> true
        JinhakMissionLane.STRATEGY,
        JinhakMissionLane.ADMISSION_KNOWLEDGE,
        JinhakMissionLane.REFERENCE,'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt",
    '''        db.rawQuery(
            "SELECT application_identity_key,quality_state,academic_year FROM canonical_applications WHERE session_id=? ORDER BY application_identity_key",
            arrayOf(sessionId)
        ).use { apps ->
            while (apps.moveToNext()) {
                val identity = apps.getString(0)
                if (identity !in selected) continue''',
    '''        val processedScoreIdentities = linkedSetOf<String>()
        db.rawQuery(
            "SELECT application_identity_key,quality_state,academic_year FROM canonical_applications " +
                "ORDER BY CASE WHEN session_id=? THEN 0 ELSE 1 END, updated_at DESC, application_identity_key",
            arrayOf(sessionId)
        ).use { apps ->
            while (apps.moveToNext()) {
                val identity = apps.getString(0)
                if (identity !in selected || !processedScoreIdentities.add(identity)) continue'''
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt",
    '''                .put("qualityState", "stale").put("qualityLabel", "canonical 연결 복구 필요")
                .put("coverageCount", 0).put("coverageComplete", false)
                .put("scoreDecision", JSONObject().put("decisionLabel", "종합: 판정 보류"))''',
    '''                .put("qualityState", "stale").put("qualityLabel", "canonical 연결 복구 필요")
                .put("coverageCount", 0).put("coverageComplete", false)
                .put("scoreDecision", enrichScoreForDisplay(score).put("decisionLabel", "종합: 판정 보류 · canonical 연결 복구 필요"))'''
)

print("v0.18.1 focused-six patch applied")
