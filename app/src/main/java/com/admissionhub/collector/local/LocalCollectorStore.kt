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
import com.admissionhub.collector.canonical.CanonicalSixApplicationGraph
import com.admissionhub.collector.canonical.AdigaOfficialAdmissionEvidence
import com.admissionhub.collector.sync.LocalRebindPolicy
import com.admissionhub.collector.score.ScoreDecisionEngine
import com.admissionhub.collector.score.StudentScoreImport
import com.admissionhub.collector.score.ApplicationReviewEngine
import com.admissionhub.collector.score.SameCardPrediction
import com.admissionhub.collector.score.ReviewExportContract
import com.admissionhub.collector.hub.HubDashboardModel
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
    10
) {
    private fun ensureFoundationSchema(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE IF NOT EXISTS application_review_inputs(application_identity_key TEXT PRIMARY KEY, input_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
        db.execSQL("CREATE TABLE IF NOT EXISTS application_review_history(review_id TEXT PRIMARY KEY, application_identity_key TEXT NOT NULL, input_json TEXT NOT NULL, saved_at TEXT NOT NULL)")
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


        db.execSQL("""
            CREATE TABLE IF NOT EXISTS canonical_applications(
              session_id TEXT NOT NULL,
              application_identity_key TEXT NOT NULL,
              canonical_application_id TEXT NOT NULL,
              academic_year INTEGER NOT NULL,
              canonical_university_id TEXT,
              canonical_campus_id TEXT,
              canonical_recruitment_unit_id TEXT,
              canonical_admission_track_id TEXT,
              university TEXT,
              campus TEXT,
              department TEXT,
              admission TEXT,
              admission_category TEXT,
              capacity INTEGER,
              jinhak_confidence TEXT NOT NULL,
              parse_source TEXT NOT NULL,
              coverage_json TEXT NOT NULL,
              coverage_count INTEGER NOT NULL DEFAULT 0,
              adiga_binding_quality TEXT NOT NULL,
              adiga_match_count INTEGER NOT NULL DEFAULT 0,
              adiga_binding_json TEXT NOT NULL,
              quality_state TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(session_id,application_identity_key)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_canonical_apps_session_quality ON canonical_applications(session_id,quality_state,university,department)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_canonical_apps_canonical_id ON canonical_applications(canonical_application_id)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS hub_application_slots(
              slot INTEGER PRIMARY KEY,
              canonical_application_id TEXT NOT NULL,
              application_identity_key TEXT NOT NULL,
              display_label TEXT NOT NULL,
              user_pinned INTEGER NOT NULL DEFAULT 1,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_hub_slot_identity ON hub_application_slots(application_identity_key)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS hub_quality_audits(
              session_id TEXT PRIMARY KEY,
              audit_json TEXT NOT NULL,
              generated_at TEXT NOT NULL
            )
        """.trimIndent())

        db.execSQL("""
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

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_student_profiles(
              profile_id TEXT PRIMARY KEY,
              academic_year INTEGER NOT NULL,
              source_type TEXT NOT NULL,
              source_json TEXT NOT NULL,
              verification_state TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_score_profile_year ON score_student_profiles(academic_year,updated_at)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_conversion_results(
              application_identity_key TEXT PRIMARY KEY,
              academic_year INTEGER NOT NULL,
              score_value REAL,
              max_score REAL,
              score_scale TEXT,
              comparison_direction TEXT,
              formula_source TEXT,
              formula_version TEXT,
              identity_binding_verified INTEGER NOT NULL DEFAULT 0,
              verified INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL,
              detail_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_official_outcomes(
              outcome_id TEXT PRIMARY KEY,
              application_identity_key TEXT NOT NULL,
              academic_year INTEGER NOT NULL,
              metric_name TEXT NOT NULL,
              metric_value REAL,
              score_scale TEXT,
              max_score REAL,
              source_name TEXT NOT NULL,
              source_url TEXT,
              verified INTEGER NOT NULL DEFAULT 0,
              primary_reference INTEGER NOT NULL DEFAULT 0,
              detail_json TEXT NOT NULL,
              observed_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_score_outcome_identity ON score_official_outcomes(application_identity_key,academic_year,metric_name)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_prediction_snapshots(
              snapshot_id TEXT PRIMARY KEY,
              application_identity_key TEXT NOT NULL,
              observed_at TEXT NOT NULL,
              provider TEXT NOT NULL,
              structured INTEGER NOT NULL DEFAULT 0,
              metrics_json TEXT NOT NULL,
              source_label TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_score_prediction_identity ON score_prediction_snapshots(application_identity_key,observed_at)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_decision_assessments(
              application_identity_key TEXT PRIMARY KEY,
              decision_code TEXT NOT NULL,
              decision_label TEXT NOT NULL,
              confidence TEXT NOT NULL,
              result_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS jinhak_mission_targets(
              session_id TEXT NOT NULL,
              target_id TEXT NOT NULL,
              identity_key TEXT NOT NULL,
              lane TEXT NOT NULL,
              state TEXT NOT NULL,
              state_rank INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              first_persisted_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(session_id,target_id)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_jinhak_mission_session_state ON jinhak_mission_targets(session_id,state,state_rank)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_jinhak_mission_session_identity ON jinhak_mission_targets(session_id,identity_key,lane)")

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

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS jinhak_mission_runtime(
              session_id TEXT PRIMARY KEY,
              active_target_id TEXT,
              current_batch_target TEXT,
              mission_origin_route TEXT,
              mission_needs_return INTEGER NOT NULL DEFAULT 0,
              report_bridge_json TEXT,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
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
        if (oldVersion < 5) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 6) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 7) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 8) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 9) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 10) ensureFoundationSchema(db)
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
            .put("jinhakAuthDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_AUTH_DIAGNOSTICS"))
            .put("jinhakTerminalSummary", latestSyncStateDetail(sessionId, "JINHAK_TERMINAL_SEAL"))
            .put("canonicalHub", canonicalHubSummary(sessionId))
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

    fun writeUnifiedExport(sessionId: String, writer: Writer, exporterVersion: String = "0.13.0", exporterBuildCode: Int = 113000) {
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
        writer.write(",\"analysisReady\":{\"contractVersion\":4,\"purpose\":\"canonical-six-application-hub-generation\",\"authoritativeLayers\":[\"sources.adiga.records\",\"sources.jinhak.records\",\"sources.jinhak.pageAnalyses\",\"observationEvidence\",\"errorEvidence\",\"syncDiagnostics\"],\"recommendedWorkbookSheets\":[\"Dashboard\",\"SixApplications\",\"CanonicalApplications\",\"ApplicationMissions\",\"UnifiedRecords\",\"JinhakPredictions\",\"HistoricalResults\",\"Observations\",\"Coverage\",\"QualityAudit\",\"Errors\"],\"rowKeyFields\":[\"provider\",\"year\",\"university\",\"department\",\"admission\",\"applicationIdentityKey\",\"recordType\",\"observedAt\"],\"flattenMetricsForSpreadsheet\":true,\"preserveRawEvidence\":true,\"doNotInferMissingBindings\":true,\"observationFirst\":true},\"combinationPolicy\":{\"officialBaseline\":\"adiga\",\"predictionAnalysis\":\"jinhak\",\"keepProviderSemanticsSeparate\":true,\"doNotOverwriteHistoricalWithPrediction\":true},\"sources\":{\"adiga\":{\"runId\":")
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
        val score = scoreDecisionSummary(sessionId)
        val hub = HubDashboardModel.build(canonicalHubSummary(sessionId), status, JSONObject(), score)
        ReviewExportContract.append(writer, exporterVersion, exporterBuildCode, status.optString("collectorVersion"), Instant.now().toString(), currentStudentScoreProfile(), score, hub)
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

    private fun jinhakMissionStateRank(state: String): Int = when (state.lowercase()) {
        "pending" -> 0
        "clicked" -> 10
        "deferred" -> 20
        "failed" -> 30
        "skipped" -> 40
        "confirmed" -> 50
        else -> -1
    }

    /** Upsert a mission target without ever allowing a lower-ranked state to overwrite progress. */
    fun upsertJinhakMissionTarget(sessionId: String, payload: JSONObject): Boolean {
        if (sessionId.isBlank()) return false
        val targetId = payload.optString("targetId").takeIf { it.isNotBlank() && it != "null" } ?: return false
        val identityKey = payload.optString("identityKey").takeIf { it.isNotBlank() && it != "null" } ?: return false
        val lane = payload.optString("lane").takeIf { it.isNotBlank() && it != "reference" && it != "null" } ?: return false
        val state = payload.optString("state", "pending").lowercase()
        val rank = jinhakMissionStateRank(state)
        if (rank < 0) return false
        val now = Instant.now().toString()
        val db = writableDatabase
        db.beginTransaction()
        return try {
            val existing = db.rawQuery(
                "SELECT state_rank,first_persisted_at FROM jinhak_mission_targets WHERE session_id=? AND target_id=? LIMIT 1",
                arrayOf(sessionId, targetId)
            ).use { c -> if (c.moveToFirst()) Pair(c.getInt(0), c.getString(1)) else null }
            if (existing != null && existing.first > rank) {
                db.setTransactionSuccessful()
                false
            } else {
                val cv = ContentValues().apply {
                    put("session_id", sessionId)
                    put("target_id", targetId)
                    put("identity_key", identityKey)
                    put("lane", lane)
                    put("state", state)
                    put("state_rank", rank)
                    put("payload_json", payload.toString())
                    put("first_persisted_at", existing?.second ?: now)
                    put("updated_at", now)
                }
                db.insertWithOnConflict("jinhak_mission_targets", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
                db.setTransactionSuccessful()
                true
            }
        } finally {
            db.endTransaction()
        }
    }

    fun loadJinhakMissionTargets(sessionId: String): List<JSONObject> {
        if (sessionId.isBlank()) return emptyList()
        val out = mutableListOf<JSONObject>()
        readableDatabase.rawQuery(
            "SELECT payload_json FROM jinhak_mission_targets WHERE session_id=? ORDER BY first_persisted_at,target_id",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                runCatching { JSONObject(c.getString(0)) }.getOrNull()?.let(out::add)
            }
        }
        return out
    }

    fun storeJinhakMissionRuntime(sessionId: String, payload: JSONObject) {
        if (sessionId.isBlank()) return
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            putNullable("active_target_id", payload.optString("activeTargetId").takeIf { it.isNotBlank() && it != "null" })
            putNullable("current_batch_target", payload.optString("currentBatchTarget").takeIf { it.isNotBlank() && it != "null" })
            putNullable("mission_origin_route", payload.optString("missionOriginRoute").takeIf { it.isNotBlank() && it != "null" })
            put("mission_needs_return", if (payload.optBoolean("missionNeedsReturn", false)) 1 else 0)
            val bridge = payload.optJSONObject("reportBridgeContext")
            putNullable("report_bridge_json", bridge?.toString())
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("jinhak_mission_runtime", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun loadJinhakMissionRuntime(sessionId: String): JSONObject? {
        if (sessionId.isBlank()) return null
        return readableDatabase.rawQuery(
            "SELECT active_target_id,current_batch_target,mission_origin_route,mission_needs_return,report_bridge_json,updated_at FROM jinhak_mission_runtime WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c ->
            if (!c.moveToFirst()) return@use null
            JSONObject()
                .put("activeTargetId", if (c.isNull(0)) JSONObject.NULL else c.getString(0))
                .put("currentBatchTarget", if (c.isNull(1)) JSONObject.NULL else c.getString(1))
                .put("missionOriginRoute", if (c.isNull(2)) JSONObject.NULL else c.getString(2))
                .put("missionNeedsReturn", c.getInt(3) != 0)
                .put("reportBridgeContext", if (c.isNull(4)) JSONObject.NULL else runCatching { JSONObject(c.getString(4)) }.getOrNull() ?: JSONObject.NULL)
                .put("updatedAt", c.getString(5))
        }
    }

    fun jinhakMissionPersistenceSummary(sessionId: String): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("persistedTargets", 0).put("persistedIdentities", 0)
        val db = readableDatabase
        val counts = db.rawQuery(
            "SELECT COUNT(*),COUNT(DISTINCT identity_key)," +
                "SUM(CASE WHEN state='pending' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='clicked' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='deferred' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='confirmed' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='failed' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='skipped' THEN 1 ELSE 0 END) " +
                "FROM jinhak_mission_targets WHERE session_id=?",
            arrayOf(sessionId)
        ).use { c ->
            if (!c.moveToFirst()) intArrayOf(0,0,0,0,0,0,0,0)
            else IntArray(8) { i -> if (c.isNull(i)) 0 else c.getInt(i) }
        }
        val runtimePresent = db.rawQuery(
            "SELECT active_target_id IS NOT NULL FROM jinhak_mission_runtime WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c -> c.moveToFirst() && c.getInt(0) != 0 }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("persistedTargets", counts[0])
            .put("persistedIdentities", counts[1])
            .put("pending", counts[2])
            .put("clicked", counts[3])
            .put("deferred", counts[4])
            .put("confirmed", counts[5])
            .put("failed", counts[6])
            .put("skipped", counts[7])
            .put("activeTargetPersisted", runtimePresent)
            .put("monotonicStateGuard", true)
            .put("credentialStored", false)
            .put("sessionSecretStored", false)
            .put("coverage", jinhakMissionCoveragePersistenceSummary(sessionId))
    }


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

    fun currentStudentScoreProfile(): JSONObject = readableDatabase.rawQuery(
        "SELECT source_json FROM score_student_profiles ORDER BY updated_at DESC LIMIT 1", emptyArray()
    ).use { c -> if (c.moveToFirst()) runCatching { JSONObject(c.getString(0)) }.getOrDefault(JSONObject()) else JSONObject().put("status", "NOT_IMPORTED") }

    fun saveStudentScoreImport(profile: JSONObject) {
        require(profile.optString("fingerprint").isNotBlank())
        upsertStudentScoreProfile(profile.getString("fingerprint"), profile.getInt("academicYear"), "user-transcript-import", profile, "USER_CONFIRMED_INPUT")
    }

    fun loadApplicationReviewInput(identity: String): JSONObject = readableDatabase.rawQuery(
        "SELECT input_json FROM application_review_inputs WHERE application_identity_key=?", arrayOf(identity)
    ).use { c -> if (c.moveToFirst()) JSONObject(c.getString(0)) else JSONObject() }

    fun saveApplicationReviewInput(sessionId: String, identity: String, input: JSONObject) {
        val slots = loadHubApplicationSlots()
        require((0 until slots.length()).any { slots.optJSONObject(it)?.optString("applicationIdentityKey") == identity }) { "현재 선택한 6장에만 근거를 등록할 수 있습니다." }
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val candidate = (0 until candidates.length()).mapNotNull { candidates.optJSONObject(it) }.firstOrNull { it.optString("applicationIdentityKey") == identity }
            ?: error("지원안 연결을 먼저 복구하세요.")
        val clean = ApplicationReviewEngine.sanitize(input).put("applicationIdentityKey", identity).put("academicYear", candidate.getInt("academicYear"))
        // A changed transcript invalidates old comparisons until the user explicitly rechecks the source.
        if (clean.optBoolean("sourceReviewConfirmed")) clean.put("profileFingerprint", currentStudentScoreProfile().optString("fingerprint"))
        val now = Instant.now().toString(); clean.put("reviewedAt", now)
        val db = writableDatabase; db.beginTransaction()
        try {
            val cv = ContentValues().apply { put("application_identity_key", identity); put("input_json", clean.toString()); put("updated_at", now) }
            db.insertWithOnConflict("application_review_inputs", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            val history = ContentValues().apply { put("review_id", UUID.randomUUID().toString()); put("application_identity_key", identity); put("input_json", clean.toString()); put("saved_at", now) }
            db.insertOrThrow("application_review_history", null, history)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }

    fun materializeSelectedPredictions(sessionId: String) {
        val run = unifiedProviderRunId(sessionId, "jinhak") ?: return
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val slots = loadHubApplicationSlots()
        val selected = (0 until slots.length()).mapNotNull { slots.optJSONObject(it)?.optString("applicationIdentityKey") }.toSet()
        for (i in 0 until candidates.length()) {
            val c = candidates.getJSONObject(i); val identity = c.optString("applicationIdentityKey")
            if (identity !in selected) continue
            readableDatabase.rawQuery("SELECT json FROM records WHERE run_id=? AND application_identity_key=? ORDER BY updated_at", arrayOf(run, identity)).use { rows ->
                while (rows.moveToNext()) {
                    val record = runCatching { JSONObject(rows.getString(0)) }.getOrNull() ?: continue
                    val metrics = SameCardPrediction.extract(c, record) ?: continue
                    storePredictionSnapshot(identity, metrics.getString("observedAt"), "jinhak", true, metrics, "같은 지원 카드에서 확인한 진학사 수치")
                }
            }
        }
    }

    fun upsertStudentScoreProfile(
        profileId: String,
        academicYear: Int,
        sourceType: String,
        source: JSONObject,
        verificationState: String
    ) {
        if (profileId.isBlank()) return
        val cv = ContentValues().apply {
            put("profile_id", profileId.take(160))
            put("academic_year", academicYear)
            put("source_type", sourceType.take(80))
            put("source_json", source.toString())
            put("verification_state", verificationState.take(80))
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("score_student_profiles", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun upsertUniversityConversionResult(
        applicationIdentityKey: String,
        academicYear: Int,
        scoreValue: Double?,
        maxScore: Double?,
        scoreScale: String?,
        comparisonDirection: String?,
        formulaSource: String?,
        formulaVersion: String?,
        identityBindingVerified: Boolean,
        verified: Boolean,
        status: String,
        detail: JSONObject = JSONObject()
    ) {
        if (applicationIdentityKey.isBlank()) return
        val cv = ContentValues().apply {
            put("application_identity_key", applicationIdentityKey)
            put("academic_year", academicYear)
            if (scoreValue == null) putNull("score_value") else put("score_value", scoreValue)
            if (maxScore == null) putNull("max_score") else put("max_score", maxScore)
            if (scoreScale.isNullOrBlank()) putNull("score_scale") else put("score_scale", scoreScale.take(120))
            if (comparisonDirection.isNullOrBlank()) putNull("comparison_direction") else put("comparison_direction", comparisonDirection.take(40))
            if (formulaSource.isNullOrBlank()) putNull("formula_source") else put("formula_source", formulaSource.take(500))
            if (formulaVersion.isNullOrBlank()) putNull("formula_version") else put("formula_version", formulaVersion.take(120))
            put("identity_binding_verified", if (identityBindingVerified) 1 else 0)
            put("verified", if (verified) 1 else 0)
            put("status", status.take(80))
            put("detail_json", detail.toString())
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("score_conversion_results", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun hasVerifiedNumericOfficialOutcome(applicationIdentityKey: String): Boolean {
        if (applicationIdentityKey.isBlank()) return false
        return readableDatabase.rawQuery(
            "SELECT 1 FROM score_official_outcomes WHERE application_identity_key=? AND verified=1 AND metric_value IS NOT NULL LIMIT 1",
            arrayOf(applicationIdentityKey)
        ).use { it.moveToFirst() }
    }

    fun storeOfficialAdmissionOutcome(
        applicationIdentityKey: String,
        academicYear: Int,
        metricName: String,
        metricValue: Double?,
        scoreScale: String?,
        maxScore: Double?,
        sourceName: String,
        sourceUrl: String?,
        verified: Boolean,
        primaryReference: Boolean,
        detail: JSONObject = JSONObject()
    ): String? {
        if (applicationIdentityKey.isBlank() || metricName.isBlank() || sourceName.isBlank()) return null
        val observedAt = Instant.now().toString()
        val outcomeId = RecordUtils.sha256(listOf(applicationIdentityKey, academicYear, metricName, metricValue, scoreScale, sourceName, sourceUrl).joinToString("|"))
        val cv = ContentValues().apply {
            put("outcome_id", outcomeId)
            put("application_identity_key", applicationIdentityKey)
            put("academic_year", academicYear)
            put("metric_name", metricName.take(160))
            if (metricValue == null) putNull("metric_value") else put("metric_value", metricValue)
            if (scoreScale.isNullOrBlank()) putNull("score_scale") else put("score_scale", scoreScale.take(120))
            if (maxScore == null) putNull("max_score") else put("max_score", maxScore)
            put("source_name", sourceName.take(240))
            if (sourceUrl.isNullOrBlank()) putNull("source_url") else put("source_url", sourceUrl.take(1000))
            put("verified", if (verified) 1 else 0)
            put("primary_reference", if (primaryReference) 1 else 0)
            put("detail_json", detail.toString())
            put("observed_at", observedAt)
        }
        writableDatabase.insertWithOnConflict("score_official_outcomes", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        return outcomeId
    }

    fun storePredictionSnapshot(
        applicationIdentityKey: String,
        observedAt: String,
        provider: String,
        structured: Boolean,
        metrics: JSONObject,
        sourceLabel: String
    ): String? {
        if (applicationIdentityKey.isBlank() || provider.isBlank() || observedAt.isBlank()) return null
        val snapshotId = RecordUtils.sha256("$applicationIdentityKey|$provider|$observedAt|${RecordUtils.sha256(metrics.toString())}")
        val cv = ContentValues().apply {
            put("snapshot_id", snapshotId)
            put("application_identity_key", applicationIdentityKey)
            put("observed_at", observedAt)
            put("provider", provider.take(80))
            put("structured", if (structured) 1 else 0)
            put("metrics_json", metrics.toString())
            put("source_label", sourceLabel.take(240))
        }
        writableDatabase.insertWithOnConflict("score_prediction_snapshots", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        return snapshotId
    }

    fun scoreDecisionSummary(sessionId: String): JSONObject {
        val db = readableDatabase
        val fullProfile = currentStudentScoreProfile()
        val canonicalEvidenceSessionId = canonicalSessionForExactPinnedRebind(sessionId)
        val candidates = loadCanonicalApplicationCandidates(canonicalEvidenceSessionId)
        val candidateById = (0 until candidates.length()).map { candidates.getJSONObject(it) }.associateBy { it.optString("applicationIdentityKey") }
        val slots = loadHubApplicationSlots()
        val selected = (0 until slots.length()).mapNotNull { slots.optJSONObject(it)?.optString("applicationIdentityKey") }.toSet()
        val byIdentity = JSONObject()
        var verifiedConversions = 0
        var officialOutcomeAvailable = 0
        var comparableDecisions = 0
        var decisionHolds = 0
        var predictionCollected = 0
        var structuredPredictions = 0

        val studentProfile = db.rawQuery(
            "SELECT profile_id,academic_year,source_type,verification_state,updated_at FROM score_student_profiles ORDER BY updated_at DESC LIMIT 1",
            emptyArray()
        ).use { c ->
            if (!c.moveToFirst()) JSONObject().put("status", "NOT_IMPORTED")
            else JSONObject()
                .put("status", "IMPORTED")
                .put("profileId", c.getString(0))
                .put("academicYear", c.getInt(1))
                .put("sourceType", c.getString(2))
                .put("verificationState", c.getString(3))
                .put("updatedAt", c.getString(4))
        }

        val processedScoreIdentities = linkedSetOf<String>()
        db.rawQuery(
            "SELECT application_identity_key,quality_state,academic_year FROM canonical_applications " +
                "ORDER BY CASE WHEN session_id=? THEN 0 ELSE 1 END, updated_at DESC, application_identity_key",
            arrayOf(sessionId)
        ).use { apps ->
            while (apps.moveToNext()) {
                val identity = apps.getString(0)
                if (identity !in selected || !processedScoreIdentities.add(identity)) continue
                val canonicalQuality = apps.getString(1)
                val academicYear = apps.getInt(2)
                val conversion = db.rawQuery(
                    "SELECT academic_year,score_value,max_score,score_scale,comparison_direction,formula_source,formula_version,identity_binding_verified,verified,status,detail_json,updated_at FROM score_conversion_results WHERE application_identity_key=? LIMIT 1",
                    arrayOf(identity)
                ).use { c ->
                    if (!c.moveToFirst()) null else JSONObject()
                        .put("academicYear", c.getInt(0))
                        .put("scoreValue", if (c.isNull(1)) JSONObject.NULL else c.getDouble(1))
                        .put("maxScore", if (c.isNull(2)) JSONObject.NULL else c.getDouble(2))
                        .put("scoreScale", if (c.isNull(3)) JSONObject.NULL else c.getString(3))
                        .put("comparisonDirection", if (c.isNull(4)) JSONObject.NULL else c.getString(4))
                        .put("formulaSource", if (c.isNull(5)) JSONObject.NULL else c.getString(5))
                        .put("formulaVersion", if (c.isNull(6)) JSONObject.NULL else c.getString(6))
                        .put("identityBindingVerified", c.getInt(7) != 0)
                        .put("verified", c.getInt(8) != 0)
                        .put("status", c.getString(9))
                        .put("detail", runCatching { JSONObject(c.getString(10)) }.getOrDefault(JSONObject()))
                        .put("updatedAt", c.getString(11))
                }
                if (conversion?.optBoolean("verified", false) == true && conversion.optString("status") == "verified") verifiedConversions += 1

                val outcomes = JSONArray()
                db.rawQuery(
                    "SELECT outcome_id,academic_year,metric_name,metric_value,score_scale,max_score,source_name,source_url,verified,primary_reference,detail_json,observed_at FROM score_official_outcomes WHERE application_identity_key=? ORDER BY academic_year DESC,observed_at DESC",
                    arrayOf(identity)
                ).use { c ->
                    while (c.moveToNext()) {
                        outcomes.put(JSONObject()
                            .put("outcomeId", c.getString(0))
                            .put("academicYear", c.getInt(1))
                            .put("metricName", c.getString(2))
                            .put("metricValue", if (c.isNull(3)) JSONObject.NULL else c.getDouble(3))
                            .put("scoreScale", if (c.isNull(4)) JSONObject.NULL else c.getString(4))
                            .put("maxScore", if (c.isNull(5)) JSONObject.NULL else c.getDouble(5))
                            .put("sourceName", c.getString(6))
                            .put("sourceUrl", if (c.isNull(7)) JSONObject.NULL else c.getString(7))
                            .put("verified", c.getInt(8) != 0)
                            .put("primaryReference", c.getInt(9) != 0)
                            .put("detail", runCatching { JSONObject(c.getString(10)) }.getOrDefault(JSONObject()))
                            .put("observedAt", c.getString(11)))
                    }
                }
                if ((0 until outcomes.length()).any { outcomes.getJSONObject(it).optBoolean("verified") }) officialOutcomeAvailable += 1

                var prediction: JSONObject? = db.rawQuery(
                    "SELECT observed_at,provider,structured,metrics_json,source_label FROM score_prediction_snapshots WHERE application_identity_key=? ORDER BY observed_at DESC LIMIT 1",
                    arrayOf(identity)
                ).use { c ->
                    if (!c.moveToFirst()) null else JSONObject()
                        .put("observedAt", c.getString(0))
                        .put("provider", c.getString(1))
                        .put("structured", c.getInt(2) != 0)
                        .put("metrics", runCatching { JSONObject(c.getString(3)) }.getOrDefault(JSONObject()))
                        .put("sourceLabel", c.getString(4))
                }
                if (prediction == null) {
                    val collected = db.rawQuery(
                        "SELECT confirmed_at FROM jinhak_mission_coverage WHERE session_id=? AND identity_key=? AND lane='current-prediction' LIMIT 1",
                        arrayOf(sessionId, identity)
                    ).use { c -> if (c.moveToFirst()) c.getString(0) else null }
                    if (!collected.isNullOrBlank()) {
                        prediction = JSONObject()
                            .put("observedAt", collected)
                            .put("provider", "jinhak")
                            .put("structured", false)
                            .put("sourceLabel", "current-prediction mission coverage")
                            .put("status", "COLLECTED_UNSTRUCTURED")
                    }
                }
                if (prediction != null) {
                    predictionCollected += 1
                    if (prediction.optBoolean("structured", false)) structuredPredictions += 1
                }

                val evaluation = ScoreDecisionEngine.evaluate(canonicalQuality, conversion, outcomes, prediction)
                if (evaluation.optBoolean("hold", true)) decisionHolds += 1 else comparableDecisions += 1
                val reference = evaluation.optJSONObject("referenceOutcome")
                val conversionLabel = if (conversion?.optBoolean("verified", false) == true && conversion.has("scoreValue") && !conversion.isNull("scoreValue")) {
                    val value = java.math.BigDecimal.valueOf(conversion.optDouble("scoreValue")).stripTrailingZeros().toPlainString()
                    val max = if (conversion.has("maxScore") && !conversion.isNull("maxScore")) "/${java.math.BigDecimal.valueOf(conversion.optDouble("maxScore")).stripTrailingZeros().toPlainString()}" else ""
                    "대학 환산: $value$max · 검증"
                } else "대학 환산: 미확인"
                val outcomeLabel = when {
                    reference != null -> {
                        val value = java.math.BigDecimal.valueOf(reference.optDouble("metricValue")).stripTrailingZeros().toPlainString()
                        "공식 입결: ${reference.optInt("academicYear", academicYear)} ${reference.optString("metricName", "참고선")} $value"
                    }
                    outcomes.length() > 0 -> "공식 입결: ${outcomes.length()}건 · 비교 기준 미확정"
                    else -> "공식 입결: 미확인"
                }
                val predictionLabel = when {
                    prediction == null -> "진학사 예측: 미확인"
                    prediction.optBoolean("structured", false) -> prediction.optString("displayLabel").takeIf { it.isNotBlank() }
                        ?: "진학사 예측: 구조화 자료 있음"
                    else -> "진학사 예측: 수집됨 · 값 구조화 대기"
                }
                val decisionLabel = "종합: ${evaluation.optString("decisionLabel", "판정 보류")}".replace("종합: 판정 보류 ·", "종합: 판정 보류 ·")
                val row = JSONObject()
                    .put("academicYear", academicYear)
                    .put("canonicalQuality", canonicalQuality)
                    .put("conversion", conversion ?: JSONObject.NULL)
                    .put("officialOutcomes", outcomes)
                    .put("prediction", prediction ?: JSONObject.NULL)
                    .put("evaluation", evaluation)
                    .put("conversionLabel", conversionLabel)
                    .put("officialOutcomeLabel", outcomeLabel)
                    .put("predictionLabel", predictionLabel)
                    .put("decisionLabel", decisionLabel)
                val reviewCandidate = candidateById[identity] ?: JSONObject()
                val reviewInput = loadApplicationReviewInput(identity)
                    .put("applicationIdentityKey", identity)
                    .put("academicYear", reviewCandidate.optInt("academicYear", 0))
                val review = ApplicationReviewEngine.evaluate(reviewCandidate, reviewInput, fullProfile, prediction, Instant.now())
                row.put("applicationReview", review).put("predictionLabel", SameCardPrediction.label(prediction))
                val reviewInput = review.getJSONObject("input")
                if (reviewInput.has("ownScore") && !reviewInput.isNull("ownScore")) row.put("conversionLabel", "대학 환산 입력: ${reviewInput.optDouble("ownScore")} · ${if (review.optBoolean("comparisonReady")) "사용자 근거 확인" else "확인 필요"}")
                if (reviewInput.has("referenceScore") && !reviewInput.isNull("referenceScore")) row.put("officialOutcomeLabel", "입결 입력: ${reviewInput.optInt("outcomeYear")} ${reviewInput.optString("metricName")} ${reviewInput.optDouble("referenceScore")}")
                row.put("decisionLabel", "원서 검토: ${review.optString("label")}")
                byIdentity.put(identity, row)

                val cv = ContentValues().apply {
                    put("application_identity_key", identity)
                    put("decision_code", evaluation.optString("decisionCode", "UNKNOWN"))
                    put("decision_label", evaluation.optString("decisionLabel", "판정 보류"))
                    put("confidence", evaluation.optString("confidence", "INSUFFICIENT_EVIDENCE"))
                    put("result_json", evaluation.toString())
                    put("updated_at", Instant.now().toString())
                }
                writableDatabase.insertWithOnConflict("score_decision_assessments", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            }
        }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("studentProfile", if (fullProfile.optString("status") == "IMPORTED") fullProfile else studentProfile)
            .put("byIdentity", byIdentity)
            .put("summary", JSONObject()
                .put("verifiedConversions", verifiedConversions)
                .put("officialOutcomeAvailable", officialOutcomeAvailable)
                .put("comparableDecisions", comparableDecisions)
                .put("decisionHolds", decisionHolds)
                .put("predictionCollected", predictionCollected)
                .put("structuredPredictions", structuredPredictions)
                .put("probabilityInferred", false)
                .put("missingValuesDefaultToZero", false))
    }

    fun providerRunIdForUnifiedSession(sessionId: String, provider: String): String? = unifiedProviderRunId(sessionId, provider)

    fun adoptUnifiedSessionCollectorVersion(sessionId: String, collectorVersion: String) {
        if (sessionId.isBlank() || collectorVersion.isBlank()) return
        val cv = ContentValues().apply {
            put("collector_version", collectorVersion)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.update("unified_sessions", cv, "session_id=?", arrayOf(sessionId))
    }

    private fun unifiedProviderRunId(sessionId: String, provider: String): String? {
        val column = if (provider == "adiga") "adiga_run_id" else if (provider == "jinhak") "jinhak_run_id" else return null
        return readableDatabase.rawQuery(
            "SELECT $column FROM unified_sessions WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c -> if (c.moveToFirst() && !c.isNull(0)) c.getString(0) else null }
    }

    fun prepareSelectedSixRecovery(sessionId: String): JSONObject {
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

    fun rebuildCanonicalApplicationGraph(sessionId: String): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("error", "missing-session")
        val apps = CanonicalSixApplicationGraph.missionApplications(
            loadJinhakMissionTargets(sessionId),
            loadJinhakMissionCoverage(sessionId)
        )
        val adigaRunId = unifiedProviderRunId(sessionId, "adiga")
        val jinhakRunId = unifiedProviderRunId(sessionId, "jinhak")
        val byUniversity = apps.groupBy { CanonicalSixApplicationGraph.normalizeUniversityKey(it.university) }
        val matches = linkedMapOf<String, LinkedHashMap<String, JSONObject>>()
        val exactFingerprints = linkedMapOf<String, MutableSet<String>>()
        val officialStructuralFingerprints = linkedMapOf<String, MutableSet<String>>()
        val officialAdmissionEvidence = linkedMapOf<String, MutableList<JSONObject>>()

        if (!adigaRunId.isNullOrBlank() && apps.isNotEmpty()) {
            readableDatabase.rawQuery(
                "SELECT fingerprint,COALESCE(year,-1),university,department,admission,record_type FROM records WHERE run_id=? AND university IS NOT NULL",
                arrayOf(adigaRunId)
            ).use { c ->
                while (c.moveToNext()) {
                    val university = if (c.isNull(2)) null else c.getString(2)
                    val candidates = byUniversity[CanonicalSixApplicationGraph.normalizeUniversityKey(university)].orEmpty()
                    if (candidates.isEmpty()) continue
                    val year = c.getInt(1)
                    val department = if (c.isNull(3)) null else c.getString(3)
                    val admission = if (c.isNull(4)) null else c.getString(4)
                    val recordType = if (c.isNull(5)) "unknown" else c.getString(5)
                    for (app in candidates) {
                        if (year > 0 && app.year > 0 && year != app.year) continue
                        val deptQuality = CanonicalSixApplicationGraph.departmentMatchQuality(app.department, department)
                        if (deptQuality == "none" || deptQuality == "missing") continue
                        val admissionQuality = CanonicalSixApplicationGraph.admissionMatchQuality(app.admission, admission)
                        if (admissionQuality == "none") continue
                        val matchClass = if (deptQuality == "exact" && admissionQuality == "exact") "accepted" else "provisional"
                        val signature = listOf(
                            CanonicalSixApplicationGraph.normalizeUniversityKey(university),
                            CanonicalSixApplicationGraph.normalizeDepartmentKey(department),
                            CanonicalSixApplicationGraph.normalizeAdmissionKey(admission)
                        ).joinToString("|")
                        val bucket = matches.getOrPut(app.identityKey) { linkedMapOf() }
                        val row = bucket[signature]
                        if (row == null) {
                            bucket[signature] = JSONObject()
                                .put("matchClass", matchClass)
                                .put("university", university ?: JSONObject.NULL)
                                .put("department", department ?: JSONObject.NULL)
                                .put("admission", admission ?: JSONObject.NULL)
                                .put("departmentMatch", deptQuality)
                                .put("admissionMatch", admissionQuality)
                                .put("recordCount", 1)
                                .put("recordTypes", JSONArray().put(recordType))
                        } else {
                            row.put("recordCount", row.optInt("recordCount", 0) + 1)
                            val types = row.optJSONArray("recordTypes") ?: JSONArray().also { row.put("recordTypes", it) }
                            if ((0 until types.length()).none { types.optString(it) == recordType }) types.put(recordType)
                            if (row.optString("matchClass") != "accepted" && matchClass == "accepted") row.put("matchClass", "accepted")
                        }
                        if (matchClass == "accepted") exactFingerprints.getOrPut(app.identityKey) { linkedSetOf() }.add(c.getString(0))
                    }
                }
            }
        }

        if (!adigaRunId.isNullOrBlank() && apps.isNotEmpty()) {
            readableDatabase.rawQuery(
                "SELECT fingerprint,COALESCE(year,-1),university,record_type,json FROM records WHERE run_id=? AND record_type IN ('current-admission-criteria-table','historical-admission-result-table') AND university IS NOT NULL",
                arrayOf(adigaRunId)
            ).use { c ->
                while (c.moveToNext()) {
                    val recordFingerprint = c.getString(0)
                    val recordYear = c.getInt(1)
                    val university = if (c.isNull(2)) null else c.getString(2)
                    val recordType = c.getString(3)
                    val candidates = byUniversity[CanonicalSixApplicationGraph.normalizeUniversityKey(university)].orEmpty()
                    if (candidates.isEmpty()) continue
                    val record = runCatching { JSONObject(c.getString(4)) }.getOrNull() ?: continue
                    for (app in candidates) {
                        val evidence = AdigaOfficialAdmissionEvidence.inspect(
                            recordType,
                            recordYear,
                            record,
                            AdigaOfficialAdmissionEvidence.AppRef(app.year, app.university, app.department, app.admission, app.admissionCategory)
                        ).onEach { it.put("recordFingerprint", recordFingerprint) }
                        if (evidence.isNotEmpty()) {
                            officialAdmissionEvidence.getOrPut(app.identityKey) { mutableListOf() }.addAll(evidence)
                            if (evidence.any { it.optString("scope") in setOf("row-bound-current", "table-segment-current") }) {
                                officialStructuralFingerprints.getOrPut(app.identityKey) { linkedSetOf() }.add(recordFingerprint)
                            }
                        }
                    }
                }
            }
        }

        val db = writableDatabase
        db.beginTransaction()
        try {
            db.delete("canonical_applications", "session_id=?", arrayOf(sessionId))
            for (app in apps) {
                val universityId = CanonicalSixApplicationGraph.canonicalUniversityId(app.university)
                val campusId = CanonicalSixApplicationGraph.canonicalCampusId(universityId, app.campus)
                val unitId = CanonicalSixApplicationGraph.canonicalRecruitmentUnitId(universityId, app.year, app.department)
                val trackId = CanonicalSixApplicationGraph.canonicalAdmissionTrackId(unitId, app.year, app.admission, app.admissionCategory)
                val canonicalApplicationId = CanonicalSixApplicationGraph.canonicalApplicationId(app)
                val coverage = CanonicalSixApplicationGraph.coverageJson(app)
                val coverageCount = coverage.optInt("coveredCount", 0)
                val fullCoverage = coverage.optBoolean("complete", false)
                val matchRows = matches[app.identityKey]?.values?.toList().orEmpty()
                val acceptedSignatures = matchRows.count { it.optString("matchClass") == "accepted" }
                val provisionalSignatures = matchRows.count { it.optString("matchClass") == "provisional" }
                val officialEvidenceRows = officialAdmissionEvidence[app.identityKey].orEmpty()
                val rowBoundCurrent = officialEvidenceRows.count { it.optString("scope") == "row-bound-current" }
                val rowBoundRelated = officialEvidenceRows.count { it.optString("scope") == "row-bound-current-related" }
                val tableSegmentCurrent = officialEvidenceRows.count { it.optString("scope") == "table-segment-current" }
                val tableSegmentHistorical = officialEvidenceRows.count { it.optString("scope") == "table-segment-historical" }
                val currentUniversityEvidence = officialEvidenceRows.count { it.optString("scope") == "university-current" }
                val structuralCurrentEvidence = rowBoundCurrent + tableSegmentCurrent
                val bindingQuality = when {
                    acceptedSignatures == 1 -> "accepted"
                    acceptedSignatures > 1 -> "provisional"
                    structuralCurrentEvidence > 0 -> "accepted"
                    provisionalSignatures > 0 || rowBoundRelated > 0 || currentUniversityEvidence > 0 || tableSegmentHistorical > 0 -> "provisional"
                    else -> "provider-only"
                }
                val qualityState = when {
                    !fullCoverage -> "incomplete"
                    bindingQuality == "accepted" -> "accepted"
                    bindingQuality == "provisional" -> "provisional"
                    else -> "provider-only"
                }
                val bindingJson = JSONObject()
                    .put("schemaVersion", 2)
                    .put("bindingPolicyVersion", "official-structural-v2")
                    .put("officialBaseline", "adiga")
                    .put("bindingQuality", bindingQuality)
                    .put("acceptedSignatures", acceptedSignatures)
                    .put("provisionalSignatures", provisionalSignatures)
                    .put("officialRowBoundCurrent", rowBoundCurrent)
                    .put("officialRowBoundRelated", rowBoundRelated)
                    .put("officialTableSegmentCurrent", tableSegmentCurrent)
                    .put("officialTableSegmentHistorical", tableSegmentHistorical)
                    .put("officialStructuralCurrent", structuralCurrentEvidence)
                    .put("officialUniversityCurrent", currentUniversityEvidence)
                    .put("officialAdmissionEvidence", JSONArray(officialEvidenceRows.take(36)))
                    .put("matches", JSONArray(matchRows))
                    .put("sameRowRequiredForOfficialAccepted", false)
                    .put("sameRowOrExplicitTableScopeRequiredForOfficialAccepted", true)
                    .put("acceptedBindingMethods", JSONArray(listOf("same-row", "same-official-table-explicit-scope-segment")))
                    .put("doNotInferMissingBindings", true)

                if (universityId != null && app.university != null) upsertCanonicalEntity(
                    CanonicalEntity(universityId, com.admissionhub.collector.canonical.CanonicalEntityType.UNIVERSITY, null, app.university),
                    JSONObject().put("source", "jinhak-same-card-mission").put("rawLabelPreserved", true)
                )
                if (campusId != null && app.campus != null) upsertCanonicalEntity(
                    CanonicalEntity(campusId, com.admissionhub.collector.canonical.CanonicalEntityType.CAMPUS, null, app.campus, universityId),
                    JSONObject().put("source", "jinhak-same-card-mission")
                )
                if (unitId != null && app.department != null) upsertCanonicalEntity(
                    CanonicalEntity(unitId, com.admissionhub.collector.canonical.CanonicalEntityType.RECRUITMENT_UNIT, app.year, app.department, campusId ?: universityId),
                    JSONObject().put("source", "jinhak-same-card-mission").put("canonicalization", "comparison-key-only")
                )
                if (trackId != null && app.admission != null) upsertCanonicalEntity(
                    CanonicalEntity(trackId, com.admissionhub.collector.canonical.CanonicalEntityType.ADMISSION_TRACK, app.year, app.admission, unitId),
                    JSONObject().put("source", "jinhak-same-card-mission").put("admissionCategory", app.admissionCategory ?: JSONObject.NULL)
                )

                val cv = ContentValues().apply {
                    put("session_id", sessionId)
                    put("application_identity_key", app.identityKey)
                    put("canonical_application_id", canonicalApplicationId)
                    put("academic_year", app.year)
                    putNullable("canonical_university_id", universityId)
                    putNullable("canonical_campus_id", campusId)
                    putNullable("canonical_recruitment_unit_id", unitId)
                    putNullable("canonical_admission_track_id", trackId)
                    putNullable("university", app.university)
                    putNullable("campus", app.campus)
                    putNullable("department", app.department)
                    putNullable("admission", app.admission)
                    putNullable("admission_category", app.admissionCategory)
                    if (app.capacity == null) putNull("capacity") else put("capacity", app.capacity)
                    put("jinhak_confidence", app.confidence)
                    put("parse_source", app.parseSource)
                    put("coverage_json", coverage.toString())
                    put("coverage_count", coverageCount)
                    put("adiga_binding_quality", bindingQuality)
                    put("adiga_match_count", matchRows.size)
                    put("adiga_binding_json", bindingJson.toString())
                    put("quality_state", qualityState)
                    put("updated_at", Instant.now().toString())
                }
                db.insertOrThrow("canonical_applications", null, cv)

                if (!jinhakRunId.isNullOrBlank()) {
                    val update = ContentValues().apply {
                        put("quality_state", qualityState)
                        putNullable("canonical_university_id", universityId)
                        putNullable("canonical_department_id", unitId)
                        putNullable("canonical_admission_id", trackId)
                    }
                    db.update("records", update, "run_id=? AND application_identity_key=?", arrayOf(jinhakRunId, app.identityKey))
                }
                if (bindingQuality == "accepted" && !adigaRunId.isNullOrBlank()) {
                    val acceptedEvidenceFingerprints = linkedSetOf<String>().apply {
                        addAll(exactFingerprints[app.identityKey].orEmpty())
                        addAll(officialStructuralFingerprints[app.identityKey].orEmpty())
                    }
                    acceptedEvidenceFingerprints.forEach { fp ->
                        val update = ContentValues().apply {
                            put("quality_state", "accepted")
                            putNullable("canonical_university_id", universityId)
                            putNullable("canonical_department_id", unitId)
                            putNullable("canonical_admission_id", trackId)
                            put("application_identity_key", app.identityKey)
                        }
                        db.update("records", update, "run_id=? AND fingerprint=?", arrayOf(adigaRunId, fp))
                    }
                }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        val audit = refreshCanonicalQualityAudit(sessionId)
        return canonicalHubSummary(sessionId).put("rebuild", JSONObject()
            .put("missionApplications", apps.size)
            .put("qualityAuditGenerated", true)
            .put("qualityAuditPublishState", audit.optString("publishState")))
    }

    fun loadCanonicalApplicationCandidates(sessionId: String): JSONArray {
        val out = JSONArray()
        if (sessionId.isBlank()) return out
        readableDatabase.rawQuery(
            "SELECT application_identity_key,canonical_application_id,academic_year,university,campus,department,admission,admission_category,capacity,jinhak_confidence,coverage_json,adiga_binding_quality,adiga_match_count,adiga_binding_json,quality_state,updated_at FROM canonical_applications WHERE session_id=? ORDER BY university,admission,department,application_identity_key",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                out.put(JSONObject()
                    .put("applicationIdentityKey", c.getString(0))
                    .put("canonicalApplicationId", c.getString(1))
                    .put("academicYear", c.getInt(2))
                    .put("university", if (c.isNull(3)) JSONObject.NULL else c.getString(3))
                    .put("campus", if (c.isNull(4)) JSONObject.NULL else c.getString(4))
                    .put("department", if (c.isNull(5)) JSONObject.NULL else c.getString(5))
                    .put("admission", if (c.isNull(6)) JSONObject.NULL else c.getString(6))
                    .put("admissionCategory", if (c.isNull(7)) JSONObject.NULL else c.getString(7))
                    .put("capacity", if (c.isNull(8)) JSONObject.NULL else c.getInt(8))
                    .put("jinhakConfidence", c.getString(9))
                    .put("coverage", runCatching { JSONObject(c.getString(10)) }.getOrDefault(JSONObject()))
                    .put("adigaBindingQuality", c.getString(11))
                    .put("adigaMatchCount", c.getInt(12))
                    .put("adigaBinding", runCatching { JSONObject(c.getString(13)) }.getOrDefault(JSONObject()))
                    .put("qualityState", c.getString(14))
                    .put("displayLabel", CanonicalSixApplicationGraph.displayLabel(
                        if (c.isNull(3)) null else c.getString(3),
                        if (c.isNull(6)) null else c.getString(6),
                        if (c.isNull(5)) null else c.getString(5),
                        if (c.isNull(4)) null else c.getString(4)
                    ))
                    .put("updatedAt", c.getString(15)))
            }
        }
        return out
    }

    fun loadHubApplicationSlots(): JSONArray {
        val rows = linkedMapOf<Int, JSONObject>()
        readableDatabase.rawQuery(
            "SELECT slot,canonical_application_id,application_identity_key,display_label,user_pinned,updated_at FROM hub_application_slots ORDER BY slot",
            emptyArray()
        ).use { c ->
            while (c.moveToNext()) rows[c.getInt(0)] = JSONObject()
                .put("slot", c.getInt(0))
                .put("occupied", true)
                .put("canonicalApplicationId", c.getString(1))
                .put("applicationIdentityKey", c.getString(2))
                .put("displayLabel", c.getString(3))
                .put("userPinned", c.getInt(4) != 0)
                .put("updatedAt", c.getString(5))
        }
        val out = JSONArray()
        for (slot in 1..CanonicalSixApplicationGraph.SLOT_COUNT) {
            out.put(rows[slot] ?: JSONObject().put("slot", slot).put("occupied", false).put("userPinned", false))
        }
        return out
    }

    fun setHubApplicationSlot(sessionId: String, slot: Int, identityKey: String): JSONObject {
        require(slot in 1..CanonicalSixApplicationGraph.SLOT_COUNT) { "slot out of range" }
        val candidate = readableDatabase.rawQuery(
            "SELECT canonical_application_id,university,admission,department,campus FROM canonical_applications WHERE session_id=? AND application_identity_key=? LIMIT 1",
            arrayOf(sessionId, identityKey)
        ).use { c ->
            if (!c.moveToFirst()) null else JSONObject()
                .put("canonicalApplicationId", c.getString(0))
                .put("university", if (c.isNull(1)) JSONObject.NULL else c.getString(1))
                .put("admission", if (c.isNull(2)) JSONObject.NULL else c.getString(2))
                .put("department", if (c.isNull(3)) JSONObject.NULL else c.getString(3))
                .put("campus", if (c.isNull(4)) JSONObject.NULL else c.getString(4))
        } ?: return JSONObject().put("ok", false).put("error", "candidate-not-found")

        fun existingSlotRow(db: SQLiteDatabase, targetSlot: Int): JSONObject? = db.rawQuery(
            "SELECT canonical_application_id,application_identity_key,display_label,user_pinned,updated_at FROM hub_application_slots WHERE slot=? LIMIT 1",
            arrayOf(targetSlot.toString())
        ).use { c -> if (!c.moveToFirst()) null else JSONObject()
            .put("canonicalApplicationId", c.getString(0))
            .put("applicationIdentityKey", c.getString(1))
            .put("displayLabel", c.getString(2))
            .put("userPinned", c.getInt(3) != 0)
            .put("updatedAt", c.getString(4)) }

        val db = writableDatabase
        db.beginTransaction()
        try {
            val currentAtTarget = existingSlotRow(db, slot)
            val duplicateSlot = db.rawQuery(
                "SELECT slot FROM hub_application_slots WHERE application_identity_key=? LIMIT 1",
                arrayOf(identityKey)
            ).use { c -> if (c.moveToFirst()) c.getInt(0) else null }
            if (duplicateSlot != null && duplicateSlot != slot) {
                if (currentAtTarget == null) {
                    db.delete("hub_application_slots", "slot=?", arrayOf(duplicateSlot.toString()))
                } else {
                    val moved = ContentValues().apply {
                        put("slot", duplicateSlot)
                        put("canonical_application_id", currentAtTarget.getString("canonicalApplicationId"))
                        put("application_identity_key", currentAtTarget.getString("applicationIdentityKey"))
                        put("display_label", currentAtTarget.getString("displayLabel"))
                        put("user_pinned", 1)
                        put("updated_at", Instant.now().toString())
                    }
                    db.insertWithOnConflict("hub_application_slots", null, moved, SQLiteDatabase.CONFLICT_REPLACE)
                }
            }
            val display = CanonicalSixApplicationGraph.displayLabel(
                candidate.optString("university").takeIf { it.isNotBlank() && it != "null" },
                candidate.optString("admission").takeIf { it.isNotBlank() && it != "null" },
                candidate.optString("department").takeIf { it.isNotBlank() && it != "null" },
                candidate.optString("campus").takeIf { it.isNotBlank() && it != "null" }
            )
            val cv = ContentValues().apply {
                put("slot", slot)
                put("canonical_application_id", candidate.getString("canonicalApplicationId"))
                put("application_identity_key", identityKey)
                put("display_label", display)
                put("user_pinned", 1)
                put("updated_at", Instant.now().toString())
            }
            db.insertWithOnConflict("hub_application_slots", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        val audit = refreshCanonicalQualityAudit(sessionId)
        return JSONObject().put("ok", true).put("slot", slot).put("qualityAudit", audit)
    }

    fun clearHubApplicationSlot(sessionId: String, slot: Int): JSONObject {
        require(slot in 1..CanonicalSixApplicationGraph.SLOT_COUNT) { "slot out of range" }
        writableDatabase.delete("hub_application_slots", "slot=?", arrayOf(slot.toString()))
        return JSONObject().put("ok", true).put("slot", slot).put("qualityAudit", refreshCanonicalQualityAudit(sessionId))
    }

    fun refreshCanonicalQualityAudit(sessionId: String): JSONObject {
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val byIdentity = linkedMapOf<String, JSONObject>()
        var accepted = 0
        var provisional = 0
        var providerOnly = 0
        var incomplete = 0
        var fullCoverage = 0
        for (i in 0 until candidates.length()) {
            val item = candidates.optJSONObject(i) ?: continue
            byIdentity[item.optString("applicationIdentityKey")] = item
            if (item.optJSONObject("coverage")?.optBoolean("complete", false) == true) fullCoverage += 1
            when (item.optString("qualityState")) {
                "accepted" -> accepted += 1
                "provisional" -> provisional += 1
                "provider-only" -> providerOnly += 1
                else -> incomplete += 1
            }
        }
        val slots = loadHubApplicationSlots()
        var selected = 0
        var resolvable = 0
        var selectedFullCoverage = 0
        var selectedAccepted = 0
        var selectedProvisional = 0
        var selectedProviderOnly = 0
        val selectedIdentities = linkedSetOf<String>()
        val staleSlots = JSONArray()
        for (i in 0 until slots.length()) {
            val slot = slots.optJSONObject(i) ?: continue
            if (!slot.optBoolean("occupied", false)) continue
            selected += 1
            val identity = slot.optString("applicationIdentityKey")
            if (identity.isNotBlank()) selectedIdentities += identity
            val candidate = byIdentity[identity]
            if (candidate == null) {
                staleSlots.put(slot.optInt("slot"))
                continue
            }
            resolvable += 1
            if (candidate.optJSONObject("coverage")?.optBoolean("complete", false) == true) selectedFullCoverage += 1
            when (candidate.optString("qualityState")) {
                "accepted" -> selectedAccepted += 1
                "provisional" -> selectedProvisional += 1
                "provider-only" -> selectedProviderOnly += 1
            }
        }
        val blockers = JSONArray()
        if (selected < CanonicalSixApplicationGraph.SLOT_COUNT) blockers.put("six-application-selection-incomplete")
        if (selectedIdentities.size != selected) blockers.put("duplicate-application-slot")
        if (staleSlots.length() > 0) blockers.put("stale-slot-binding")
        if (selectedFullCoverage < selected) blockers.put("selected-application-core-coverage-incomplete")
        val repairNeededCandidates = (candidates.length() - fullCoverage).coerceAtLeast(0)
        val warnings = JSONArray()
        if (repairNeededCandidates > 0) warnings.put("candidate-core-coverage-incomplete")
        if (selectedProvisional > 0) warnings.put("selected-provisional-adiga-binding")
        if (selectedProviderOnly > 0) warnings.put("selected-provider-only-no-safe-adiga-binding")
        val observations = observationStats(sessionId)
        if (observations.optInt("unknownOrPotential", 0) > 0) warnings.put("unclassified-observations-preserved")
        val hubReady = selected == CanonicalSixApplicationGraph.SLOT_COUNT &&
            selectedIdentities.size == CanonicalSixApplicationGraph.SLOT_COUNT &&
            resolvable == CanonicalSixApplicationGraph.SLOT_COUNT &&
            selectedFullCoverage == CanonicalSixApplicationGraph.SLOT_COUNT
        val publishState = when {
            !hubReady && selected < CanonicalSixApplicationGraph.SLOT_COUNT -> "WAITING_FOR_USER_SELECTION"
            !hubReady -> "BLOCKED_QUALITY"
            selectedProvisional > 0 || selectedProviderOnly > 0 -> "READY_WITH_WARNINGS"
            else -> "READY"
        }
        val audit = JSONObject()
            .put("schemaVersion", 1)
            .put("generatedAt", Instant.now().toString())
            .put("candidateCount", candidates.length())
            .put("fullCoreCoverageCandidates", fullCoverage)
            .put("repairNeededCandidates", repairNeededCandidates)
            .put("candidateQuality", JSONObject()
                .put("accepted", accepted)
                .put("provisional", provisional)
                .put("providerOnly", providerOnly)
                .put("incomplete", incomplete))
            .put("sixSlots", JSONObject()
                .put("required", CanonicalSixApplicationGraph.SLOT_COUNT)
                .put("selected", selected)
                .put("uniqueSelected", selectedIdentities.size)
                .put("resolvable", resolvable)
                .put("fullCoreCoverage", selectedFullCoverage)
                .put("accepted", selectedAccepted)
                .put("provisional", selectedProvisional)
                .put("providerOnly", selectedProviderOnly)
                .put("staleSlots", staleSlots)
                .put("userControlled", true)
                .put("externalCollectionMayMutate", false))
            .put("hubReady", hubReady)
            .put("publishState", publishState)
            .put("blockers", blockers)
            .put("warnings", warnings)
            .put("observationCoverage", observations)
            .put("predictionDoesNotOverwriteHistoricalActual", true)
            .put("officialBindingPolicy", "same-row-or-explicit-same-table-scope")
            .put("doNotInferMissingBindings", true)
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            put("audit_json", audit.toString())
            put("generated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("hub_quality_audits", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        return audit
    }

    fun canonicalApplicationCount(sessionId: String?): Int {
        if (sessionId.isNullOrBlank()) return 0
        return readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM canonical_applications WHERE session_id=?",
            arrayOf(sessionId)
        ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
    }

    fun pinnedHubSlotCount(): Int = readableDatabase.rawQuery(
        "SELECT COUNT(*) FROM hub_application_slots WHERE user_pinned=1",
        emptyArray()
    ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }

    /**
     * Returns the newest canonical session that can resolve every currently pinned Hub slot.
     * This deliberately prefers preserved local evidence over starting a new browser mission.
     */
    fun latestReusableCanonicalSessionId(): String? {
        val pinned = pinnedHubSlotCount()
        val candidates = mutableListOf<String>()
        readableDatabase.rawQuery(
            "SELECT session_id,COUNT(*),MAX(updated_at) FROM canonical_applications GROUP BY session_id HAVING COUNT(*)>=6 ORDER BY MAX(updated_at) DESC",
            emptyArray()
        ).use { c -> while (c.moveToNext()) candidates += c.getString(0) }
        for (sessionId in candidates) {
            if (pinned <= 0) return sessionId
            val matched = readableDatabase.rawQuery(
                "SELECT COUNT(*) FROM canonical_applications WHERE session_id=? AND application_identity_key IN (SELECT application_identity_key FROM hub_application_slots WHERE user_pinned=1)",
                arrayOf(sessionId)
            ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
            if (matched == pinned) return sessionId
        }
        return null
    }

    fun localRebindDecision(): JSONObject {
        val latest = latestUnifiedSession()
        val reusable = latestReusableCanonicalSessionId()
        val latestCandidates = canonicalApplicationCount(latest)
        val reusableCandidates = canonicalApplicationCount(reusable)
        val latestStatus = if (latest.isNullOrBlank()) "none" else readableDatabase.rawQuery(
            "SELECT status FROM unified_sessions WHERE session_id=? LIMIT 1",
            arrayOf(latest)
        ).use { c -> if (c.moveToFirst()) c.getString(0) else "unknown" }
        val pinned = pinnedHubSlotCount()
        val input = LocalRebindPolicy.Input(
            pinnedSlots = pinned,
            reusableCandidateCount = reusableCandidates,
            latestCandidateCount = latestCandidates,
            latestStatus = latestStatus,
            latestIsReusableSource = !latest.isNullOrBlank() && latest == reusable
        )
        return JSONObject()
            .put("schemaVersion", 1)
            .put("pinnedSlots", pinned)
            .put("latestSessionId", latest ?: JSONObject.NULL)
            .put("latestSessionStatus", latestStatus)
            .put("latestCandidateCount", latestCandidates)
            .put("reusableSessionId", reusable ?: JSONObject.NULL)
            .put("reusableCandidateCount", reusableCandidates)
            .put("preferLocalRebind", LocalRebindPolicy.preferLocalRebind(input))
            .put("suppressInterruptedBrowserResume", LocalRebindPolicy.suppressInterruptedBrowserResume(input))
            .put("providerNetworkRequired", false)
            .put("credentialsRead", false)
            .put("sessionSecretsRead", false)
    }

    private fun canonicalSessionForExactPinnedRebind(sessionId: String): String {
        if (sessionId.isBlank()) return sessionId
        val pinned = pinnedHubSlotCount()
        if (pinned <= 0) return sessionId
        val matchedCurrent = readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM canonical_applications WHERE session_id=? AND application_identity_key IN (SELECT application_identity_key FROM hub_application_slots WHERE user_pinned=1)",
            arrayOf(sessionId)
        ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        if (matchedCurrent == pinned) return sessionId
        return latestReusableCanonicalSessionId() ?: sessionId
    }

    fun canonicalHubSummary(sessionId: String): JSONObject {
        val canonicalEvidenceSessionId = canonicalSessionForExactPinnedRebind(sessionId)
        val candidates = loadCanonicalApplicationCandidates(canonicalEvidenceSessionId)
        val slots = loadHubApplicationSlots()
        val audit = readableDatabase.rawQuery(
            "SELECT audit_json FROM hub_quality_audits WHERE session_id=? LIMIT 1",
            arrayOf(canonicalEvidenceSessionId)
        ).use { c ->
            if (c.moveToFirst()) runCatching { JSONObject(c.getString(0)) }.getOrNull() else null
        } ?: refreshCanonicalQualityAudit(sessionId)
        return JSONObject()
            .put("schemaVersion", 1)
            .put("candidateGraph", candidates)
            .put("canonicalEvidenceSessionId", canonicalEvidenceSessionId)
            .put("slots", slots)
            .put("qualityAudit", audit)
            .put("selectedRecoveryPlan", selectedSixRecoveryPlan(canonicalEvidenceSessionId))
            .put("crossSessionContinuity", localRebindDecision())
            .put("slotPolicy", JSONObject()
                .put("slots", CanonicalSixApplicationGraph.SLOT_COUNT)
                .put("userControlsAddChangeReplaceOrder", true)
                .put("externalCollectionAutoSelection", false))
    }

    private fun nullableInt(obj: JSONObject, key: String): Int? =
        if (!obj.has(key) || obj.isNull(key)) null else obj.optInt(key).takeIf { it != 0 }

    private fun nullableString(obj: JSONObject, key: String): String? =
        if (!obj.has(key) || obj.isNull(key)) null else obj.optString(key).trim().takeIf { it.isNotBlank() }

    private fun ContentValues.putNullable(key: String, value: String?) {
        if (value == null) putNull(key) else put(key, value)
    }
}
