from pathlib import Path

MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
VAULT = Path('app/src/main/java/com/admissionhub/collector/session/SecureSessionVault.kt')
GRADLE = Path('app/build.gradle.kts')
MANIFEST = Path('app/src/main/AndroidManifest.xml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


main = MAIN.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

# ---------------------------------------------------------------------------
# v0.9.2 Persistent Session Bundle
# - store provider session cookies in a dedicated Android-Keystore encrypted
#   multi-origin bundle, separate from unified collection/export data;
# - migrate the existing v1 single-origin lease locally on first restore;
# - if both provider bundles restore, bypass DOM login preflight entirely and
#   start the existing unified collection directly;
# - passwords/form values/DOM storage/CAPTCHA are never captured;
# - raw session secrets are never exported or logged.
# ---------------------------------------------------------------------------

main = replace_once(
    main,
    '        private const val VERSION = "0.9.1"\n        private const val BUILD_CODE = 10910\n',
    '        private const val VERSION = "0.9.2"\n        private const val BUILD_CODE = 10920\n',
    'main version'
)
gradle = replace_once(
    gradle,
    '        versionCode = 10910\n        versionName = "0.9.1"\n',
    '        versionCode = 10920\n        versionName = "0.9.2"\n',
    'gradle version'
)
manifest = replace_once(
    manifest,
    'android:label="Admission Collector v0.9.1 Mission Bootstrap Recovery"',
    'android:label="Admission Collector v0.9.2 Persistent Session Bundle"',
    'manifest label'
)

main = replace_once(
    main,
    '    private var startupLoginVerifiedAtMs = 0L\n',
    '    private var startupLoginVerifiedAtMs = 0L\n'
    '    private var startupSessionPreflightBypassed = false\n',
    'stored-session telemetry field'
)

main = replace_once(
    main,
    '            text = "세션 확인/갱신"\n',
    '            text = "로그인 세션 저장/갱신"\n',
    'session button label'
)

# Reset direct-session telemetry with every new startup attempt.
main = replace_once(
    main,
    '        startupLoginUiOpenCount = 0\n        startupLoginVerifiedAtMs = 0L\n        startupLoginPollGeneration += 1\n',
    '        startupLoginUiOpenCount = 0\n'
    '        startupLoginVerifiedAtMs = 0L\n'
    '        startupSessionPreflightBypassed = false\n\n'
    '        // v0.9.2: restore the encrypted provider session bundles first. When both are\n'
    '        // present, do not navigate through the login-preflight UI at all. Server-side\n'
    '        // expiry is still handled by the existing batch login-pause/recovery path.\n'
    '        val storedAdiga = runCatching { sessionVault.restore(ProviderId.ADIGA.wireName) }.getOrNull()\n'
    '        val storedJinhak = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()\n'
    '        startupLoginAdigaRestoredLease = storedAdiga?.restored == true\n'
    '        startupLoginJinhakRestoredLease = storedJinhak?.restored == true\n'
    '        if (startupLoginAdigaRestoredLease && startupLoginJinhakRestoredLease) {\n'
    '            CookieManager.getInstance().flush()\n'
    '            startupSessionPreflightBypassed = true\n'
    '            startupLoginPreflightActive = false\n'
    '            startupLoginPreflightVerified = true\n'
    '            startupLoginStage = "stored-session-direct"\n'
    '            startupLoginVerifiedAtMs = System.currentTimeMillis()\n'
    '            startupLoginPollGeneration += 1\n'
    '            unifiedButton.text = "통합 수집 시작 중"\n'
    '            sessionState.text = "● 암호화 로그인 세션 복원 완료"\n'
    '            status.text = "저장된 어디가·진학사 로그인 세션을 복원했습니다. 로그인 사전검사를 건너뛰고 통합 수집을 시작합니다."\n'
    '            recordRuntimeEvent("startup-stored-session-direct", JSONObject()\n'
    '                .put("trigger", startupLoginTrigger)\n'
    '                .put("adigaRestored", true)\n'
    '                .put("jinhakRestored", true)\n'
    '                .put("passwordStored", false)\n'
    '                .put("sessionSecretStoredLocally", true)\n'
    '                .put("sessionSecretExported", false))\n'
    '            handler.postDelayed({\n'
    '                if (!unifiedRunning && !batchRunning && startupSessionPreflightBypassed) {\n'
    '                    startUnifiedCollectionAuthenticated()\n'
    '                }\n'
    '            }, 300L)\n'
    '            return\n'
    '        }\n\n'
    '        startupLoginPollGeneration += 1\n',
    'direct stored-session bootstrap'
)

# Make exported precheck semantics explicit: internal collection readiness may be
# satisfied by encrypted session restoration, while DOM authentication is only
# claimed when it was actually observed.
main = replace_once(
    main,
    '                    .put("verified", startupLoginPreflightVerified)\n'
    '                    .put("adigaAuthenticated", startupLoginAdigaAuthenticated)\n'
    '                    .put("jinhakAuthenticated", startupLoginJinhakAuthenticated)\n'
    '                    .put("adigaRestoredLease", startupLoginAdigaRestoredLease)\n'
    '                    .put("jinhakRestoredLease", startupLoginJinhakRestoredLease)\n'
    '                    .put("loginUiOpenCount", startupLoginUiOpenCount)\n'
    '                    .put("verifiedAtMs", startupLoginVerifiedAtMs)\n'
    '                    .put("credentialStored", false)),\n',
    '                    .put("verified", startupLoginAdigaAuthenticated && startupLoginJinhakAuthenticated)\n'
    '                    .put("collectionBootstrapReady", startupLoginPreflightVerified)\n'
    '                    .put("bypassedByStoredSession", startupSessionPreflightBypassed)\n'
    '                    .put("adigaAuthenticated", startupLoginAdigaAuthenticated)\n'
    '                    .put("jinhakAuthenticated", startupLoginJinhakAuthenticated)\n'
    '                    .put("adigaRestoredLease", startupLoginAdigaRestoredLease)\n'
    '                    .put("jinhakRestoredLease", startupLoginJinhakRestoredLease)\n'
    '                    .put("loginUiOpenCount", startupLoginUiOpenCount)\n'
    '                    .put("verifiedAtMs", startupLoginVerifiedAtMs)\n'
    '                    .put("passwordStored", false)\n'
    '                    .put("sessionSecretStoredLocally", startupLoginAdigaRestoredLease || startupLoginJinhakRestoredLease)\n'
    '                    .put("sessionSecretExported", false)),\n',
    'precheck session semantics'
)

# Do not describe an encrypted session cookie as "no credential" in runtime
# telemetry. It is a session secret, distinct from the user's password.
main = main.replace(
    '.put("credentialStored", false)',
    '.put("passwordStored", false).put("sessionSecretStoredLocally", true).put("sessionSecretExported", false)'
)

VAULT.write_text(r'''package com.admissionhub.collector.session

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.webkit.CookieManager
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.security.KeyStore
import java.time.Instant
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * v0.9.2 device-local persistent WebView session bundle.
 *
 * Security boundary:
 * - stores first-party WebView session cookie material only after an authenticated page was observed;
 * - never stores a password, form value, DOM/localStorage/sessionStorage value or CAPTCHA material;
 * - all raw cookie/session material is AES-GCM encrypted with a non-exportable Android Keystore key;
 * - raw session material never enters unified JSON, diagnostics, logs, cloud sync, or GitHub;
 * - Android application backup is disabled by the manifest, so the encrypted prefs remain device-local;
 * - SessionLeaseSummary contains metadata only. A session cookie is explicitly treated as a secret.
 *
 * v1 compatibility:
 * - existing single-origin v0.9.1 leases are decrypted locally with the legacy key and migrated to the
 *   dedicated v2 multi-origin store on first restore. No session material leaves the device.
 */
class SecureSessionVault(context: Context) {
    data class SessionLeaseSummary(
        val provider: String,
        val leaseId: String,
        val origin: String,
        val capturedAt: String,
        val collectorVersion: String,
        val cookieCount: Int,
        val originCount: Int = 1,
        val storageVersion: Int = 2,
        val restored: Boolean = false
    ) {
        fun toJson(): JSONObject = JSONObject()
            .put("provider", provider)
            .put("leaseId", leaseId)
            .put("origin", origin)
            .put("capturedAt", capturedAt)
            .put("collectorVersion", collectorVersion)
            .put("cookieCount", cookieCount)
            .put("originCount", originCount)
            .put("storageVersion", storageVersion)
            .put("restored", restored)
            .put("containsPassword", false)
            .put("containsSessionSecret", true)
            .put("cloudExportAllowed", false)
    }

    private data class Bundle(
        val provider: String,
        val leaseId: String,
        val capturedAt: String,
        val collectorVersion: String,
        val entries: LinkedHashMap<String, String>
    )

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences(PREFS_V2, Context.MODE_PRIVATE)
    private val legacyPrefs = appContext.getSharedPreferences(PREFS_V1, Context.MODE_PRIVATE)

    fun captureAuthenticated(provider: String, pageUrl: String, collectorVersion: String): SessionLeaseSummary? {
        val pageOrigin = safeOrigin(pageUrl) ?: return null
        val existing = loadV2(provider) ?: loadLegacy(provider)
        val entries = linkedMapOf<String, String>()
        existing?.entries?.forEach { (origin, header) ->
            if (origin.isNotBlank() && header.isNotBlank()) entries[origin] = header
        }

        val manager = CookieManager.getInstance()
        val captureUrls = linkedSetOf(pageUrl)
        canonicalHome(provider)?.let { captureUrls.add(it) }
        for (url in captureUrls) {
            val origin = safeOrigin(url) ?: continue
            val header = manager.getCookie(url).orEmpty().trim()
            if (header.isNotBlank()) entries[origin] = header
        }
        if (entries.isEmpty()) return null

        val leaseId = existing?.leaseId?.takeIf { it.isNotBlank() } ?: UUID.randomUUID().toString()
        val capturedAt = Instant.now().toString()
        val bundle = Bundle(provider, leaseId, capturedAt, collectorVersion, entries)
        saveV2(bundle)
        return summaryOf(bundle, restored = false, preferredOrigin = pageOrigin)
    }

    fun restore(provider: String): SessionLeaseSummary? {
        val bundle = loadV2(provider) ?: migrateLegacy(provider) ?: return null
        val manager = CookieManager.getInstance()
        manager.setAcceptCookie(true)
        var restoredCookies = 0
        var restoredOrigins = 0
        for ((origin, header) in bundle.entries) {
            var restoredThisOrigin = 0
            header.split(';').map { it.trim() }.filter { it.contains('=') }.forEach { cookie ->
                runCatching {
                    // CookieManager#getCookie does not expose original attributes. Restore only the
                    // first-party name/value at the captured host and do not broaden Domain scope.
                    manager.setCookie(origin, "$cookie; Path=/; Secure")
                    restoredCookies += 1
                    restoredThisOrigin += 1
                }
            }
            if (restoredThisOrigin > 0) restoredOrigins += 1
        }
        manager.flush()
        if (restoredCookies <= 0) return summaryOf(bundle, restored = false)
        return SessionLeaseSummary(
            provider = bundle.provider,
            leaseId = bundle.leaseId,
            origin = bundle.entries.keys.firstOrNull().orEmpty(),
            capturedAt = bundle.capturedAt,
            collectorVersion = bundle.collectorVersion,
            cookieCount = restoredCookies,
            originCount = restoredOrigins,
            storageVersion = 2,
            restored = true
        )
    }

    fun summary(provider: String): SessionLeaseSummary? {
        val bundle = loadV2(provider) ?: legacyAsBundle(provider) ?: return null
        return summaryOf(bundle, restored = false)
    }

    fun clear(provider: String) {
        prefs.edit().remove(secretKey(provider)).remove(metadataKey(provider)).apply()
        legacyPrefs.edit().remove(legacySecretKey(provider)).remove(legacyMetadataKey(provider)).apply()
    }

    private fun saveV2(bundle: Bundle) {
        val entriesJson = JSONArray()
        bundle.entries.forEach { (origin, header) ->
            entriesJson.put(JSONObject().put("origin", origin).put("cookieHeader", header))
        }
        val payload = JSONObject()
            .put("schemaVersion", 2)
            .put("provider", bundle.provider)
            .put("leaseId", bundle.leaseId)
            .put("capturedAt", bundle.capturedAt)
            .put("collectorVersion", bundle.collectorVersion)
            .put("entries", entriesJson)
        val encrypted = encrypt(payload.toString().toByteArray(Charsets.UTF_8), KEY_ALIAS_V2)
        val count = bundle.entries.values.sumOf { cookieCount(it) }
        prefs.edit()
            .putString(secretKey(bundle.provider), encrypted)
            .putString(metadataKey(bundle.provider), JSONObject()
                .put("provider", bundle.provider)
                .put("leaseId", bundle.leaseId)
                .put("capturedAt", bundle.capturedAt)
                .put("collectorVersion", bundle.collectorVersion)
                .put("cookieCount", count)
                .put("originCount", bundle.entries.size)
                .put("storageVersion", 2)
                .toString())
            .apply()
    }

    private fun loadV2(provider: String): Bundle? {
        val encoded = prefs.getString(secretKey(provider), null)?.takeIf { it.isNotBlank() } ?: return null
        val raw = runCatching { String(decrypt(encoded, KEY_ALIAS_V2), Charsets.UTF_8) }.getOrNull() ?: return null
        val payload = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        if (payload.optInt("schemaVersion", 0) != 2 || payload.optString("provider") != provider) return null
        val entries = linkedMapOf<String, String>()
        val array = payload.optJSONArray("entries") ?: JSONArray()
        for (i in 0 until array.length()) {
            val obj = array.optJSONObject(i) ?: continue
            val origin = obj.optString("origin").takeIf { safeOrigin(it) == it } ?: continue
            val header = obj.optString("cookieHeader").trim()
            if (header.isNotBlank()) entries[origin] = header
        }
        if (entries.isEmpty()) return null
        return Bundle(
            provider = provider,
            leaseId = payload.optString("leaseId").ifBlank { UUID.randomUUID().toString() },
            capturedAt = payload.optString("capturedAt").ifBlank { Instant.now().toString() },
            collectorVersion = payload.optString("collectorVersion").ifBlank { "unknown" },
            entries = entries
        )
    }

    private fun migrateLegacy(provider: String): Bundle? {
        val legacy = loadLegacy(provider) ?: return null
        saveV2(legacy)
        // Remove the old encrypted copy only after the new encrypted bundle has been written.
        legacyPrefs.edit().remove(legacySecretKey(provider)).remove(legacyMetadataKey(provider)).apply()
        return legacy
    }

    private fun legacyAsBundle(provider: String): Bundle? = loadLegacy(provider)

    private fun loadLegacy(provider: String): Bundle? {
        val encoded = legacyPrefs.getString(legacySecretKey(provider), null)?.takeIf { it.isNotBlank() } ?: return null
        val raw = runCatching { String(decrypt(encoded, KEY_ALIAS_V1), Charsets.UTF_8) }.getOrNull() ?: return null
        val payload = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        if (payload.optString("provider") != provider) return null
        val origin = payload.optString("origin").takeIf { safeOrigin(it) == it } ?: return null
        val header = payload.optString("cookieHeader").trim().takeIf { it.isNotBlank() } ?: return null
        return Bundle(
            provider = provider,
            leaseId = payload.optString("leaseId").ifBlank { UUID.randomUUID().toString() },
            capturedAt = payload.optString("capturedAt").ifBlank { Instant.now().toString() },
            collectorVersion = payload.optString("collectorVersion").ifBlank { "legacy-v1" },
            entries = linkedMapOf(origin to header)
        )
    }

    private fun summaryOf(bundle: Bundle, restored: Boolean, preferredOrigin: String? = null): SessionLeaseSummary {
        val origin = preferredOrigin?.takeIf { bundle.entries.containsKey(it) } ?: bundle.entries.keys.firstOrNull().orEmpty()
        return SessionLeaseSummary(
            provider = bundle.provider,
            leaseId = bundle.leaseId,
            origin = origin,
            capturedAt = bundle.capturedAt,
            collectorVersion = bundle.collectorVersion,
            cookieCount = bundle.entries.values.sumOf { cookieCount(it) },
            originCount = bundle.entries.size,
            storageVersion = 2,
            restored = restored
        )
    }

    private fun canonicalHome(provider: String): String? = when (provider.lowercase()) {
        "adiga" -> "https://www.adiga.kr/"
        "jinhak" -> "https://www.jinhak.com/"
        else -> null
    }

    private fun cookieCount(header: String): Int =
        header.split(';').count { it.trim().contains('=') }

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

    private fun secretKey(provider: String) = "bundle_${provider.lowercase()}"
    private fun metadataKey(provider: String) = "bundle_meta_${provider.lowercase()}"
    private fun legacySecretKey(provider: String) = "secret_${provider.lowercase()}"
    private fun legacyMetadataKey(provider: String) = "meta_${provider.lowercase()}"

    private fun key(alias: String): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
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

    private fun encrypt(bytes: ByteArray, alias: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key(alias))
        val iv = cipher.iv
        val encrypted = cipher.doFinal(bytes)
        val out = ByteArray(1 + iv.size + encrypted.size)
        out[0] = iv.size.toByte()
        System.arraycopy(iv, 0, out, 1, iv.size)
        System.arraycopy(encrypted, 0, out, 1 + iv.size, encrypted.size)
        return Base64.encodeToString(out, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String, alias: String): ByteArray {
        val all = Base64.decode(encoded, Base64.NO_WRAP)
        require(all.isNotEmpty())
        val ivSize = all[0].toInt() and 0xff
        require(ivSize in 12..32 && all.size > 1 + ivSize)
        val iv = all.copyOfRange(1, 1 + ivSize)
        val encrypted = all.copyOfRange(1 + ivSize, all.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(alias), GCMParameterSpec(128, iv))
        return cipher.doFinal(encrypted)
    }

    companion object {
        private const val PREFS_V2 = "admission_secure_session_bundle_v2"
        private const val KEY_ALIAS_V2 = "admission_collector_session_bundle_v2"
        private const val PREFS_V1 = "admission_secure_session_v1"
        private const val KEY_ALIAS_V1 = "admission_collector_session_v1"
    }
}
''')

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

print('Applied v0.9.2 persistent session bundle patch')
