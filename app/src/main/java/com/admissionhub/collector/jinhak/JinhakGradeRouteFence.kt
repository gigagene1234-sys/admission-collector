package com.admissionhub.collector.jinhak

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * v0.17.4 final lower-grade transport fence.
 *
 * high1/high2/high12 are forbidden collector destinations and forbidden request
 * material even when buried inside repeatedly encoded query/fragment/ReturnURL
 * values. The implementation is deliberately fail-closed for those markers and
 * never relies on DOM/UI hiding.
 */
object JinhakGradeRouteFence {
    const val SCHEMA_VERSION = 5
    private const val MAX_DECODE_ROUNDS = 12
    private const val MAX_SCAN_CHARS = 65_536

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
        var candidate = normalize(url.take(MAX_SCAN_CHARS))
        repeat(MAX_DECODE_ROUNDS + 1) {
            if (containsLowerGradeRoute(candidate)) return true
            val decoded = runCatching {
                URLDecoder.decode(candidate, StandardCharsets.UTF_8.name())
            }.getOrDefault(candidate)
            val normalized = normalize(decoded.take(MAX_SCAN_CHARS))
            if (normalized == candidate) return false
            candidate = normalized
        }
        return containsLowerGradeRoute(candidate)
    }

    fun isHigh3(url: String): Boolean {
        if (url.isBlank() || isBlockedLowerGrade(url)) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        val path = normalize(uri.path.orEmpty())
        return path == "/jh/high3" || path.startsWith("/jh/high3/")
    }

    fun protectedHigh3Core(): String = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()

    private fun normalize(value: String): String = value.lowercase().replace('\\', '/')

    private fun containsLowerGradeRoute(value: String): Boolean {
        if (value.isBlank()) return false
        val normalized = normalize(value)
        return lowerGradeRouteMarkers.any(normalized::contains) ||
            lowerGradeTerminalMarkers.any { marker ->
                normalized == marker ||
                    normalized.endsWith(marker) ||
                    normalized.contains("$marker?") ||
                    normalized.contains("$marker#") ||
                    normalized.contains("$marker&") ||
                    normalized.contains("$marker=") ||
                    normalized.contains("$marker%")
            }
    }
}
