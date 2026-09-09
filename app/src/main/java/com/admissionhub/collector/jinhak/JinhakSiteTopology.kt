package com.admissionhub.collector.jinhak

import java.net.URI

enum class JinhakMissionLane(val wireName: String, val basePriority: Int) {
    SAVED_APPLICATIONS("saved-applications", 100),
    CURRENT_PREDICTION("current-prediction", 96),
    MOCK_SUPPORT("mock-support", 94),
    ACTUAL_ADMIT("actual-admit", 98),
    UNIVERSITY_RESULT("university-result", 92),
    SCORE_ANALYSIS("score-analysis", 88),
    RECOMMENDATION("recommendation", 48),
    STRATEGY("strategy", 82),
    ADMISSION_KNOWLEDGE("admission-knowledge", 76),
    REFERENCE("reference", 35),
    MEDIA("media", 12),
    UNKNOWN("unknown", 5)
}

/**
 * v0.19.0 route map. Jinhak network collection is deliberately limited to the protected
 * early-admission saved-application library. Lane classification is retained for imported legacy
 * observations, but it no longer expands the live crawler beyond the library.
 */
object JinhakSiteTopology {
    private const val ROOT = "https://www.jinhak.com"

    fun userSessionBootstrapUrl(): String = JinhakStorageOnlyPolicy.LIBRARY_URL

    fun protectedCoreProbeUrl(): String = JinhakStorageOnlyPolicy.LIBRARY_URL

    fun isUserSessionBootstrapUrl(url: String): Boolean = JinhakStorageOnlyPolicy.isLibrary(url)

    fun missionSeeds(): List<String> = listOf(JinhakStorageOnlyPolicy.LIBRARY_URL)

    fun lane(url: String, label: String = ""): JinhakMissionLane {
        val lower = url.lowercase()
        val path = runCatching { URI(url).path?.lowercase().orEmpty() }.getOrDefault(lower)
        val text = "$lower ${label.lowercase()}"
        return when {
            path.contains("/four-year-university/library") || Regex("(수시|정시)?\\s*저장소").containsMatchIn(text) -> JinhakMissionLane.SAVED_APPLICATIONS
            path.contains("/four-year-university/report/pass-predict") -> JinhakMissionLane.CURRENT_PREDICTION
            path.contains("/four-year-university/report/actual-admission") -> JinhakMissionLane.ACTUAL_ADMIT
            path.contains("/four-year-university/report/admission-result") -> JinhakMissionLane.UNIVERSITY_RESULT
            Regex("(actual|actual-admit|admitreport|resultreport|passcase|실제합격자)").containsMatchIn(text) -> JinhakMissionLane.ACTUAL_ADMIT
            Regex("(sapplysample|모의지원\\s*리포트|지원자\\s*분포)").containsMatchIn(text) -> JinhakMissionLane.MOCK_SUPPORT
            path.contains("university-major-predict") || Regex("(합격예측\\s*리포트|대학.?학과별\\s*합격예측|합격안정성)").containsMatchIn(text) -> JinhakMissionLane.CURRENT_PREDICTION
            path.contains("/univ-major/univ-info/univ-search/detail") || Regex("(입시결과|최근\\s*3개년\\s*경쟁률|모집요강)").containsMatchIn(text) -> JinhakMissionLane.UNIVERSITY_RESULT
            Regex("(score|calc|성적분석|교과분석|수능최저)").containsMatchIn(text) -> JinhakMissionLane.SCORE_ANALYSIS
            path.contains("recommend-university") || text.contains("추천대학") -> JinhakMissionLane.RECOMMENDATION
            path.contains("/ipsi-analysis/ipsi-strategy") || text.contains("입시전략") -> JinhakMissionLane.STRATEGY
            path.contains("/ipsi-knowledge") || text.contains("입시지식") || text.contains("입시 상식") -> JinhakMissionLane.ADMISSION_KNOWLEDGE
            path.contains("/jinhak-tv") -> JinhakMissionLane.MEDIA
            path.contains("/early/") || path.contains("/univ-major/") || path.contains("/univ-entrance-info/") -> JinhakMissionLane.REFERENCE
            else -> JinhakMissionLane.UNKNOWN
        }
    }

    fun priority(url: String, label: String = ""): Int {
        if (JinhakStorageOnlyPolicy.isLibrary(url)) return 120
        return lane(url, label).basePriority.coerceIn(0, 120)
    }

    fun isCoreMissionRoute(url: String, label: String = ""): Boolean =
        JinhakStorageOnlyPolicy.isLibrary(url)

    fun isDefaultSusiCoreTraversalUrl(url: String, label: String = ""): Boolean =
        JinhakStorageOnlyPolicy.isLibrary(url)

    fun shouldExpandEditorial(url: String, label: String = ""): Boolean = false
}
