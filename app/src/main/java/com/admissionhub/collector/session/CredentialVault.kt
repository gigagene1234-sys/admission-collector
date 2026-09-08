package com.admissionhub.collector.session

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.nio.ByteBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Local credential vault used only to resume user-requested provider login.
 *
 * - Credentials are encrypted with an AndroidKeyStore AES-GCM key.
 * - Plaintext credentials are never exported, logged, written to SQLite, or sent to cloud workers.
 * - `persist=false` keeps a credential in process memory only.
 * - Old unversioned/plain preference payloads are never read.
 */
class CredentialVault(context: Context) {
    data class Credential(val username: String, val password: String, val persisted: Boolean)

    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val memory = linkedMapOf<String, Credential>()

    @Synchronized
    fun save(provider: String, username: String, password: String, persist: Boolean = true) {
        val key = normalize(provider)
        require(username.isNotBlank()) { "아이디를 입력하세요." }
        require(password.isNotBlank()) { "비밀번호를 입력하세요." }
        val credential = Credential(username, password, persist)
        memory[key] = credential
        if (!persist) {
            prefs.edit().remove(prefKey(key)).apply()
            return
        }
        val plaintext = JSONObject()
            .put("schemaVersion", 2)
            .put("provider", key)
            .put("username", username)
            .put("password", password)
            .toString()
            .toByteArray(Charsets.UTF_8)
        val encrypted = encrypt(plaintext)
        prefs.edit().putString(prefKey(key), PREFIX + Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit()
    }

    @Synchronized
    fun load(provider: String): Credential? {
        val key = normalize(provider)
        memory[key]?.let { return it }
        val stored = prefs.getString(prefKey(key), null) ?: return null
        if (!stored.startsWith(PREFIX)) {
            // Never consume an old plaintext/custom payload.
            prefs.edit().remove(prefKey(key)).apply()
            return null
        }
        return runCatching {
            val decoded = Base64.decode(stored.removePrefix(PREFIX), Base64.NO_WRAP)
            val json = JSONObject(String(decrypt(decoded), Charsets.UTF_8))
            require(json.optInt("schemaVersion") == 2)
            require(json.optString("provider") == key)
            Credential(json.getString("username"), json.getString("password"), true)
        }.onSuccess { memory[key] = it }
            .onFailure { prefs.edit().remove(prefKey(key)).apply() }
            .getOrNull()
    }

    @Synchronized
    fun has(provider: String): Boolean = load(provider) != null

    @Synchronized
    fun clear(provider: String) {
        val key = normalize(provider)
        memory.remove(key)
        prefs.edit().remove(prefKey(key)).commit()
    }

    fun summary(provider: String): JSONObject = JSONObject()
        .put("provider", normalize(provider))
        .put("stored", has(provider))
        .put("storage", if (has(provider)) "android-keystore-aes-gcm" else "none")
        .put("credentialExportAllowed", false)
        .put("passwordExported", false)

    private fun encrypt(plaintext: ByteArray): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val iv = cipher.iv
        val ciphertext = cipher.doFinal(plaintext)
        return ByteBuffer.allocate(4 + iv.size + ciphertext.size)
            .putInt(iv.size).put(iv).put(ciphertext).array()
    }

    private fun decrypt(payload: ByteArray): ByteArray {
        val buffer = ByteBuffer.wrap(payload)
        val ivLength = buffer.int
        require(ivLength in 12..32 && ivLength <= buffer.remaining()) { "암호화 로그인 정보가 손상되었습니다." }
        val iv = ByteArray(ivLength).also(buffer::get)
        val ciphertext = ByteArray(buffer.remaining()).also(buffer::get)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
        return cipher.doFinal(ciphertext)
    }

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
                .setUserAuthenticationRequired(false)
                .build()
        )
        return generator.generateKey()
    }

    private fun normalize(provider: String): String = provider.trim().lowercase().take(40)
    private fun prefKey(provider: String) = "credential_$provider"

    companion object {
        private const val PREFS = "admission_local_credentials_v2"
        private const val KEY_ALIAS = "admission_hub_credentials_aes_v2"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val PREFIX = "v2:"
    }
}
