package com.admissionhub.collector.session

import android.content.Context
import android.util.Base64
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.URI
import java.security.KeyStore
import java.time.Instant
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties

/**
 * Hardware/OS-keystore protected backup for the authenticated WebView session.
 *
 * Security boundary:
 * - never stores a password, form value, CSRF value, CAPTCHA material or raw DOM;
 * - encrypted cookie material remains on this Android device only;
 * - cloud/export/diagnostic code receives only SessionLeaseSummary;
 * - leaseId is an opaque random identifier, never a reversible encryption seed.
 */
class SecureSessionVault(context: Context) {
    data class SessionLeaseSummary(
        val provider: String,
        val leaseId: String,
        val origin: String,
        val capturedAt: String,
        val collectorVersion: String,
        val cookieCount: Int,
        val restored: Boolean = false
    ) {
        fun toJson(): JSONObject = JSONObject()
            .put("provider", provider)
            .put("leaseId", leaseId)
            .put("origin", origin)
            .put("capturedAt", capturedAt)
            .put("collectorVersion", collectorVersion)
            .put("cookieCount", cookieCount)
            .put("restored", restored)
            .put("containsCredential", false)
            .put("cloudExportAllowed", false)
    }

    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun captureAuthenticated(provider: String, pageUrl: String, collectorVersion: String): SessionLeaseSummary? {
        val origin = safeOrigin(pageUrl) ?: return null
        val cookieHeader = CookieManager.getInstance().getCookie(pageUrl).orEmpty().trim()
        if (cookieHeader.isBlank()) return null
        val cookieCount = cookieHeader.split(';').count { it.trim().contains('=') }
        val leaseId = existingMetadata(provider)?.optString("leaseId")?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString()
        val capturedAt = Instant.now().toString()
        val payload = JSONObject()
            .put("provider", provider)
            .put("leaseId", leaseId)
            .put("origin", origin)
            .put("cookieHeader", cookieHeader)
            .put("capturedAt", capturedAt)
            .put("collectorVersion", collectorVersion)
        val encrypted = encrypt(payload.toString().toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString(secretKey(provider), encrypted)
            .putString(metadataKey(provider), JSONObject()
                .put("provider", provider)
                .put("leaseId", leaseId)
                .put("origin", origin)
                .put("capturedAt", capturedAt)
                .put("collectorVersion", collectorVersion)
                .put("cookieCount", cookieCount)
                .toString())
            .apply()
        return SessionLeaseSummary(provider, leaseId, origin, capturedAt, collectorVersion, cookieCount)
    }

    fun restore(provider: String): SessionLeaseSummary? {
        val encoded = prefs.getString(secretKey(provider), null)?.takeIf { it.isNotBlank() } ?: return null
        val raw = runCatching { String(decrypt(encoded), Charsets.UTF_8) }.getOrNull() ?: return null
        val payload = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        if (payload.optString("provider") != provider) return null
        val origin = payload.optString("origin")
        val cookieHeader = payload.optString("cookieHeader")
        if (origin.isBlank() || cookieHeader.isBlank()) return null
        val manager = CookieManager.getInstance()
        var restored = 0
        cookieHeader.split(';').map { it.trim() }.filter { it.contains('=') }.forEach { cookie ->
            runCatching {
                manager.setCookie(origin, "$cookie; Secure; SameSite=Lax")
                restored += 1
            }
        }
        manager.flush()
        return SessionLeaseSummary(
            provider = provider,
            leaseId = payload.optString("leaseId"),
            origin = origin,
            capturedAt = payload.optString("capturedAt"),
            collectorVersion = payload.optString("collectorVersion"),
            cookieCount = restored,
            restored = restored > 0
        )
    }

    fun summary(provider: String): SessionLeaseSummary? {
        val meta = existingMetadata(provider) ?: return null
        return SessionLeaseSummary(
            provider = provider,
            leaseId = meta.optString("leaseId"),
            origin = meta.optString("origin"),
            capturedAt = meta.optString("capturedAt"),
            collectorVersion = meta.optString("collectorVersion"),
            cookieCount = meta.optInt("cookieCount", 0),
            restored = false
        )
    }

    fun clear(provider: String) {
        prefs.edit().remove(secretKey(provider)).remove(metadataKey(provider)).apply()
    }

    private fun existingMetadata(provider: String): JSONObject? =
        prefs.getString(metadataKey(provider), null)?.let { runCatching { JSONObject(it) }.getOrNull() }

    private fun safeOrigin(raw: String): String? {
        return try {
            val uri = URI(raw)
            val scheme = uri.scheme?.lowercase()?.takeIf { it == "https" } ?: return null
            val host = uri.host?.lowercase()?.takeIf { it.isNotBlank() } ?: return null
            "$scheme://$host/"
        } catch (_: Exception) {
            null
        }
    }

    private fun secretKey(provider: String) = "secret_${provider.lowercase()}"
    private fun metadataKey(provider: String) = "meta_${provider.lowercase()}"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }

    private fun encrypt(bytes: ByteArray): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val iv = cipher.iv
        val encrypted = cipher.doFinal(bytes)
        val out = ByteArray(1 + iv.size + encrypted.size)
        out[0] = iv.size.toByte()
        System.arraycopy(iv, 0, out, 1, iv.size)
        System.arraycopy(encrypted, 0, out, 1 + iv.size, encrypted.size)
        return Base64.encodeToString(out, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): ByteArray {
        val all = Base64.decode(encoded, Base64.NO_WRAP)
        require(all.isNotEmpty())
        val ivSize = all[0].toInt() and 0xff
        require(ivSize in 12..32 && all.size > 1 + ivSize)
        val iv = all.copyOfRange(1, 1 + ivSize)
        val encrypted = all.copyOfRange(1 + ivSize, all.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        return cipher.doFinal(encrypted)
    }

    companion object {
        private const val PREFS = "admission_secure_session_v1"
        private const val KEY_ALIAS = "admission_collector_session_v1"
    }
}
