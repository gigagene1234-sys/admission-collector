package com.admissionhub.collector.jinhak

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * Keeps the admission collector inside the 고3·N수 product during authentication and collection.
 *
 * Jinhak can expose high1/high2/high12 product routes on the same host and can also carry a return
 * route inside a generic member-login URL. The high3 collector must reject those lower-grade
 * destinations before navigation. A plain /jh/member/login URL remains legal because it is a shared
 * authentication surface; lower-grade context inside that surface is fenced separately in the DOM.
 */
object JinhakGradeRouteFence {
    const val SCHEMA_VERSION = 3

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

        // A shared login URL is allowed only when it does not carry an explicit lower-grade
        // destination in query/fragment/redirect parameters. Decode repeatedly so nested redirect
        // parameters such as %252Fjh%252Fhigh2%252F... cannot bypass the route fence.
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
