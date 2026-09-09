package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * v0.18.2 separates "visible high3" from authenticated protected-session proof.
 * Public high3 pages are never authentication proof. A collector session is verified only after
 * a protected saved-application/report route finishes in the collector WebView without redirecting
 * to a login surface.
 */
object JinhakProtectedSessionPolicy {
    const val SCHEMA_VERSION = 1

    enum class Evidence {
        PUBLIC_HIGH3,
        PROTECTED_SAVED_APPLICATIONS,
        PROTECTED_REPORT,
        LOGIN,
        LOWER_GRADE,
        OTHER
    }

    fun evidence(rawUrl: String): Evidence {
        val url = rawUrl.trim()
        if (url.isBlank()) return Evidence.OTHER
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) return Evidence.LOWER_GRADE
        if (JinhakDedicatedAuthPolicy.isLoginSurface(url)) return Evidence.LOGIN
        val uri = runCatching { URI(url) }.getOrNull() ?: return Evidence.OTHER
        val host = uri.host?.lowercase().orEmpty()
        if (host != "www.jinhak.com" && host != "jinhak.com") return Evidence.OTHER
        val path = uri.path.orEmpty().lowercase().replace('\\', '/').trimEnd('/')
        if (path == "/jh/high3/early/four-year-university/library") {
            return Evidence.PROTECTED_SAVED_APPLICATIONS
        }
        if (path.startsWith("/jh/high3/early/four-year-university/report/")) {
            return Evidence.PROTECTED_REPORT
        }
        if (path == "/jh/high3" || path.startsWith("/jh/high3/")) return Evidence.PUBLIC_HIGH3
        return Evidence.OTHER
    }

    fun isProtectedProofUrl(url: String): Boolean = when (evidence(url)) {
        Evidence.PROTECTED_SAVED_APPLICATIONS, Evidence.PROTECTED_REPORT -> true
        else -> false
    }

    fun isPublicHigh3Only(url: String): Boolean = evidence(url) == Evidence.PUBLIC_HIGH3

    fun shouldRunMissionStallFence(protectedVerified: Boolean, missionTargetCount: Int): Boolean =
        protectedVerified && missionTargetCount > 0
}
