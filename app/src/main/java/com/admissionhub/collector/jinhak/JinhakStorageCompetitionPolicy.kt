package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * v0.18.3 deliberately narrows Jinhak collection to the protected Susi saved-application
 * repository. Competition values are accepted only when they are visibly rendered on the same
 * saved-application card; no applicant/capacity ratio is invented and no university is inferred
 * from a neighbouring card.
 */
object JinhakStorageCompetitionPolicy {
    const val ENABLED = true
    const val REFRESH_INTERVAL_MS = 15L * 60L * 1000L

    data class Reading(
        val currentApplicationCompetition: Double?,
        val displayedCompetition: Double?,
        val currentSemanticsVerified: Boolean,
        val evidenceLabel: String?
    )

    fun isStorageUrl(url: String): Boolean {
        val path = runCatching { URI(url).path?.lowercase()?.trimEnd('/').orEmpty() }.getOrDefault("")
        return path == "/jh/high3/early/four-year-university/library"
    }

    fun readCompetition(text: String): Reading {
        val normalized = text.replace(Regex("\\s+"), " ").trim()
        if (normalized.isBlank()) return Reading(null, null, false, null)

        val qualified = Regex(
            "(?:현재|실시간|원서\\s*접수|원서접수|접수)\\s*경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)\\s*(?::\\s*1|배)?",
            RegexOption.IGNORE_CASE
        ).find(normalized)
        if (qualified != null) {
            val value = qualified.groupValues.getOrNull(1)?.toDoubleOrNull()
            return Reading(value, value, value != null, qualified.value.take(80))
        }

        val generic = Regex("경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)\\s*(?::\\s*1|배)?", RegexOption.IGNORE_CASE)
        for (match in generic.findAll(normalized)) {
            val start = (match.range.first - 28).coerceAtLeast(0)
            val end = (match.range.last + 1 + 12).coerceAtMost(normalized.length)
            val context = normalized.substring(start, end)
            if (Regex("모의\\s*지원|전년도|작년|지난해|최근\\s*[0-9]+개년|202[0-6]\\s*학년도").containsMatchIn(context)) continue
            val value = match.groupValues.getOrNull(1)?.toDoubleOrNull() ?: continue
            return Reading(null, value, false, match.value.take(80))
        }
        return Reading(null, null, false, null)
    }
}
