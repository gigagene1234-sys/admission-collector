package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

/**
 * Evidence-safe comparison engine.
 *
 * It never manufactures a university conversion formula, an official cut, or an admission
 * probability. A relation is emitted only when formula/scoring scope, score scale, comparison
 * direction and one official reference are explicit. Direct same-row application binding remains
 * a separate fact from a verified university-wide scoring scope.
 */
object ScoreDecisionEngine {
    const val SCHEMA_VERSION = 2

    fun evaluate(
        canonicalQuality: String,
        conversion: JSONObject?,
        officialOutcomes: JSONArray,
        prediction: JSONObject?
    ): JSONObject {
        val conversionDetail = conversion?.optJSONObject("detail") ?: JSONObject()
        val directIdentityBinding = conversion?.optBoolean("identityBindingVerified", false) == true
        val scoringScopeBinding = conversionDetail.optBoolean("scoringScopeBindingVerified", false)
        val base = JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("canonicalQuality", canonicalQuality)
            .put("predictionAvailable", prediction != null)
            .put("predictionStructured", prediction?.optBoolean("structured", false) == true)
            .put("predictionObservedAt", prediction?.optString("observedAt").orEmpty())
            .put("directApplicationBindingVerified", directIdentityBinding)
            .put("scoringScopeBindingVerified", scoringScopeBinding)
            .put("probabilityInferred", false)
            .put("unsupportedThresholdsUsed", false)

        if (conversion == null || !conversion.optBoolean("verified", false) || conversion.optString("status") != "verified") {
            return hold(base, "UNVERIFIED_CONVERSION", "판정 보류 · 대학별 공식 환산 산식 확인 필요")
        }
        if (!conversion.has("scoreValue") || conversion.isNull("scoreValue")) {
            return hold(base, "MISSING_CONVERSION_SCORE", "판정 보류 · 대학 환산점수 없음")
        }
        val scale = conversion.optString("scoreScale").trim()
        if (scale.isBlank() || scale == "null") {
            return hold(base, "MISSING_SCORE_SCALE", "판정 보류 · 점수 척도 미확인")
        }
        val direction = conversion.optString("comparisonDirection").trim()
        if (direction !in setOf("higher-is-better", "lower-is-better")) {
            return hold(base, "UNKNOWN_COMPARISON_DIRECTION", "판정 보류 · 점수 방향성 미확인")
        }
        if (canonicalQuality != "accepted" && !directIdentityBinding && !scoringScopeBinding) {
            return hold(base, "UNVERIFIED_SCORING_SCOPE", "판정 보류 · 이 모집단위에 적용할 공식 환산 범위 확인 필요")
        }

        val comparable = mutableListOf<JSONObject>()
        val ownFinite = conversion.optNullableDouble("scoreValue")
            ?: return hold(base, "INVALID_CONVERSION_SCORE", "판정 보류 · 환산점수가 유효한 숫자가 아님")
        val conversionMax = conversion.optNullableDouble("maxScore")
        for (i in 0 until officialOutcomes.length()) {
            val outcome = officialOutcomes.optJSONObject(i) ?: continue
            if (!outcome.optBoolean("verified", false)) continue
            if (!outcome.has("metricValue") || outcome.isNull("metricValue")) continue
            if (outcome.optNullableDouble("metricValue") == null) continue
            if (outcome.optString("scoreScale").trim() != scale) continue
            val outcomeMax = outcome.optNullableDouble("maxScore")
            if (conversionMax != null && outcomeMax != null && abs(conversionMax - outcomeMax) > 1e-9) continue
            comparable += outcome
        }
        if (comparable.isEmpty()) {
            return hold(base, "NO_COMPARABLE_OFFICIAL_OUTCOME", "판정 보류 · 같은 척도로 직접 비교할 수 있는 검증된 공식 입결 없음")
        }
        val primary = comparable.filter { it.optBoolean("primaryReference", false) }
        val reference = when {
            primary.size == 1 -> primary.first()
            primary.size > 1 -> return hold(base, "AMBIGUOUS_PRIMARY_REFERENCE", "판정 보류 · 공식 기준점이 여러 개 지정됨")
            comparable.size == 1 -> comparable.first()
            else -> return hold(base, "AMBIGUOUS_OFFICIAL_REFERENCE", "판정 보류 · 비교할 공식 입결 지표 선택 필요")
        }

        val own = ownFinite
        val ref = reference.optDouble("metricValue")
        val advantage = if (direction == "higher-is-better") own - ref else ref - own
        val relation = when {
            advantage > 1e-9 -> "ABOVE_REFERENCE"
            advantage < -1e-9 -> "BELOW_REFERENCE"
            else -> "AT_REFERENCE"
        }
        val label = when (relation) {
            "ABOVE_REFERENCE" -> "공식 참고선보다 유리"
            "BELOW_REFERENCE" -> "공식 참고선보다 불리"
            else -> "공식 참고선과 동일"
        }
        return base
            .put("status", "COMPARABLE")
            .put("hold", false)
            .put("decisionCode", relation)
            .put("decisionLabel", label)
            .put("confidence", "VERIFIED_COMPARISON")
            .put("advantageMargin", advantage)
            .put("scoreScale", scale)
            .put("comparisonDirection", direction)
            .put("referenceOutcome", JSONObject(reference.toString()))
    }

    private fun hold(base: JSONObject, code: String, label: String): JSONObject = base
        .put("status", "HOLD")
        .put("hold", true)
        .put("decisionCode", code)
        .put("decisionLabel", label)
        .put("confidence", "INSUFFICIENT_EVIDENCE")
        .put("advantageMargin", JSONObject.NULL)

    private fun JSONObject.optNullableDouble(key: String): Double? =
        if (!has(key) || isNull(key)) null else optDouble(key).takeUnless { it.isNaN() || it.isInfinite() }
}
