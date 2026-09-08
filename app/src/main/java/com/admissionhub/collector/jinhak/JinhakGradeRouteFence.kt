package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * Keeps the admission collector inside the 고3 product during authentication and collection.
 *
 * Jinhak may expose high1/high2/high12 navigation on the same host. Those routes must never be
 * followed by the high3 collector because changing product context can invalidate or replace the
 * authenticated high3 session. Login/member routes are deliberately not blocked here.
 */
object JinhakGradeRouteFence {
    const val SCHEMA_VERSION = 1

    fun isBlockedLowerGrade(url: String): Boolean {
        if (url.isBlank()) return false
        val path = runCatching { URI(url).path.orEmpty().lowercase() }.getOrElse { url.lowercase() }
        return path.contains("/jh/high1/") ||
            path.endsWith("/jh/high1") ||
            path.contains("/jh/high2/") ||
            path.endsWith("/jh/high2") ||
            path.contains("/jh/high12/") ||
            path.endsWith("/jh/high12")
    }

    fun isHigh3(url: String): Boolean {
        if (url.isBlank()) return false
        val path = runCatching { URI(url).path.orEmpty().lowercase() }.getOrElse { url.lowercase() }
        return path.contains("/jh/high3/") || path.endsWith("/jh/high3")
    }

    fun protectedHigh3Core(): String = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
}
