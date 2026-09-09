package com.admissionhub.collector.jinhak

/**
 * v0.19.0 collection-scope policy.
 *
 * The six pinned applications remain the local identity scope, but Jinhak live network collection
 * no longer chases report/evidence lanes. It reads only the protected early-admission storage and
 * periodically snapshots same-card competition data. Missing report lanes are therefore not a
 * crawler error in this mode; they also are not silently treated as satisfied evidence.
 */
object JinhakFocusedSixPolicy {
    const val SCHEMA_VERSION = 2
    const val REQUIRED_PINNED_APPLICATIONS = 6
    const val MAX_UNCHANGED_STATE_SNAPSHOTS = 2

    val REQUIRED_LANES: Set<JinhakMissionLane> = setOf(JinhakMissionLane.SAVED_APPLICATIONS)

    fun isFocusedCoreUrl(rawUrl: String, label: String = ""): Boolean =
        JinhakStorageOnlyPolicy.isLibrary(rawUrl)

    fun shouldSuppressPageType(pageType: String): Boolean = pageType != "jinhak-early-storage"

    fun shouldAllowGenericNavigation(
        pinnedCount: Int,
        outstandingMissionTargets: Int,
        coreComplete: Boolean
    ): Boolean = false

    fun shouldEscapeRepeatedState(
        repeatedCountForState: Int,
        pageType: String,
        hasOutstandingMission: Boolean
    ): Boolean = pageType != "jinhak-early-storage" && repeatedCountForState >= MAX_UNCHANGED_STATE_SNAPSHOTS

    fun pinnedIdentityKeys(slotRows: List<Pair<Boolean, String>>): Set<String> =
        slotRows.asSequence()
            .filter { it.first }
            .map { it.second.trim() }
            .filter { it.isNotBlank() }
            .toCollection(linkedSetOf())
}
