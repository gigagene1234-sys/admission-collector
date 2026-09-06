from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
EVIDENCE = ROOT / 'app/src/main/java/com/admissionhub/collector/canonical/AdigaOfficialAdmissionEvidence.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)

main = MAIN.read_text()
store = STORE.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.10.0"',
    'private const val BUILD_CODE = 110000',
    'fun rebuildCanonicalApplicationGraph(sessionId: String): JSONObject',
    'fun refreshCanonicalQualityAudit(sessionId: String): JSONObject',
    'private fun currentExpectedJinhakMissionIdentities(): Set<String>',
    'private fun startBatch()',
]:
    if token not in main and token not in store:
        raise SystemExit('v0.10.0 precondition failed: ' + token)

EVIDENCE.write_text(r'''package com.admissionhub.collector.canonical

import org.json.JSONArray
import org.json.JSONObject

/**
 * Conservative parser for official Adiga table evidence.
 *
 * It never invents a recruitment-unit/admission binding. A current-year table only earns
 * row-bound support when the SAME table row contains both the application department and
 * admission label. University-level or historical mentions are retained as evidence only.
 */
object AdigaOfficialAdmissionEvidence {
    data class AppRef(
        val year: Int,
        val university: String?,
        val department: String?,
        val admission: String?,
        val admissionCategory: String?
    )

    fun inspect(recordType: String, recordYear: Int, record: JSONObject, app: AppRef): List<JSONObject> {
        if (recordType !in setOf("current-admission-criteria-table", "historical-admission-result-table")) return emptyList()
        val metrics = record.optJSONObject("metrics") ?: return emptyList()
        val rows = metrics.optJSONArray("rows") ?: return emptyList()
        val out = mutableListOf<JSONObject>()
        for (ri in 0 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            val cells = (0 until row.length()).map { row.optString(it).trim() }.filter { it.isNotBlank() }
            if (cells.isEmpty()) continue
            val rowText = cells.joinToString(" | ").take(1200)
            val admissionQuality = admissionEvidenceQuality(cells, app.admission, app.admissionCategory)
            if (admissionQuality == "none") continue
            val departmentQuality = departmentEvidenceQuality(cells, app.department)
            val currentYear = recordType == "current-admission-criteria-table" && recordYear == app.year
            val scope = when {
                currentYear && departmentQuality in setOf("exact", "suffix-equivalent") && admissionQuality == "exact" -> "row-bound-current"
                currentYear && departmentQuality in setOf("exact", "suffix-equivalent") -> "row-bound-current-related"
                currentYear -> "university-current"
                else -> "historical"
            }
            out += JSONObject()
                .put("recordType", recordType)
                .put("recordYear", recordYear)
                .put("rowIndex", ri)
                .put("scope", scope)
                .put("departmentMatch", departmentQuality)
                .put("admissionMatch", admissionQuality)
                .put("rowEvidence", rowText)
                .put("sourcePage", record.optString("sourcePage").take(500))
                .put("sourceRowFingerprint", record.optString("sourceRowFingerprint").take(100))
                .put("officialSource", true)
                .put("bindingInferred", false)
        }
        return out
    }

    private fun admissionEvidenceQuality(cells: List<String>, admission: String?, category: String?): String {
        val target = CanonicalSixApplicationGraph.normalizeAdmissionKey(admission)
        val categoryKey = CanonicalSixApplicationGraph.normalizeAdmissionKey(category)
        val normalized = cells.map(CanonicalSixApplicationGraph::normalizeAdmissionKey)
        if (target.isNotBlank() && normalized.any { it == target || (target.length >= 3 && it.contains(target)) }) return "exact"
        if (target.isNotBlank() && normalized.any { it.length >= 3 && target.contains(it) }) return "related"
        if (categoryKey.isNotBlank() && normalized.any { it == categoryKey || (it.length >= 2 && (it.contains(categoryKey) || categoryKey.contains(it))) }) return "category-only"
        return "none"
    }

    private fun departmentEvidenceQuality(cells: List<String>, department: String?): String {
        var best = "none"
        for (cell in cells) {
            when (CanonicalSixApplicationGraph.departmentMatchQuality(department, cell)) {
                "exact" -> return "exact"
                "suffix-equivalent" -> best = "suffix-equivalent"
            }
        }
        return best
    }
}
''')

# Version / label.
main = replace_once(main, 'private const val VERSION = "0.10.0"', 'private const val VERSION = "0.10.1"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 110000', 'private const val BUILD_CODE = 110010', 'main build code')
gradle = replace_once(gradle, 'versionCode = 110000', 'versionCode = 110010', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.10.0"', 'versionName = "0.10.1"', 'gradle version name')
manifest = replace_once(manifest, 'Admission Hub v0.10.0 Canonical Six Graph', 'Admission Hub v0.10.1 Selected Six Recovery', 'manifest label')

# ---------------------------------------------------------------------------
# Local database v8: persistent selected-six recovery scope.
# ---------------------------------------------------------------------------
store = replace_once(
    store,
    'import com.admissionhub.collector.canonical.CanonicalSixApplicationGraph\n',
    'import com.admissionhub.collector.canonical.CanonicalSixApplicationGraph\nimport com.admissionhub.collector.canonical.AdigaOfficialAdmissionEvidence\n',
    'evidence import'
)
store = replace_once(store, '    7\n) {', '    8\n) {', 'database version')

schema_anchor = '''        db.execSQL("""\n            CREATE TABLE IF NOT EXISTS jinhak_mission_targets('''
schema_insert = '''        db.execSQL("""
            CREATE TABLE IF NOT EXISTS hub_selected_recovery_scope(
              session_id TEXT NOT NULL,
              application_identity_key TEXT NOT NULL,
              missing_lanes_json TEXT NOT NULL,
              state TEXT NOT NULL,
              attempt_count INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(session_id,application_identity_key)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_hub_selected_recovery_state ON hub_selected_recovery_scope(session_id,state,updated_at)")

'''
store = replace_once(store, schema_anchor, schema_insert + schema_anchor, 'selected recovery schema')
store = replace_once(
    store,
    '''        if (oldVersion < 7) {
            ensureFoundationSchema(db)
        }
''',
    '''        if (oldVersion < 7) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 8) {
            ensureFoundationSchema(db)
        }
''',
    'db upgrade v8'
)

# Public provider run + session adoption helpers.
provider_helper_anchor = '''    private fun unifiedProviderRunId(sessionId: String, provider: String): String? {'''
provider_helpers = '''    fun providerRunIdForUnifiedSession(sessionId: String, provider: String): String? = unifiedProviderRunId(sessionId, provider)

    fun adoptUnifiedSessionCollectorVersion(sessionId: String, collectorVersion: String) {
        if (sessionId.isBlank() || collectorVersion.isBlank()) return
        val cv = ContentValues().apply {
            put("collector_version", collectorVersion)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.update("unified_sessions", cv, "session_id=?", arrayOf(sessionId))
    }

'''
store = replace_once(store, provider_helper_anchor, provider_helpers + provider_helper_anchor, 'provider run helpers')

# Selected-six recovery plan and persistence methods before rebuildCanonicalApplicationGraph.
rebuild_anchor = '''    fun rebuildCanonicalApplicationGraph(sessionId: String): JSONObject {'''
recovery_methods = r'''    fun prepareSelectedSixRecovery(sessionId: String): JSONObject {
        val slots = loadHubApplicationSlots()
        val selected = mutableListOf<String>()
        for (i in 0 until slots.length()) {
            val row = slots.optJSONObject(i) ?: continue
            if (!row.optBoolean("occupied", false)) continue
            row.optString("applicationIdentityKey").takeIf { it.isNotBlank() }?.let(selected::add)
        }
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val byIdentity = linkedMapOf<String, JSONObject>()
        for (i in 0 until candidates.length()) {
            val row = candidates.optJSONObject(i) ?: continue
            byIdentity[row.optString("applicationIdentityKey")] = row
        }
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.delete("hub_selected_recovery_scope", "session_id=?", arrayOf(sessionId))
            for (identity in selected.distinct()) {
                val candidate = byIdentity[identity]
                val missing = candidate?.optJSONObject("coverage")?.optJSONArray("missing") ?: JSONArray()
                val state = if (candidate == null) "stale" else if (missing.length() == 0) "complete" else "pending"
                val cv = ContentValues().apply {
                    put("session_id", sessionId)
                    put("application_identity_key", identity)
                    put("missing_lanes_json", missing.toString())
                    put("state", state)
                    put("attempt_count", 0)
                    put("updated_at", Instant.now().toString())
                }
                db.insertWithOnConflict("hub_selected_recovery_scope", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return selectedSixRecoveryPlan(sessionId)
    }

    fun selectedSixRecoveryPlan(sessionId: String): JSONObject {
        val entries = JSONArray()
        val identities = JSONArray()
        var pending = 0
        var complete = 0
        var stale = 0
        readableDatabase.rawQuery(
            "SELECT application_identity_key,missing_lanes_json,state,attempt_count,updated_at FROM hub_selected_recovery_scope WHERE session_id=? ORDER BY application_identity_key",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                val state = c.getString(2)
                when (state) { "pending", "running" -> pending += 1; "complete" -> complete += 1; else -> stale += 1 }
                identities.put(c.getString(0))
                entries.put(JSONObject()
                    .put("applicationIdentityKey", c.getString(0))
                    .put("missingLanes", runCatching { JSONArray(c.getString(1)) }.getOrDefault(JSONArray()))
                    .put("state", state)
                    .put("attemptCount", c.getInt(3))
                    .put("updatedAt", c.getString(4)))
            }
        }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("requiredSlots", CanonicalSixApplicationGraph.SLOT_COUNT)
            .put("scopedIdentities", identities.length())
            .put("identities", identities)
            .put("pendingIdentities", pending)
            .put("completeIdentities", complete)
            .put("staleIdentities", stale)
            .put("entries", entries)
            .put("active", identities.length() == CanonicalSixApplicationGraph.SLOT_COUNT && pending > 0)
            .put("selectedOnly", true)
            .put("externalCollectionMayChangeSlots", false)
    }

    fun updateSelectedRecoveryFromCoverage(sessionId: String) {
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val byIdentity = linkedMapOf<String, JSONObject>()
        for (i in 0 until candidates.length()) {
            val row = candidates.optJSONObject(i) ?: continue
            byIdentity[row.optString("applicationIdentityKey")] = row
        }
        val scope = selectedSixRecoveryPlan(sessionId).optJSONArray("entries") ?: JSONArray()
        val db = writableDatabase
        for (i in 0 until scope.length()) {
            val row = scope.optJSONObject(i) ?: continue
            val identity = row.optString("applicationIdentityKey")
            val candidate = byIdentity[identity]
            val missing = candidate?.optJSONObject("coverage")?.optJSONArray("missing") ?: JSONArray()
            val state = if (candidate == null) "stale" else if (missing.length() == 0) "complete" else "pending"
            val cv = ContentValues().apply {
                put("missing_lanes_json", missing.toString())
                put("state", state)
                put("updated_at", Instant.now().toString())
            }
            db.update("hub_selected_recovery_scope", cv, "session_id=? AND application_identity_key=?", arrayOf(sessionId, identity))
        }
    }

    fun finishSelectedSixRecoveryScope(sessionId: String, terminalState: String) {
        if (sessionId.isBlank()) return
        val cv = ContentValues().apply {
            put("state", terminalState.take(40))
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.update("hub_selected_recovery_scope", cv, "session_id=? AND state IN ('pending','running')", arrayOf(sessionId))
    }

'''
store = replace_once(store, rebuild_anchor, recovery_methods + rebuild_anchor, 'selected recovery methods')

# Add official table evidence indexing to canonical rebuild.
match_decl = '''        val matches = linkedMapOf<String, LinkedHashMap<String, JSONObject>>()
        val exactFingerprints = linkedMapOf<String, MutableSet<String>>()
'''
match_decl_new = '''        val matches = linkedMapOf<String, LinkedHashMap<String, JSONObject>>()
        val exactFingerprints = linkedMapOf<String, MutableSet<String>>()
        val officialAdmissionEvidence = linkedMapOf<String, MutableList<JSONObject>>()
'''
store = replace_once(store, match_decl, match_decl_new, 'official evidence map')

before_db = '''        val db = writableDatabase
        db.beginTransaction()
'''
official_scan = r'''        if (!adigaRunId.isNullOrBlank() && apps.isNotEmpty()) {
            readableDatabase.rawQuery(
                "SELECT COALESCE(year,-1),university,record_type,json FROM records WHERE run_id=? AND record_type IN ('current-admission-criteria-table','historical-admission-result-table') AND university IS NOT NULL",
                arrayOf(adigaRunId)
            ).use { c ->
                while (c.moveToNext()) {
                    val recordYear = c.getInt(0)
                    val university = if (c.isNull(1)) null else c.getString(1)
                    val recordType = c.getString(2)
                    val candidates = byUniversity[CanonicalSixApplicationGraph.normalizeUniversityKey(university)].orEmpty()
                    if (candidates.isEmpty()) continue
                    val record = runCatching { JSONObject(c.getString(3)) }.getOrNull() ?: continue
                    for (app in candidates) {
                        val evidence = AdigaOfficialAdmissionEvidence.inspect(
                            recordType,
                            recordYear,
                            record,
                            AdigaOfficialAdmissionEvidence.AppRef(app.year, app.university, app.department, app.admission, app.admissionCategory)
                        )
                        if (evidence.isNotEmpty()) officialAdmissionEvidence.getOrPut(app.identityKey) { mutableListOf() }.addAll(evidence)
                    }
                }
            }
        }

'''
# Replace only the db transaction immediately after matching loops by anchoring on exact occurrence after rebuild start.
rebuild_pos = store.index('    fun rebuildCanonicalApplicationGraph(sessionId: String): JSONObject {')
db_pos = store.index(before_db, rebuild_pos)
if db_pos < 0:
    raise SystemExit('canonical rebuild db transaction anchor not found')
store = store[:db_pos] + official_scan + store[db_pos:]

# Upgrade binding quality using same-row official current evidence only; preserve weaker evidence without inference.
binding_old = '''                val acceptedSignatures = matchRows.count { it.optString("matchClass") == "accepted" }
                val provisionalSignatures = matchRows.count { it.optString("matchClass") == "provisional" }
                val bindingQuality = when {
                    acceptedSignatures == 1 -> "accepted"
                    acceptedSignatures > 1 -> "provisional"
                    provisionalSignatures > 0 -> "provisional"
                    else -> "provider-only"
                }
'''
binding_new = '''                val acceptedSignatures = matchRows.count { it.optString("matchClass") == "accepted" }
                val provisionalSignatures = matchRows.count { it.optString("matchClass") == "provisional" }
                val officialEvidenceRows = officialAdmissionEvidence[app.identityKey].orEmpty()
                val rowBoundCurrent = officialEvidenceRows.count { it.optString("scope") == "row-bound-current" }
                val rowBoundRelated = officialEvidenceRows.count { it.optString("scope") == "row-bound-current-related" }
                val currentUniversityEvidence = officialEvidenceRows.count { it.optString("scope") == "university-current" }
                val bindingQuality = when {
                    acceptedSignatures == 1 -> "accepted"
                    acceptedSignatures > 1 -> "provisional"
                    rowBoundCurrent == 1 -> "accepted"
                    rowBoundCurrent > 1 -> "provisional"
                    provisionalSignatures > 0 || rowBoundRelated > 0 || currentUniversityEvidence > 0 -> "provisional"
                    else -> "provider-only"
                }
'''
store = replace_once(store, binding_old, binding_new, 'binding quality evidence')

binding_json_old = '''                    .put("provisionalSignatures", provisionalSignatures)
                    .put("matches", JSONArray(matchRows))
                    .put("doNotInferMissingBindings", true)
'''
binding_json_new = '''                    .put("provisionalSignatures", provisionalSignatures)
                    .put("officialRowBoundCurrent", rowBoundCurrent)
                    .put("officialRowBoundRelated", rowBoundRelated)
                    .put("officialUniversityCurrent", currentUniversityEvidence)
                    .put("officialAdmissionEvidence", JSONArray(officialEvidenceRows.take(24)))
                    .put("matches", JSONArray(matchRows))
                    .put("sameRowRequiredForOfficialAccepted", true)
                    .put("doNotInferMissingBindings", true)
'''
store = replace_once(store, binding_json_old, binding_json_new, 'binding json official evidence')

# Quality audit shows candidate-level repair requirement even before six slots are selected.
quality_anchor = '''        val warnings = JSONArray()
        if (selectedProvisional > 0) warnings.put("selected-provisional-adiga-binding")
'''
quality_new = '''        val repairNeededCandidates = (candidates.length() - fullCoverage).coerceAtLeast(0)
        val warnings = JSONArray()
        if (repairNeededCandidates > 0) warnings.put("candidate-core-coverage-incomplete")
        if (selectedProvisional > 0) warnings.put("selected-provisional-adiga-binding")
'''
store = replace_once(store, quality_anchor, quality_new, 'quality repair warnings')
store = replace_once(
    store,
    '''            .put("fullCoreCoverageCandidates", fullCoverage)
            .put("candidateQuality", JSONObject()
''',
    '''            .put("fullCoreCoverageCandidates", fullCoverage)
            .put("repairNeededCandidates", repairNeededCandidates)
            .put("candidateQuality", JSONObject()
''',
    'quality repair count'
)

# Include recovery plan in Hub summary.
store = replace_once(
    store,
    '''            .put("qualityAudit", audit)
            .put("slotPolicy", JSONObject()
''',
    '''            .put("qualityAudit", audit)
            .put("selectedRecoveryPlan", selectedSixRecoveryPlan(sessionId))
            .put("slotPolicy", JSONObject()
''',
    'hub summary recovery plan'
)

# ---------------------------------------------------------------------------
# MainActivity: selected-six recovery mode + visible repair status.
# ---------------------------------------------------------------------------
main = replace_once(
    main,
    '''    private lateinit var hubManageButton: Button
''',
    '''    private lateinit var hubManageButton: Button
    private lateinit var hubRecoveryButton: Button
''',
    'hub recovery button field'
)
main = replace_once(
    main,
    '''    private var jinhakTerminalSealed = false
''',
    '''    private var jinhakTerminalSealed = false
    private var selectedSixRecoveryMode = false
    private val selectedSixRecoveryIdentityKeys = linkedSetOf<String>()
    private var selectedSixRecoverySessionId: String? = null
''',
    'selected recovery state'
)

# Add recovery button to hub row.
main = replace_once(
    main,
    '''        hubManageButton = Button(this).apply {
            text = "지원 6장 관리"
            setOnClickListener { showHubSixManager() }
        }
        hubRow.addView(hubState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        hubRow.addView(hubManageButton)
''',
    '''        hubManageButton = Button(this).apply {
            text = "지원 6장 관리"
            setOnClickListener { showHubSixManager() }
        }
        hubRecoveryButton = Button(this).apply {
            text = "선택 6장 보강"
            setOnClickListener { startSelectedSixRecovery() }
        }
        hubRow.addView(hubState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        hubRow.addView(hubManageButton)
        hubRow.addView(hubRecoveryButton)
''',
    'hub recovery button ui'
)

# Richer Hub state text.
refresh_old = '''        val selected = slots.optInt("selected", 0)
        val candidates = audit.optInt("candidateCount", 0)
        val publish = audit.optString("publishState", "WAITING_FOR_USER_SELECTION")
'''
refresh_new = '''        val selected = slots.optInt("selected", 0)
        val candidates = audit.optInt("candidateCount", 0)
        val completeCandidates = audit.optInt("fullCoreCoverageCandidates", 0)
        val repairCandidates = audit.optInt("repairNeededCandidates", (candidates - completeCandidates).coerceAtLeast(0))
        val selectedComplete = slots.optInt("fullCoreCoverage", 0)
        val publish = audit.optString("publishState", "WAITING_FOR_USER_SELECTION")
'''
main = replace_once(main, refresh_old, refresh_new, 'hub refresh counts')
main = replace_once(
    main,
    '''        hubState.text = "지원 6장 $selected/6 · 후보 $candidates · $readyText"
''',
    '''        hubState.text = "지원 6장 $selected/6 · 후보 $candidates · 완전 $completeCandidates · 보강 $repairCandidates · $readyText"
        if (::hubRecoveryButton.isInitialized) {
            hubRecoveryButton.isEnabled = selected == 6 && selectedComplete < 6 && !unifiedRunning && !batchRunning
            hubRecoveryButton.text = if (selected == 6 && selectedComplete < 6) "선택 6장 보강 (${6 - selectedComplete})" else "선택 6장 보강"
        }
''',
    'hub refresh text'
)

# Insert selected recovery functions before showHubSixManager.
manager_anchor = '''    private fun showHubSixManager() {'''
selected_functions = r'''    private fun restoreSelectedSixRecoveryScope(sessionId: String): Boolean {
        val plan = localStore.selectedSixRecoveryPlan(sessionId)
        if (!plan.optBoolean("active", false)) return false
        selectedSixRecoveryIdentityKeys.clear()
        val identities = plan.optJSONArray("identities") ?: JSONArray()
        for (i in 0 until identities.length()) identities.optString(i).takeIf { it.isNotBlank() }?.let(selectedSixRecoveryIdentityKeys::add)
        selectedSixRecoveryMode = selectedSixRecoveryIdentityKeys.size == 6
        selectedSixRecoverySessionId = if (selectedSixRecoveryMode) sessionId else null
        return selectedSixRecoveryMode
    }

    private fun startSelectedSixRecovery() {
        if (startupLoginPreflightActive || unifiedRunning || batchRunning) {
            Toast.makeText(this, "현재 로그인/수집 작업이 끝난 뒤 보강을 시작해주세요.", Toast.LENGTH_LONG).show()
            return
        }
        val sessionId = localStore.latestUnifiedSession()
        if (sessionId.isNullOrBlank()) {
            Toast.makeText(this, "보강할 통합 수집 세션이 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        localStore.rebuildCanonicalApplicationGraph(sessionId)
        val plan = localStore.prepareSelectedSixRecovery(sessionId)
        if (plan.optInt("scopedIdentities", 0) != 6) {
            Toast.makeText(this, "먼저 '지원 6장 관리'에서 정확히 6개 지원안을 선택해주세요.", Toast.LENGTH_LONG).show()
            refreshHubState(sessionId, localStore.canonicalHubSummary(sessionId))
            return
        }
        if (plan.optInt("pendingIdentities", 0) == 0) {
            Toast.makeText(this, "선택한 6장은 핵심 coverage가 모두 완료되어 보강이 필요하지 않습니다.", Toast.LENGTH_LONG).show()
            refreshHubState(sessionId, localStore.canonicalHubSummary(sessionId))
            return
        }
        selectedSixRecoveryIdentityKeys.clear()
        val identities = plan.optJSONArray("identities") ?: JSONArray()
        for (i in 0 until identities.length()) identities.optString(i).takeIf { it.isNotBlank() }?.let(selectedSixRecoveryIdentityKeys::add)
        selectedSixRecoveryMode = selectedSixRecoveryIdentityKeys.size == 6
        selectedSixRecoverySessionId = sessionId
        if (!selectedSixRecoveryMode) {
            Toast.makeText(this, "선택 6장 recovery scope를 만들지 못했습니다.", Toast.LENGTH_LONG).show()
            return
        }

        localStore.adoptUnifiedSessionCollectorVersion(sessionId, VERSION)
        unifiedSessionId = sessionId
        unifiedRunning = true
        unifiedPhase = "jinhak"
        provider = ProviderId.JINHAK
        localRunId = localStore.providerRunIdForUnifiedSession(sessionId, ProviderId.JINHAK.wireName)
        unifiedPendingAdigaStart = false
        unifiedPendingJinhakStart = false
        unifiedJinhakAutoCapture = false
        jinhakTransitionAuthGateActive = true
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "selected-six-recovery-auth-gate"
        jinhakIncompleteCoverageRecoveryAttempts.clear()
        restoreJinhakMissionPersistence(sessionId, "selected-six-recovery-start")
        localStore.updateUnifiedSession(sessionId, "jinhak", "running", "selected-six-recovery")
        localStore.recordSyncState(
            sessionId,
            UnifiedSyncState.JINHAK_USER_SESSION_MISSION.name,
            ProviderId.JINHAK.wireName,
            JSONObject()
                .put("mode", "selected-six-recovery")
                .put("selectedIdentities", selectedSixRecoveryIdentityKeys.size)
                .put("pendingIdentities", plan.optInt("pendingIdentities", 0))
                .put("selectedOnly", true),
            false
        )
        activateProcessResumeJournal("selected-six-recovery")
        unifiedButton.text = "선택 6장 보강 종료"
        hubRecoveryButton.isEnabled = false
        status.text = "선택한 6장 중 누락된 report lane만 보강하기 위해 진학사 보호경로 인증을 확인합니다."
        val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
        if (coreProbe.isBlank()) {
            unifiedRunning = false
            selectedSixRecoveryMode = false
            Toast.makeText(this, "진학사 보호경로를 확인할 수 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        webView.loadUrl(coreProbe)
    }

'''
main = replace_once(main, manager_anchor, selected_functions + manager_anchor, 'selected recovery functions')

# Filter expected identities only while selected recovery mode is active.
expected_old = '''    private fun currentExpectedJinhakMissionIdentities(): Set<String> = when {
        jinhakNormalizedIdentitySeedKeys.isNotEmpty() -> jinhakNormalizedIdentitySeedKeys.toSet()
        jinhakMissionCoverage.isNotEmpty() -> jinhakMissionCoverage.keys.toSet()
        else -> emptySet()
    }
'''
expected_new = '''    private fun currentExpectedJinhakMissionIdentities(): Set<String> = when {
        selectedSixRecoveryMode && selectedSixRecoveryIdentityKeys.isNotEmpty() -> selectedSixRecoveryIdentityKeys.toSet()
        jinhakNormalizedIdentitySeedKeys.isNotEmpty() -> jinhakNormalizedIdentitySeedKeys.toSet()
        jinhakMissionCoverage.isNotEmpty() -> jinhakMissionCoverage.keys.toSet()
        else -> emptySet()
    }
'''
main = replace_once(main, expected_old, expected_new, 'selected expected identities')

# Selected recovery does not need six fresh mission returns; complete selected applications need not be revisited.
main = main.replace('''        if (jinhakApplicationMissionReturns < expected.size) return false

        jinhakCoreCoverageClosurePending = true
        jinhakIncompleteCoverageFinishes += 1
''', '''        if (!selectedSixRecoveryMode && jinhakApplicationMissionReturns < expected.size) return false

        jinhakCoreCoverageClosurePending = true
        jinhakIncompleteCoverageFinishes += 1
''', 1)
main = main.replace('''        if (jinhakApplicationMissionReturns < expected.size) return

        jinhakCoreCoverageClosurePending = true
        jinhakCoreCoverageClosureFences += 1
''', '''        if (!selectedSixRecoveryMode && jinhakApplicationMissionReturns < expected.size) return

        jinhakCoreCoverageClosurePending = true
        jinhakCoreCoverageClosureFences += 1
''', 1)

# Reuse the existing attached Jinhak run during selected recovery; do not replace the session's full record history.
start_batch_old = '''        if (provider == ProviderId.JINHAK) {
            localRunId = localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
            unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->
'''
start_batch_new = '''        if (provider == ProviderId.JINHAK) {
            localRunId = if (selectedSixRecoveryMode) {
                unifiedSessionId?.let { localStore.providerRunIdForUnifiedSession(it, ProviderId.JINHAK.wireName) }
                    ?: localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
            } else {
                localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
            }
            unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->
'''
main = replace_once(main, start_batch_old, start_batch_new, 'reuse jinhak run')

# Restore selected recovery scope after process death before Jinhak resume.
resume_anchor = '''            val restoredMissionTargets = restoreJinhakMissionPersistence(sessionId, "activity-resume")
'''
main = replace_once(main, resume_anchor, '''            restoreSelectedSixRecoveryScope(sessionId)
            val restoredMissionTargets = restoreJinhakMissionPersistence(sessionId, "activity-resume")
''', 'restore selected scope')

# At unified finish, rebuild coverage/official binding then terminalize selected recovery scope.
finish_anchor = '''            val canonicalSummary = localStore.rebuildCanonicalApplicationGraph(sessionId)
            val qualityAudit = canonicalSummary.optJSONObject("qualityAudit") ?: JSONObject()
'''
finish_new = '''            val canonicalSummary = localStore.rebuildCanonicalApplicationGraph(sessionId)
            if (selectedSixRecoveryMode || selectedSixRecoverySessionId == sessionId) {
                localStore.updateSelectedRecoveryFromCoverage(sessionId)
            }
            val qualityAudit = canonicalSummary.optJSONObject("qualityAudit") ?: JSONObject()
'''
main = replace_once(main, finish_anchor, finish_new, 'finish recovery update')

# Clear runtime mode only after Hub audit was generated; persist terminal scope state.
finish_status_anchor = '''            status.text = if (hubAudit.optBoolean("hubReady", false)) {
                "통합 수집 + canonical merge + quality audit 완료 · 지원 6장 Hub 준비 완료."
            } else {
                "통합 수집 + canonical merge 완료 · 지원 6장 $selected/6 선택 후 Hub 게시가 완료됩니다."
            }
'''
finish_status_new = '''            val recoveryWasActive = selectedSixRecoveryMode || selectedSixRecoverySessionId == sessionId
            if (recoveryWasActive) {
                val selectedFull = hubAudit.optJSONObject("sixSlots")?.optInt("fullCoreCoverage", 0) ?: 0
                localStore.finishSelectedSixRecoveryScope(sessionId, if (selectedFull == 6) "complete" else "incomplete")
                selectedSixRecoveryMode = false
                selectedSixRecoveryIdentityKeys.clear()
                selectedSixRecoverySessionId = null
            }
            status.text = if (hubAudit.optBoolean("hubReady", false)) {
                "통합 수집 + canonical merge + quality audit 완료 · 지원 6장 Hub 준비 완료."
            } else if (recoveryWasActive) {
                "선택 6장 보강 종료 · 남은 누락과 공식 결합 상태를 Hub 품질 점검에서 확인하세요."
            } else {
                "통합 수집 + canonical merge 완료 · 지원 6장 $selected/6 선택 후 Hub 게시가 완료됩니다."
            }
'''
main = replace_once(main, finish_status_anchor, finish_status_new, 'finish selected recovery cleanup')

# Diagnostics expose selected recovery scope.
diag_anchor = '''                .put("terminalSealed", jinhakTerminalSealed)
'''
if diag_anchor in main:
    main = main.replace(diag_anchor, '''                .put("terminalSealed", jinhakTerminalSealed)
                .put("selectedSixRecoveryMode", selectedSixRecoveryMode)
                .put("selectedSixRecoveryIdentities", selectedSixRecoveryIdentityKeys.size)
''', 1)

MAIN.write_text(main)
STORE.write_text(store)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

checks = {
    'version': 'private const val VERSION = "0.10.1"' in main and 'versionName = "0.10.1"' in gradle,
    'build': 'private const val BUILD_CODE = 110010' in main and 'versionCode = 110010' in gradle,
    'recovery-ui': '선택 6장 보강' in main and 'startSelectedSixRecovery' in main,
    'recovery-scope': 'hub_selected_recovery_scope' in store and 'prepareSelectedSixRecovery' in store,
    'selected-filter': 'selectedSixRecoveryMode && selectedSixRecoveryIdentityKeys.isNotEmpty()' in main,
    'official-evidence': EVIDENCE.exists() and 'sameRowRequiredForOfficialAccepted' in store,
    'no-auto-six': 'externalCollectionAutoSelection' in main and 'externalCollectionMayChangeSlots' in store,
}
failed = [k for k,v in checks.items() if not v]
if failed:
    raise SystemExit('v0.10.1 postcondition failure: ' + ', '.join(failed))
print('v0.10.1 selected six recovery + official admission binding patch applied')
