package com.admissionhub.collector.session

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Device-only credential store used only when the user explicitly enables automatic login.
 *
 * Credentials are encrypted by an Android Keystore AES/GCM key and are never included in export,
 * diagnostics, logs, SQLite, cloud tasks, or URLs. Native WebView cookies remain owned by WebView.
 */
class CredentialVault(context: Context) {
    data class Credential(val username: String, val password: String)

    private val app = context.applicationContext
    private val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val keyStore: KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    fun has(provider: String): Boolean = load(provider) != null

    fun save(provider: String, username: String, password: String) {
        require(username.isNotBlank()) { "아이디를 입력하세요." }
        require(password.isNotBlank()) { "비밀번호를 입력하세요." }
        val payload = JSONObject()
            .put("username", username)
            .put("password", password)
            .toString().toByteArray(Charsets.UTF_8)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val ciphertext = cipher.doFinal(payload)
        val blob = ByteArray(1 + cipher.iv.size + ciphertext.size)
        blob[0] = cipher.iv.size.toByte()
        System.arraycopy(cipher.iv, 0, blob, 1, cipher.iv.size)
        System.arraycopy(ciphertext, 0, blob, 1 + cipher.iv.size, ciphertext.size)
        prefs.edit().putString(key(provider), Base64.encodeToString(blob, Base64.NO_WRAP)).commit()
    }

    fun load(provider: String): Credential? {
        val encoded = prefs.getString(key(provider), null) ?: return null
        return runCatching {
            val blob = Base64.decode(encoded, Base64.NO_WRAP)
            require(blob.size > 14)
            val ivSize = blob[0].toInt() and 0xff
            require(ivSize in 12..32 && 1 + ivSize < blob.size)
            val iv = blob.copyOfRange(1, 1 + ivSize)
            val ciphertext = blob.copyOfRange(1 + ivSize, blob.size)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, iv))
            val obj = JSONObject(String(cipher.doFinal(ciphertext), Charsets.UTF_8))
            val username = obj.optString("username")
            val password = obj.optString("password")
            if (username.isBlank() || password.isBlank()) null else Credential(username, password)
        }.getOrElse {
            // Corrupt or invalidated keystore data must fail closed rather than prompt-loop forever.
            prefs.edit().remove(key(provider)).commit()
            null
        }
    }

    fun clear(provider: String) {
        prefs.edit().remove(key(provider)).commit()
    }

    fun clearAll() {
        prefs.edit().clear().commit()
    }

    private fun getOrCreateKey(): SecretKey {
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setUserAuthenticationRequired(false)
                .build()
        )
        return generator.generateKey()
    }

    private fun key(provider: String) = "credential_${provider.lowercase()}"

    companion object {
        private const val PREFS = "admission_secure_credentials_v2"
        private const val KEY_ALIAS = "admission_hub_credential_aes_v2"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
