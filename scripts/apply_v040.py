from pathlib import Path

ROOT = Path('.')
MAIN_PATHS = [
    ROOT / 'MainActivity.kt',
    ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt',
]
ADIGA = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/AdigaAdapter.kt'
SNAPSHOT = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
LOCAL_STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
BUILD = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'anchor not found: {label}')
    return text.replace(old, new, 1)


LOCAL_STORE.parent.mkdir(parents=True, exist_ok=True)
LOCAL_STORE.write_text(r'''package com.admissionhub.collector.local

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
    1
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
              json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(run_id, fingerprint)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX idx_runs_provider_status ON runs(provider,status,updated_at)")
        db.execSQL("CREATE INDEX idx_pages_run_state ON pages(run_id,state)")
        db.execSQL("CREATE INDEX idx_documents_run_state ON documents(run_id,state)")
        db.execSQL("CREATE INDEX idx_records_run_year ON records(run_id,year)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun beginOrResume(provider: String, collectorVersion: String): String {
        val db = writableDatabase
        val existing = db.rawQuery(
            "SELECT run_id FROM runs WHERE provider=? AND status IN ('collecting','stopped','incomplete') ORDER BY updated_at DESC LIMIT 1",
            arrayOf(provider)
        ).use { c -> if (c.moveToFirst()) c.getString(0) else null }
        val now = Instant.now().toString()
        if (!existing.isNullOrBlank()) {
            val cv = ContentValues().apply {
                put("collector_version", collectorVersion)
                put("status", "collecting")
                putNull("completion_reason")
                put("updated_at", now)
            }
            db.update("runs", cv, "run_id=?", arrayOf(existing))
            return existing
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
            .put("completedPages", scalar("SELECT COUNT(*) FROM pages WHERE run_id=? AND state='completed'"))
            .put("errorPages", scalar("SELECT COUNT(*) FROM pages WHERE run_id=? AND state='error'"))
            .put("completedDocuments", scalar("SELECT COUNT(*) FROM documents WHERE run_id=? AND state='completed'"))
            .put("errorDocuments", scalar("SELECT COUNT(*) FROM documents WHERE run_id=? AND state='error'"))
            .put("unresolved", unresolvedCount(runId))
    }

    private fun nullableInt(obj: JSONObject, key: String): Int? =
        if (!obj.has(key) || obj.isNull(key)) null else obj.optInt(key).takeIf { it != 0 }

    private fun nullableString(obj: JSONObject, key: String): String? =
        if (!obj.has(key) || obj.isNull(key)) null else obj.optString(key).trim().takeIf { it.isNotBlank() }

    private fun ContentValues.putNullable(key: String, value: String?) {
        if (value == null) putNull(key) else put(key, value)
    }
}
''')

# MainActivity: preserve the v0.3.9 engine, but route Adiga batch state through local SQLite.
for path in MAIN_PATHS:
    s = path.read_text()
    s = s.replace('import com.admissionhub.collector.cloud.CloudOffloadCoordinator\n', 'import com.admissionhub.collector.cloud.CloudOffloadCoordinator\nimport com.admissionhub.collector.local.LocalCollectorStore\n')
    s = s.replace('    private lateinit var cloudOffload: CloudOffloadCoordinator\n', '    private lateinit var cloudOffload: CloudOffloadCoordinator\n    private lateinit var localStore: LocalCollectorStore\n')
    s = s.replace('    private var batchCloudFinalCheckInProgress = false\n', '''    private var batchCloudFinalCheckInProgress = false
    private var batchLocalResumePlans = 0
    private var batchLocalPagesScheduled = 0
    private var batchLocalPagesSkipped = 0
    private var batchLocalRecordsPersisted = 0
    private var localRunId: String? = null
''')
    s = s.replace('        private const val MAX_BATCH_PAGES = 2000\n', '        private const val MAX_BATCH_PAGES = 3200\n')
    s = s.replace('        private const val MAX_PAGE_RETRIES = 2\n', '        private const val MAX_PAGE_RETRIES = 3\n')
    s = s.replace('        private const val VERSION = "0.3.9"\n', '        private const val VERSION = "0.4.0"\n        private const val BUILD_CODE = 10400\n        private const val LOCAL_FIRST_BETA = true\n')
    s = replace_once(s,
        '        cloudOffload = CloudOffloadCoordinator(this)\n        buildUi()\n',
        '        cloudOffload = CloudOffloadCoordinator(this)\n        localStore = LocalCollectorStore(this)\n        buildUi()\n',
        f'localStore init {path}')
    s = s.replace('            text = "Admission Collector v$VERSION · build 10039"', '            text = "Admission Collector v$VERSION · build $BUILD_CODE · LOCAL-FIRST"')

    old_cloud_button = '''        val cloudSettings = Button(this).apply {
            text = "Cloud 설정"
            setOnClickListener {
                cloudOffload.showSettingsDialog(this@MainActivity) {
                    status.text = if (cloudOffload.isConfigured()) {
                        "Cloudflare Offload 설정됨"
                    } else {
                        "Cloudflare Offload 미설정: 로컬 수집 모드"
                    }
                }
            }
        }
        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(cloudSettings, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
'''
    new_local_button = '''        val localState = Button(this).apply {
            text = "로컬 진행상태"
            setOnClickListener {
                val runId = localRunId ?: localStore.latestResumableRun(provider.wireName)
                val message = if (runId == null) {
                    "현재 이어받을 로컬 수집이 없습니다."
                } else {
                    localStore.stats(runId).toString(2)
                }
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Local-First 저장 상태")
                    .setMessage(message)
                    .setPositiveButton("확인", null)
                    .show()
            }
        }
        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(localState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
'''
    s = replace_once(s, old_cloud_button, new_local_button, f'local state button {path}')

    # Reset local counters with the existing batch counters.
    s = replace_once(s,
        '        batchCloudFinalCheckInProgress = false\n        disarmBatchNavigationWatchdog()\n        currentBatchTarget = canonicalizeBatchUrl(url)\n',
        '''        batchCloudFinalCheckInProgress = false
        batchLocalResumePlans = 0
        batchLocalPagesScheduled = 0
        batchLocalPagesSkipped = 0
        batchLocalRecordsPersisted = 0
        disarmBatchNavigationWatchdog()
        currentBatchTarget = canonicalizeBatchUrl(url)
''', f'local reset {path}')

    old_start_tail = '''        batchButton.text = "일괄 수집 중지"
        status.text = if (cloudOffload.isConfigured()) {
            "Cloud 체크포인트 연결 준비 중…"
        } else {
            "Cloud 토큰 미설정: 로컬 안전모드로 수집 시작"
        }
        cloudOffload.beginOrResume(provider.wireName, VERSION) { runId ->
            runOnUiThread {
                if (!batchRunning) return@runOnUiThread
                prepareCloudRecoveryAndStart(runId)
            }
        }
'''
    new_start_tail = '''        batchButton.text = "일괄 수집 중지"
        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            localRunId = localStore.beginOrResume(provider.wireName, VERSION)
            status.text = "Local-First 수집 시작: Cloudflare 호출 없음 / run ${localRunId?.take(8)}…"
            beginBatchNavigation(null)
        } else {
            status.text = "현재 공급자는 로컬 단일 페이지 모드"
            beginBatchNavigation(null)
        }
'''
    s = replace_once(s, old_start_tail, new_start_tail, f'local start {path}')

    # On manual stop, persist resumable run state.
    s = replace_once(s,
        '        status.text = "일괄 수집 중지: $reason"\n        if (batchSnapshots.length() > 0) finalizeBatchJson("stopped")\n',
        '''        status.text = "일괄 수집 중지: $reason"
        localRunId?.let { localStore.markRun(it, "stopped", reason) }
        if (batchSnapshots.length() > 0 || localRunId != null) finalizeBatchJson("stopped")
''', f'stop persist {path}')

    # Error path: persist document/page error locally instead of uploading it.
    old_error_upload = '''                batchErrors.put(error)
                cloudOffload.uploadError(
                    provider = provider.wireName,
                    familyKey = activeAction?.familyKey,
                    requestedYear = activeAction?.requestedYear,
                    page = activeAction?.page,
                    retryCount = activeAction?.retry ?: 0,
                    error = error
                )
'''
    new_error_store = '''                batchErrors.put(error)
                localRunId?.let { runId ->
                    val key = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                    localStore.markDocument(runId, key, "error", activeAction?.retry ?: 0, errorType)
                    if (activeAction != null) {
                        localStore.markPage(
                            runId, activeAction.familyKey, activeAction.requestedYear,
                            activeAction.page, activeAction.totalPages, "error", activeAction.retry, errorType
                        )
                    }
                }
'''
    s = replace_once(s, old_error_upload, new_error_store, f'error local store {path}')

    # Success path: local records + local page/document checkpoints; no cloud upload.
    old_success_upload = '''            val pageRecords = normalizeSnapshot(snapshot)
            RecordUtils.appendUniqueRecords(batchRecords, pageRecords)
            cloudOffload.uploadPage(
                provider = provider.wireName,
                records = pageRecords,
                familyKey = activeAction?.familyKey ?: plan?.familyKey,
                requestedYear = activeAction?.requestedYear ?: plan?.requestedYear,
                page = activeAction?.page ?: if (plan != null) 1 else null,
                retryCount = activeAction?.retry ?: 0
            )
            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())
'''
    new_success_store = '''            val pageRecords = normalizeSnapshot(snapshot)
            RecordUtils.appendUniqueRecords(batchRecords, pageRecords)
            localRunId?.let { runId ->
                batchLocalRecordsPersisted += localStore.storeRecords(runId, provider.wireName, pageRecords)
                val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                localStore.markDocument(runId, navKey, "completed")
                when {
                    activeAction != null -> localStore.markPage(
                        runId, activeAction.familyKey, activeAction.requestedYear,
                        activeAction.page, activeAction.totalPages, "completed", activeAction.retry
                    )
                    plan != null -> localStore.markPage(
                        runId, plan.familyKey, plan.requestedYear,
                        1, plan.totalPages, "completed", 0
                    )
                }
            }
            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())
'''
    s = replace_once(s, old_success_upload, new_success_store, f'success local store {path}')

    # End of queue uses local completion instead of Cloud verification.
    s = s.replace('        verifyCloudCompletionOrFinish()\n    }\n\n    private fun verifyCloudCompletionOrFinish', '''        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) verifyLocalCompletionOrFinish()
        else verifyCloudCompletionOrFinish()
    }

    private fun verifyLocalCompletionOrFinish() {
        if (!batchRunning || batchPausedForLogin) return
        val runId = localRunId
        if (runId == null) {
            finishBatch("completed")
            return
        }
        val unresolved = localStore.unresolvedCount(runId)
        if (unresolved > 0) finishBatch("completed-with-local-errors")
        else finishBatch("completed")
    }

    private fun verifyCloudCompletionOrFinish''')

    # Terminal pagination failure is a local page checkpoint.
    old_record_failure = '''        batchErrors.put(error)
        cloudOffload.uploadError(
            provider = provider.wireName,
            familyKey = action.familyKey,
            requestedYear = action.requestedYear,
            page = action.page,
            retryCount = action.retry,
            error = error
        )
'''
    new_record_failure = '''        batchErrors.put(error)
        localRunId?.let { runId ->
            localStore.markPage(
                runId, action.familyKey, action.requestedYear,
                action.page, action.totalPages, "error", action.retry, type
            )
            localStore.markDocument(runId, canonicalizeBatchUrl(action.baseUrl), "error", action.retry, type)
        }
'''
    s = replace_once(s, old_record_failure, new_record_failure, f'pagination failure local {path}')

    # Local resume plan before old Cloud branch.
    old_plan_gate = '''        if (!cloudOffload.isConfigured()) {
            enqueuePageActions(baseUrl, plan, (2..plan.totalPages).toList())
            return
        }
'''
    new_plan_gate = '''        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            val runId = localRunId
            if (runId == null) {
                enqueuePageActions(baseUrl, plan, (2..plan.totalPages).toList())
                return
            }
            val localPlan = localStore.resumePlan(runId, plan.familyKey, plan.requestedYear, plan.totalPages)
            val pages = (localPlan.retry + localPlan.missing).distinct().sorted()
            batchLocalResumePlans += 1
            batchLocalPagesScheduled += pages.size
            batchLocalPagesSkipped += localPlan.completedCount
            status.text = "Local resume: ${pages.size}쪽 수집 / ${localPlan.completedCount}쪽 완료로 건너뜀"
            enqueuePageActions(baseUrl, plan, pages)
            return
        }
        if (!cloudOffload.isConfigured()) {
            enqueuePageActions(baseUrl, plan, (2..plan.totalPages).toList())
            return
        }
'''
    s = replace_once(s, old_plan_gate, new_plan_gate, f'local resume plan {path}')

    # Persistent document dedupe across app restarts.
    s = replace_once(s,
        '            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue\n            if (batchVisited.contains(url)) continue\n',
        '''            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            if (batchVisited.contains(url)) continue
            val runId = localRunId
            if (runId != null && localStore.isDocumentCompleted(runId, url)) continue
''', f'discovered local dedupe {path}')

    # Provider seeds: always revisit dynamic lists to rebuild pagination plans, but skip completed static documents.
    s = replace_once(s,
        '            if (url.isBlank() || !isProviderUrl(url) || batchVisited.contains(url) || batchQueued.contains(url)) continue\n            batchQueued.add(url)\n',
        '''            if (url.isBlank() || !isProviderUrl(url) || batchVisited.contains(url) || batchQueued.contains(url)) continue
            val runId = localRunId
            if (runId != null && !currentAdapter().isDynamicListPage(url) && localStore.isDocumentCompleted(runId, url)) continue
            batchQueued.add(url)
''', f'seed local dedupe {path}')

    # Local-first finish: never close or mutate the Cloud run.
    old_finish_cloud = '''        val effectiveReason = if (reason == "completed" && batchCloudPagesDeferred > 0) "completed-with-deferred-errors" else reason
        finalizeBatchJson(effectiveReason)
        if (effectiveReason == "completed" && batchCloudPagesDeferred == 0) {
            cloudOffload.finish(
                reason = effectiveReason,
                summary = JSONObject()
                    .put("attemptedPages", batchPageCount)
                    .put("successfulPages", batchSnapshots.length())
                    .put("errorPages", batchErrors.length())
                    .put("records", batchRecords.length())
                    .put("paginationRetries", batchPaginationRetries)
                    .put("cloudResumePlans", batchCloudResumePlans)
                    .put("cloudPagesScheduled", batchCloudPagesScheduled)
                    .put("cloudPagesSkipped", batchCloudPagesSkipped)
                    .put("cloudPagesDeferred", batchCloudPagesDeferred)
            )
        }
'''
    new_finish_local = '''        val effectiveReason = if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            reason
        } else if (reason == "completed" && batchCloudPagesDeferred > 0) {
            "completed-with-deferred-errors"
        } else reason
        localRunId?.let { runId ->
            val runState = if (effectiveReason == "completed" && localStore.unresolvedCount(runId) == 0) "completed" else "incomplete"
            localStore.markRun(runId, runState, effectiveReason)
        }
        finalizeBatchJson(effectiveReason)
        if (!LOCAL_FIRST_BETA && effectiveReason == "completed" && batchCloudPagesDeferred == 0) {
            cloudOffload.finish(
                reason = effectiveReason,
                summary = JSONObject()
                    .put("attemptedPages", batchPageCount)
                    .put("successfulPages", batchSnapshots.length())
                    .put("errorPages", batchErrors.length())
                    .put("records", batchRecords.length())
                    .put("paginationRetries", batchPaginationRetries)
                    .put("cloudResumePlans", batchCloudResumePlans)
                    .put("cloudPagesScheduled", batchCloudPagesScheduled)
                    .put("cloudPagesSkipped", batchCloudPagesSkipped)
                    .put("cloudPagesDeferred", batchCloudPagesDeferred)
            )
        }
'''
    s = replace_once(s, old_finish_cloud, new_finish_local, f'finish local {path}')

    # Status text tailored to local incomplete runs.
    s = s.replace('''        status.text = when {
            effectiveReason == "cloud-verification-failed" ->
                "로컬 수집 종료: Cloud 최종 완결성 확인 실패 / 서버 run은 닫지 않고 유지합니다."
            batchCloudPagesDeferred > 0 ->
                "수집 종료: 서버 오류 ${batchCloudPagesDeferred}쪽은 Cloud에 보류 / 전체 완료로 확정하지 않습니다."
            else ->
                "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"
        }
''', '''        status.text = when {
            LOCAL_FIRST_BETA && effectiveReason == "completed-with-local-errors" ->
                "Local-First 1차 순회 종료: 미해결 오류는 로컬에 저장됨 / 다음 실행에서 해당 지점만 재개합니다."
            LOCAL_FIRST_BETA && effectiveReason == "completed" ->
                "어디가 로컬 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 재시도 $batchPaginationRetries / 로컬 레코드 ${localRunId?.let { localStore.stats(it).optInt("records") } ?: batchRecords.length()}"
            effectiveReason == "cloud-verification-failed" ->
                "로컬 수집 종료: Cloud 최종 완결성 확인 실패 / 서버 run은 닫지 않고 유지합니다."
            batchCloudPagesDeferred > 0 ->
                "수집 종료: 서버 오류 ${batchCloudPagesDeferred}쪽은 Cloud에 보류 / 전체 완료로 확정하지 않습니다."
            else ->
                "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"
        }
''')

    # Final JSON: all persisted records from the resumed run, not only this process segment.
    s = replace_once(s,
        '    private fun finalizeBatchJson(reason: String) {\n        val out = JSONObject()\n',
        '''    private fun finalizeBatchJson(reason: String) {
        val persistedRecords = localRunId?.let { localStore.loadRecords(it) } ?: batchRecords
        val localStats = localRunId?.let { localStore.stats(it) } ?: JSONObject()
        val out = JSONObject()
''', f'finalize persisted records {path}')
    s = s.replace('                .put("records", batchRecords.length())\n', '                .put("records", persistedRecords.length())\n', 1)
    # There can be a second summary fragment in Cloud finish; only the first replacement above is intentional.
    s = replace_once(s,
        '                .put("dynamicSearchBootstraps", batchBootstrapSearchAttempted.size))\n            .put("errors", batchErrors)\n',
        '''                .put("dynamicSearchBootstraps", batchBootstrapSearchAttempted.size)
                .put("localResumePlans", batchLocalResumePlans)
                .put("localPagesScheduled", batchLocalPagesScheduled)
                .put("localPagesSkipped", batchLocalPagesSkipped)
                .put("localRecordsPersistedThisSegment", batchLocalRecordsPersisted))
            .put("localFirst", JSONObject()
                .put("enabled", LOCAL_FIRST_BETA)
                .put("cloudRequestsDuringBatch", 0)
                .put("snapshotScope", "current-process-segment")
                .put("stats", localStats))
            .put("errors", batchErrors)
''', f'local json summary {path}')
    # Replace final records field nearest finalize body.
    marker = '            .put("cloudOffload", cloudOffload.snapshotStatus())\n            .put("records", batchRecords)\n'
    if marker in s:
        s = s.replace(marker, '            .put("cloudOffload", JSONObject().put("mode", "disabled-during-v0.4.0-local-first"))\n            .put("records", persistedRecords)\n', 1)
    else:
        raise SystemExit(f'final records marker missing: {path}')

    # Close local store and remove the old duplicate destroy call.
    s = s.replace('        cloudOffload.shutdown()\n', '        cloudOffload.shutdown()\n        localStore.close()\n')
    s = s.replace('''        if (::webView.isInitialized) {
            webView.stopLoading()
            webView.destroy()
        }
        webView.stopLoading()
        webView.destroy()
''', '''        if (::webView.isInitialized) {
            webView.stopLoading()
            webView.destroy()
        }
''')

    path.write_text(s)

# Adiga: 2027 current + 2026/2025 historical via 2027/2026 pages.
a = ADIGA.read_text()
old_seeds = '''    override fun seedUrls(): List<String> = listOf(
        "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2026",
        "https://www.adiga.kr/ucp/cls/uni/classUnivView.do?menuId=PCCLSINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/cls/uni/classUnivView.do?menuId=PCCLSINF2000&searchSyr=2026",
        "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2026",
        "https://www.adiga.kr/sco/agu/univScoScaAnlsView.do?menuId=PCSCOAGU2000",
        "https://www.adiga.kr/uct/ces/archiveView.do?menuId=PCUCTCES1000",
        "https://www.adiga.kr/uct/acd/adc/characteristicsView.do?menuId=PCUCTACD1100",
        "https://www.adiga.kr/uct/acd/ueg/univEtenGuideView.do?menuId=PCUCTACD3100",
        "https://www.adiga.kr/uct/acd/ade/criteriaAndResultView.do?menuId=PCUCTACD2000"
    )
'''
new_seeds = '''    override fun seedUrls(): List<String> = listOf(
        // 2027 current admissions + university codes/details. 2027 university detail pages
        // contain the 2026 actual result section.
        "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/cls/uni/classUnivView.do?menuId=PCCLSINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2027",
        // 2026 university/admission views expose 2025 actual results. The huge 2026
        // department list is intentionally omitted because it duplicated the 2027 list
        // in prior device runs and is not needed to obtain the 2025 historical result.
        "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2026",
        "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2026",
        "https://www.adiga.kr/uct/acd/ade/criteriaAndResultView.do?menuId=PCUCTACD2000&searchSyr=2027",
        "https://www.adiga.kr/uct/acd/ade/criteriaAndResultView.do?menuId=PCUCTACD2000&searchSyr=2026",
        "https://www.adiga.kr/uct/acd/adc/characteristicsView.do?menuId=PCUCTACD1100",
        "https://www.adiga.kr/uct/acd/ueg/univEtenGuideView.do?menuId=PCUCTACD3100"
    )
'''
a = replace_once(a, old_seeds, new_seeds, 'Adiga seed policy')
a = a.replace('            url.contains("/ucp/cls/uni/classUnivView.do") -> "adiga-department-list"\n            url.contains("/ucp/prc/uni/admssUnivView.do") -> "adiga-admission-list"\n', '            url.contains("/ucp/cls/uni/classUnivView.do") -> "adiga-department-list"\n            url.contains("/ucp/prc/uni/admssUnivView.do") -> "adiga-admission-list"\n            url.contains("/ucp/uvt/uni/univDetailSelection.do") -> "adiga-university-detail"\n            url.contains("/uct/acd/ade/criteriaAndResultPopup.do") -> "adiga-criteria-result-detail"\n')
a = replace_once(a,
'''        val out = when {
            url.contains("/ucp/uvt/uni/univView.do") -> parseUniversityList(snapshot)
            url.contains("/ucp/cls/uni/classUnivView.do") -> parseDepartmentList(snapshot)
            url.contains("/uct/acd/adc/characteristicsView.do") -> parseCharacteristicsIndex(snapshot)
''',
'''        val out = when {
            url.contains("/ucp/uvt/uni/univView.do") -> parseUniversityList(snapshot)
            url.contains("/ucp/cls/uni/classUnivView.do") -> parseDepartmentList(snapshot)
            url.contains("/ucp/prc/uni/admssUnivView.do") -> parseAdmissionList(snapshot)
            url.contains("/ucp/uvt/uni/univDetailSelection.do") -> parseUniversityDetail(snapshot)
            url.contains("/uct/acd/ade/criteriaAndResultPopup.do") -> parseUniversityDetail(snapshot)
            url.contains("/uct/acd/adc/characteristicsView.do") -> parseCharacteristicsIndex(snapshot)
''', 'Adiga normalize dispatch')

insert_before = '    private fun parseCharacteristicsIndex(snapshot: JSONObject): JSONArray {'
if insert_before not in a:
    raise SystemExit('Adiga insert anchor missing')
new_parsers = r'''    private fun parseAdmissionList(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstTableRows(snapshot) ?: return out
        if (rows.length() < 2) return out
        val pageYear = queryYear(snapshot.optString("url"))
        val previousYear = pageYear?.minus(1)
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 5) continue
            val university = normalizeUniversityCell(row.optString(0))
            val department = row.optString(1).trim()
            if (!looksLikeUniversity(university) || department.isBlank() || department.contains("검색결과가 없습니다")) continue
            val metrics = JSONObject()
                .put("region", valueOrNull(row.optString(2)))
                .put("previousCompetition", numberOrNull(row.optString(3)))
                .put("competitionYear", previousYear ?: JSONObject.NULL)
                .put("capacity", intOrNull(row.optString(4)))
                .put("previousAdmissionGrade", numberOrNull(row.optString(5)))
                .put("historicalResultYear", previousYear ?: JSONObject.NULL)
            out.put(JSONObject()
                .put("recordType", "admission-search-summary")
                .put("year", pageYear ?: JSONObject.NULL)
                .put("university", university)
                .put("campus", extractCampus(university) ?: JSONObject.NULL)
                .put("department", department)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                .put("sourceRowOrdinal", sourceRowOrdinal(snapshot, ri))
                .put("sourceRowFingerprint", scopedRowFingerprint("admission-search-summary", pageYear, row))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun parseUniversityDetail(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val url = snapshot.optString("url")
        val admissionYear = queryYear(url)
        val resultYear = admissionYear?.minus(1)
        val universityCode = queryParam(url, "unvCd")
        val university = inferUniversityFromSnapshot(snapshot)
        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until tables.length()) {
            val table = tables.optJSONObject(ti) ?: continue
            val rows = table.optJSONArray("rows") ?: continue
            if (rows.length() == 0) continue
            val evidence = rows.toString()
            val historical = resultYear != null && (
                evidence.contains("${resultYear}학년도") ||
                    Regex("(경쟁률|충원|최종등록|등록자|50%|70%|입시결과|전형 결과)").containsMatchIn(evidence)
                )
            val recordYear = if (historical) resultYear else admissionYear
            val recordType = if (historical) "historical-admission-result-table" else "current-admission-criteria-table"
            val metrics = JSONObject()
                .put("admissionYear", admissionYear ?: JSONObject.NULL)
                .put("historicalResultYear", resultYear ?: JSONObject.NULL)
                .put("universityCode", universityCode ?: JSONObject.NULL)
                .put("tableIndex", ti)
                .put("caption", valueOrNull(table.optString("caption")))
                .put("rows", rows)
            out.put(JSONObject()
                .put("recordType", recordType)
                .put("year", recordYear ?: JSONObject.NULL)
                .put("university", university ?: JSONObject.NULL)
                .put("campus", university?.let { extractCampus(it) } ?: JSONObject.NULL)
                .put("department", JSONObject.NULL)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", if (university != null && recordYear != null) "high" else "medium")
                .put("sourcePage", url)
                .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                .put("sourceRowFingerprint", scopedRowFingerprint(recordType, recordYear, rows))
                .put("rawEvidence", evidence.take(12000)))
        }
        if (out.length() == 0) {
            val evidence = buildString {
                val context = snapshot.optJSONArray("context") ?: JSONArray()
                for (i in 0 until context.length()) append(context.optString(i)).append(' ')
                val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
                for (i in 0 until minOf(blocks.length(), 80)) append(blocks.optString(i)).append(' ')
            }.trim()
            if (evidence.isNotBlank()) {
                out.put(JSONObject()
                    .put("recordType", "university-detail-text")
                    .put("year", admissionYear ?: JSONObject.NULL)
                    .put("university", university ?: JSONObject.NULL)
                    .put("campus", university?.let { extractCampus(it) } ?: JSONObject.NULL)
                    .put("department", JSONObject.NULL)
                    .put("admission", JSONObject.NULL)
                    .put("metrics", JSONObject()
                        .put("admissionYear", admissionYear ?: JSONObject.NULL)
                        .put("historicalResultYear", resultYear ?: JSONObject.NULL)
                        .put("universityCode", universityCode ?: JSONObject.NULL))
                    .put("confidence", "medium")
                    .put("sourcePage", url)
                    .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                    .put("sourceRowFingerprint", RecordUtils.sha256("${admissionYear ?: "na"}|$evidence"))
                    .put("rawEvidence", evidence.take(12000)))
            }
        }
        return out
    }

    private fun inferUniversityFromSnapshot(snapshot: JSONObject): String? {
        val candidates = mutableListOf<String>()
        val context = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until context.length()) candidates += context.optString(i)
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 60)) candidates += blocks.optString(i)
        val regex = Regex("([가-힣A-Za-z0-9·()\\- ]+(?:대학교|대학)(?:\\[[^]]+])?)")
        for (candidate in candidates) {
            val match = regex.find(candidate)?.groupValues?.getOrNull(1)?.trim() ?: continue
            val normalized = normalizeUniversityCell(match)
            if (looksLikeUniversity(normalized)) return normalized
        }
        return null
    }

'''
a = a.replace(insert_before, new_parsers + insert_before, 1)

# criteria index gets explicit admission year and historical result year.
old_criteria_metrics = '''            val metrics = JSONObject()
                .put("holisticRecruitment", intOrNull(row.optString(1)))
                .put("curriculumRecruitment", intOrNull(row.optString(2)))
                .put("csatRecruitment", intOrNull(row.optString(3)))
                .put("registeredAt", valueOrNull(row.optString(4)))
                .put("columnLabels", JSONArray(labels))
            out.put(indexRecord("criteria-result-index", university, metrics, snapshot, row))
'''
new_criteria_metrics = '''            val admissionYear = queryYear(snapshot.optString("url"))
            val metrics = JSONObject()
                .put("holisticRecruitment", intOrNull(row.optString(1)))
                .put("curriculumRecruitment", intOrNull(row.optString(2)))
                .put("csatRecruitment", intOrNull(row.optString(3)))
                .put("registeredAt", valueOrNull(row.optString(4)))
                .put("columnLabels", JSONArray(labels))
                .put("admissionYear", admissionYear ?: JSONObject.NULL)
                .put("historicalResultYear", admissionYear?.minus(1) ?: JSONObject.NULL)
            out.put(indexRecord("criteria-result-index", university, metrics, snapshot, row, admissionYear))
'''
a = replace_once(a, old_criteria_metrics, new_criteria_metrics, 'criteria year metadata')

# indexRecord can carry a year when the source page is explicitly year-scoped.
a = a.replace('''    private fun indexRecord(type: String, university: String, metrics: JSONObject, snapshot: JSONObject, row: JSONArray): JSONObject = JSONObject()
        .put("recordType", type).put("year", JSONObject.NULL).put("university", university)
''', '''    private fun indexRecord(type: String, university: String, metrics: JSONObject, snapshot: JSONObject, row: JSONArray, year: Int? = null): JSONObject = JSONObject()
        .put("recordType", type).put("year", year ?: JSONObject.NULL).put("university", university)
''')
a = a.replace('.put("sourceRowFingerprint", scopedRowFingerprint(type, null, row))\n', '.put("sourceRowFingerprint", scopedRowFingerprint(type, year, row))\n')
ADIGA.write_text(a)

# SnapshotScript: capture hidden detail tables and infer university detail URLs from onclick codes.
ss = SNAPSHOT.read_text()
ss = replace_once(ss,
'''  var tables=[];
  var tableNodes=document.querySelectorAll('table,[role=table]');
  for(var ti=0;ti<tableNodes.length && tables.length<50;ti++){
    var table=tableNodes[ti];
    if(!visible(table)) continue;
''',
'''  var tables=[];
  var captureHiddenDetail=/\/(?:ucp\/uvt\/uni\/univDetailSelection|uct\/acd\/ade\/criteriaAndResultPopup)\.do$/i.test(location.pathname);
  var tableNodes=document.querySelectorAll('table,[role=table]');
  for(var ti=0;ti<tableNodes.length && tables.length<120;ti++){
    var table=tableNodes[ti];
    if(!captureHiddenDetail && !visible(table)) continue;
''', 'hidden detail tables')
ss = ss.replace('''      var tr=trNodes[ri];
      if(!visible(tr)) continue;
''', '''      var tr=trNodes[ri];
      if(!captureHiddenDetail && !visible(tr)) continue;
''', 1)
ss = ss.replace('''        var cell=cellNodes[ci];
        if(!visible(cell)) continue;
''', '''        var cell=cellNodes[ci];
        if(!captureHiddenDetail && !visible(cell)) continue;
''', 1)

# Add robust route inference helper before forbidden regex.
helper_anchor = '  var forbidden=/password|passwd|cookie|session|token|csrf|transkey|captcha|credential|secret/i;\n'
helper = r'''  function inferAcademicYear(){
    try{
      var q=new URL(location.href).searchParams.get('searchSyr');
      if(/^20[0-9]{2}$/.test(String(q||''))) return String(q);
    }catch(e){}
    var controls=document.querySelectorAll('[name=searchSyr],#searchSyr,select[name*=Syr],input[name*=Syr]');
    for(var i=0;i<controls.length;i++){
      var v=String(controls[i].value||'').trim();
      if(/^20[0-9]{2}$/.test(v)) return v;
    }
    var m=(document.body&&document.body.innerText?document.body.innerText:'').match(/(20[0-9]{2})학년도/);
    return m?m[1]:'';
  }
  function inferredUniversityDetailRoute(script){
    if(!/\/ucp\/uvt\/uni\/univView\.do$/i.test(location.pathname)) return '';
    script=String(script||'');
    var codeMatch=script.match(/\b(0[0-9]{6})\b/);
    if(!codeMatch) return '';
    var year=inferAcademicYear();
    if(!year) return '';
    return location.origin+'/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr='+encodeURIComponent(year)+'&unvCd='+encodeURIComponent(codeMatch[1]);
  }

'''
ss = replace_once(ss, helper_anchor, helper + helper_anchor, 'university detail route helper')
ss = replace_once(ss,
'''    if(!route && onclick){ route=routeFromScript(onclick); if(route) scriptCandidates++; }
    if(!route && /^javascript:/i.test(raw)){ route=routeFromScript(raw); if(route) scriptCandidates++; }
''',
'''    if(!route && onclick){ route=routeFromScript(onclick); if(route) scriptCandidates++; }
    if(!route && /^javascript:/i.test(raw)){ route=routeFromScript(raw); if(route) scriptCandidates++; }
    if(!route){
      route=inferredUniversityDetailRoute(scriptText+' '+dataRaw+' '+raw);
      if(route) scriptCandidates++;
    }
''', 'detail route use')
ss = ss.replace('    if(nav.length>=240) break;\n', '    if(nav.length>=700) break;\n')
SNAPSHOT.write_text(ss)

# Android package metadata only; Cloudflare production stays on v0.3.9 and is not touched.
b = BUILD.read_text()
b = b.replace('versionCode = 10039', 'versionCode = 10400')
b = b.replace('versionName = "0.3.9"', 'versionName = "0.4.0"')
BUILD.write_text(b)

m = MANIFEST.read_text()
m = m.replace('android:label="Admission Collector v0.3.9"', 'android:label="Admission Collector v0.4.0 Local"')
MANIFEST.write_text(m)

# Both MainActivity copies are intentionally kept identical.
if MAIN_PATHS[0].read_bytes() != MAIN_PATHS[1].read_bytes():
    raise SystemExit('MainActivity copies diverged')

checks = {
    MAIN_PATHS[0]: [
        'private const val VERSION = "0.4.0"',
        'private const val LOCAL_FIRST_BETA = true',
        'LocalCollectorStore',
        'cloudRequestsDuringBatch", 0',
        'verifyLocalCompletionOrFinish',
        'Local resume:'
    ],
    ADIGA: [
        'univDetailSelection.do',
        'historical-admission-result-table',
        'admission-search-summary',
        'historicalResultYear'
    ],
    SNAPSHOT: ['captureHiddenDetail', 'inferredUniversityDetailRoute', 'nav.length>=700'],
    LOCAL_STORE: ['class LocalCollectorStore', 'fun resumePlan', 'fun storeRecords', 'fun unresolvedCount'],
    BUILD: ['versionCode = 10400', 'versionName = "0.4.0"'],
    MANIFEST: ['android:label="Admission Collector v0.4.0 Local"'],
}
for path, needles in checks.items():
    text = path.read_text()
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'missing {needle!r} in {path}')

print('v0.4.0 local-first Adiga patch applied')
