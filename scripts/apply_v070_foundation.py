from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

m = MAIN.read_text()

# Version and imports.
m = m.replace('private const val VERSION = "0.6.7"', 'private const val VERSION = "0.7.0"', 1)
m = m.replace('private const val BUILD_CODE = 10670', 'private const val BUILD_CODE = 10700', 1)
import_anchor = 'import com.admissionhub.collector.local.LocalCollectorStore\n'
imports = '''import com.admissionhub.collector.local.LocalCollectorStore\nimport com.admissionhub.collector.observation.ObservationEvidence\nimport com.admissionhub.collector.jinhak.JinhakCapabilityProbe\nimport com.admissionhub.collector.provider.ProviderCapabilities\nimport com.admissionhub.collector.provider.ProviderCapability\nimport com.admissionhub.collector.sync.UnifiedSyncState\n'''
if import_anchor not in m:
    raise SystemExit('MainActivity import anchor missing')
m = m.replace(import_anchor, imports, 1)

# Rename the old "relevant" gate: this is now only a structured-type confidence hint,
# never a reason to discard an observation.
m = m.replace('private fun isJinhakAutoCaptureRelevant(pageType: String): Boolean = pageType in setOf(',
              'private fun isJinhakKnownStructuredPageType(pageType: String): Boolean = pageType in setOf(', 1)
m = m.replace('isJinhakAutoCaptureRelevant(snapshot.optString("providerPageType"))',
              'isJinhakKnownStructuredPageType(snapshot.optString("providerPageType"))')

# URL-only dedupe is invalid for viewpoint/time-dependent Jinhak screens.
m = m.replace('''        val pageKey = RecordUtils.sha256(canonical)\n        if (unifiedJinhakCapturedPages.contains(pageKey)) return\n''',
              '''        val pageKey = RecordUtils.sha256(canonical)\n''', 1)
m = m.replace('''                if (!unifiedJinhakCapturedPages.add(pageKey)) return@checkSessionState\n                collectCurrentPage(autoUnified = true)\n''',
              '''                collectCurrentPage(autoUnified = true)\n''', 1)

# Replace discard-on-unknown behavior with observation-first behavior.
old_gate = '''            val pageType = snapshot.optString("providerPageType")\n            if (provider == ProviderId.JINHAK && autoUnified && !isJinhakAutoCaptureRelevant(pageType)) {\n                recordRuntimeEvent("jinhak-nonadmission-page-skipped", JSONObject()\n                    .put("pageType", pageType.take(80))\n                    .put("safePath", runtimeSafePath(snapshot.optString("url"))))\n                status.text = "진학사 자동 분석 제외: 입시 데이터 화면이 아닌 ${pageType.ifBlank { "unclassified" }} 페이지입니다. 원하는 리포트/대학정보 화면을 여세요."\n                return@collectSnapshot\n            }\n            val records = normalizeSnapshot(snapshot)\n'''
new_gate = '''            val pageType = snapshot.optString("providerPageType")\n            val knownStructuredType = provider != ProviderId.JINHAK || isJinhakKnownStructuredPageType(pageType)\n            if (provider == ProviderId.JINHAK && autoUnified && !knownStructuredType) {\n                recordRuntimeEvent("jinhak-unclassified-observation-preserved", JSONObject()\n                    .put("pageType", pageType.take(80))\n                    .put("safePath", runtimeSafePath(snapshot.optString("url"))))\n            }\n            val records = normalizeSnapshot(snapshot)\n'''
if old_gate not in m:
    raise SystemExit('Jinhak discard gate anchor missing')
m = m.replace(old_gate, new_gate, 1)

# Insert Observation Store persistence immediately after the sanitized Jinhak digest is built.
obs_anchor = '''                lastJinhakDigest = buildJinhakDigest(snapshot, records, runId, collectedAt)\n                if (unifiedRunning && unifiedPhase == "jinhak") {\n'''
obs_new = '''                lastJinhakDigest = buildJinhakDigest(snapshot, records, runId, collectedAt)\n                val safeRouteKey = runtimeSafePath(snapshot.optString("url"))\n                val explicitContext = ObservationEvidence.explicitContextFromDigest(lastJinhakDigest)\n                val sessionObj = snapshot.optJSONObject("session") ?: JSONObject()\n                val authStateClass = when {\n                    sessionObj.optBoolean("needsLogin", false) -> "auth-required"\n                    sessionObj.optBoolean("authenticated", false) -> "authenticated"\n                    else -> "unknown"\n                }\n                val observationId = localStore.storeObservationEvidence(\n                    sessionId = unifiedSessionId,\n                    runId = runId,\n                    provider = ProviderId.JINHAK.wireName,\n                    safeRouteKey = safeRouteKey,\n                    pageTypeGuess = pageType,\n                    pageTypeConfidence = if (knownStructuredType) 0.95 else 0.45,\n                    authStateClass = authStateClass,\n                    explicitContext = explicitContext,\n                    evidence = lastJinhakDigest,\n                    captureVersion = VERSION\n                )\n                lastJinhakDigest.put("observationId", observationId)\n                probeJinhakOfficialCapabilities(unifiedSessionId, pageType, safeRouteKey)\n                if (unifiedRunning && unifiedPhase == "jinhak") {\n'''
if obs_anchor not in m:
    raise SystemExit('Jinhak digest persistence anchor missing')
m = m.replace(obs_anchor, obs_new, 1)

# Avoid wording that implies unknown observations are worthless.
m = m.replace('''            .put("analysisRelevance", if (isJinhakKnownStructuredPageType(snapshot.optString("providerPageType"))) "admission-relevant" else "reference-or-editorial")''',
              '''            .put("analysisRelevance", if (isJinhakKnownStructuredPageType(snapshot.optString("providerPageType"))) "known-structured-type" else "unclassified-potential-value")''', 1)

# Add the safe official-output capability probe. This never receives href/action/form values.
probe_marker = '    private fun sanitizeJinhakAnalysisText(value: String, maxLen: Int): String {\n'
probe_func = r'''    private fun probeJinhakOfficialCapabilities(sessionId: String?, pageType: String, safeRouteKey: String) {
        if (provider != ProviderId.JINHAK || !::webView.isInitialized) return
        webView.evaluateJavascript(JinhakCapabilityProbe.javascript()) { encoded ->
            val raw = runCatching { decodeJsString(encoded) }.getOrNull() ?: return@evaluateJavascript
            val snapshot = runCatching { JinhakCapabilityProbe.parse(raw) }.getOrNull() ?: return@evaluateJavascript
            if (snapshot.capabilities.isEmpty()) return@evaluateJavascript

            val grouped = snapshot.capabilities.groupBy { capability ->
                when (capability.kind) {
                    "structured-export" -> ProviderCapability.AUTHORIZED_EXPORT_IMPORT.name
                    "report-output", "download", "email-report" -> ProviderCapability.AUTHORIZED_REPORT_IMPORT.name
                    else -> "VISIBLE_OFFICIAL_OUTPUT"
                }
            }
            for ((capability, items) in grouped) {
                val evidence = JSONArray()
                items.forEach { item ->
                    evidence.put(JSONObject()
                        .put("kind", item.kind)
                        .put("label", item.label)
                        .put("evidenceClass", item.evidenceClass))
                }
                localStore.storeProviderCapabilityEvidence(
                    sessionId = sessionId,
                    provider = ProviderId.JINHAK.wireName,
                    capability = capability,
                    status = "candidate-visible-official-ui",
                    safeRouteKey = safeRouteKey,
                    evidence = JSONObject()
                        .put("pageType", pageType)
                        .put("controls", evidence)
                )
            }
            recordRuntimeEvent("jinhak-official-output-capability-observed", JSONObject()
                .put("pageType", pageType.take(80))
                .put("safePath", safeRouteKey.take(300))
                .put("controls", snapshot.capabilities.size)
                .put("structuredExportSignal", snapshot.hasStructuredExportSignal)
                .put("reportOutputSignal", snapshot.hasReportOutputSignal))
        }
    }

'''
if probe_marker not in m:
    raise SystemExit('probe insertion marker missing')
m = m.replace(probe_marker, probe_func + probe_marker, 1)

# Record architecture-level sync states without pretending unavailable stages have completed.
start_state_anchor = '''        localStore.updateUnifiedSession(sessionId, "adiga", "running", "user-start")\n        persistRuntimeCheckpoint(forceResume = true)\n'''
start_state_new = '''        localStore.updateUnifiedSession(sessionId, "adiga", "running", "user-start")\n        localStore.recordSyncState(sessionId, UnifiedSyncState.PRECHECK.name, null, JSONObject().put("collectorVersion", VERSION), false)\n        localStore.recordSyncState(sessionId, UnifiedSyncState.ADIGA_PUBLIC_SYNC.name, ProviderId.ADIGA.wireName, JSONObject().put("mode", "legacy-local-first-until-deterministic-planner-activation"), false)\n        persistRuntimeCheckpoint(forceResume = true)\n'''
if start_state_anchor not in m:
    raise SystemExit('start sync state anchor missing')
m = m.replace(start_state_anchor, start_state_new, 1)

jinhak_state_anchor = '''        localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$adigaReason")\n        persistRuntimeCheckpoint(forceResume = true)\n'''
jinhak_state_new = '''        localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$adigaReason")\n        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY.name, ProviderId.JINHAK.wireName, JSONObject().put("authorizedConnectorActive", false), false)\n        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK.name, ProviderId.JINHAK.wireName, JSONObject().put("observationFirst", true), false)\n        persistRuntimeCheckpoint(forceResume = true)\n'''
if jinhak_state_anchor not in m:
    raise SystemExit('Jinhak sync state anchor missing')
m = m.replace(jinhak_state_anchor, jinhak_state_new, 1)

# Make capability architecture visible in provider status without changing user workflow.
open_status_old = '''        status.text = if (which == ProviderId.JINHAK) "진학사 분석 모드: 로그인 후 원하는 리포트/대학 화면을 여세요." else "어디가 복구 보류: 진학사 분석 이후 한밭대 381쪽부터 재시도 예정"\n'''
open_status_new = '''        val capabilities = ProviderCapabilities.profile(which)\n        status.text = if (which == ProviderId.JINHAK) {\n            "진학사 observation-first 모드 · 공식 export/report capability 자동 탐지 · 현재 화면은 분류 여부와 무관하게 증거 보존"\n        } else {\n            "어디가 공식정보 모드 · deterministic ID/year planner 기반 전환 준비 · 기존 체크포인트 보존"\n        }\n'''
if open_status_old not in m:
    raise SystemExit('openProvider status anchor missing')
m = m.replace(open_status_old, open_status_new, 1)

MAIN.write_text(m)

# ---------------------------------------------------------------------------
# SQLite v4 foundation schema.
# ---------------------------------------------------------------------------
s = STORE.read_text()
s = s.replace('import com.admissionhub.collector.parser.RecordUtils\n',
              'import com.admissionhub.collector.parser.RecordUtils\nimport com.admissionhub.collector.observation.ObservationEvidence\nimport com.admissionhub.collector.adiga.AdigaPlanTask\nimport com.admissionhub.collector.canonical.CanonicalEntity\nimport com.admissionhub.collector.canonical.ProviderEntityMapping\n', 1)
s = s.replace('''    3\n) {\n''', '''    4\n) {\n''', 1)

# Add common schema helper before onCreate.
oncreate_marker = '    override fun onCreate(db: SQLiteDatabase) {\n'
foundation_helper = r'''    private fun ensureFoundationSchema(db: SQLiteDatabase) {
        // Content-aware captures: same route can expose different data at another time/context.
        runCatching { db.execSQL("ALTER TABLE unified_analysis_captures ADD COLUMN content_fingerprint TEXT") }
        runCatching { db.execSQL("ALTER TABLE unified_analysis_captures ADD COLUMN context_fingerprint TEXT") }
        runCatching { db.execSQL("ALTER TABLE unified_sessions ADD COLUMN orchestrator_state TEXT") }
        runCatching { db.execSQL("ALTER TABLE unified_sessions ADD COLUMN requires_user_action INTEGER NOT NULL DEFAULT 0") }
        db.execSQL("DROP INDEX IF EXISTS idx_unified_capture_page")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_unified_capture_route ON unified_analysis_captures(session_id,provider,page_key)")
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_capture_identity ON unified_analysis_captures(session_id,provider,page_key,context_fingerprint,content_fingerprint)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS observations(
              observation_id TEXT PRIMARY KEY,
              session_id TEXT,
              run_id TEXT,
              provider TEXT NOT NULL,
              safe_route_key TEXT NOT NULL,
              page_type_guess TEXT,
              page_type_confidence REAL NOT NULL DEFAULT 0,
              auth_state_class TEXT,
              explicit_context_json TEXT NOT NULL,
              context_fingerprint TEXT NOT NULL,
              content_fingerprint TEXT NOT NULL,
              capture_version TEXT NOT NULL,
              evidence_json TEXT NOT NULL,
              reprocess_state TEXT NOT NULL DEFAULT 'pending',
              first_observed_at TEXT NOT NULL,
              last_observed_at TEXT NOT NULL,
              seen_count INTEGER NOT NULL DEFAULT 1,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_observations_session_provider ON observations(session_id,provider,last_observed_at)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_observations_route ON observations(provider,safe_route_key)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_observations_reprocess ON observations(provider,reprocess_state,last_observed_at)")
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_content_identity ON observations(provider,safe_route_key,context_fingerprint,content_fingerprint)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS provider_capability_evidence(
              evidence_id TEXT PRIMARY KEY,
              session_id TEXT,
              provider TEXT NOT NULL,
              capability TEXT NOT NULL,
              status TEXT NOT NULL,
              safe_route_key TEXT NOT NULL,
              evidence_json TEXT NOT NULL,
              observed_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_provider_capability ON provider_capability_evidence(provider,capability,observed_at)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS sync_state_events(
              event_id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              state TEXT NOT NULL,
              provider TEXT,
              requires_user_action INTEGER NOT NULL DEFAULT 0,
              detail_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_sync_state_session ON sync_state_events(session_id,created_at)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS canonical_entities(
              canonical_id TEXT PRIMARY KEY,
              entity_type TEXT NOT NULL,
              academic_year INTEGER,
              canonical_name TEXT NOT NULL,
              parent_canonical_id TEXT,
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_canonical_entity_type_year ON canonical_entities(entity_type,academic_year,canonical_name)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS provider_entity_mappings(
              provider TEXT NOT NULL,
              provider_entity_type TEXT NOT NULL,
              provider_entity_id TEXT NOT NULL,
              academic_year INTEGER NOT NULL DEFAULT -1,
              canonical_entity_id TEXT NOT NULL,
              raw_label TEXT,
              confidence REAL NOT NULL DEFAULT 0,
              evidence_observation_id TEXT,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(provider,provider_entity_type,provider_entity_id,academic_year)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_provider_mapping_canonical ON provider_entity_mappings(canonical_entity_id,provider)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS adiga_plan_tasks(
              task_id TEXT PRIMARY KEY,
              session_id TEXT,
              academic_year INTEGER NOT NULL,
              university_code TEXT NOT NULL,
              task_type TEXT NOT NULL,
              safe_url TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'planned',
              retry_count INTEGER NOT NULL DEFAULT 0,
              error_type TEXT,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_adiga_plan_identity ON adiga_plan_tasks(academic_year,university_code,task_type)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_adiga_plan_state ON adiga_plan_tasks(state,updated_at)")
    }

'''
if oncreate_marker not in s:
    raise SystemExit('LocalStore onCreate marker missing')
s = s.replace(oncreate_marker, foundation_helper + oncreate_marker, 1)

# Ensure v4 schema on fresh databases.
oncreate_end_anchor = '        db.execSQL("CREATE UNIQUE INDEX idx_unified_capture_page ON unified_analysis_captures(session_id,provider,page_key)")\n    }\n\n    override fun onUpgrade'
if oncreate_end_anchor not in s:
    raise SystemExit('LocalStore onCreate end anchor missing')
s = s.replace(oncreate_end_anchor,
              '        db.execSQL("CREATE UNIQUE INDEX idx_unified_capture_page ON unified_analysis_captures(session_id,provider,page_key)")\n        ensureFoundationSchema(db)\n    }\n\n    override fun onUpgrade', 1)

# Add v4 migration.
upgrade_end_anchor = '''            db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_capture_page ON unified_analysis_captures(session_id,provider,page_key)")\n        }\n    }\n\n    fun beginOrResumeUnifiedSession'''
upgrade_end_new = '''            db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_capture_page ON unified_analysis_captures(session_id,provider,page_key)")\n        }\n        if (oldVersion < 4) {\n            ensureFoundationSchema(db)\n        }\n    }\n\n    fun beginOrResumeUnifiedSession'''
if upgrade_end_anchor not in s:
    raise SystemExit('LocalStore upgrade end anchor missing')
s = s.replace(upgrade_end_anchor, upgrade_end_new, 1)

# Replace route-only capture identity with context/content-aware identity.
old_store_capture = r'''    fun storeUnifiedAnalysisCapture(
        sessionId: String,
        provider: String,
        pageKey: String,
        pageType: String?,
        payload: JSONObject
    ) {
        if (sessionId.isBlank() || provider.isBlank() || pageKey.isBlank()) return
        val now = Instant.now().toString()
        val captureId = RecordUtils.sha256("$sessionId|$provider|$pageKey")
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            put("capture_id", captureId)
            put("provider", provider)
            put("page_key", pageKey)
            put("page_type", pageType)
            put("payload_json", payload.toString())
            put("captured_at", now)
        }
        writableDatabase.insertWithOnConflict(
            "unified_analysis_captures", null, cv, SQLiteDatabase.CONFLICT_REPLACE
        )
        writableDatabase.execSQL(
            "UPDATE unified_sessions SET updated_at=? WHERE session_id=?",
            arrayOf(now, sessionId)
        )
    }
'''
new_store_capture = r'''    fun storeUnifiedAnalysisCapture(
        sessionId: String,
        provider: String,
        pageKey: String,
        pageType: String?,
        payload: JSONObject
    ) {
        if (sessionId.isBlank() || provider.isBlank() || pageKey.isBlank()) return
        val now = Instant.now().toString()
        val context = ObservationEvidence.explicitContextFromDigest(payload)
        val identity = ObservationEvidence.identity(provider, pageKey, context, payload)
        val captureId = RecordUtils.sha256(
            "$sessionId|$provider|$pageKey|${identity.contextFingerprint}|${identity.contentFingerprint}"
        )
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            put("capture_id", captureId)
            put("provider", provider)
            put("page_key", pageKey)
            put("page_type", pageType)
            put("content_fingerprint", identity.contentFingerprint)
            put("context_fingerprint", identity.contextFingerprint)
            put("payload_json", payload.toString())
            put("captured_at", now)
        }
        writableDatabase.insertWithOnConflict(
            "unified_analysis_captures", null, cv, SQLiteDatabase.CONFLICT_REPLACE
        )
        writableDatabase.execSQL(
            "UPDATE unified_sessions SET updated_at=? WHERE session_id=?",
            arrayOf(now, sessionId)
        )
    }
'''
if old_store_capture not in s:
    raise SystemExit('storeUnifiedAnalysisCapture anchor missing')
s = s.replace(old_store_capture, new_store_capture, 1)

# Add foundation persistence APIs before unifiedStatus.
status_marker = '    fun unifiedStatus(sessionId: String): JSONObject {\n'
foundation_methods = r'''    fun storeObservationEvidence(
        sessionId: String?,
        runId: String?,
        provider: String,
        safeRouteKey: String,
        pageTypeGuess: String?,
        pageTypeConfidence: Double,
        authStateClass: String,
        explicitContext: JSONObject,
        evidence: JSONObject,
        captureVersion: String
    ): String {
        val route = safeRouteKey.ifBlank { "unknown" }.take(500)
        val identity = ObservationEvidence.identity(provider, route, explicitContext, evidence)
        val now = Instant.now().toString()
        val db = writableDatabase
        val exists = db.rawQuery(
            "SELECT observation_id,seen_count,first_observed_at FROM observations WHERE observation_id=? LIMIT 1",
            arrayOf(identity.observationId)
        ).use { c ->
            if (c.moveToFirst()) Triple(c.getString(0), c.getInt(1), c.getString(2)) else null
        }
        if (exists == null) {
            val cv = ContentValues().apply {
                put("observation_id", identity.observationId)
                putNullable("session_id", sessionId)
                putNullable("run_id", runId)
                put("provider", provider)
                put("safe_route_key", route)
                putNullable("page_type_guess", pageTypeGuess)
                put("page_type_confidence", pageTypeConfidence.coerceIn(0.0, 1.0))
                put("auth_state_class", authStateClass.take(80))
                put("explicit_context_json", explicitContext.toString())
                put("context_fingerprint", identity.contextFingerprint)
                put("content_fingerprint", identity.contentFingerprint)
                put("capture_version", captureVersion)
                put("evidence_json", evidence.toString())
                put("reprocess_state", "pending")
                put("first_observed_at", now)
                put("last_observed_at", now)
                put("seen_count", 1)
                put("updated_at", now)
            }
            db.insertOrThrow("observations", null, cv)
        } else {
            val cv = ContentValues().apply {
                putNullable("session_id", sessionId)
                putNullable("run_id", runId)
                putNullable("page_type_guess", pageTypeGuess)
                put("page_type_confidence", pageTypeConfidence.coerceIn(0.0, 1.0))
                put("auth_state_class", authStateClass.take(80))
                put("capture_version", captureVersion)
                put("evidence_json", evidence.toString())
                put("last_observed_at", now)
                put("seen_count", exists.second + 1)
                put("updated_at", now)
            }
            db.update("observations", cv, "observation_id=?", arrayOf(identity.observationId))
        }
        return identity.observationId
    }

    fun observationStats(sessionId: String?): JSONObject {
        val where = if (sessionId == null) "" else " WHERE session_id=?"
        val args = if (sessionId == null) emptyArray() else arrayOf(sessionId)
        fun scalar(sql: String): Int = readableDatabase.rawQuery(sql + where, args).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        return JSONObject()
            .put("observations", scalar("SELECT COUNT(*) FROM observations"))
            .put("unknownOrPotential", scalar("SELECT COUNT(*) FROM observations" + if (where.isBlank()) " WHERE page_type_guess IS NULL OR page_type_guess IN ('','jinhak-other')" else " WHERE session_id=? AND (page_type_guess IS NULL OR page_type_guess IN ('','jinhak-other'))"))
    }

    fun storeProviderCapabilityEvidence(
        sessionId: String?,
        provider: String,
        capability: String,
        status: String,
        safeRouteKey: String,
        evidence: JSONObject
    ) {
        val now = Instant.now().toString()
        val stable = "$provider|$capability|$status|$safeRouteKey|${evidence.toString()}"
        val id = RecordUtils.sha256(stable)
        val cv = ContentValues().apply {
            put("evidence_id", id)
            putNullable("session_id", sessionId)
            put("provider", provider)
            put("capability", capability)
            put("status", status)
            put("safe_route_key", safeRouteKey.take(500))
            put("evidence_json", evidence.toString())
            put("observed_at", now)
        }
        writableDatabase.insertWithOnConflict("provider_capability_evidence", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun recordSyncState(
        sessionId: String,
        state: String,
        provider: String?,
        detail: JSONObject,
        requiresUserAction: Boolean
    ) {
        val now = Instant.now().toString()
        val eventId = RecordUtils.sha256("$sessionId|$state|${provider ?: ""}|$now|${detail.toString()}")
        val cv = ContentValues().apply {
            put("event_id", eventId)
            put("session_id", sessionId)
            put("state", state)
            putNullable("provider", provider)
            put("requires_user_action", if (requiresUserAction) 1 else 0)
            put("detail_json", detail.toString())
            put("created_at", now)
        }
        writableDatabase.insertOrThrow("sync_state_events", null, cv)
        val session = ContentValues().apply {
            put("orchestrator_state", state)
            put("requires_user_action", if (requiresUserAction) 1 else 0)
            put("updated_at", now)
        }
        writableDatabase.update("unified_sessions", session, "session_id=?", arrayOf(sessionId))
    }

    fun storeAdigaPlanTasks(sessionId: String?, tasks: List<AdigaPlanTask>): Int {
        if (tasks.isEmpty()) return 0
        val db = writableDatabase
        var count = 0
        db.beginTransaction()
        try {
            for (task in tasks) {
                val cv = ContentValues().apply {
                    put("task_id", task.taskId)
                    putNullable("session_id", sessionId)
                    put("academic_year", task.academicYear)
                    put("university_code", task.universityCode)
                    put("task_type", task.taskType.name)
                    put("safe_url", task.url)
                    put("state", "planned")
                    put("retry_count", 0)
                    putNull("error_type")
                    put("updated_at", Instant.now().toString())
                }
                if (db.insertWithOnConflict("adiga_plan_tasks", null, cv, SQLiteDatabase.CONFLICT_IGNORE) != -1L) count += 1
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return count
    }

    fun upsertCanonicalEntity(entity: CanonicalEntity, metadata: JSONObject = JSONObject()) {
        val now = Instant.now().toString()
        val cv = ContentValues().apply {
            put("canonical_id", entity.canonicalId)
            put("entity_type", entity.entityType.name)
            if (entity.academicYear == null) putNull("academic_year") else put("academic_year", entity.academicYear)
            put("canonical_name", entity.canonicalName)
            putNullable("parent_canonical_id", entity.parentCanonicalId)
            put("metadata_json", metadata.toString())
            put("created_at", now)
            put("updated_at", now)
        }
        writableDatabase.insertWithOnConflict("canonical_entities", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun upsertProviderEntityMapping(mapping: ProviderEntityMapping) {
        val cv = ContentValues().apply {
            put("provider", mapping.provider)
            put("provider_entity_type", mapping.providerEntityType)
            put("provider_entity_id", mapping.providerEntityId)
            put("academic_year", mapping.academicYear ?: -1)
            put("canonical_entity_id", mapping.canonicalEntityId)
            putNullable("raw_label", mapping.rawLabel)
            put("confidence", mapping.confidence.coerceIn(0.0, 1.0))
            putNullable("evidence_observation_id", mapping.evidenceObservationId)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("provider_entity_mappings", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

'''
if status_marker not in s:
    raise SystemExit('unifiedStatus marker missing')
s = s.replace(status_marker, foundation_methods + status_marker, 1)

# Enrich unified status with architecture state + observation counts.
status_query_old = '"SELECT collector_version,status,phase,adiga_run_id,jinhak_run_id,completion_reason,started_at,updated_at FROM unified_sessions WHERE session_id=? LIMIT 1"'
status_query_new = '"SELECT collector_version,status,phase,adiga_run_id,jinhak_run_id,completion_reason,started_at,updated_at,orchestrator_state,requires_user_action FROM unified_sessions WHERE session_id=? LIMIT 1"'
if status_query_old not in s:
    raise SystemExit('unified status query anchor missing')
s = s.replace(status_query_old, status_query_new, 1)
status_fields_anchor = '''                    .put("updatedAt", c.getString(7))\n'''
status_fields_new = '''                    .put("updatedAt", c.getString(7))\n                    .put("orchestratorState", if (c.isNull(8)) JSONObject.NULL else c.getString(8))\n                    .put("requiresUserAction", !c.isNull(9) && c.getInt(9) != 0)\n'''
if status_fields_anchor not in s:
    raise SystemExit('unified status fields anchor missing')
s = s.replace(status_fields_anchor, status_fields_new, 1)
policy_anchor = '''            .put("predictionIsNotHistoricalActual", true))\n        return out\n'''
policy_new = '''            .put("predictionIsNotHistoricalActual", true))\n            .put("observationStore", observationStats(sessionId))\n        return out\n'''
if policy_anchor not in s:
    raise SystemExit('unified status policy anchor missing')
s = s.replace(policy_anchor, policy_new, 1)

# Stream Observation Evidence in unified export so future parsers can reprocess it offline.
write_analyses_end = '''            writer.write("]")\n        }\n\n        writer.write("{\\\"schemaVersion\\\":2,\\\"type\\\":\\\"admission-unified-two-provider-export\\\",\\\"session\\\":")\n'''
write_observations = r'''            writer.write("]")
        }
        fun writeObservations() {
            writer.write("[")
            var first = true
            readableDatabase.rawQuery(
                "SELECT observation_id,provider,safe_route_key,page_type_guess,page_type_confidence,auth_state_class,explicit_context_json,content_fingerprint,context_fingerprint,capture_version,evidence_json,reprocess_state,first_observed_at,last_observed_at,seen_count FROM observations WHERE session_id=? ORDER BY last_observed_at,observation_id",
                arrayOf(sessionId)
            ).use { c ->
                while (c.moveToNext()) {
                    if (!first) writer.write(",")
                    first = false
                    writer.write("{\"observationId\":")
                    writeNullableString(c.getString(0))
                    writer.write(",\"provider\":")
                    writeNullableString(c.getString(1))
                    writer.write(",\"safeRouteKey\":")
                    writeNullableString(c.getString(2))
                    writer.write(",\"pageTypeGuess\":")
                    writeNullableString(if (c.isNull(3)) null else c.getString(3))
                    writer.write(",\"pageTypeConfidence\":${c.getDouble(4)}")
                    writer.write(",\"authStateClass\":")
                    writeNullableString(if (c.isNull(5)) null else c.getString(5))
                    writer.write(",\"explicitContext\":${c.getString(6)}")
                    writer.write(",\"contentFingerprint\":")
                    writeNullableString(c.getString(7))
                    writer.write(",\"contextFingerprint\":")
                    writeNullableString(c.getString(8))
                    writer.write(",\"captureVersion\":")
                    writeNullableString(c.getString(9))
                    writer.write(",\"evidence\":${c.getString(10)}")
                    writer.write(",\"reprocessState\":")
                    writeNullableString(c.getString(11))
                    writer.write(",\"firstObservedAt\":")
                    writeNullableString(c.getString(12))
                    writer.write(",\"lastObservedAt\":")
                    writeNullableString(c.getString(13))
                    writer.write(",\"seenCount\":${c.getInt(14)}}")
                }
            }
            writer.write("]")
        }

        writer.write("{\"schemaVersion\":3,\"type\":\"admission-unified-two-provider-export\",\"session\":")
'''
if write_analyses_end not in s:
    raise SystemExit('writeUnifiedExport insertion anchor missing')
s = s.replace(write_analyses_end, write_observations, 1)
export_tail_old = '''        writer.write("}}}")\n        writer.flush()\n'''
export_tail_new = '''        writer.write("}},\\\"observationEvidence\\\":")\n        writeObservations()\n        writer.write("}")\n        writer.flush()\n'''
if export_tail_old not in s:
    raise SystemExit('writeUnifiedExport tail anchor missing')
s = s.replace(export_tail_old, export_tail_new, 1)

STORE.write_text(s)

# App metadata.
g = GRADLE.read_text()
g = g.replace('versionCode = 10670', 'versionCode = 10700', 1)
g = g.replace('versionName = "0.6.7"', 'versionName = "0.7.0"', 1)
GRADLE.write_text(g)

x = MANIFEST.read_text()
x = x.replace('Admission Collector v0.6.7 Targeted Jinhak Analyzer',
              'Admission Collector v0.7.0 Observation Foundation', 1)
MANIFEST.write_text(x)
