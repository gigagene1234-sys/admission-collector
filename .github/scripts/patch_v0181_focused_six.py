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


# Version metadata.
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

# Focused-six policy import and runtime diagnostics.
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

# The v0.18.0 form probe was too short for the real hydrated login page. Keep it bounded,
# but give the page enough time to expose the actual fields.
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

# After authentication, do not continue from whichever generic high3 page happened to be
# returned by the login router. Bootstrap the personalized saved-application surface first.
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

# Seed the mission scheduler from the six user-pinned identities before any Jinhak crawl.
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
    '''        if (provider == ProviderId.JINHAK) {
''',
    '''        if (provider == ProviderId.JINHAK) {
            activateV0181PinnedSixFocus("start-batch")
'''
)

# Pinned six identities are authoritative even if the newest candidate graph is stale.
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

# Strictly remove unknown/editorial routes from the selected-six frontier.
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

# When six applications are pinned there is no generic fallback mission. Exhaustion advances
# the mission scheduler instead of wandering into strategy/knowledge/reference content.
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

# Export focused-six diagnostics next to the v0.18.0 auth diagnostics. This replacement is
# intentionally applied to every diagnostics builder that has the stable v0.18.0 suffix.
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

# Jinhak topology: selected-six collection starts at protected/prediction surfaces and no
# longer seeds or considers editorial strategy/knowledge as default traversal.
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

# Preserve verified score conversion/outcome rows for pinned applications even when the newest
# canonical graph is stale. Current-session rows win, then the newest reusable row for that identity.
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

# A stale canonical card remains HOLD/unresolvable, but verified score evidence attached to the
# pinned identity is still displayed instead of being silently replaced by an empty placeholder.
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
