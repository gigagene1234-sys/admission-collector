package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * v0.19.0 intentionally narrows Jinhak collection to the user's protected early-admission
 * saved-application library. Authentication is site-owned: the same collector WebView is allowed
 * to follow Jinhak's natural login redirect and only a natural return to [LIBRARY_URL] proves the
 * protected session. No public high3 page, report route, or other product route is collection scope.
 */
object JinhakStorageOnlyPolicy {
    const val SCHEMA_VERSION = 1
    const val MODE = "storage-only-competition-monitor-v0190"
    const val LIBRARY_URL = "https://www.jinhak.com/jh/high3/early/four-year-university/library"
    const val MONITOR_INTERVAL_MS = 15L * 60L * 1000L

    enum class MainFrameDecision {
        ALLOW_LIBRARY,
        ALLOW_SITE_LOGIN,
        ALLOW_BLANK,
        BLOCK_LOWER_GRADE,
        BLOCK_NON_LIBRARY
    }

    fun isLibrary(rawUrl: String): Boolean {
        val uri = runCatching { URI(rawUrl.trim()) }.getOrNull() ?: return false
        val host = uri.host?.lowercase().orEmpty()
        if (host != "www.jinhak.com" && host != "jinhak.com") return false
        return uri.path.orEmpty().replace('\\', '/').trimEnd('/').lowercase() ==
            "/jh/high3/early/four-year-university/library"
    }

    fun isSiteLogin(rawUrl: String): Boolean = JinhakDedicatedAuthPolicy.isLoginSurface(rawUrl)

    fun decision(rawUrl: String): MainFrameDecision {
        val url = rawUrl.trim()
        if (url.isBlank() || url == "about:blank") return MainFrameDecision.ALLOW_BLANK
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) return MainFrameDecision.BLOCK_LOWER_GRADE
        if (isSiteLogin(url)) return MainFrameDecision.ALLOW_SITE_LOGIN
        if (isLibrary(url)) return MainFrameDecision.ALLOW_LIBRARY
        return MainFrameDecision.BLOCK_NON_LIBRARY
    }

    fun allowsCollectionNavigation(rawUrl: String): Boolean = isLibrary(rawUrl)

    fun shouldPauseForLogin(rawUrl: String): Boolean = isSiteLogin(rawUrl)

    fun shouldResumeFromNaturalReturn(rawUrl: String): Boolean = isLibrary(rawUrl)

    fun shouldScheduleRefresh(
        monitorActive: Boolean,
        protectedSessionVerified: Boolean,
        currentUrl: String
    ): Boolean = monitorActive && protectedSessionVerified && isLibrary(currentUrl)
}
