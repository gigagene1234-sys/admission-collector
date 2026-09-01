package com.admissionhub.collector.jinhak

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONObject

/**
 * Carries a SAME-APPLICATION identity across Jinhak report navigation.
 *
 * This is provenance propagation, not inference: a bridge may only be armed from an already
 * Gate-A-bound application card. Destination pages never borrow identity from siblings or
 * page-wide text. The bridge expires quickly and is cleared when the mission returns.
 */
object JinhakReportContextBridge {
    const val BRIDGE_VERSION = 1
    private const val MAX_AGE_MS = 5 * 60_000L

    private val reportPageTypes = setOf(
        "jinhak-prediction-report",
        "jinhak-mock-support-report",
        "jinhak-actual-admit-report",
        "jinhak-score-calc-report",
        "jinhak-sat-minimum"
    )

    fun isReportPageType(pageType: String): Boolean = pageType in reportPageTypes

    fun isReportAction(label: String, kind: String): Boolean {
        if (kind == "mission-link-navigation") return true
        return Regex(
            "(합격\\s*예측|모의\\s*지원|실제\\s*합격자|과거\\s*입시결과|성적\\s*분석|성적\\s*산출|리포트|지원자\\s*분포)",
            RegexOption.IGNORE_CASE
        ).containsMatchIn(label)
    }

    fun laneHint(label: String): String = when {
        Regex("실제\\s*합격자|과거\\s*입시결과", RegexOption.IGNORE_CASE).containsMatchIn(label) -> "actual-admit"
        Regex("모의\\s*지원|지원자\\s*분포", RegexOption.IGNORE_CASE).containsMatchIn(label) -> "mock-support"
        Regex("성적\\s*(?:분석|산출)|환산\\s*점수", RegexOption.IGNORE_CASE).containsMatchIn(label) -> "score-analysis"
        Regex("합격\\s*예측|합격\\s*안정성", RegexOption.IGNORE_CASE).containsMatchIn(label) -> "current-prediction"
        else -> "reference"
    }

    fun arm(
        context: JinhakApplicationMission.Context,
        originSafeRoute: String,
        actionLabel: String,
        actionKind: String
    ): JSONObject {
        require(!context.identityKey.isNullOrBlank()) { "Report bridge requires Gate-A application identity" }
        val now = System.currentTimeMillis()
        val lane = laneHint(actionLabel)
        val originCardFingerprint = RecordUtils.sha256(
            listOf(
                context.identityKey ?: "",
                context.rawCombinedLabel ?: "",
                context.university ?: "",
                context.departmentRaw ?: "",
                context.admission ?: ""
            ).joinToString("|")
        )
        val actionToken = RecordUtils.sha256(
            listOf(context.identityKey ?: "", originSafeRoute, actionLabel, actionKind, lane, now.toString()).joinToString("|")
        )
        return JSONObject(context.toJson().toString())
            .put("reportBridgeVersion", BRIDGE_VERSION)
            .put("reportBridgeArmedAtMs", now)
            .put("reportBridgeOriginSafeRoute", originSafeRoute.take(300))
            .put("reportBridgeActionLabel", actionLabel.take(120))
            .put("reportBridgeActionKind", actionKind.take(48))
            .put("reportBridgeLaneHint", lane)
            .put("reportBridgeActionToken", actionToken)
            .put("originCardFingerprint", originCardFingerprint)
            .put("identityProvenance", "same-application-card-before-navigation")
    }

    fun resolve(
        pageType: String,
        liveContext: JinhakApplicationMission.Context?,
        bridge: JSONObject?,
        nowMs: Long = System.currentTimeMillis()
    ): JSONObject? {
        if (!isReportPageType(pageType)) return liveContext?.toJson()
        val bridged = bridge ?: return liveContext?.toJson()
        val armedAt = bridged.optLong("reportBridgeArmedAtMs", 0L)
        if (armedAt <= 0L || nowMs - armedAt > MAX_AGE_MS) return liveContext?.toJson()
        val bridgedContext = JinhakApplicationMission.fromJson(bridged)
        if (bridgedContext?.identityKey.isNullOrBlank()) return liveContext?.toJson()
        if (liveContext?.identityKey != null && liveContext.identityKey != bridgedContext?.identityKey) {
            // Never overwrite a different explicitly bound application context.
            return liveContext.toJson()
        }
        return JSONObject(bridged.toString())
            .put("reportBridgeAppliedToPageType", pageType)
            .put("reportBridgeAppliedAtMs", nowMs)
    }

    fun context(bridge: JSONObject?): JinhakApplicationMission.Context? =
        JinhakApplicationMission.fromJson(bridge)

    fun token(bridge: JSONObject?): String? = bridge?.optString("reportBridgeActionToken")
        ?.takeIf { it.isNotBlank() && it != "null" }
}
