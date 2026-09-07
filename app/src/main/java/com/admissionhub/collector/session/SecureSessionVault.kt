package com.admissionhub.collector.session

import android.content.Context
import org.json.JSONObject
import java.net.URI
import java.time.Instant
import java.util.UUID

/** Auth-proof metadata only. Cookies remain under the browser's native lifecycle and are never copied or replayed. */
class SecureSessionVault(context: Context) {
    data class SessionLeaseSummary(
        val provider: String, val leaseId: String, val origin: String, val capturedAt: String,
        val collectorVersion: String, val cookieCount: Int = 0, val originCount: Int = 1,
        val storageVersion: Int = 3, val restored: Boolean = false
    ) {
        fun toJson(): JSONObject = JSONObject().put("provider", provider).put("leaseId", leaseId).put("origin", origin)
            .put("capturedAt", capturedAt).put("collectorVersion", collectorVersion).put("cookieCount", cookieCount)
            .put("originCount", originCount).put("storageVersion", storageVersion).put("restored", restored)
            .put("containsPassword", false).put("containsSessionSecret", false).put("cloudExportAllowed", false)
    }
    private val metadata = mutableMapOf<String, SessionLeaseSummary>()
    init {
        for (name in listOf("admission_secure_session_bundle_v2", "admission_secure_session_v1"))
            context.applicationContext.getSharedPreferences(name, Context.MODE_PRIVATE).edit().clear().commit()
    }
    fun captureAuthenticated(provider: String, pageUrl: String, collectorVersion: String): SessionLeaseSummary? {
        val u = runCatching { URI(pageUrl) }.getOrNull() ?: return null
        val host = u.host.orEmpty().lowercase()
        val domain = when (provider.lowercase()) { "jinhak" -> "jinhak.com"; "adiga" -> "adiga.kr"; else -> return null }
        if (u.scheme != "https" || !(host == domain || host.endsWith(".$domain"))) return null
        val value = SessionLeaseSummary(provider, metadata[provider]?.leaseId ?: UUID.randomUUID().toString(), "https://$host", Instant.now().toString(), collectorVersion)
        metadata[provider] = value
        return value
    }
    fun restore(provider: String): SessionLeaseSummary? = metadata[provider]?.copy(restored = false)
    fun summary(provider: String): SessionLeaseSummary? = metadata[provider]
    fun clear(provider: String) { metadata.remove(provider) }
}
