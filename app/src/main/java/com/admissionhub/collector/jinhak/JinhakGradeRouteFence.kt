package com.admissionhub.collector.jinhak

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * Keeps the admission collector inside the 고3·N수 product at the transport/navigation layer.
 *
 * High1/high2/high12 routes on the same host are forbidden collector destinations. The rule also
 * applies when a lower-grade destination is nested inside query, fragment, return, or redirect
 * parameters. UI hiding/click suppression is intentionally outside this policy and is not used as
 * a substitute for route isolation.
 */
object JinhakGradeRouteFence {
    const val SCHEMA_VERSION = 4

    private val lowerGradeRouteMarkers = listOf(
        "/jh/high1/",
        "/jh/high2/",
        "/jh/high12/"
    )

    private val lowerGradeTerminalMarkers = listOf(
        "/jh/high1",
        "/jh/high2",
        "/jh/high12"
    )

    fun isBlockedLowerGrade(url: String): Boolean {
        if (url.isBlank()) return false
        val uri = runCatching { URI(url) }.getOrNull()
        val path = uri?.path.orEmpty().lowercase()
        if (containsLowerGradeRoute(path)) return true

        var context = buildString {
            append(uri?.rawQuery.orEmpty())
            append('#')
            append(uri?.rawFragment.orEmpty())
        }.lowercase()
        repeat(3) {
            if (containsLowerGradeRoute(context)) return true
            val decoded = runCatching {
                URLDecoder.decode(context, StandardCharsets.UTF_8.name())
            }.getOrDefault(context).lowercase()
            if (decoded == context) return false
            context = decoded
        }
        return containsLowerGradeRoute(context)
    }

    fun isHigh3(url: String): Boolean {
        if (url.isBlank()) return false
        val uri = runCatching { URI(url) }.getOrNull()
        val path = uri?.path.orEmpty().lowercase()
        return path.contains("/jh/high3/") || path.endsWith("/jh/high3")
    }

    fun protectedHigh3Core(): String = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()

    private fun containsLowerGradeRoute(value: String): Boolean {
        if (value.isBlank()) return false
        val normalized = value.lowercase()
        return lowerGradeRouteMarkers.any(normalized::contains) ||
            lowerGradeTerminalMarkers.any { marker ->
                normalized == marker ||
                    normalized.endsWith(marker) ||
                    normalized.contains("$marker?") ||
                    normalized.contains("$marker#") ||
                    normalized.contains("$marker&") ||
                    normalized.contains("$marker=")
            }
    }
}
