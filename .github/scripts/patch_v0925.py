from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
CELLS = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionCellSupervisor.kt'
COVERAGE = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionCoverageLedger.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


def replace_all_checked(text: str, old: str, new: str, minimum: int, label: str) -> str:
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f'{label}: expected at least {minimum} match(es), found {count}')
    return text.replace(old, new)


main = MAIN.read_text()
store = STORE.read_text()
cells = CELLS.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.9.24"',
    'private const val BUILD_CODE = 109240',
    'jinhakInheritedReportLaneActions',
    'JINHAK_SINGLE_WEBVIEW_STABILITY_MODE = true',
    'finishJinhakPostMissionLoginIfReady',
    'jinhakReportBridgeConfirmed',
]:
    if token not in main:
        raise SystemExit('v0.9.24 MainActivity precondition failed: ' + token)
for token in ['jinhak_mission_targets', 'jinhak_mission_runtime', 'null,\n    5\n)']:
    if token not in store:
        raise SystemExit('v0.9.24 LocalCollectorStore precondition failed: ' + token)
if 'fun invalidateAll(' not in cells or 'fun resetForRun(' not in cells:
    raise SystemExit('MissionCellSupervisor precondition failed')

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.9.24"', 'private const val VERSION = "0.9.25"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 109240', 'private const val BUILD_CODE = 109250', 'main build code')
gradle = replace_once(gradle, 'versionCode = 109240', 'versionCode = 109250', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.9.24"', 'versionName = "0.9.25"', 'gradle version name')
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.24 Report Lane Mission Bridge',
    'Admission Collector v0.9.25 Mission Coverage Terminal Seal',
    'manifest label'
)

# Separate coverage state from the navigation target ledger.  v0.9.24 proved that report lanes
# can be attached to all application identities, but only current-prediction had persistent target
# state.  This ledger is small, monotonic and contains no credential/session material.
COVERAGE.write_text(r'''package com.admissionhub.collector.jinhak

import org.json.JSONArray
import org.json.JSONObject

/**
 * Monotonic per-application report coverage ledger.
 *
 * Navigation targets and report coverage are deliberately separate: a report can be reached by
 * an inherited, read-only report-family control without owning a persistent navigation target.
 * Persisting the confirmed lane prevents process death from erasing which report families were
 * already proven for each SAME-APPLICATION identity.
 */
class JinhakMissionCoverageLedger {
    private val lanesByIdentity = linkedMapOf<String, MutableSet<String>>()
    private val sourceByKey = linkedMapOf<String, String>()

    fun clear() {
        lanesByIdentity.clear()
        sourceByKey.clear()
    }

    fun confirm(identityKey: String?, lane: String, source: String = "runtime"): Boolean {
        val identity = identityKey?.takeIf { it.isNotBlank() } ?: return false
        if (lane.isBlank() || lane == "reference") return false
        val changed = lanesByIdentity.getOrPut(identity) { linkedSetOf() }.add(lane)
        if (changed) sourceByKey["$identity|$lane"] = source.take(80)
        return changed
    }

    fun restore(payloads: List<JSONObject>): Int {
        var restored = 0
        payloads.forEach { obj ->
            val identity = obj.optString("identityKey").takeIf { it.isNotBlank() && it != "null" } ?: return@forEach
            val lane = obj.optString("lane").takeIf { it.isNotBlank() && it != "reference" && it != "null" } ?: return@forEach
            if (confirm(identity, lane, obj.optString("source", "sqlite-restore"))) restored += 1
        }
        return restored
    }

    fun lanes(identityKey: String): Set<String> = lanesByIdentity[identityKey]?.toSet().orEmpty()

    fun allCoreComplete(expectedIdentities: Set<String>): Boolean =
        expectedIdentities.isNotEmpty() && expectedIdentities.all { identity ->
            val lanes = lanesByIdentity[identity].orEmpty()
            CORE_LANES.all(lanes::contains)
        }

    fun summary(expectedIdentities: Set<String> = lanesByIdentity.keys): JSONObject {
        val expected = expectedIdentities.filter { it.isNotBlank() }.toSet()
        val laneCounts = JSONObject()
        ALL_TRACKED_LANES.forEach { lane ->
            laneCounts.put(lane, expected.count { lanesByIdentity[it]?.contains(lane) == true })
        }
        val complete = expected.count { identity -> CORE_LANES.all { it in lanes(identity) } }
        val missingByLane = JSONObject()
        CORE_LANES.forEach { lane -> missingByLane.put(lane, (expected.size - laneCounts.optInt(lane)).coerceAtLeast(0)) }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("expectedIdentities", expected.size)
            .put("knownIdentities", lanesByIdentity.size)
            .put("requiredCoreLanes", JSONArray(CORE_LANES))
            .put("laneCoverage", laneCounts)
            .put("completeIdentities", complete)
            .put("incompleteIdentities", (expected.size - complete).coerceAtLeast(0))
            .put("coreComplete", expected.isNotEmpty() && complete == expected.size)
            .put("missingByLane", missingByLane)
            .put("credentialStored", false)
            .put("sessionSecretStored", false)
    }

    companion object {
        val CORE_LANES = listOf(
            "saved-application",
            "current-prediction",
            "mock-support",
            "actual-admit",
            "score-analysis"
        )
        private val ALL_TRACKED_LANES = CORE_LANES + listOf("university-result", "strategy")
    }
}
''')

# MainActivity owns one coverage ledger and a terminal closure state.
main = replace_once(
    main,
    'import com.admissionhub.collector.jinhak.JinhakMissionTargetLedger\nimport com.admissionhub.collector.jinhak.JinhakMissionCellSupervisor\n',
    'import com.admissionhub.collector.jinhak.JinhakMissionTargetLedger\nimport com.admissionhub.collector.jinhak.JinhakMissionCoverageLedger\nimport com.admissionhub.collector.jinhak.JinhakMissionCellSupervisor\n',
    'coverage ledger import'
)
main = replace_once(
    main,
    '    private val jinhakMissionTargetLedger = JinhakMissionTargetLedger()\n    private var jinhakActiveMissionTargetId: String? = null\n',
    '''    private val jinhakMissionTargetLedger = JinhakMissionTargetLedger()
    private val jinhakMissionCoverageLedger = JinhakMissionCoverageLedger()
    private var jinhakCoreCoverageClosureFences = 0
    private var jinhakCoreCoverageClosurePending = false
    private var jinhakTerminalSeals = 0
    private var jinhakTerminalSealed = false
    private var jinhakActiveMissionTargetId: String? = null
''',
    'coverage ledger fields'
)
main = replace_once(
    main,
    '        jinhakInheritedReportLaneActions = 0\n        jinhakMissionAnchorActionsAttempted = 0\n',
    '''        jinhakInheritedReportLaneActions = 0
        jinhakCoreCoverageClosureFences = 0
        jinhakCoreCoverageClosurePending = false
        jinhakTerminalSeals = 0
        jinhakTerminalSealed = false
        jinhakMissionAnchorActionsAttempted = 0
''',
    'coverage closure reset'
)
main = replace_once(
    main,
    '        if (!preserveJinhakMissionState) {\n            jinhakMissionCoverage.clear()\n            jinhakMissionTargetLedger.clear()\n        }\n',
    '''        if (!preserveJinhakMissionState) {
            jinhakMissionCoverage.clear()
            jinhakMissionCoverageLedger.clear()
            jinhakMissionTargetLedger.clear()
        }
''',
    'coverage ledger reset with mission'
)

# Route all authoritative coverage confirmations through one persistence helper.
main = replace_all_checked(
    main,
    'jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() }.add("saved-application")',
    'markJinhakMissionCoverage(identity, "saved-application", "normalized-storage")',
    1,
    'saved application coverage'
)
main = replace_all_checked(
    main,
    'jinhakMissionCoverage.getOrPut(actionMission.identityKey) { linkedSetOf() }.add("saved-application")',
    'markJinhakMissionCoverage(actionMission.identityKey, "saved-application", "mission-start")',
    1,
    'mission start saved coverage'
)
main = replace_all_checked(
    main,
    'jinhakMissionCoverage.getOrPut(missionKey) { linkedSetOf() }.add(resolvedLane)',
    'markJinhakMissionCoverage(missionKey, resolvedLane, "slow-lane-report")',
    1,
    'slow lane coverage'
)
main = replace_all_checked(
    main,
    'if (lane != "reference") jinhakMissionCoverage.getOrPut(missionKey) { linkedSetOf() }.add(lane)',
    'if (lane != "reference") markJinhakMissionCoverage(missionKey, lane, "report-page")',
    1,
    'report page coverage'
)

# Add persistence/closure helpers immediately before runtime persistence.
anchor = '    private fun persistJinhakMissionRuntimeState(trigger: String, mutatedTarget: JSONObject? = null) {\n'
helpers = r'''    private fun markJinhakMissionCoverage(identityKey: String?, lane: String, source: String): Boolean {
        val identity = identityKey?.takeIf { it.isNotBlank() } ?: return false
        if (lane.isBlank() || lane == "reference") return false
        val mapChanged = jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() }.add(lane)
        val ledgerChanged = jinhakMissionCoverageLedger.confirm(identity, lane, source)
        if (ledgerChanged) {
            unifiedSessionId?.takeIf { unifiedRunning && unifiedPhase == "jinhak" }?.let { sessionId ->
                localStore.upsertJinhakMissionCoverage(sessionId, identity, lane, source)
            }
            recordRuntimeEvent("jinhak-mission-coverage-confirmed", JSONObject()
                .put("applicationIdentityHash", identity.take(24))
                .put("lane", lane.take(40))
                .put("source", source.take(60)))
            handler.post { maybeSealJinhakCoreCoverage("coverage:$lane") }
        }
        return mapChanged || ledgerChanged
    }

    private fun restoreJinhakMissionCoveragePersistence(sessionId: String): Int {
        val payloads = localStore.loadJinhakMissionCoverage(sessionId)
        val restored = jinhakMissionCoverageLedger.restore(payloads)
        payloads.forEach { obj ->
            val identity = obj.optString("identityKey").takeIf { it.isNotBlank() && it != "null" } ?: return@forEach
            val lane = obj.optString("lane").takeIf { it.isNotBlank() && it != "reference" && it != "null" } ?: return@forEach
            jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() }.add(lane)
        }
        return restored
    }

    private fun currentExpectedJinhakMissionIdentities(): Set<String> = when {
        jinhakNormalizedIdentitySeedKeys.isNotEmpty() -> jinhakNormalizedIdentitySeedKeys.toSet()
        jinhakMissionCoverage.isNotEmpty() -> jinhakMissionCoverage.keys.toSet()
        else -> emptySet()
    }

    private fun jinhakCoreCoverageAudit(): JSONObject =
        jinhakMissionCoverageLedger.summary(currentExpectedJinhakMissionIdentities())

    private fun maybeSealJinhakCoreCoverage(trigger: String) {
        if (!batchRunning || provider != ProviderId.JINHAK || batchPausedForLogin || jinhakCoreCoverageClosurePending) return
        val expected = currentExpectedJinhakMissionIdentities()
        // The final product is six-application centered.  Requiring at least six discovered
        // identities also prevents a partially rendered storage page from closing the crawl early.
        if (expected.size < 6) return
        val audit = jinhakMissionCoverageLedger.summary(expected)
        if (!audit.optBoolean("coreComplete", false)) return
        if (jinhakMissionTargetLedger.outstandingCount() > 0) return
        if (jinhakApplicationMissionReturns < expected.size) return

        jinhakCoreCoverageClosurePending = true
        jinhakCoreCoverageClosureFences += 1
        recordRuntimeEvent("jinhak-core-coverage-closure", JSONObject()
            .put("trigger", trigger.take(80))
            .put("coverage", audit)
            .put("missionReturns", jinhakApplicationMissionReturns)
            .put("genericActionsAvoided", (MAX_JINHAK_GENERIC_ACTIONS - jinhakGenericActionsExecuted).coerceAtLeast(0)))
        persistLiveJinhakDiagnostics("core-coverage-closure", force = true)
        handler.postDelayed({
            if (batchRunning && provider == ProviderId.JINHAK && !batchPausedForLogin) {
                finishBatch("completed")
            }
        }, 120L)
    }

    private fun sealJinhakTerminalState(reason: String) {
        if (provider != ProviderId.JINHAK || jinhakTerminalSealed) return
        jinhakTerminalSealed = true
        jinhakTerminalSeals += 1
        jinhakMissionCells.sealComplete("finish:${reason.take(80)}")
        jinhakAgentActionInFlight = false
        batchCollecting = false
        jinhakActiveMissionTargetId = null
        currentBatchTarget = null
        jinhakMissionNeedsReturn = false
        jinhakReportBridgeContext = null
        jinhakCoreCoverageClosurePending = false
        ++jinhakProgressFenceGeneration
        ++jinhakStallWatchdogGeneration
        ++batchNavigationWatchdogGeneration
        persistJinhakMissionRuntimeState("terminal-seal")
        recordRuntimeEvent("jinhak-terminal-seal", JSONObject()
            .put("reason", reason.take(100))
            .put("coverage", jinhakCoreCoverageAudit())
            .put("missionCells", jinhakMissionCells.diagnostics(System.currentTimeMillis())))
    }

'''
main = replace_once(main, anchor, helpers + anchor, 'insert coverage persistence helpers')

# Restore the independent coverage ledger on process/session resume.
main = replace_once(
    main,
    '        localStore.loadJinhakMissionRuntime(sessionId)?.let { runtime ->\n',
    '        restoreJinhakMissionCoveragePersistence(sessionId)\n        localStore.loadJinhakMissionRuntime(sessionId)?.let { runtime ->\n',
    'restore coverage before mission runtime'
)

# Every Jinhak finish path gets a terminal seal before the generic finish logic snapshots diagnostics.
main = replace_once(
    main,
    '    private fun finishBatch(reason: String) {\n        jinhakLoginRecoveryEpisodeStartedAtMs = 0L\n',
    '    private fun finishBatch(reason: String) {\n        if (provider == ProviderId.JINHAK) sealJinhakTerminalState(reason)\n        jinhakLoginRecoveryEpisodeStartedAtMs = 0L\n',
    'terminal seal at finishBatch'
)

# Diagnostics expose persisted coverage, the Phase-7-style core coverage audit and terminal seal.
main = replace_once(
    main,
    '                        .put("inheritedReportLaneActions", jinhakInheritedReportLaneActions)\n                        .put("consentGatesEncountered", jinhakConsentGatesEncountered)\n',
    '''                        .put("inheritedReportLaneActions", jinhakInheritedReportLaneActions)
                        .put("coreCoverageClosureFences", jinhakCoreCoverageClosureFences)
                        .put("coreCoverageClosurePending", jinhakCoreCoverageClosurePending)
                        .put("terminalSeals", jinhakTerminalSeals)
                        .put("terminalSealed", jinhakTerminalSealed)
                        .put("coreCoverageAudit", jinhakCoreCoverageAudit())
                        .put("missionCoveragePersistence", unifiedSessionId?.let { localStore.jinhakMissionCoveragePersistenceSummary(it) } ?: JSONObject())
                        .put("consentGatesEncountered", jinhakConsentGatesEncountered)
''',
    'coverage diagnostics'
)

# After UnifiedSyncSession itself is clean, persist a final canonical terminal summary.  The normal
# crawl diagnostic is intentionally pre-finish; this extra event removes ambiguity for the future
# progress UI and resume logic.
main = replace_once(
    main,
    '            markProcessResumeJournalClean("unified-finish:${reason.take(80)}")\n            startupLoginPreflightVerified = false\n',
    '''            markProcessResumeJournalClean("unified-finish:${reason.take(80)}")
            if (sessionId != null && provider == ProviderId.JINHAK) {
                localStore.recordSyncState(
                    sessionId,
                    "JINHAK_TERMINAL_SEAL",
                    ProviderId.JINHAK.wireName,
                    JSONObject()
                        .put("terminal", true)
                        .put("reason", reason.take(100))
                        .put("processJournalClean", true)
                        .put("missionCells", jinhakMissionCells.diagnostics(System.currentTimeMillis()))
                        .put("coreCoverageAudit", jinhakCoreCoverageAudit())
                        .put("coveragePersistence", localStore.jinhakMissionCoveragePersistenceSummary(sessionId)),
                    false
                )
            }
            startupLoginPreflightVerified = false
''',
    'final terminal summary'
)

# Local SQLite schema v6 adds per-identity/lane coverage without touching credential/session data.
store = replace_once(store, '    5\n) {', '    6\n) {', 'database version')
coverage_table = r'''
        db.execSQL("""
            CREATE TABLE IF NOT EXISTS jinhak_mission_coverage(
              session_id TEXT NOT NULL,
              identity_key TEXT NOT NULL,
              lane TEXT NOT NULL,
              source TEXT NOT NULL,
              confirmed_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(session_id,identity_key,lane)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_jinhak_coverage_session_lane ON jinhak_mission_coverage(session_id,lane)")
'''
store = replace_once(
    store,
    '        db.execSQL("CREATE INDEX IF NOT EXISTS idx_jinhak_mission_session_identity ON jinhak_mission_targets(session_id,identity_key,lane)")\n\n        db.execSQL("""\n            CREATE TABLE IF NOT EXISTS jinhak_mission_runtime(',
    '        db.execSQL("CREATE INDEX IF NOT EXISTS idx_jinhak_mission_session_identity ON jinhak_mission_targets(session_id,identity_key,lane)")\n' + coverage_table + '\n        db.execSQL("""\n            CREATE TABLE IF NOT EXISTS jinhak_mission_runtime(',
    'coverage schema'
)
store = replace_once(
    store,
    '        if (oldVersion < 5) {\n            ensureFoundationSchema(db)\n        }\n',
    '        if (oldVersion < 5) {\n            ensureFoundationSchema(db)\n        }\n        if (oldVersion < 6) {\n            ensureFoundationSchema(db)\n        }\n',
    'coverage schema upgrade'
)

coverage_methods = r'''
    fun upsertJinhakMissionCoverage(
        sessionId: String,
        identityKey: String,
        lane: String,
        source: String
    ): Boolean {
        if (sessionId.isBlank() || identityKey.isBlank() || lane.isBlank() || lane == "reference") return false
        val now = Instant.now().toString()
        val db = writableDatabase
        val existing = db.rawQuery(
            "SELECT confirmed_at FROM jinhak_mission_coverage WHERE session_id=? AND identity_key=? AND lane=? LIMIT 1",
            arrayOf(sessionId, identityKey, lane)
        ).use { c -> if (c.moveToFirst()) c.getString(0) else null }
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            put("identity_key", identityKey)
            put("lane", lane)
            put("source", source.take(80))
            put("confirmed_at", existing ?: now)
            put("updated_at", now)
        }
        db.insertWithOnConflict("jinhak_mission_coverage", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        return existing == null
    }

    fun loadJinhakMissionCoverage(sessionId: String): List<JSONObject> {
        if (sessionId.isBlank()) return emptyList()
        val out = mutableListOf<JSONObject>()
        readableDatabase.rawQuery(
            "SELECT identity_key,lane,source,confirmed_at,updated_at FROM jinhak_mission_coverage WHERE session_id=? ORDER BY identity_key,lane",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                out += JSONObject()
                    .put("identityKey", c.getString(0))
                    .put("lane", c.getString(1))
                    .put("source", c.getString(2))
                    .put("confirmedAt", c.getString(3))
                    .put("updatedAt", c.getString(4))
            }
        }
        return out
    }

    fun jinhakMissionCoveragePersistenceSummary(sessionId: String): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("persistedCoverage", 0).put("persistedIdentities", 0)
        val db = readableDatabase
        val counts = db.rawQuery(
            "SELECT COUNT(*),COUNT(DISTINCT identity_key) FROM jinhak_mission_coverage WHERE session_id=?",
            arrayOf(sessionId)
        ).use { c -> if (c.moveToFirst()) intArrayOf(c.getInt(0), c.getInt(1)) else intArrayOf(0, 0) }
        val laneCounts = JSONObject()
        db.rawQuery(
            "SELECT lane,COUNT(DISTINCT identity_key) FROM jinhak_mission_coverage WHERE session_id=? GROUP BY lane ORDER BY lane",
            arrayOf(sessionId)
        ).use { c -> while (c.moveToNext()) laneCounts.put(c.getString(0), c.getInt(1)) }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("persistedCoverage", counts[0])
            .put("persistedIdentities", counts[1])
            .put("laneCoverage", laneCounts)
            .put("monotonicConfirmedOnly", true)
            .put("credentialStored", false)
            .put("sessionSecretStored", false)
    }

'''
store = replace_once(
    store,
    '    private fun nullableInt(obj: JSONObject, key: String): Int? =\n',
    coverage_methods + '    private fun nullableInt(obj: JSONObject, key: String): Int? =\n',
    'coverage persistence methods'
)
store = replace_once(
    store,
    '            .put("sessionSecretStored", false)\n    }\n\n    private fun nullableInt',
    '            .put("sessionSecretStored", false)\n            .put("coverage", jinhakMissionCoveragePersistenceSummary(sessionId))\n    }\n\n' + coverage_methods + '    private fun nullableInt',
    'mission persistence summary coverage'
) if coverage_methods not in store else store
# The previous insertion is intentionally idempotence-guarded.  If methods are already inserted,
# attach coverage to the summary with a narrower replacement.
if '.put("coverage", jinhakMissionCoveragePersistenceSummary(sessionId))' not in store:
    store = replace_once(
        store,
        '            .put("sessionSecretStored", false)\n    }\n\n    private fun nullableInt',
        '            .put("sessionSecretStored", false)\n            .put("coverage", jinhakMissionCoveragePersistenceSummary(sessionId))\n    }\n\n    private fun nullableInt',
        'mission persistence summary coverage narrow'
    )
store = replace_once(
    store,
    '        out.put("jinhakDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_CRAWL_DIAGNOSTICS"))\n            .put("jinhakAuthDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_AUTH_DIAGNOSTICS"))\n',
    '        out.put("jinhakDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_CRAWL_DIAGNOSTICS"))\n            .put("jinhakAuthDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_AUTH_DIAGNOSTICS"))\n            .put("jinhakTerminalSummary", latestSyncStateDetail(sessionId, "JINHAK_TERMINAL_SEAL"))\n',
    'terminal summary export'
)

# Mission supervisor gets an explicit terminal state instead of looking WAITING/IDLE after the run.
cells = replace_once(
    cells,
    '    private var snapshotCompletions = 0\n',
    '    private var snapshotCompletions = 0\n    private var terminalState = "ACTIVE"\n    private var terminalReason = ""\n',
    'terminal fields'
)
cells = replace_once(
    cells,
    '        snapshotCompletions = 0\n        addEvent(CELL_SUPERVISOR, "RUN_RESET", null, reason, nowMs)\n',
    '        snapshotCompletions = 0\n        terminalState = "ACTIVE"\n        terminalReason = ""\n        addEvent(CELL_SUPERVISOR, "RUN_RESET", null, reason, nowMs)\n',
    'terminal reset'
)
seal_method = r'''    @Synchronized
    fun sealComplete(reason: String, nowMs: Long = System.currentTimeMillis()): InvalidationResult {
        val invalidated = invalidateAllInternal("terminal-seal:${reason.take(80)}", nowMs)
        terminalState = "COMPLETE"
        terminalReason = reason.take(120)
        addEvent(CELL_SUPERVISOR, "COMPLETE", null, terminalReason, nowMs)
        return invalidated
    }

'''
cells = replace_once(
    cells,
    '    @Synchronized\n    fun diagnostics(nowMs: Long = System.currentTimeMillis()): JSONObject {\n',
    seal_method + '    @Synchronized\n    fun diagnostics(nowMs: Long = System.currentTimeMillis()): JSONObject {\n',
    'terminal seal method'
)
cells = replace_once(
    cells,
    '        val state = when {\n            rendererState == "DEAD" -> "RENDERER_DEAD"\n',
    '        val state = when {\n            terminalState == "COMPLETE" -> "COMPLETE"\n            rendererState == "DEAD" -> "RENDERER_DEAD"\n',
    'terminal diagnostics state'
)
cells = replace_once(
    cells,
    '            .put("supervisorState", state)\n            .put("staleOwnershipMs", staleOwnershipMs)\n',
    '            .put("supervisorState", state)\n            .put("terminalState", terminalState)\n            .put("terminalReason", terminalReason.ifBlank { JSONObject.NULL })\n            .put("staleOwnershipMs", staleOwnershipMs)\n',
    'terminal diagnostics fields'
)

# Safety invariants.
for forbidden in [
    '.put("password", credentials.password)',
    '.putString("processCookie"',
    '.putString("processToken"',
    'supportsBatchCrawl = true',
]:
    if forbidden in main:
        raise SystemExit('privacy/architecture invariant failed: ' + forbidden)

MAIN.write_text(main)
STORE.write_text(store)
CELLS.write_text(cells)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('Applied v0.9.25 Mission Coverage Terminal Seal patch')
