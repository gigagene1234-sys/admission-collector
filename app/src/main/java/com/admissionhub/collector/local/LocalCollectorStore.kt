package com.admissionhub.collector.local

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
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
    3
) {
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

    fun unifiedStatus(sessionId: String): JSONObject {
        val out = JSONObject().put("sessionId", sessionId)
        var adigaRun: String? = null
        var jinhakRun: String? = null
        readableDatabase.rawQuery(
            "SELECT collector_version,status,phase,adiga_run_id,jinhak_run_id,completion_reason,started_at,updated_at FROM unified_sessions WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c ->
            if (c.moveToFirst()) {
                out.put("collectorVersion", c.getString(0))
                    .put("status", c.getString(1))
                    .put("phase", c.getString(2))
                    .put("completionReason", if (c.isNull(5)) JSONObject.NULL else c.getString(5))
                    .put("startedAt", c.getString(6))
                    .put("updatedAt", c.getString(7))
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
