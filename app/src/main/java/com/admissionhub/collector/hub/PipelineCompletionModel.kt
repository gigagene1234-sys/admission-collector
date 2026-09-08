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

        val verified = diagnostics.optInt("jinhakV0912ProtectedCoreVerified", 0) > 0 ||
            diagnostics.optBoolean("authVerifiedForBatch", false)
        val batchStarts = diagnostics.optInt("jinhakBatchStartCount", 0)
        val manualWaits = diagnostics.optInt("jinhakV0165ManualLoginWaits", 0)
        val manualHandoffs = diagnostics.optInt("jinhakV0165ManualLoginVerifiedHandoffs", 0)
        val predictions = summary.optInt("predictionCollected", 0)
        val records = providerRecords(status, "jinhak")
        val snapshots = diagnostics.optInt("successfulSnapshots", 0)
        val evidenceObserved = predictions > 0 || records > 0 || snapshots > 0

        val terminalReviews = (0 until cards.length()).count { index ->
            val card = cards.optJSONObject(index) ?: return@count false
            if (!card.optBoolean("occupied", false)) return@count false
            val review = card.optJSONObject("applicationReview") ?: JSONObject()
            val relation = review.optString("relation", review.optString("code", "HOLD"))
            relation != "HOLD" || review.optString("disclaimer").isNotBlank() ||
                (review.optJSONArray("missing")?.length() ?: 0) > 0 ||
                (review.optJSONArray("risks")?.length() ?: 0) > 0 ||
                (review.optJSONArray("reasons")?.length() ?: 0) > 0
        }

        val officialVerified = summary.optInt("officialCurrentComponentsVerified", 0)
        val conversions = summary.optInt("verifiedConversions", 0)
        val officialState = if (officialVerified >= selected && selected > 0) "COMPLETE" else "HOLD"
        val conversionState = if (conversions >= selected && selected > 0) "COMPLETE" else "HOLD"

        val stages = JSONArray()
            .put(stage(
                "1. 진학사 로그인 확인",
                if (verified) "COMPLETE" else if (manualWaits > 0 || manualHandoffs > 0) "IN_PROGRESS" else "WAITING",
                "protected high3 확인",
                "${if (verified) 1 else 0}/1 · 사이트 로그인 대기 $manualWaits · 검증 handoff $manualHandoffs"
            ))
            .put(stage(
                "2. 진학사 수집 시작",
                if (batchStarts > 0) "COMPLETE" else if (verified) "READY" else "WAITING",
                "batch 시작 1회 이상",
                "$batchStarts 회"
            ))
            .put(stage(
                "3. 진학사 사용자 열람 자료",
                if (evidenceObserved) "COMPLETE" else if (batchStarts > 0) "IN_PROGRESS" else "WAITING",
                "records / successfulSnapshots / 구조화 예측 중 하나 이상 실제 증가",
                "records $records · snapshots $snapshots · 지원안 예측 $predictions/$selected"
            ))
            .put(stage(
                "4. 공식 근거",
                officialState,
                "어디가/대학 공식 근거 또는 명시적 HOLD 상태 확인",
                "$officialVerified/$selected 공식 구성요소 검증"
            ))
            .put(stage(
                "5. 공식 환산",
                conversionState,
                "검증 산식 또는 정량대상 아님 명시; 나머지는 HOLD 유지",
                "$conversions/$selected 검증 환산"
            ))
            .put(stage(
                "6. 근거 안전 판단",
                if (terminalReviews >= selected && selected > 0) "COMPLETE" else "HOLD",
                "비교 가능 또는 disclaimer/missing/risks/reasons가 보존된 HOLD",
                "$terminalReviews/$selected 안전한 종결 상태"
            ))

        val runtimeComplete = selected > 0 && verified && batchStarts > 0 && evidenceObserved
        val terminal = runtimeComplete && terminalReviews >= selected
        val holdStages = listOf(officialState, conversionState).count { it == "HOLD" }
        val completionState = when {
            !terminal -> "INCOMPLETE"
            holdStages > 0 -> "TERMINAL_WITH_HOLDS"
            else -> "COMPLETE"
        }

        return JSONObject()
            .put("stages", stages)
            .put("complete", terminal)
            .put("completionState", completionState)
            .put("holdStages", holdStages)
            .put("completionRule", "protected high3 확인 → batch 시작 → 진학사 근거 관측 → 6장 모두 비교 가능 또는 근거가 명시된 HOLD")
    }

    private fun providerRecords(status: JSONObject, provider: String): Int {
        val direct = status.optJSONObject(provider)?.optJSONObject("stats")?.optInt("records", -1) ?: -1
        if (direct >= 0) return direct
        val nested = status.optJSONObject("session")?.optJSONObject(provider)?.optJSONObject("stats")?.optInt("records", -1) ?: -1
        return if (nested >= 0) nested else 0
    }

    private fun stage(label: String, state: String, criterion: String, evidence: String) = JSONObject()
        .put("label", label)
        .put("state", state)
        .put("criterion", criterion)
        .put("evidence", evidence)
}
