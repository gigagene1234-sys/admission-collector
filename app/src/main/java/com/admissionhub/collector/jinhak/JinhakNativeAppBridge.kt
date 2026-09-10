package com.admissionhub.collector.jinhak

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import org.json.JSONArray
import org.json.JSONObject

/**
 * v0.18.4 optional bridge for the official Jinhak Android application.
 *
 * This bridge intentionally does not attempt to copy cookies, credentials, tokens, or any other
 * authentication material from the provider application. Android application/WebView sessions are
 * separate. Instead, with explicit Accessibility permission from the user, Admission Hub can
 * observe already-rendered, non-editable text while the official app is showing the Susi saved
 * application repository. This avoids depending on Admission Hub's WebView login for those
 * observations.
 */
object JinhakNativeAppBridge {
    const val OFFICIAL_APP_PACKAGE = "com.jinhak.jinhakmobile.android"
    const val PREFS = "jinhak_native_bridge_v0184"
    const val KEY_LATEST = "latest_storage_observation"
    const val STORAGE_WEB_URL = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
    const val MAX_OBSERVATION_AGE_MS = 30L * 60L * 1000L

    data class Status(
        val serviceEnabled: Boolean,
        val appInstalled: Boolean,
        val latestObservedAtMs: Long,
        val latestFresh: Boolean
    )

    fun status(context: Context): Status {
        val latest = latest(context)
        val observedAt = latest?.optLong("observedAtMs", 0L) ?: 0L
        val age = if (observedAt > 0L) System.currentTimeMillis() - observedAt else Long.MAX_VALUE
        return Status(
            serviceEnabled = isAccessibilityServiceEnabled(context),
            appInstalled = isOfficialAppInstalled(context),
            latestObservedAtMs = observedAt,
            latestFresh = observedAt > 0L && age in 0..MAX_OBSERVATION_AGE_MS
        )
    }

    fun isOfficialAppInstalled(context: Context): Boolean = runCatching {
        context.packageManager.getLaunchIntentForPackage(OFFICIAL_APP_PACKAGE) != null
    }.getOrDefault(false)

    fun isAccessibilityServiceEnabled(context: Context): Boolean {
        val manager = context.getSystemService(Context.ACCESSIBILITY_SERVICE) as? AccessibilityManager ?: return false
        val expected = ComponentName(context, JinhakNativeBridgeAccessibilityService::class.java)
        return manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { info ->
                val service = info.resolveInfo?.serviceInfo ?: return@any false
                service.packageName == expected.packageName && service.name == expected.className
            }
    }

    fun accessibilitySettingsIntent(): Intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    /**
     * Prefer an app-owned deep link only when Android reports that the official package can handle
     * it. Otherwise launch the official app's normal entry point and let the user navigate there.
     */
    fun launchOfficialApp(context: Context): Boolean {
        val pm = context.packageManager
        val deepLink = Intent(Intent.ACTION_VIEW, Uri.parse(STORAGE_WEB_URL)).apply {
            setPackage(OFFICIAL_APP_PACKAGE)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        val launch = pm.getLaunchIntentForPackage(OFFICIAL_APP_PACKAGE)?.apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        val chosen = if (deepLink.resolveActivity(pm) != null) deepLink else launch
        if (chosen == null) return false
        return runCatching { context.startActivity(chosen); true }.getOrDefault(false)
    }

    fun latest(context: Context): JSONObject? {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_LATEST, null)
            ?.takeIf { it.isNotBlank() }
            ?: return null
        return runCatching { JSONObject(raw) }.getOrNull()
    }

    internal fun storeObservation(context: Context, visibleLines: List<String>, observedAtMs: Long) {
        val sanitized = visibleLines
            .asSequence()
            .map { it.replace(Regex("\\s+"), " ").trim() }
            .filter { it.isNotBlank() }
            .distinct()
            .take(260)
            .map { it.take(320) }
            .toList()
        val joined = sanitized.joinToString("\n").take(48_000)
        if (!looksLikeSusiStorage(joined)) return

        val readings = JSONArray()
        sanitized.forEachIndexed { index, line ->
            val reading = JinhakStorageCompetitionPolicy.readCompetition(line)
            if (reading.displayedCompetition != null) {
                readings.put(JSONObject()
                    .put("lineIndex", index)
                    .put("displayedCompetition", reading.displayedCompetition)
                    .put("currentApplicationCompetition", reading.currentApplicationCompetition ?: JSONObject.NULL)
                    .put("currentCompetitionSemanticsVerified", reading.currentSemanticsVerified)
                    .put("evidenceLabel", reading.evidenceLabel ?: JSONObject.NULL))
            }
        }
        val payload = JSONObject()
            .put("schemaVersion", 1)
            .put("sourceClass", "jinhak-user-viewed-native-app")
            .put("provider", "jinhak")
            .put("packageName", OFFICIAL_APP_PACKAGE)
            .put("scope", "susi-saved-application-visible-text")
            .put("observedAtMs", observedAtMs)
            .put("observedAt", java.time.Instant.ofEpochMilli(observedAtMs).toString())
            .put("lines", JSONArray(sanitized))
            .put("competitionReadings", readings)
            .put("credentialFieldsCaptured", false)
            .put("editableFieldsCaptured", false)
            .put("cookiesCaptured", false)
            .put("sessionSecretsCaptured", false)
            .put("officialEvidence", false)
            .put("probabilityInferred", false)

        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_LATEST, payload.toString())
            .apply()
    }

    fun looksLikeSusiStorage(text: String): Boolean {
        val normalized = text.replace(Regex("\\s+"), " ").trim()
        if (normalized.isBlank()) return false
        val hasSusi = normalized.contains("수시", ignoreCase = true)
        val hasStorage = Regex("저장\\s*(?:대학|지원|원서|목록|소)|지원\\s*저장|수시\\s*저장", RegexOption.IGNORE_CASE)
            .containsMatchIn(normalized)
        val hasAdmissionMaterial = Regex("대학|학과|전형|경쟁률|모집|지원", RegexOption.IGNORE_CASE)
            .containsMatchIn(normalized)
        val looksLogin = Regex("아이디\\s*$|비밀번호\\s*$|로그인\\s*$", setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE))
            .containsMatchIn(normalized)
        return hasSusi && hasStorage && hasAdmissionMaterial && !looksLogin
    }
}
