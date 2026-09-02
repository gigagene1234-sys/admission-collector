package com.admissionhub.collector.local

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.admissionhub.collector.parser.RecordUtils
import com.admissionhub.collector.observation.ObservationEvidence
import com.admissionhub.collector.adiga.AdigaPlanTask
import com.admissionhub.collector.canonical.CanonicalEntity
import com.admissionhub.collector.canonical.ProviderEntityMapping
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.io.Writer
import java.util.UUID

data class LocalResumePlan(
    val missing: List<Int>,
    val retry: List<Int>,
    val completedCount: Int
)

class LocalCollectorStore(context: Context) : SQLiteOpenHelper(
    context.applicationContext,
    "admission_collector_local_v1.db",
    null,
    4
) {
    private fun ensureFoundationSchema(db: SQLiteDatabase) {
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

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""
            CREATE TABLE runs(
              run_id TEXT PRIMARY KEY,
              provider TEXT NOT NULL,
              collector_version TEXT NOT NULL,
              status TEXT NOT NULL,
              completion_reason TEXT,
              started_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("""
            CREATE TABLE documents(
              run_id TEXT NOT NULL,
              navigation_key TEXT NOT NULL,
              state TEXT NOT NULL,
              error_type TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(run_id, navigation_key)
            )
        """.trimIndent())
        db.execSQL("""
            CREATE TABLE pages(
              run_id TEXT NOT NULL,
              family_key TEXT NOT NULL,
              requested_year INTEGER NOT NULL,
              page INTEGER NOT NULL,
              total_pages INTEGER NOT NULL,
              state TEXT NOT NULL,
              retry_count INTEGER NOT NULL DEFAULT 0,
              error_type TEXT,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(run_id, family_key, requested_year, page)
            )
        """.trimIndent())
        db.execSQL("""
            CREATE TABLE records(
              run_id TEXT NOT NULL,
              fingerprint TEXT NOT NULL,
              provider TEXT NOT NULL,
              record_type TEXT,
              year INTEGER,
              university TEXT,
              department TEXT,
              admission TEXT,
              capture_version TEXT,
              data_scope TEXT,
              observed_at TEXT,
              quality_state TEXT,
              provider_entity_id TEXT,
              canonical_university_id TEXT,
              canonical_department_id TEXT,
              canonical_admission_id TEXT,
              application_identity_key TEXT,
              json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(run_id, fingerprint)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX idx_runs_provider_status ON runs(provider,status,updated_at)")
        db.execSQL("CREATE INDEX idx_pages_run_state ON pages(run_id,state)")
        db.execSQL("CREATE INDEX idx_documents_run_state ON documents(run_id,state)")
        db.execSQL("CREATE INDEX idx_records_run_year ON records(run_id,year)")
        db.execSQL("""
            CREATE TABLE unified_sessions(
              session_id TEXT PRIMARY KEY,
              collector_version TEXT NOT NULL,
              status TEXT NOT NULL,
              phase TEXT NOT NULL,
              adiga_run_id TEXT,
              jinhak_run_id TEXT,
              completion_reason TEXT,
              started_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("""
            CREATE TABLE unified_analysis_captures(
              session_id TEXT NOT NULL,
              capture_id TEXT NOT NULL,
              provider TEXT NOT NULL,
              page_key TEXT NOT NULL,
              page_type TEXT,
              payload_json TEXT NOT NULL,
              captured_at TEXT NOT NULL,
              PRIMARY KEY(session_id,capture_id)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX idx_unified_sessions_status ON unified_sessions(status,updated_at)")
        db.execSQL("CREATE UNIQUE INDEX idx_unified_capture_page ON unified_analysis_captures(session_id,provider,page_key)")
        ensureFoundationSchema(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            val additions = listOf(
                "capture_version TEXT",
                "data_scope TEXT",
                "observed_at TEXT",
                "quality_state TEXT",
                "provider_entity_id TEXT",
                "canonical_university_id TEXT",
                "canonical_department_id TEXT",
                "canonical_admission_id TEXT",
                "application_identity_key TEXT"
            )
            for (column in additions) db.execSQL("ALTER TABLE records ADD COLUMN $column")
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_records_run_quality ON records(run_id,quality_state)")
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_records_application_identity ON records(run_id,application_identity_key)")
        }
        if (oldVersion < 3) {
            db.execSQL("""
                CREATE TABLE IF NOT EXISTS unified_sessions(
                  session_id TEXT PRIMARY KEY,
                  collector_version TEXT NOT NULL,
                  status TEXT NOT NULL,
                  phase TEXT NOT NULL,
                  adiga_run_id TEXT,
                  jinhak_run_id TEXT,
                  completion_reason TEXT,
                  started_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
            """.trimIndent())
            db.execSQL("""
                CREATE TABLE IF NOT EXISTS unified_analysis_captures(
                  session_id TEXT NOT NULL,
                  capture_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  page_key TEXT NOT NULL,
                  page_type TEXT,
                  payload_json TEXT NOT NULL,
                  captured_at TEXT NOT NULL,
                  PRIMARY KEY(session_id,capture_id)
                )
            """.trimIndent())
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_unified_sessions_status ON unified_sessions(status,updated_at)")
            db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_capture_page ON unified_analysis_captures(session_id,provider,page_key)")
        }
        if (oldVersion < 4) {
            ensureFoundationSchema(db)
        }
    }

    fun beginOrResumeUnifiedSession(collectorVersion: String): String {
        val db = writableDatabase
        val existing = db.rawQuery(
            "SELECT session_id FROM unified_sessions WHERE status='running' ORDER BY updated_at DESC LIMIT 1",
            emptyArray()
        ).use { c -> if (c.moveToFirst()) c.getString(0) else null }
        val now = Instant.now().toString()
        if (!existing.isNullOrBlank()) {
            val cv = ContentValues().apply {
                put("collector_version", collectorVersion)
                put("status", "running")
                put("updated_at", now)
            }
            db.update("unified_sessions", cv, "session_id=?", arrayOf(existing))
            return existing
        }
        val sessionId = UUID.randomUUID().toString()
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            put("collector_version", collectorVersion)
            put("status", "running")
            put("phase", "adiga")
            putNull("adiga_run_id")
            putNull("jinhak_run_id")
            putNull("completion_reason")
            put("started_at", now)
            put("updated_at", now)
        }
        db.insertOrThrow("unified_sessions", null, cv)
        return sessionId
    }

    fun latestUnifiedSession(): String? = readableDatabase.rawQuery(
        "SELECT session_id FROM unified_sessions ORDER BY updated_at DESC LIMIT 1",
        emptyArray()
    ).use { c -> if (c.moveToFirst()) c.getString(0) else null }

    fun attachUnifiedProviderRun(sessionId: String, provider: String, runId: String) {
        val column = when (provider) {
            "adiga" -> "adiga_run_id"
            "jinhak" -> "jinhak_run_id"
            else -> return
        }
        val cv = ContentValues().apply {
            put(column, runId)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.update("unified_sessions", cv, "session_id=?", arrayOf(sessionId))
    }

    fun updateUnifiedSession(sessionId: String, phase: String, status: String, reason: String?) {
        val cv = ContentValues().apply {
            put("phase", phase)
            put("status", status)
            if (reason == null) putNull("completion_reason") else put("completion_reason", reason)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.update("unified_sessions", cv, "session_id=?", arrayOf(sessionId))
    }

    fun storeUnifiedAnalysisCapture(
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

    fun storeObservationEvidence(
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
        val args: Array<String> = if (sessionId == null) emptyArray() else arrayOf(sessionId)
        val totalSql = if (sessionId == null) {
            "SELECT COUNT(*) FROM observations"
        } else {
            "SELECT COUNT(*) FROM observations WHERE session_id=?"
        }
        val unknownSql = if (sessionId == null) {
            "SELECT COUNT(*) FROM observations WHERE page_type_guess IS NULL OR page_type_guess IN ('','jinhak-other')"
        } else {
            "SELECT COUNT(*) FROM observations WHERE session_id=? AND (page_type_guess IS NULL OR page_type_guess IN ('','jinhak-other'))"
        }
        fun scalar(sql: String): Int = readableDatabase.rawQuery(sql, args).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        return JSONObject()
            .put("observations", scalar(totalSql))
            .put("unknownOrPotential", scalar(unknownSql))
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
        requiresUserAction: Boolean,
        updateOrchestrator: Boolean = true
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
            if (updateOrchestrator) {
                put("orchestrator_state", state)
                put("requires_user_action", if (requiresUserAction) 1 else 0)
            }
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

    private fun latestSyncStateDetail(sessionId: String, state: String): JSONObject {
        return readableDatabase.rawQuery(
            "SELECT detail_json FROM sync_state_events WHERE session_id=? AND state=? ORDER BY created_at DESC,event_id DESC LIMIT 1",
            arrayOf(sessionId, state)
        ).use { c ->
            if (!c.moveToFirst()) return@use JSONObject()
            runCatching { JSONObject(c.getString(0)) }.getOrDefault(JSONObject())
        }
    }

    fun unifiedStatus(sessionId: String): JSONObject {
        val out = JSONObject().put("sessionId", sessionId)
        var adigaRun: String? = null
        var jinhakRun: String? = null
        readableDatabase.rawQuery(
            "SELECT collector_version,status,phase,adiga_run_id,jinhak_run_id,completion_reason,started_at,updated_at,orchestrator_state,requires_user_action FROM unified_sessions WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c ->
            if (c.moveToFirst()) {
                out.put("collectorVersion", c.getString(0))
                    .put("status", c.getString(1))
                    .put("phase", c.getString(2))
                    .put("completionReason", if (c.isNull(5)) JSONObject.NULL else c.getString(5))
                    .put("startedAt", c.getString(6))
                    .put("updatedAt", c.getString(7))
                    .put("orchestratorState", if (c.isNull(8)) JSONObject.NULL else c.getString(8))
                    .put("requiresUserAction", !c.isNull(9) && c.getInt(9) != 0)
                adigaRun = if (c.isNull(3)) null else c.getString(3)
                jinhakRun = if (c.isNull(4)) null else c.getString(4)
            }
        }
        out.put("adiga", JSONObject()
            .put("runId", adigaRun ?: JSONObject.NULL)
            .put("stats", adigaRun?.let { stats(it) } ?: JSONObject()))
        out.put("jinhak", JSONObject()
            .put("runId", jinhakRun ?: JSONObject.NULL)
            .put("stats", jinhakRun?.let { stats(it) } ?: JSONObject()))

        val pageTypes = JSONObject()
        var captures = 0
        readableDatabase.rawQuery(
            "SELECT COALESCE(page_type,'unknown'),COUNT(*) FROM unified_analysis_captures WHERE session_id=? GROUP BY COALESCE(page_type,'unknown') ORDER BY 1",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                pageTypes.put(c.getString(0), c.getInt(1))
                captures += c.getInt(1)
            }
        }
        out.put("jinhakAnalysisCaptures", captures)
            .put("jinhakPageTypes", pageTypes)
            .put("sourcePolicy", JSONObject()
                .put("adiga", "official-current-and-historical-baseline")
                .put("jinhak", "user-viewed-derived-analysis-and-prediction")
                .put("predictionIsNotHistoricalActual", true))
            .put("observationStore", observationStats(sessionId))
        out.put("jinhakDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_CRAWL_DIAGNOSTICS"))
        return out
    }

    fun buildUnifiedExport(sessionId: String): JSONObject {
        val status = unifiedStatus(sessionId)
        val adigaRun = status.optJSONObject("adiga")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
        val jinhakRun = status.optJSONObject("jinhak")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
        val analyses = JSONArray()
        readableDatabase.rawQuery(
            "SELECT page_type,payload_json,captured_at FROM unified_analysis_captures WHERE session_id=? ORDER BY captured_at",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                val payload = runCatching { JSONObject(c.getString(1)) }.getOrNull() ?: continue
                analyses.put(JSONObject()
                    .put("pageType", if (c.isNull(0)) JSONObject.NULL else c.getString(0))
                    .put("capturedAt", c.getString(2))
                    .put("analysis", payload))
            }
        }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("type", "admission-unified-two-provider-export")
            .put("session", status)
            .put("combinationPolicy", JSONObject()
                .put("officialBaseline", "adiga")
                .put("predictionAnalysis", "jinhak")
                .put("keepProviderSemanticsSeparate", true)
                .put("doNotOverwriteHistoricalWithPrediction", true))
            .put("sources", JSONObject()
                .put("adiga", JSONObject()
                    .put("runId", adigaRun ?: JSONObject.NULL)
                    .put("records", adigaRun?.let { loadRecords(it) } ?: JSONArray()))
                .put("jinhak", JSONObject()
                    .put("runId", jinhakRun ?: JSONObject.NULL)
                    .put("records", jinhakRun?.let { loadRecords(it) } ?: JSONArray())
                    .put("pageAnalyses", analyses)))
    }

    fun writeUnifiedExport(sessionId: String, writer: Writer) {
        val status = unifiedStatus(sessionId)
        val adigaRun = status.optJSONObject("adiga")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
        val jinhakRun = status.optJSONObject("jinhak")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }

        fun writeNullableString(value: String?) {
            if (value == null) writer.write("null") else writer.write(JSONObject.quote(value))
        }
        fun writeRecords(runId: String?) {
            writer.write("[")
            var first = true
            if (runId != null) {
                readableDatabase.rawQuery(
                    "SELECT json FROM records WHERE run_id=? ORDER BY updated_at,fingerprint",
                    arrayOf(runId)
                ).use { c ->
                    while (c.moveToNext()) {
                        if (!first) writer.write(",")
                        first = false
                        writer.write(c.getString(0))
                    }
                }
            }
            writer.write("]")
        }
        fun writeAnalyses() {
            writer.write("[")
            var first = true
            readableDatabase.rawQuery(
                "SELECT page_type,payload_json,captured_at FROM unified_analysis_captures WHERE session_id=? ORDER BY captured_at",
                arrayOf(sessionId)
            ).use { c ->
                while (c.moveToNext()) {
                    if (!first) writer.write(",")
                    first = false
                    writer.write("{\"pageType\":")
                    writeNullableString(if (c.isNull(0)) null else c.getString(0))
                    writer.write(",\"capturedAt\":")
                    writeNullableString(c.getString(2))
                    writer.write(",\"analysis\":")
                    writer.write(c.getString(1))
                    writer.write("}")
                }
            }
            writer.write("]")
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

        fun safeNavigationEvidence(raw: String?): String? {
            if (raw.isNullOrBlank()) return null
            return try {
                val uri = java.net.URI(raw)
                val host = uri.host.orEmpty().lowercase()
                val path = uri.path.orEmpty().ifBlank { "/" }
                if (host.isBlank()) path.substringBefore('?').take(500) else "$host$path".take(500)
            } catch (_: Exception) { raw.substringBefore('?').substringBefore('#').take(500) }
        }
        fun writeErrors(runId: String?) {
            writer.write("{\"documents\":[")
            var firstDocument = true
            if (runId != null) {
                readableDatabase.rawQuery(
                    "SELECT navigation_key,state,error_type,retry_count,updated_at FROM documents WHERE run_id=? AND (state!='completed' OR error_type IS NOT NULL) ORDER BY updated_at,navigation_key",
                    arrayOf(runId)
                ).use { c ->
                    while (c.moveToNext()) {
                        if (!firstDocument) writer.write(",")
                        firstDocument = false
                        writer.write("{\"safePath\":")
                        writeNullableString(safeNavigationEvidence(c.getString(0)))
                        writer.write(",\"state\":")
                        writeNullableString(c.getString(1))
                        writer.write(",\"errorType\":")
                        writeNullableString(if (c.isNull(2)) null else c.getString(2))
                        writer.write(",\"retryCount\":${c.getInt(3)},\"updatedAt\":")
                        writeNullableString(c.getString(4))
                        writer.write("}")
                    }
                }
            }
            writer.write("],\"pages\":[")
            var firstPage = true
            if (runId != null) {
                readableDatabase.rawQuery(
                    "SELECT family_key,requested_year,page,total_pages,state,error_type,retry_count,updated_at FROM pages WHERE run_id=? AND (state!='completed' OR error_type IS NOT NULL) ORDER BY updated_at,family_key,page",
                    arrayOf(runId)
                ).use { c ->
                    while (c.moveToNext()) {
                        if (!firstPage) writer.write(",")
                        firstPage = false
                        writer.write("{\"familyKey\":")
                        writeNullableString(safeNavigationEvidence(c.getString(0)))
                        writer.write(",\"requestedYear\":${c.getInt(1)},\"page\":${c.getInt(2)},\"totalPages\":${c.getInt(3)},\"state\":")
                        writeNullableString(c.getString(4))
                        writer.write(",\"errorType\":")
                        writeNullableString(if (c.isNull(5)) null else c.getString(5))
                        writer.write(",\"retryCount\":${c.getInt(6)},\"updatedAt\":")
                        writeNullableString(c.getString(7))
                        writer.write("}")
                    }
                }
            }
            writer.write("]}")
        }
        fun writeSyncDiagnostics() {
            writer.write("[")
            var first = true
            readableDatabase.rawQuery(
                "SELECT state,provider,requires_user_action,detail_json,created_at FROM sync_state_events WHERE session_id=? ORDER BY created_at,event_id",
                arrayOf(sessionId)
            ).use { c ->
                while (c.moveToNext()) {
                    if (!first) writer.write(",")
                    first = false
                    writer.write("{\"state\":")
                    writeNullableString(c.getString(0))
                    writer.write(",\"provider\":")
                    writeNullableString(if (c.isNull(1)) null else c.getString(1))
                    writer.write(",\"requiresUserAction\":${c.getInt(2) != 0},\"detail\":${c.getString(3)},\"createdAt\":")
                    writeNullableString(c.getString(4))
                    writer.write("}")
                }
            }
            writer.write("]")
        }

        writer.write("{\"schemaVersion\":4,\"type\":\"admission-unified-two-provider-export\",\"session\":")
        writer.write(status.toString())
        writer.write(",\"analysisReady\":{\"contractVersion\":3,\"purpose\":\"assistant-xlsx-dashboard-generation\",\"authoritativeLayers\":[\"sources.adiga.records\",\"sources.jinhak.records\",\"sources.jinhak.pageAnalyses\",\"observationEvidence\",\"errorEvidence\",\"syncDiagnostics\"],\"recommendedWorkbookSheets\":[\"Dashboard\",\"ApplicationMissions\",\"UnifiedRecords\",\"JinhakPredictions\",\"HistoricalResults\",\"Observations\",\"Coverage\",\"Errors\"],\"rowKeyFields\":[\"provider\",\"year\",\"university\",\"department\",\"admission\",\"applicationIdentityKey\",\"recordType\",\"observedAt\"],\"flattenMetricsForSpreadsheet\":true,\"preserveRawEvidence\":true,\"doNotInferMissingBindings\":true,\"observationFirst\":true},\"combinationPolicy\":{\"officialBaseline\":\"adiga\",\"predictionAnalysis\":\"jinhak\",\"keepProviderSemanticsSeparate\":true,\"doNotOverwriteHistoricalWithPrediction\":true},\"sources\":{\"adiga\":{\"runId\":")
        writeNullableString(adigaRun)
        writer.write(",\"records\":")
        writeRecords(adigaRun)
        writer.write("},\"jinhak\":{\"runId\":")
        writeNullableString(jinhakRun)
        writer.write(",\"records\":")
        writeRecords(jinhakRun)
        writer.write(",\"pageAnalyses\":")
        writeAnalyses()
        writer.write("}},\"observationEvidence\":")
        writeObservations()
        writer.write(",\"errorEvidence\":{\"adiga\":")
        writeErrors(adigaRun)
        writer.write(",\"jinhak\":")
        writeErrors(jinhakRun)
        writer.write("},\"syncDiagnostics\":")
        writeSyncDiagnostics()
        writer.write("}")
        writer.flush()
    }

    fun beginOrResume(provider: String, collectorVersion: String): String {
        val db = writableDatabase
        var existingId: String? = null
        var existingVersion: String? = null
        db.rawQuery(
            "SELECT run_id,collector_version FROM runs WHERE provider=? AND status IN ('collecting','stopped','incomplete') ORDER BY updated_at DESC LIMIT 1",
            arrayOf(provider)
        ).use { c ->
            if (c.moveToFirst()) {
                existingId = c.getString(0)
                existingVersion = c.getString(1)
            }
        }
        val now = Instant.now().toString()

        // Jinhak parser generations must never silently mix in one beta run.
        if (provider == "jinhak" && !existingId.isNullOrBlank() && existingVersion != collectorVersion) {
            val close = ContentValues().apply {
                put("status", "stopped")
                put("completion_reason", "parser-version-boundary:${existingVersion ?: "unknown"}->$collectorVersion")
                put("updated_at", now)
            }
            db.update("runs", close, "run_id=?", arrayOf(existingId))
            existingId = null
            existingVersion = null
        }

        if (!existingId.isNullOrBlank()) {
            val cv = ContentValues().apply {
                put("collector_version", collectorVersion)
                put("status", "collecting")
                putNull("completion_reason")
                put("updated_at", now)
            }
            db.update("runs", cv, "run_id=?", arrayOf(existingId))
            return existingId!!
        }

        val id = UUID.randomUUID().toString()
        val cv = ContentValues().apply {
            put("run_id", id)
            put("provider", provider)
            put("collector_version", collectorVersion)
            put("status", "collecting")
            putNull("completion_reason")
            put("started_at", now)
            put("updated_at", now)
        }
        db.insertOrThrow("runs", null, cv)
        return id
    }

    fun latestResumableRun(provider: String): String? = readableDatabase.rawQuery(
        "SELECT run_id FROM runs WHERE provider=? AND status IN ('collecting','stopped','incomplete') ORDER BY updated_at DESC LIMIT 1",
        arrayOf(provider)
    ).use { c -> if (c.moveToFirst()) c.getString(0) else null }

    fun latestRun(provider: String): String? = readableDatabase.rawQuery(
        "SELECT run_id FROM runs WHERE provider=? ORDER BY updated_at DESC LIMIT 1",
        arrayOf(provider)
    ).use { c -> if (c.moveToFirst()) c.getString(0) else null }

    fun markRun(runId: String, status: String, reason: String?) {
        val cv = ContentValues().apply {
            put("status", status)
            if (reason == null) putNull("completion_reason") else put("completion_reason", reason)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.update("runs", cv, "run_id=?", arrayOf(runId))
    }

    fun markDocument(runId: String, navigationKey: String, state: String, retryCount: Int = 0, errorType: String? = null) {
        if (navigationKey.isBlank()) return
        val cv = ContentValues().apply {
            put("run_id", runId)
            put("navigation_key", navigationKey)
            put("state", state)
            if (errorType == null) putNull("error_type") else put("error_type", errorType)
            put("retry_count", retryCount)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("documents", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun isDocumentCompleted(runId: String, navigationKey: String): Boolean {
        if (navigationKey.isBlank()) return false
        return readableDatabase.rawQuery(
            "SELECT state FROM documents WHERE run_id=? AND navigation_key=? LIMIT 1",
            arrayOf(runId, navigationKey)
        ).use { c -> c.moveToFirst() && c.getString(0) == "completed" }
    }

    fun markPage(
        runId: String,
        familyKey: String,
        requestedYear: Int?,
        page: Int,
        totalPages: Int,
        state: String,
        retryCount: Int = 0,
        errorType: String? = null
    ) {
        if (familyKey.isBlank() || page < 1) return
        val cv = ContentValues().apply {
            put("run_id", runId)
            put("family_key", familyKey)
            put("requested_year", requestedYear ?: -1)
            put("page", page)
            put("total_pages", totalPages.coerceAtLeast(page))
            put("state", state)
            put("retry_count", retryCount)
            if (errorType == null) putNull("error_type") else put("error_type", errorType)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("pages", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun resumePlan(runId: String, familyKey: String, requestedYear: Int?, totalPages: Int): LocalResumePlan {
        val states = linkedMapOf<Int, String>()
        readableDatabase.rawQuery(
            "SELECT page,state FROM pages WHERE run_id=? AND family_key=? AND requested_year=?",
            arrayOf(runId, familyKey, (requestedYear ?: -1).toString())
        ).use { c ->
            while (c.moveToNext()) states[c.getInt(0)] = c.getString(1)
        }
        val missing = mutableListOf<Int>()
        val retry = mutableListOf<Int>()
        var completed = 0
        for (page in 2..totalPages) {
            when (states[page]) {
                "completed" -> completed += 1
                "error" -> retry += page
                else -> missing += page
            }
        }
        return LocalResumePlan(missing, retry, completed)
    }

    fun storeRecords(runId: String, provider: String, records: JSONArray): Int {
        if (records.length() == 0) return 0
        val db = writableDatabase
        var stored = 0
        db.beginTransaction()
        try {
            for (i in 0 until records.length()) {
                val obj = records.optJSONObject(i) ?: continue
                val year = nullableInt(obj, "year")
                val rowFp = obj.optString("sourceRowFingerprint")
                val fingerprint = if (rowFp.isNotBlank()) {
                    RecordUtils.sha256("${obj.optString("recordType")}|${year ?: "na"}|$rowFp")
                } else {
                    RecordUtils.sha256(obj.toString())
                }
                val cv = ContentValues().apply {
                    put("run_id", runId)
                    put("fingerprint", fingerprint)
                    put("provider", provider)
                    put("record_type", nullableString(obj, "recordType"))
                    if (year == null) putNull("year") else put("year", year)
                    putNullable("university", nullableString(obj, "university"))
                    putNullable("department", nullableString(obj, "department"))
                    putNullable("admission", nullableString(obj, "admission"))
                    putNullable("capture_version", nullableString(obj, "captureVersion"))
                    putNullable("data_scope", nullableString(obj, "dataScope"))
                    putNullable("observed_at", nullableString(obj, "observedAt"))
                    putNullable("quality_state", nullableString(obj, "qualityState"))
                    putNullable("provider_entity_id", nullableString(obj, "providerEntityId"))
                    putNullable("canonical_university_id", nullableString(obj, "canonicalUniversityId"))
                    putNullable("canonical_department_id", nullableString(obj, "canonicalDepartmentId"))
                    putNullable("canonical_admission_id", nullableString(obj, "canonicalAdmissionId"))
                    putNullable("application_identity_key", nullableString(obj, "applicationIdentityKey"))
                    put("json", obj.toString())
                    put("updated_at", Instant.now().toString())
                }
                val result = db.insertWithOnConflict("records", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
                if (result != -1L) stored += 1
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return stored
    }

    fun loadRecords(runId: String): JSONArray {
        val out = JSONArray()
        readableDatabase.rawQuery(
            "SELECT json FROM records WHERE run_id=? ORDER BY year,university,department,record_type,fingerprint",
            arrayOf(runId)
        ).use { c ->
            while (c.moveToNext()) {
                runCatching { JSONObject(c.getString(0)) }.getOrNull()?.let { out.put(it) }
            }
        }
        return out
    }

    fun unresolvedCount(runId: String): Int {
        fun count(table: String): Int = readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM $table WHERE run_id=? AND state='error'",
            arrayOf(runId)
        ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        return count("pages") + count("documents")
    }

    fun stats(runId: String): JSONObject {
        fun scalar(sql: String): Int = readableDatabase.rawQuery(sql, arrayOf(runId)).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        return JSONObject()
            .put("runId", runId)
            .put("records", scalar("SELECT COUNT(*) FROM records WHERE run_id=?"))
            .put("acceptedRecords", scalar("SELECT COUNT(*) FROM records WHERE run_id=? AND quality_state='accepted'"))
            .put("provisionalRecords", scalar("SELECT COUNT(*) FROM records WHERE run_id=? AND quality_state='provisional'"))
            .put("completedPages", scalar("SELECT COUNT(*) FROM pages WHERE run_id=? AND state='completed'"))
            .put("errorPages", scalar("SELECT COUNT(*) FROM pages WHERE run_id=? AND state='error'"))
            .put("completedDocuments", scalar("SELECT COUNT(*) FROM documents WHERE run_id=? AND state='completed'"))
            .put("errorDocuments", scalar("SELECT COUNT(*) FROM documents WHERE run_id=? AND state='error'"))
            .put("unresolved", unresolvedCount(runId))
    }


    /** Privacy-safe operational snapshot. No DOM, cookies, credentials, raw records or URLs are included. */
    fun diagnosticSnapshot(runId: String, maxErrorPages: Int = 200): JSONObject {
        val db = readableDatabase
        val run = JSONObject()
        db.rawQuery(
            "SELECT provider,collector_version,status,completion_reason,started_at,updated_at FROM runs WHERE run_id=? LIMIT 1",
            arrayOf(runId)
        ).use { c ->
            if (c.moveToFirst()) {
                run.put("runId", runId)
                    .put("provider", c.getString(0))
                    .put("collectorVersion", c.getString(1))
                    .put("status", c.getString(2))
                    .put("completionReason", if (c.isNull(3)) JSONObject.NULL else c.getString(3))
                    .put("startedAt", c.getString(4))
                    .put("updatedAt", c.getString(5))
            }
        }

        val failedPages = JSONArray()
        db.rawQuery(
            "SELECT family_key,requested_year,page,total_pages,retry_count,error_type,updated_at " +
                "FROM pages WHERE run_id=? AND state='error' ORDER BY family_key,requested_year,page LIMIT ?",
            arrayOf(runId, maxErrorPages.toString())
        ).use { c ->
            while (c.moveToNext()) {
                val yr = c.getInt(1)
                failedPages.put(JSONObject()
                    .put("familyKey", c.getString(0))
                    .put("requestedYear", if (yr == -1) JSONObject.NULL else yr)
                    .put("page", c.getInt(2))
                    .put("totalPages", c.getInt(3))
                    .put("retryCount", c.getInt(4))
                    .put("errorType", if (c.isNull(5)) JSONObject.NULL else c.getString(5))
                    .put("updatedAt", c.getString(6)))
            }
        }

        val familyProgress = JSONArray()
        db.rawQuery(
            "SELECT family_key,requested_year,MAX(total_pages),COUNT(*)," +
                "SUM(CASE WHEN state='completed' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='error' THEN 1 ELSE 0 END) " +
                "FROM pages WHERE run_id=? GROUP BY family_key,requested_year ORDER BY family_key,requested_year",
            arrayOf(runId)
        ).use { c ->
            while (c.moveToNext()) {
                val yr = c.getInt(1)
                familyProgress.put(JSONObject()
                    .put("familyKey", c.getString(0))
                    .put("requestedYear", if (yr == -1) JSONObject.NULL else yr)
                    .put("totalPages", c.getInt(2))
                    .put("knownPageCheckpoints", c.getInt(3))
                    .put("completed", c.getInt(4))
                    .put("errors", c.getInt(5)))
            }
        }

        val documentErrorsByType = JSONArray()
        db.rawQuery(
            "SELECT COALESCE(error_type,'unknown'),COUNT(*) FROM documents WHERE run_id=? AND state='error' GROUP BY error_type ORDER BY COUNT(*) DESC",
            arrayOf(runId)
        ).use { c ->
            while (c.moveToNext()) {
                documentErrorsByType.put(JSONObject().put("errorType", c.getString(0)).put("count", c.getInt(1)))
            }
        }

        val recordBreakdown = JSONArray()
        db.rawQuery(
            "SELECT COALESCE(record_type,'unknown'),COALESCE(year,-1),COUNT(*) FROM records WHERE run_id=? GROUP BY record_type,year ORDER BY year,record_type",
            arrayOf(runId)
        ).use { c ->
            while (c.moveToNext()) {
                val yr = c.getInt(1)
                recordBreakdown.put(JSONObject()
                    .put("recordType", c.getString(0))
                    .put("year", if (yr == -1) JSONObject.NULL else yr)
                    .put("count", c.getInt(2)))
            }
        }

        return JSONObject()
            .put("schemaVersion", 1)
            .put("generatedAt", Instant.now().toString())
            .put("run", run)
            .put("stats", stats(runId))
            .put("failedPages", failedPages)
            .put("familyProgress", familyProgress)
            .put("documentErrorsByType", documentErrorsByType)
            .put("recordBreakdown", recordBreakdown)
            .put("privacy", "no-dom-no-record-content-no-cookie-no-credential-no-url")
    }

    private fun nullableInt(obj: JSONObject, key: String): Int? =
        if (!obj.has(key) || obj.isNull(key)) null else obj.optInt(key).takeIf { it != 0 }

    private fun nullableString(obj: JSONObject, key: String): String? =
        if (!obj.has(key) || obj.isNull(key)) null else obj.optString(key).trim().takeIf { it.isNotBlank() }

    private fun ContentValues.putNullable(key: String, value: String?) {
        if (value == null) putNull(key) else put(key, value)
    }
}
