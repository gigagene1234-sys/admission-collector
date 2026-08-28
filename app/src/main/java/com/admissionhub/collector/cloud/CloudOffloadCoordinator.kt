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
 * Optional Cloudflare offload coordinator for Admission Collector v0.3.2.
 *
 * The collector remains fully usable when this is not configured. When configured,
 * normalized page records and checkpoint/error metadata are streamed to the Worker.
 * The user's Adiga/Jinhak credentials, cookies, CSRF tokens and CAPTCHA data are not sent.
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

    fun workerUrl(): String = prefs.getString(KEY_URL, "")?.trim()?.trimEnd('/') ?: ""

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

        client?.createRun(
            provider = provider,
            collectorVersion = collectorVersion,
            metadata = JSONObject()
                .put("client", "android")
                .put("checkpointMode", "incremental")
        ) { result ->
            val runId = result.getOrNull()
            val error = result.exceptionOrNull()
            synchronized(lock) {
                creatingRun = false
                if (runId != null) {
                    activeRunId = runId
                    prefs.edit()
                        .putString(KEY_ACTIVE_RUN, runId)
                        .putString(KEY_ACTIVE_PROVIDER, provider)
                        .apply()
                } else {
                    lastError = error?.message ?: "run creation failed"
                }
            }
            if (runId != null) flushPending()
            onReady?.invoke(runId)
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

    fun snapshotStatus(): JSONObject = JSONObject()
        .put("configured", isConfigured())
        .put("workerUrl", workerUrl().ifBlank { JSONObject.NULL })
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
            hint = "https://...workers.dev"
            setText(workerUrl())
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        val tokenInput = EditText(activity).apply {
            hint = if (token().isBlank()) "INGEST_TOKEN" else "토큰 유지: 비워두기"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        layout.addView(urlInput)
        layout.addView(tokenInput)

        AlertDialog.Builder(activity)
            .setTitle("Cloudflare Offload 설정")
            .setMessage("어디가/진학사 로그인 정보와 쿠키는 전송하지 않습니다. Worker URL과 수집용 토큰만 저장합니다.")
            .setView(layout)
            .setNeutralButton("설정 삭제") { _, _ ->
                clearConfiguration()
                onChanged?.invoke()
            }
            .setNegativeButton("취소", null)
            .setPositiveButton("저장") { _, _ ->
                val url = urlInput.text.toString().trim().trimEnd('/')
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
        private const val PREFS = "admission_cloud_offload"
        private const val KEY_URL = "worker_url"
        private const val KEY_TOKEN = "ingest_token"
        private const val KEY_ACTIVE_RUN = "active_run_id"
        private const val KEY_ACTIVE_PROVIDER = "active_provider"
        private const val MAX_PENDING_CHUNKS = 200
    }
}
