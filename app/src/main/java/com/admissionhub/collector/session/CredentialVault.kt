package com.admissionhub.collector.session

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import java.time.Instant
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Device-local encrypted login credential vault for the beta collector.
 *
 * The user explicitly opts in by saving credentials inside the Android app.
 * Values are encrypted with a non-exportable Android Keystore AES key and are
 * never written to unified exports, runtime diagnostics, Cloudflare, Vercel or GitHub.
 */
class CredentialVault(context: Context) {
    data class Credentials(
        val provider: String,
        val username: String,
        val password: String,
        val savedAt: String
    )

    data class Summary(
        val provider: String,
        val usernameHint: String,
        val savedAt: String
    )

    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun save(provider: String, username: String, password: String): Summary {
        require(provider.isNotBlank())
        require(username.isNotBlank())
        require(password.isNotBlank())
        val savedAt = Instant.now().toString()
        val payload = JSONObject()
            .put("schemaVersion", 1)
            .put("provider", provider)
            .put("username", username)
            .put("password", password)
            .put("savedAt", savedAt)
        prefs.edit().putString(key(provider), encrypt(payload.toString().toByteArray(Charsets.UTF_8))).apply()
        return Summary(provider, mask(username), savedAt)
    }

    fun load(provider: String): Credentials? {
        val encoded = prefs.getString(key(provider), null)?.takeIf { it.isNotBlank() } ?: return null
        val raw = runCatching { String(decrypt(encoded), Charsets.UTF_8) }.getOrNull() ?: return null
        val payload = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        if (payload.optInt("schemaVersion", 0) != 1 || payload.optString("provider") != provider) return null
        val username = payload.optString("username")
        val password = payload.optString("password")
        if (username.isBlank() || password.isBlank()) return null
        return Credentials(provider, username, password, payload.optString("savedAt"))
    }

    fun summary(provider: String): Summary? {
        val c = load(provider) ?: return null
        return Summary(c.provider, mask(c.username), c.savedAt)
    }

    fun has(provider: String): Boolean = load(provider) != null

    fun clear(provider: String) {
        prefs.edit().remove(key(provider)).apply()
    }

    private fun mask(value: String): String {
        if (value.length <= 2) return "••"
        return value.take(1) + "•".repeat((value.length - 2).coerceAtMost(8)) + value.takeLast(1)
    }

    private fun key(provider: String) = "credential_${provider.lowercase()}"

    private fun secretKey(): SecretKey {
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
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
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
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
        return cipher.doFinal(encrypted)
    }

    companion object {
        private const val PREFS = "admission_local_credentials_v1"
        private const val KEY_ALIAS = "admission_collector_credentials_v1"
    }
}
