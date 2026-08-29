package com.admissionhub.collector.cloud

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.util.concurrent.Executors

/**
 * v0.3.3 Cloudflare offload client.
 *
 * No credentials are hard-coded here.
 * Supply workerUrl/token from runtime configuration and store the token
 * with a device-protected mechanism in the host app.
 */
class CloudOffloadClient(
    private val workerUrl: String,
    private val tokenProvider: () -> String?
) {
    private val io = Executors.newSingleThreadExecutor()

    data class PageState(
        val familyKey: String,
        val requestedYear: Int?,
        val page: Int,
        val state: String = "completed",
        val retryCount: Int = 0,
        val errorType: String? = null
    )

    fun createRun(
        provider: String,
        collectorVersion: String,
        metadata: JSONObject = JSONObject(),
        callback: (Result<String>) -> Unit
    ) = io.execute {
        callback(runCatching {
            val response = post(
                "/v1/runs",
                JSONObject()
                    .put("provider", provider)
                    .put("collectorVersion", collectorVersion)
                    .put("metadata", metadata)
            )
            response.getString("runId")
        })
    }

    fun uploadChunk(
        runId: String,
        provider: String,
        records: JSONArray,
        page: PageState?,
        error: JSONObject? = null,
        callback: (Result<Unit>) -> Unit = {}
    ) = io.execute {
        callback(runCatching {
            val body = JSONObject()
                .put("chunkId", UUID.randomUUID().toString())
                .put("provider", provider)
                .put("records", records)

            if (page != null) {
                body.put("page", JSONObject()
                    .put("familyKey", page.familyKey)
                    .put("requestedYear", page.requestedYear ?: JSONObject.NULL)
                    .put("page", page.page)
                    .put("state", page.state)
                    .put("retryCount", page.retryCount)
                    .put("errorType", page.errorType ?: JSONObject.NULL)
                )
            }

            if (error != null) body.put("error", error)
            post("/v1/runs/${encode(runId)}/chunks", body)
            Unit
        })
    }

    fun finishRun(
        runId: String,
        completionReason: String,
        summary: JSONObject,
        callback: (Result<Unit>) -> Unit = {}
    ) = io.execute {
        callback(runCatching {
            post(
                "/v1/runs/${encode(runId)}/finish",
                JSONObject()
                    .put("status", "uploaded")
                    .put("completionReason", completionReason)
                    .put("summary", summary)
            )
            Unit
        })
    }

    fun getStatus(
        runId: String,
        callback: (Result<JSONObject>) -> Unit
    ) = io.execute {
        callback(runCatching { get("/v1/runs/${encode(runId)}/status") })
    }

    fun getLatestActiveRun(
        provider: String,
        callback: (Result<String?>) -> Unit
    ) = io.execute {
        callback(runCatching {
            get("/v1/runs/latest?provider=${encode(provider)}")
                .optString("runId")
                .takeIf { it.isNotBlank() && it != "null" }
        })
    }

    fun getResumePlan(
        runId: String,
        familyKey: String,
        requestedYear: Int?,
        totalPages: Int,
        callback: (Result<JSONObject>) -> Unit
    ) = io.execute {
        callback(runCatching {
            val year = requestedYear?.toString() ?: ""
            get(
                "/v1/runs/${encode(runId)}/resume-plan" +
                    "?familyKey=${encode(familyKey)}" +
                    "&requestedYear=${encode(year)}" +
                    "&totalPages=$totalPages" +
                    "&limit=500"
            )
        })
    }

    fun getPendingPages(
        runId: String,
        callback: (Result<JSONObject>) -> Unit
    ) = io.execute {
        callback(runCatching {
            get("/v1/runs/${encode(runId)}/pending-pages?limit=500")
        })
    }

    fun shutdown() {
        io.shutdownNow()
    }

    private fun post(path: String, body: JSONObject): JSONObject =
        request("POST", path, body.toString())

    private fun get(path: String): JSONObject =
        request("GET", path, null)

    private fun request(method: String, path: String, body: String?): JSONObject {
        val token = tokenProvider()?.takeIf { it.isNotBlank() }
            ?: error("Cloud offload token is not configured")

        val base = workerUrl.trimEnd('/')
        val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 12_000
            readTimeout = 20_000
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("Accept", "application/json")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }

        try {
            if (body != null) {
                connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
            }

            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = if (stream != null) {
                BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
            } else ""

            if (code !in 200..299) {
                error("Cloud offload HTTP $code: $text")
            }
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }

    private fun encode(value: String): String =
        java.net.URLEncoder.encode(value, Charsets.UTF_8.name())
}
