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

/** Route-first map of the authenticated Jinhak admissions product. */
object JinhakSiteTopology {
    private const val ROOT = "https://www.jinhak.com"

    fun userSessionBootstrapUrl(): String = "$ROOT/jh/high3/early/four-year-university/search"

    fun protectedCoreProbeUrl(): String = "$ROOT/jh/high3/early/four-year-university/library"

    fun isUserSessionBootstrapUrl(url: String): Boolean {
        val path = runCatching { URI(url).path?.lowercase().orEmpty() }.getOrDefault("")
        return path.trimEnd('/') == "/jh/high3/early/four-year-university/search"
    }

    fun missionSeeds(): List<String> = listOf(
        userSessionBootstrapUrl(),
        protectedCoreProbeUrl(),
        "$ROOT/jh/high3/early/four-year-university/university-major-predict",
        "$ROOT/jh/high3/univ-major/univ-info/univ-search",
        "$ROOT/jh/high3/ipsi-analysis/ipsi-strategy"
    )

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
        val lane = lane(url, label)
        var score = lane.basePriority
        if (isUserSessionBootstrapUrl(url)) score = maxOf(score, 86)
        val text = "$url $label"
        if (Regex("(2027|수시|학생부교과|학생부종합|지역인재|면접)").containsMatchIn(text)) score += 4
        if (Regex("(실제합격자|과거\\s*3개년|입시결과|합격예측\\s*리포트|모의지원\\s*리포트)").containsMatchIn(text)) score += 8
        if (lane == JinhakMissionLane.MEDIA) score -= 6
        return score.coerceIn(0, 120)
    }

    fun isCoreMissionRoute(url: String, label: String = ""): Boolean = priority(url, label) >= 80

    /**
     * v0.14.2 no longer blocks read-only strategy/knowledge pages from the default Susi traversal.
     * Media and recommendation discovery remain outside the integrated crawl.
     */
    fun isDefaultSusiCoreTraversalUrl(url: String, label: String = ""): Boolean {
        if (isUserSessionBootstrapUrl(url)) return true
        return when (lane(url, label)) {
        JinhakMissionLane.SAVED_APPLICATIONS,
        JinhakMissionLane.CURRENT_PREDICTION,
        JinhakMissionLane.MOCK_SUPPORT,
        JinhakMissionLane.ACTUAL_ADMIT,
        JinhakMissionLane.UNIVERSITY_RESULT,
        JinhakMissionLane.SCORE_ANALYSIS,
        JinhakMissionLane.STRATEGY,
        JinhakMissionLane.ADMISSION_KNOWLEDGE -> true
        JinhakMissionLane.REFERENCE,
        JinhakMissionLane.RECOMMENDATION,
        JinhakMissionLane.MEDIA,
        JinhakMissionLane.UNKNOWN -> false
        }
    }

    fun shouldExpandEditorial(url: String, label: String = ""): Boolean = when (lane(url, label)) {
        JinhakMissionLane.UNIVERSITY_RESULT,
        JinhakMissionLane.STRATEGY,
        JinhakMissionLane.ADMISSION_KNOWLEDGE -> true
        else -> false
    }
}
