package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * v0.18.1 mission-scope policy.
 *
 * Once the user has six pinned applications, Jinhak collection is not an open web crawl.
 * Only routes capable of supplying one of the six evidence lanes may enter the collector
 * frontier. Editorial/strategy/knowledge/reference pages are observation-only and never
 * become autonomous navigation targets during the six-application mission.
 */
object JinhakFocusedSixPolicy {
    const val SCHEMA_VERSION = 1
    const val REQUIRED_PINNED_APPLICATIONS = 6
    const val MAX_UNCHANGED_STATE_SNAPSHOTS = 2

    val REQUIRED_LANES: Set<JinhakMissionLane> = setOf(
        JinhakMissionLane.SAVED_APPLICATIONS,
        JinhakMissionLane.CURRENT_PREDICTION,
        JinhakMissionLane.MOCK_SUPPORT,
        JinhakMissionLane.ACTUAL_ADMIT,
        JinhakMissionLane.SCORE_ANALYSIS,
        JinhakMissionLane.UNIVERSITY_RESULT
    )

    private val suppressedPathFragments = listOf(
        "/ipsi-analysis/ipsi-strategy",
        "/ipsi-knowledge",
        "/jinhak-tv",
        "/curation",
        "/susi-special",
        "/major-deep-analysis",
        "/ipsi-deep-analysis"
    )

    fun isFocusedCoreUrl(rawUrl: String, label: String = ""): Boolean {
        if (rawUrl.isBlank()) return false
        if (!JinhakStrictHigh3Sandbox.allowsCollectorNavigation(rawUrl)) return false
        val path = runCatching { URI(rawUrl).path.orEmpty().lowercase() }.getOrDefault("")
        if (suppressedPathFragments.any(path::contains)) return false
        return JinhakSiteTopology.lane(rawUrl, label) in REQUIRED_LANES
    }

    fun shouldSuppressPageType(pageType: String): Boolean = pageType in setOf(
        "jinhak-home",
        "jinhak-other",
        "jinhak-admission-strategy",
        "jinhak-admission-knowledge",
        "jinhak-admission-feature",
        "jinhak-editorial-content",
        "jinhak-media-content",
        "jinhak-curation",
        "jinhak-recommended-university"
    )

    fun shouldAllowGenericNavigation(
        pinnedCount: Int,
        outstandingMissionTargets: Int,
        coreComplete: Boolean
    ): Boolean {
        if (pinnedCount >= REQUIRED_PINNED_APPLICATIONS) return false
        return outstandingMissionTargets == 0 && coreComplete
    }

    fun shouldEscapeRepeatedState(
        repeatedCountForState: Int,
        pageType: String,
        hasOutstandingMission: Boolean
    ): Boolean {
        if (repeatedCountForState < MAX_UNCHANGED_STATE_SNAPSHOTS) return false
        if (shouldSuppressPageType(pageType)) return true
        return !hasOutstandingMission
    }

    fun pinnedIdentityKeys(slotRows: List<Pair<Boolean, String>>): Set<String> =
        slotRows.asSequence()
            .filter { it.first }
            .map { it.second.trim() }
            .filter { it.isNotBlank() }
            .toCollection(linkedSetOf())
}