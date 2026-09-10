package com.admissionhub.collector.competition

data class CompetitionBrowserTarget(
    val id: String,
    val university: String,
    val sourceUrl: String,
    val refreshMinutes: Int = 10,
)

object CompetitionBrowserPolicy {
    const val FETCH_LAG_MINUTES = 1
    const val CHECK_INTERVAL_MS = 60_000L
    const val PAGE_TIMEOUT_MS = 30_000L
    const val RENDER_SETTLE_MS = 1_500L
    const val CHALLENGE_RECHECK_MS = 2_500L
    const val MAX_CHALLENGE_RECHECKS = 6
    const val CHALLENGE_VISIBLE_RECHECK_MS = 1_500L
    const val USER_CHALLENGE_TIMEOUT_MS = 180_000L

    val targets = listOf(
        CompetitionBrowserTarget("knut", "국립한국교통대학교", "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio30150631.html"),
        CompetitionBrowserTarget("hanbat", "국립한밭대학교", "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio30040971.html"),
        CompetitionBrowserTarget("hannam", "한남대학교", "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio11560931.html"),
        CompetitionBrowserTarget("kongju", "국립공주대학교", "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio10281081.html"),
    )

    fun isDue(epochMillis: Long, refreshMinutes: Int = 10): Boolean {
        val interval = refreshMinutes.coerceIn(1, 120)
        val minute = Math.floorDiv(epochMillis, 60_000L)
        return Math.floorMod(minute, interval.toLong()) == (FETCH_LAG_MINUTES % interval).toLong()
    }
}
