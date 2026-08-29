package com.admissionhub.collector.cloud

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import org.json.JSONArray
import org.json.JSONObject

/**
 * Cloudflare checkpoint coordinator for Admission Collector v0.3.3.
 *
 * The deployed Worker URL is built in, while the ingestion token is never hard-coded.
 * Adiga/Jinhak credentials, cookies, CSRF tokens and CAPTCHA data are not sent.
 */
class CloudOffloadCoordinator(context: Context) {
    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val lock = Any()

    private var client: CloudOffloadClient? = null
    private var activeRunId: String? = null
    private var activeProvider: String? = null
    private var creatingRun = false
    private val pendingChunks = ArrayDeque<PendingChunk>()
    private var pendingFinish: PendingFinish? = null

    @Volatile private var lastError: String? = null
    @Volatile private var uploadedChunks: Int = 0
    @Volatile private var reusedRun: Boolean = false

    data class PendingChunk(
        val provider: String,
        val recordsJson: String,
        val familyKey: String?,
        val requestedYear: Int?,
        val page: Int?,
        val retryCount: Int,
        val state: String,
        val errorJson: String?
    )

    data class PendingFinish(
        val reason: String,
        val summaryJson: String
    )

    fun isConfigured(): Boolean = workerUrl().isNotBlank() && token().isNotBlank()

    fun workerUrl(): String =
        prefs.getString(KEY_URL, null)?.trim()?.trimEnd('/')?.takeIf { it.isNotBlank() }
            ?: DEFAULT_WORKER_URL

    private fun token(): String = prefs.getString(KEY_TOKEN, "") ?: ""

    fun beginOrResume(provider: String, collectorVersion: String, onReady: ((String?) -> Unit)? = null) {
        if (!isConfigured()) {
            onReady?.invoke(null)
            return
        }

        synchronized(lock) {
            val savedProvider = prefs.getString(KEY_ACTIVE_PROVIDER, null)
            val savedRun = prefs.getString(KEY_ACTIVE_RUN, null)
            if (!savedRun.isNullOrBlank() && savedProvider == provider) {
                activeRunId = savedRun
                activeProvider = provider
                reusedRun = true
                ensureClientLocked()
                onReady?.invoke(savedRun)
                return
            }
            if (creatingRun) {
                onReady?.invoke(null)
                return
            }
            creatingRun = true
            activeProvider = provider
            reusedRun = false
            ensureClientLocked()
        }

        recoverOrCreateRun(provider, collectorVersion, onReady)
    }

    /**
     * Recovers the newest unfinished server-side run when local SharedPreferences were
     * lost (for example after the one-time migration from an ephemeral debug signature).
     * This preserves D1 checkpoints without exporting browser credentials or cookies.
     */
    private fun recoverOrCreateRun(
        provider: String,
        collectorVersion: String,
        onReady: ((String?) -> Unit)?
    ) {
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (currentClient == null) {
            synchronized(lock) { creatingRun = false }
            onReady?.invoke(null)
            return
        }

        currentClient.getLatestActiveRun(provider) { lookup ->
            val recovered = lookup.getOrNull()
            if (!recovered.isNullOrBlank()) {
                synchronized(lock) {
                    creatingRun = false
                    activeRunId = recovered
                    activeProvider = provider
                    reusedRun = true
                    prefs.edit()
                        .putString(KEY_ACTIVE_RUN, recovered)
                        .putString(KEY_ACTIVE_PROVIDER, provider)
                        .apply()
                }
                flushPending()
                onReady?.invoke(recovered)
                return@getLatestActiveRun
            }

            currentClient.createRun(
                provider = provider,
                collectorVersion = collectorVersion,
                metadata = JSONObject()
                    .put("client", "android")
                    .put("checkpointMode", "incremental")
                    .put("recoveryLookup", if (lookup.isSuccess) "none-found" else "failed")
            ) { result ->
                val runId = result.getOrNull()
                val error = result.exceptionOrNull()
                synchronized(lock) {
                    creatingRun = false
                    if (runId != null) {
                        activeRunId = runId
                        activeProvider = provider
                        reusedRun = false
                        prefs.edit()
                            .putString(KEY_ACTIVE_RUN, runId)
                            .putString(KEY_ACTIVE_PROVIDER, provider)
                            .apply()
                    } else {
                        lastError = error?.message ?: lookup.exceptionOrNull()?.message ?: "run creation failed"
                    }
                }
                if (runId != null) flushPending()
                onReady?.invoke(runId)
            }
        }
    }

    fun uploadPage(
        provider: String,
        records: JSONArray,
        familyKey: String?,
        requestedYear: Int?,
        page: Int?,
        retryCount: Int = 0
    ) {
        enqueueOrSend(
            PendingChunk(
                provider = provider,
                recordsJson = records.toString(),
                familyKey = familyKey,
                requestedYear = requestedYear,
                page = page,
                retryCount = retryCount,
                state = "completed",
                errorJson = null
            )
        )
    }

    fun uploadError(
        provider: String,
        familyKey: String?,
        requestedYear: Int?,
        page: Int?,
        retryCount: Int,
        error: JSONObject
    ) {
        enqueueOrSend(
            PendingChunk(
                provider = provider,
                recordsJson = "[]",
                familyKey = familyKey,
                requestedYear = requestedYear,
                page = page,
                retryCount = retryCount,
                state = "error",
                errorJson = error.toString()
            )
        )
    }

    fun finish(reason: String, summary: JSONObject) {
        if (!isConfigured()) return
        val runId: String?
        synchronized(lock) {
            runId = activeRunId
            if (runId == null) {
                if (creatingRun) pendingFinish = PendingFinish(reason, summary.toString())
                return
            }
        }
        sendFinish(runId ?: return, reason, summary)
    }

    fun resumePlan(
        familyKey: String,
        requestedYear: Int?,
        totalPages: Int,
        callback: (Result<JSONObject>) -> Unit
    ) {
        val runId = synchronized(lock) { activeRunId }
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (runId.isNullOrBlank() || currentClient == null) {
            callback(Result.failure(IllegalStateException("No active cloud run")))
            return
        }
        currentClient.getResumePlan(runId, familyKey, requestedYear, totalPages, callback)
    }

    fun pendingPages(callback: (Result<JSONObject>) -> Unit) {
        val runId = synchronized(lock) { activeRunId }
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (runId.isNullOrBlank() || currentClient == null) {
            callback(Result.failure(IllegalStateException("No active cloud run")))
            return
        }
        currentClient.getPendingPages(runId, callback)
    }

    fun status(callback: (Result<JSONObject>) -> Unit) {
        val runId = synchronized(lock) { activeRunId }
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (runId.isNullOrBlank() || currentClient == null) {
            callback(Result.failure(IllegalStateException("No active cloud run")))
            return
        }
        currentClient.getStatus(runId, callback)
    }

    fun snapshotStatus(): JSONObject = JSONObject()
        .put("configured", isConfigured())
        .put("workerUrl", workerUrl())
        .put("activeRunId", synchronized(lock) { activeRunId } ?: JSONObject.NULL)
        .put("reusedRun", reusedRun)
        .put("uploadedChunks", uploadedChunks)
        .put("pendingChunks", synchronized(lock) { pendingChunks.size })
        .put("lastError", lastError ?: JSONObject.NULL)

    fun showSettingsDialog(activity: Activity, onChanged: (() -> Unit)? = null) {
        val layout = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            val p = (16 * resources.displayMetrics.density).toInt()
            setPadding(p, p / 2, p, 0)
        }
        val urlInput = EditText(activity).apply {
            hint = DEFAULT_WORKER_URL
            setText(workerUrl())
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        val tokenInput = EditText(activity).apply {
            hint = if (token().isBlank()) "ADMISSION_INGEST_TOKEN 입력" else "토큰 유지: 비워두기"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        layout.addView(urlInput)
        layout.addView(tokenInput)

        AlertDialog.Builder(activity)
            .setTitle("Cloudflare Offload 설정")
            .setMessage("Worker 주소는 배포된 기본값이 들어 있습니다. 수집용 토큰만 한 번 입력하면 됩니다. 어디가/진학사 로그인 정보와 쿠키는 전송하지 않습니다.")
            .setView(layout)
            .setNeutralButton("토큰/설정 삭제") { _, _ ->
                clearConfiguration()
                onChanged?.invoke()
            }
            .setNegativeButton("취소", null)
            .setPositiveButton("저장") { _, _ ->
                val url = urlInput.text.toString().trim().trimEnd('/').ifBlank { DEFAULT_WORKER_URL }
                val newToken = tokenInput.text.toString()
                val editor = prefs.edit().putString(KEY_URL, url)
                if (newToken.isNotBlank()) editor.putString(KEY_TOKEN, newToken)
                editor.apply()
                synchronized(lock) {
                    client?.shutdown()
                    client = null
                }
                onChanged?.invoke()
            }
            .show()
    }

    fun shutdown() {
        synchronized(lock) {
            client?.shutdown()
            client = null
        }
    }

    private fun clearConfiguration() {
        synchronized(lock) {
            client?.shutdown()
            client = null
            activeRunId = null
            activeProvider = null
            creatingRun = false
            pendingChunks.clear()
            pendingFinish = null
        }
        prefs.edit().clear().apply()
    }

    private fun enqueueOrSend(chunk: PendingChunk) {
        if (!isConfigured()) return
        val runId: String?
        synchronized(lock) {
            runId = activeRunId
            if (runId == null) {
                if (pendingChunks.size >= MAX_PENDING_CHUNKS) pendingChunks.removeFirst()
                pendingChunks.addLast(chunk)
                return
            }
        }
        sendChunk(runId ?: return, chunk)
    }

    private fun flushPending() {
        val runId = synchronized(lock) { activeRunId } ?: return
        val chunks = mutableListOf<PendingChunk>()
        val finish: PendingFinish?
        synchronized(lock) {
            while (pendingChunks.isNotEmpty()) chunks += pendingChunks.removeFirst()
            finish = pendingFinish
            pendingFinish = null
        }
        chunks.forEach { sendChunk(runId, it) }
        if (finish != null) sendFinish(runId, finish.reason, JSONObject(finish.summaryJson))
    }

    private fun sendChunk(runId: String, chunk: PendingChunk) {
        val currentClient = synchronized(lock) { ensureClientLocked(); client } ?: return
        val pageState = if (!chunk.familyKey.isNullOrBlank() && chunk.page != null) {
            CloudOffloadClient.PageState(
                familyKey = chunk.familyKey,
                requestedYear = chunk.requestedYear,
                page = chunk.page,
                state = chunk.state,
                retryCount = chunk.retryCount,
                errorType = chunk.errorJson?.let {
                    runCatching { JSONObject(it).optString("type", "page-error") }.getOrDefault("page-error")
                }
            )
        } else null
        val error = chunk.errorJson?.let { runCatching { JSONObject(it) }.getOrNull() }
        currentClient.uploadChunk(
            runId = runId,
            provider = chunk.provider,
            records = JSONArray(chunk.recordsJson),
            page = pageState,
            error = error
        ) { result ->
            result.onSuccess { uploadedChunks += 1 }
                .onFailure { lastError = it.message }
        }
    }

    private fun sendFinish(runId: String, reason: String, summary: JSONObject) {
        val currentClient = synchronized(lock) { ensureClientLocked(); client } ?: return
        currentClient.finishRun(runId, reason, summary) { result ->
            result.onFailure { lastError = it.message }
            if (result.isSuccess && reason == "completed") {
                synchronized(lock) {
                    activeRunId = null
                    activeProvider = null
                }
                prefs.edit().remove(KEY_ACTIVE_RUN).remove(KEY_ACTIVE_PROVIDER).apply()
            }
        }
    }

    private fun ensureClientLocked() {
        if (client != null || !isConfigured()) return
        val url = workerUrl()
        client = CloudOffloadClient(url) { token() }
    }

    companion object {
        const val DEFAULT_WORKER_URL = "https://admission-collector-offload.gigagene1234.workers.dev"
        private const val PREFS = "admission_cloud_offload"
        private const val KEY_URL = "worker_url"
        private const val KEY_TOKEN = "ingest_token"
        private const val KEY_ACTIVE_RUN = "active_run_id"
        private const val KEY_ACTIVE_PROVIDER = "active_provider"
        private const val MAX_PENDING_CHUNKS = 200
    }
}
