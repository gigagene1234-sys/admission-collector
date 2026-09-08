package com.admissionhub.collector.session

import android.content.Context
import org.json.JSONObject
import java.net.URI
import java.time.Instant
import java.util.UUID

/**
 * Auth-proof metadata only. Cookies remain under WebView's native lifecycle and are never copied.
 * Persisting this non-secret lease lets startup verify the existing browser session before asking
 * for credentials again; it never stores cookies, tokens or passwords.
 */
class SecureSessionVault(context: Context) {
    data class SessionLeaseSummary(
        val provider: String, val leaseId: String, val origin: String, val capturedAt: String,
        val collectorVersion: String, val cookieCount: Int = 0, val originCount: Int = 1,
        val storageVersion: Int = 4, val restored: Boolean = false
    ) {
        fun toJson(): JSONObject = JSONObject().put("provider", provider).put("leaseId", leaseId).put("origin", origin)
            .put("capturedAt", capturedAt).put("collectorVersion", collectorVersion).put("cookieCount", cookieCount)
            .put("originCount", originCount).put("storageVersion", storageVersion).put("restored", restored)
            .put("containsPassword", false).put("containsSessionSecret", false).put("cloudExportAllowed", false)
    }

    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val metadata = mutableMapOf<String, SessionLeaseSummary>()

    init {
        for (provider in listOf("adiga", "jinhak")) loadPersisted(provider)?.let { metadata[provider] = it }
        // Remove obsolete bundles that could contain older copied session material; do not touch WebView cookies.
        for (name in listOf("admission_secure_session_bundle_v2", "admission_secure_session_v1"))
            context.applicationContext.getSharedPreferences(name, Context.MODE_PRIVATE).edit().clear().commit()
    }

    fun captureAuthenticated(provider: String, pageUrl: String, collectorVersion: String): SessionLeaseSummary? {
        val u = runCatching { URI(pageUrl) }.getOrNull() ?: return null
        val host = u.host.orEmpty().lowercase()
        val key = provider.lowercase()
        val domain = when (key) { "jinhak" -> "jinhak.com"; "adiga" -> "adiga.kr"; else -> return null }
        if (u.scheme != "https" || !(host == domain || host.endsWith(".$domain"))) return null
        val value = SessionLeaseSummary(
            key,
            metadata[key]?.leaseId ?: UUID.randomUUID().toString(),
            "https://$host",
            Instant.now().toString(),
            collectorVersion
        )
        metadata[key] = value
        persist(value)
        return value
    }

    fun restore(provider: String): SessionLeaseSummary? {
        val key = provider.lowercase()
        val value = metadata[key] ?: loadPersisted(key)?.also { metadata[key] = it } ?: return null
        return value.copy(restored = true)
    }

    fun summary(provider: String): SessionLeaseSummary? = metadata[provider.lowercase()]

    fun clear(provider: String) {
        val key = provider.lowercase()
        metadata.remove(key)
        prefs.edit().remove(key).commit()
    }

    private fun persist(value: SessionLeaseSummary) {
        prefs.edit().putString(value.provider, value.toJson().toString()).commit()
    }

    private fun loadPersisted(provider: String): SessionLeaseSummary? = runCatching {
        val obj = JSONObject(prefs.getString(provider, null) ?: return null)
        SessionLeaseSummary(
            provider = obj.optString("provider", provider),
            leaseId = obj.optString("leaseId"),
            origin = obj.optString("origin"),
            capturedAt = obj.optString("capturedAt"),
            collectorVersion = obj.optString("collectorVersion"),
            cookieCount = 0,
            originCount = 1,
            storageVersion = 4,
            restored = true
        ).takeIf { it.leaseId.isNotBlank() && it.origin.startsWith("https://") }
    }.getOrNull()

    companion object {
        private const val PREFS = "admission_auth_lease_metadata_v4"
    }
}
