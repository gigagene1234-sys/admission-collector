package com.admissionhub.collector.hub

import org.json.JSONArray
import org.json.JSONObject

/** Read-only display model. It never changes collection state or generates probabilities. */
object PipelineCompletionModel {
    fun build(status: JSONObject, hub: JSONObject): JSONObject {
        val summary = hub.optJSONObject("summary") ?: JSONObject()
        val cards = hub.optJSONArray("cards") ?: JSONArray()
        val selected = summary.optInt("selected", 0)
        val diagnostics = status.optJSONObject("jinhakDiagnosticsSummary") ?: status
        val verified = diagnostics.optInt("jinhakV0912ProtectedCoreVerified", 0) > 0
        val batchStarts = diagnostics.optInt("jinhakBatchStartCount", 0)
        val predictions = summary.optInt("predictionCollected", 0)
        val terminalReviews = (0 until cards.length()).count { index ->
            val card = cards.optJSONObject(index) ?: return@count false
            if (!card.optBoolean("occupied", false)) return@count false
            val review = card.optJSONObject("applicationReview") ?: JSONObject()
            val relation = review.optString("relation", review.optString("code", "HOLD"))
            relation != "HOLD" || review.optString("disclaimer").isNotBlank() ||
                (review.optJSONArray("missing")?.length() ?: 0) > 0 ||
                (review.optJSONArray("risks")?.length() ?: 0) > 0
        }
        val stages = JSONArray()
            .put(stage("1. 진학사 로그인 확인", if (verified) "COMPLETE" else "WAITING", "protected high3 확인", if (verified) "1/1" else "0/1"))
            .put(stage("2. 진학사 수집 시작", if (batchStarts > 0) "COMPLETE" else if (verified) "READY" else "WAITING", "batch 시작 1회 이상", "$batchStarts 회"))
            .put(stage("3. 진학사 사용자 열람 자료", if (predictions > 0) "COMPLETE" else if (batchStarts > 0) "IN_PROGRESS" else "WAITING", "실제 수집값 증가", "$predictions/$selected 지원안"))
            .put(stage("4. 공식 근거", if (summary.optInt("officialCurrentComponentsVerified", 0) >= selected && selected > 0) "COMPLETE" else "HOLD", "어디가/대학 공식 근거 확인", "${summary.optInt("officialCurrentComponentsVerified", 0)}/$selected"))
            .put(stage("5. 공식 환산", if (summary.optInt("verifiedConversions", 0) >= selected && selected > 0) "COMPLETE" else "HOLD", "검증 산식 또는 정량대상 아님 명시", "${summary.optInt("verifiedConversions", 0)}/$selected"))
            .put(stage("6. 근거 안전 판단", if (terminalReviews >= selected && selected > 0) "COMPLETE" else "HOLD", "비교 가능 또는 근거가 명시된 HOLD", "$terminalReviews/$selected"))
        return JSONObject()
            .put("stages", stages)
            .put("complete", selected > 0 && verified && batchStarts > 0 && predictions > 0 && terminalReviews >= selected)
            .put("completionRule", "로그인 확인 → batch 시작 → 진학사 자료 관측 → 6장 모두 비교 가능 또는 근거가 명시된 HOLD")
    }

    private fun stage(label: String, state: String, criterion: String, evidence: String) = JSONObject()
        .put("label", label)
        .put("state", state)
        .put("criterion", criterion)
        .put("evidence", evidence)
}
