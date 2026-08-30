from pathlib import Path

ROOT = Path('.')
MAIN_PATHS = [
    ROOT / 'MainActivity.kt',
    ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt',
]
COORD = ROOT / 'app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadCoordinator.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
BUILD = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'anchor not found: {label}')
    return text.replace(old, new, 1)


# Local store: add compact, privacy-safe diagnostic snapshot.
s = STORE.read_text()
anchor = '''    fun latestResumableRun(provider: String): String? = readableDatabase.rawQuery(
        "SELECT run_id FROM runs WHERE provider=? AND status IN ('collecting','stopped','incomplete') ORDER BY updated_at DESC LIMIT 1",
        arrayOf(provider)
    ).use { c -> if (c.moveToFirst()) c.getString(0) else null }
'''
replacement = anchor + '''
    fun latestRun(provider: String): String? = readableDatabase.rawQuery(
        "SELECT run_id FROM runs WHERE provider=? ORDER BY updated_at DESC LIMIT 1",
        arrayOf(provider)
    ).use { c -> if (c.moveToFirst()) c.getString(0) else null }
'''
s = replace_once(s, anchor, replacement, 'latestRun')

anchor = '''    fun stats(runId: String): JSONObject {
        fun scalar(sql: String): Int = readableDatabase.rawQuery(sql, arrayOf(runId)).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        return JSONObject()
            .put("runId", runId)
            .put("records", scalar("SELECT COUNT(*) FROM records WHERE run_id=?"))
            .put("completedPages", scalar("SELECT COUNT(*) FROM pages WHERE run_id=? AND state='completed'"))
            .put("errorPages", scalar("SELECT COUNT(*) FROM pages WHERE run_id=? AND state='error'"))
            .put("completedDocuments", scalar("SELECT COUNT(*) FROM documents WHERE run_id=? AND state='completed'"))
            .put("errorDocuments", scalar("SELECT COUNT(*) FROM documents WHERE run_id=? AND state='error'"))
            .put("unresolved", unresolvedCount(runId))
    }
'''
replacement = anchor + '''

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
'''
s = replace_once(s, anchor, replacement, 'diagnosticSnapshot')
STORE.write_text(s)

# Cloud coordinator: one-shot diagnostic channel, separate from active admission run state.
s = COORD.read_text()
anchor = '''    fun status(callback: (Result<JSONObject>) -> Unit) {
        val runId = synchronized(lock) { activeRunId }
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (runId.isNullOrBlank() || currentClient == null) {
            callback(Result.failure(IllegalStateException("No active cloud run")))
            return
        }
        currentClient.getStatus(runId, callback)
    }
'''
replacement = anchor + '''

    /**
     * Sends only a compact operational diagnostic after local collection.
     * It uses a separate provider/run and does not change activeRunId or upload admission records.
     */
    fun sendDiagnostic(
        sourceProvider: String,
        collectorVersion: String,
        diagnostic: JSONObject,
        callback: (Result<String>) -> Unit = {}
    ) {
        if (!isConfigured()) {
            callback(Result.failure(IllegalStateException("Diagnostic cloud channel is not configured")))
            return
        }
        val diagnosticProvider = (sourceProvider.take(24) + "-diagnostic").take(40)
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (currentClient == null) {
            callback(Result.failure(IllegalStateException("Diagnostic client unavailable")))
            return
        }

        fun upload(runId: String) {
            val payload = JSONObject(diagnostic.toString())
                .put("type", "local-diagnostic")
                .put("sourceProvider", sourceProvider)
                .put("collectorVersion", collectorVersion)
            currentClient.uploadChunk(
                runId = runId,
                provider = diagnosticProvider,
                records = JSONArray(),
                page = null,
                error = payload
            ) { result ->
                if (result.isSuccess) callback(Result.success(runId))
                else callback(Result.failure(result.exceptionOrNull() ?: IllegalStateException("diagnostic upload failed")))
            }
        }

        currentClient.getLatestActiveRun(diagnosticProvider) { lookup ->
            val existing = lookup.getOrNull()
            if (!existing.isNullOrBlank()) {
                upload(existing)
                return@getLatestActiveRun
            }
            currentClient.createRun(
                provider = diagnosticProvider,
                collectorVersion = collectorVersion,
                metadata = JSONObject()
                    .put("client", "android")
                    .put("mode", "diagnostic-only")
                    .put("containsAdmissionRecords", false)
            ) { created ->
                val runId = created.getOrNull()
                if (runId == null) {
                    callback(Result.failure(created.exceptionOrNull() ?: lookup.exceptionOrNull() ?: IllegalStateException("diagnostic run creation failed")))
                } else upload(runId)
            }
        }
    }
'''
s = replace_once(s, anchor, replacement, 'sendDiagnostic')
COORD.write_text(s)

# Main activity: version, UI button, manual and automatic diagnostic send.
for path in MAIN_PATHS:
    s = path.read_text()
    s = replace_once(s,
        '        private const val VERSION = "0.4.2"\n        private const val BUILD_CODE = 10420\n',
        '        private const val VERSION = "0.4.3"\n        private const val BUILD_CODE = 10430\n',
        f'version {path}')

    anchor = '''        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(localState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        status = TextView(this).apply {
'''
    replacement = '''        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(localState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val actions3 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val diagnostic = Button(this).apply {
            text = "진단 로그 전송"
            setOnClickListener { sendLatestLocalDiagnostic(manual = true) }
        }
        actions3.addView(diagnostic, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        status = TextView(this).apply {
'''
    s = replace_once(s, anchor, replacement, f'diagnostic button {path}')
    s = replace_once(s,
        '        root.addView(actions2)\n        root.addView(status)\n',
        '        root.addView(actions2)\n        root.addView(actions3)\n        root.addView(status)\n',
        f'actions3 row {path}')

    anchor = '''    private fun finishBatch(reason: String) {
'''
    helper = '''    private fun sendLatestLocalDiagnostic(manual: Boolean) {
        val runId = localRunId ?: localStore.latestRun(provider.wireName)
        if (runId.isNullOrBlank()) {
            if (manual) Toast.makeText(this, "전송할 로컬 수집 로그가 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        val diagnostic = localStore.diagnosticSnapshot(runId)
            .put("trigger", if (manual) "manual" else "batch-finish")
            .put("segment", JSONObject()
                .put("attemptedPages", batchPageCount)
                .put("successfulSnapshots", batchSnapshots.length())
                .put("errorEvents", batchErrors.length())
                .put("paginationActionsCompleted", batchPageActionVisited.size)
                .put("paginationActionsFailed", batchPageActionFailed.size)
                .put("paginationRetries", batchPaginationRetries)
                .put("localPagesScheduled", batchLocalPagesScheduled)
                .put("localPagesSkipped", batchLocalPagesSkipped)
                .put("localRecordsPersisted", batchLocalRecordsPersisted))
        if (manual) status.text = "진단 로그 전송 중… 원본 입시자료는 전송하지 않습니다."
        cloudOffload.sendDiagnostic(provider.wireName, VERSION, diagnostic) { result ->
            runOnUiThread {
                if (result.isSuccess) {
                    val id = result.getOrNull()?.take(8) ?: "unknown"
                    status.text = "진단 로그 전송 완료: $id… / 원본 레코드·로그인 정보 미전송"
                    if (manual) Toast.makeText(this, "진단 로그 전송 완료", Toast.LENGTH_SHORT).show()
                } else if (manual) {
                    status.text = "진단 로그 전송 실패: ${result.exceptionOrNull()?.message ?: "unknown"}"
                    Toast.makeText(this, "진단 로그 전송 실패", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

'''
    s = replace_once(s, anchor, helper + anchor, f'diagnostic helper {path}')

    anchor = '''        finalizeBatchJson(effectiveReason)
        if (!LOCAL_FIRST_BETA && effectiveReason == "completed" && batchCloudPagesDeferred == 0) {
'''
    replacement = '''        finalizeBatchJson(effectiveReason)
        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            // Telemetry is sent only after the crawl has stopped, never per page.
            sendLatestLocalDiagnostic(manual = false)
        }
        if (!LOCAL_FIRST_BETA && effectiveReason == "completed" && batchCloudPagesDeferred == 0) {
'''
    s = replace_once(s, anchor, replacement, f'auto diagnostic {path}')
    path.write_text(s)

b = BUILD.read_text()
b = replace_once(b,
    '        versionCode = 10420\n        versionName = "0.4.2"\n',
    '        versionCode = 10430\n        versionName = "0.4.3"\n',
    'gradle version')
BUILD.write_text(b)

m = MANIFEST.read_text()
m = replace_once(m,
    'android:label="Admission Collector v0.4.2 Local"',
    'android:label="Admission Collector v0.4.3 Local"',
    'manifest label')
MANIFEST.write_text(m)

print('v0.4.3 lightweight diagnostic telemetry patch applied')
