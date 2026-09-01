from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
ADAPTER = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
CLOUD = ROOT / 'app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadCoordinator.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 occurrence, found {count}')
    return text.replace(old, new, 1)


def replace_all_checked(text: str, old: str, new: str, minimum: int, label: str) -> str:
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f'{label}: expected >= {minimum}, found {count}')
    return text.replace(old, new)

# ---------------------------------------------------------------------------
# MainActivity: bridge state, diagnostics, user-session traversal semantics.
# ---------------------------------------------------------------------------
m = MAIN.read_text()
m = once(m,
    'import com.admissionhub.collector.jinhak.JinhakSlowLanePool\n',
    'import com.admissionhub.collector.jinhak.JinhakSlowLanePool\nimport com.admissionhub.collector.jinhak.JinhakReportContextBridge\n',
    'bridge import')

m = once(m,
'''    private var jinhakSlowLaneEscalated = 0
    private var jinhakSlowLaneCompleted = 0
    private var jinhakSlowLaneFailed = 0
    private var jinhakSlowLaneUserActionRequired = 0
    private val cloudFrontierTaskIds = linkedMapOf<String, String>()
''',
'''    private var jinhakSlowLaneEscalated = 0
    private var jinhakSlowLaneCompleted = 0
    private var jinhakSlowLaneFailed = 0
    private var jinhakSlowLaneUserActionRequired = 0
    private var jinhakSlowLaneCompletedDurationMs = 0L
    private var jinhakSlowLaneMaxDurationMs = 0L
    private var jinhakReportBridgeContext: JSONObject? = null
    private var jinhakReportBridgeArmed = 0
    private var jinhakReportBridgeApplied = 0
    private var jinhakMissionAnchorActionsAttempted = 0
    private val jinhakAnchorRejectReasons = linkedMapOf<String, Int>()
    private val cloudFrontierTaskIds = linkedMapOf<String, String>()
''', 'main bridge fields')

m = once(m,
'''    private var cloudFrontierPublished = 0
    private var cloudFrontierClaimed = 0
''',
'''    private var cloudFrontierPublished = 0
    private var cloudFrontierClaimed = 0
    private var cloudFrontierCompleted = 0
    private var cloudFrontierCompletionFailed = 0
''', 'cloud completion fields')

m = m.replace('private const val VERSION = "0.8.3"', 'private const val VERSION = "0.8.4"')
m = m.replace('private const val BUILD_CODE = 10830', 'private const val BUILD_CODE = 10840')

m = once(m,
'''        jinhakSlowLaneEscalated = 0
        jinhakSlowLaneCompleted = 0
        jinhakSlowLaneFailed = 0
        jinhakSlowLaneUserActionRequired = 0
''',
'''        jinhakSlowLaneEscalated = 0
        jinhakSlowLaneCompleted = 0
        jinhakSlowLaneFailed = 0
        jinhakSlowLaneUserActionRequired = 0
        jinhakSlowLaneCompletedDurationMs = 0L
        jinhakSlowLaneMaxDurationMs = 0L
        jinhakReportBridgeContext = null
        jinhakReportBridgeArmed = 0
        jinhakReportBridgeApplied = 0
        jinhakMissionAnchorActionsAttempted = 0
        jinhakAnchorRejectReasons.clear()
''', 'reset bridge stats')

m = once(m,
'''        cloudFrontierPublished = 0
        cloudFrontierClaimed = 0
''',
'''        cloudFrontierPublished = 0
        cloudFrontierClaimed = 0
        cloudFrontierCompleted = 0
        cloudFrontierCompletionFailed = 0
''', 'reset cloud completion')

# Keep legacy enum for old exports, but new sessions enter the explicit user-session state.
m = m.replace('UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL.name', 'UnifiedSyncState.JINHAK_USER_SESSION_MISSION.name')
m = m.replace('JSONObject().put("observationFirst", true).put("boundedSameProviderTraversal", true).put("maxPages", MAX_JINHAK_AUTONAV_PAGES)',
              'JSONObject().put("observationFirst", true).put("userStartedSessionMission", true).put("boundedSameProviderTraversal", true).put("maxPages", MAX_JINHAK_AUTONAV_PAGES)')

# Explicitly allow the bounded user-session mission path without claiming broad provider crawling.
m = once(m,
'''        if (!currentAdapter().supportsBatchCrawl) {
            status.text = "진학사 현재 화면을 분석하고 로컬 이력에 누적합니다."
            collectCurrentPage()
            return
        }
''',
'''        val userSessionMissionTraversal = provider == ProviderId.JINHAK && currentAdapter().supportsUserSessionMissionTraversal
        if (!currentAdapter().supportsBatchCrawl && !userSessionMissionTraversal) {
            status.text = "현재 공급자는 단일 화면 분석 모드입니다."
            collectCurrentPage()
            return
        }
''', 'user session mission traversal gate')

m = replace_all_checked(m,
    'batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"',
    'batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else if (provider == ProviderId.JINHAK && currentAdapter().supportsUserSessionMissionTraversal) "진학사 목적형 탐색" else "현재 화면 정리"',
    3, 'idle button semantics')

# Arm a provenance bridge before a same-application report action starts.
m = once(m,
'''        jinhakLastAgentActionLabel = candidate.label
        jinhakLastAgentActionOriginRoute = route
        jinhakLastAgentActionMissionContext = actionMission ?: jinhakMissionContext
        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
        if (candidate.kind == "mission-link-navigation") jinhakMissionAnchorActionsExecuted += 1
''',
'''        jinhakLastAgentActionLabel = candidate.label
        jinhakLastAgentActionOriginRoute = route
        jinhakLastAgentActionMissionContext = actionMission ?: jinhakMissionContext
        val bridgeMission = jinhakLastAgentActionMissionContext
        if (bridgeMission?.identityKey != null && JinhakReportContextBridge.isReportAction(candidate.label, candidate.kind)) {
            jinhakReportBridgeContext = JinhakReportContextBridge.arm(
                bridgeMission,
                runtimeSafePath(route),
                candidate.label,
                candidate.kind
            )
            jinhakReportBridgeArmed += 1
        }
        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
        if (candidate.kind == "mission-link-navigation") jinhakMissionAnchorActionsAttempted += 1
''', 'arm report bridge')

# Record successful anchor execution only after JS says click succeeded, and retain reject reason.
anchor = '''            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
            if (result.optBoolean("ok", false)) {
'''
replacement = '''            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
            if (!result.optBoolean("ok", false)) {
                val rejectReason = result.optString("reason", "unknown-agent-action-failure").take(80)
                jinhakAnchorRejectReasons[rejectReason] = (jinhakAnchorRejectReasons[rejectReason] ?: 0) + 1
                recordRuntimeEvent("jinhak-agent-action-rejected", JSONObject()
                    .put("safePath", runtimeSafePath(route))
                    .put("label", candidate.label.take(80))
                    .put("kind", candidate.kind)
                    .put("reason", rejectReason)
                    .put("primaryReason", result.optString("primaryReason").take(80)))
                if (candidate.kind == "mission-link-navigation") jinhakReportBridgeContext = null
            }
            if (result.optBoolean("ok", false)) {
                if (candidate.kind == "mission-link-navigation") jinhakMissionAnchorActionsExecuted += 1
'''
m = once(m, anchor, replacement, 'agent result diagnostics')

# For deep report destinations, prefer the short-lived Gate-A bridge over missing page context.
m = once(m,
'''                jinhakMissionContext?.let { snapshot.put("missionApplicationContext", it.toJson()) }
''',
'''                val pageTypeForBridge = snapshot.optString("providerPageType")
                val effectiveMissionJson = JinhakReportContextBridge.resolve(
                    pageTypeForBridge,
                    jinhakMissionContext,
                    jinhakReportBridgeContext
                )
                effectiveMissionJson?.let { missionJson ->
                    snapshot.put("missionApplicationContext", missionJson)
                    if (JinhakReportContextBridge.isReportPageType(pageTypeForBridge) && missionJson.has("reportBridgeActionToken")) {
                        jinhakReportBridgeApplied += 1
                    }
                }
''', 'bridge snapshot injection')

# Slow-lane deferred work carries the same bridge provenance, not a freshly inferred page identity.
m = once(m,
'''                missionContext = mission?.toJson(),
''',
'''                missionContext = jinhakReportBridgeContext?.let { JSONObject(it.toString()) } ?: mission?.toJson(),
''', 'slow lane bridge provenance')

# Clear bridge whenever mission identity is intentionally cleared. This avoids leaking one card into another.
m = replace_all_checked(m,
    '        jinhakMissionContext = null\n',
    '        jinhakMissionContext = null\n        jinhakReportBridgeContext = null\n',
    3, 'bridge clear with mission clear')

# Slow lane effectiveness metrics.
m = once(m,
'''            jinhakSlowLaneCompleted += 1
            recordRuntimeEvent("jinhak-slow-lane-completed", JSONObject()
''',
'''            jinhakSlowLaneCompleted += 1
            jinhakSlowLaneCompletedDurationMs += stats.elapsedMs
            if (stats.elapsedMs > jinhakSlowLaneMaxDurationMs) jinhakSlowLaneMaxDurationMs = stats.elapsedMs
            recordRuntimeEvent("jinhak-slow-lane-completed", JSONObject()
''', 'slow duration stats')

# Track frontier completion acknowledgement rather than claim alone.
m = m.replace(
    'cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "completed", null) }',
    'cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "completed", null) { ok -> if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1 } }')
m = m.replace(
    'cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "error", reason.take(120)) }',
    'cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "error", reason.take(120)) { ok -> if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1 } }')
m = m.replace(
'''                    cloudOffload.completeFrontier(taskId, "completed", null)
''',
'''                    cloudOffload.completeFrontier(taskId, "completed", null) { ok ->
                        if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1
                    }
''')

# Extend sync diagnostics.
m = once(m,
'''                        .put("applicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
                        .put("applicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
''',
'''                        .put("applicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
                        .put("applicationAnchorActionsAttempted", jinhakMissionAnchorActionsAttempted)
                        .put("applicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
                        .put("applicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))
                        .put("reportBridgeArmed", jinhakReportBridgeArmed)
                        .put("reportBridgeApplied", jinhakReportBridgeApplied)
''', 'sync bridge diagnostics')

m = once(m,
'''                        .put("slowLaneCompleted", jinhakSlowLaneCompleted)
                        .put("slowLaneFailed", jinhakSlowLaneFailed)
''',
'''                        .put("slowLaneCompleted", jinhakSlowLaneCompleted)
                        .put("slowLaneAverageCompletedMs", if (jinhakSlowLaneCompleted > 0) jinhakSlowLaneCompletedDurationMs / jinhakSlowLaneCompleted else JSONObject.NULL)
                        .put("slowLaneMaxCompletedMs", jinhakSlowLaneMaxDurationMs)
                        .put("slowLaneFailed", jinhakSlowLaneFailed)
''', 'sync slow duration diagnostics')

m = once(m,
'''                        .put("cloudFrontierPublished", cloudFrontierPublished)
                        .put("cloudFrontierClaimed", cloudFrontierClaimed),
''',
'''                        .put("cloudFrontierPublished", cloudFrontierPublished)
                        .put("cloudFrontierClaimed", cloudFrontierClaimed)
                        .put("cloudFrontierCompleted", cloudFrontierCompleted)
                        .put("cloudFrontierCompletionFailed", cloudFrontierCompletionFailed),
''', 'sync cloud completion diagnostics')

# Also expose the new metrics in manual diagnostic bundles.
m = once(m,
'''                .put("jinhakApplicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
''',
'''                .put("jinhakApplicationAnchorActionsAttempted", jinhakMissionAnchorActionsAttempted)
                .put("jinhakApplicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
                .put("jinhakApplicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))
                .put("jinhakReportBridgeArmed", jinhakReportBridgeArmed)
                .put("jinhakReportBridgeApplied", jinhakReportBridgeApplied)
''', 'manual bridge diagnostics')

m = once(m,
'''                .put("jinhakSlowLaneCompleted", jinhakSlowLaneCompleted)
                .put("jinhakSlowLaneFailed", jinhakSlowLaneFailed)
''',
'''                .put("jinhakSlowLaneCompleted", jinhakSlowLaneCompleted)
                .put("jinhakSlowLaneAverageCompletedMs", if (jinhakSlowLaneCompleted > 0) jinhakSlowLaneCompletedDurationMs / jinhakSlowLaneCompleted else JSONObject.NULL)
                .put("jinhakSlowLaneMaxCompletedMs", jinhakSlowLaneMaxDurationMs)
                .put("jinhakSlowLaneFailed", jinhakSlowLaneFailed)
''', 'manual slow duration diagnostics')

m = once(m,
'''                .put("cloudFrontierPublished", cloudFrontierPublished)
                .put("cloudFrontierClaimed", cloudFrontierClaimed)
''',
'''                .put("cloudFrontierPublished", cloudFrontierPublished)
                .put("cloudFrontierClaimed", cloudFrontierClaimed)
                .put("cloudFrontierCompleted", cloudFrontierCompleted)
                .put("cloudFrontierCompletionFailed", cloudFrontierCompletionFailed)
''', 'manual cloud completion diagnostics')

MAIN.write_text(m)

# ---------------------------------------------------------------------------
# JinhakAdapter: explicit user-session mission + year semantic guard.
# ---------------------------------------------------------------------------
a = ADAPTER.read_text()
a = once(a,
    'import com.admissionhub.collector.jinhak.JinhakApplicationMission\n',
    'import com.admissionhub.collector.jinhak.JinhakApplicationMission\nimport com.admissionhub.collector.jinhak.JinhakReportYearGuard\n',
    'year guard import')
a = once(a,
'''    override val id = ProviderId.JINHAK
    override val supportsBatchCrawl = true
''',
'''    override val id = ProviderId.JINHAK
    override val supportsBatchCrawl = false
    override val supportsUserSessionMissionTraversal = true
''', 'jinhak traversal capability split')
a = once(a,
'''        val inferredYear = context.year ?: if (dataScope == "current-prediction" || dataScope == "current-admission") TARGET_YEAR else null
''',
'''        val inferredYear = JinhakReportYearGuard.resolvePageYear(pageType, text, TARGET_YEAR)
            ?: when {
                dataScope == "historical-result" -> null
                dataScope == "current-prediction" || dataScope == "current-admission" || dataScope == "student-profile" -> TARGET_YEAR
                else -> context.year
            }
''', 'page year guard')
a = once(a,
'''        val metrics = JinhakApplicationMission.semanticMetrics(text)
''',
'''        val metrics = JinhakReportYearGuard.annotate(
            JinhakApplicationMission.semanticMetrics(text),
            pageType,
            inferredYear
        )
''', 'year guard metrics')
a = once(a,
'''            if (row.isNull("year") && inferredYear != null) row.put("year", inferredYear)
''',
'''            if (dataScope == "historical-result") {
                val guardedHistoricalYear = JinhakReportYearGuard.sanitizeHistoricalRowYear(row, TARGET_YEAR)
                row.put("year", guardedHistoricalYear ?: JSONObject.NULL)
                val rowMetrics = row.optJSONObject("metrics") ?: JSONObject().also { row.put("metrics", it) }
                JinhakReportYearGuard.annotate(rowMetrics, pageType, guardedHistoricalYear)
            } else if (row.isNull("year") && inferredYear != null) {
                row.put("year", inferredYear)
            }
''', 'historical row year guard')
ADAPTER.write_text(a)

# ---------------------------------------------------------------------------
# Cloud coordinator: acknowledgement callback for complete frontier.
# ---------------------------------------------------------------------------
c = CLOUD.read_text()
c = once(c,
'''    fun completeFrontier(taskId: String, state: String, errorType: String?) {
        if (taskId.isBlank() || frontierAvailable != true) return
        val currentClient = synchronized(lock) { ensureClientLocked(); client } ?: return
        currentClient.completeFrontier(taskId, state, errorType) { result ->
            result.onFailure { lastError = it.message }
        }
    }
''',
'''    fun completeFrontier(taskId: String, state: String, errorType: String?, callback: (Boolean) -> Unit = {}) {
        if (taskId.isBlank() || frontierAvailable != true) { callback(false); return }
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (currentClient == null) { callback(false); return }
        currentClient.completeFrontier(taskId, state, errorType) { result ->
            result.onFailure { lastError = it.message }
            callback(result.isSuccess)
        }
    }
''', 'frontier completion callback')
CLOUD.write_text(c)

# ---------------------------------------------------------------------------
# Version metadata.
# ---------------------------------------------------------------------------
g = GRADLE.read_text().replace('versionCode = 10830', 'versionCode = 10840').replace('versionName = "0.8.3"', 'versionName = "0.8.4"')
if 'versionCode = 10840' not in g or 'versionName = "0.8.4"' not in g:
    raise SystemExit('Gradle version patch failed')
GRADLE.write_text(g)

man = MANIFEST.read_text().replace(
    'android:label="Admission Collector v0.8.3 Concurrent Slow Lane"',
    'android:label="Admission Collector v0.8.4 Report Context Bridge"'
)
if 'Admission Collector v0.8.4 Report Context Bridge' not in man:
    raise SystemExit('Manifest label patch failed')
MANIFEST.write_text(man)

print('Applied Admission Collector v0.8.4 Report Context Bridge patch')
