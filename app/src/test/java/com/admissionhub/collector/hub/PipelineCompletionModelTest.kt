package com.admissionhub.collector.hub

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PipelineCompletionModelTest {
    private fun hubWithHolds(): JSONObject {
        val cards = JSONArray()
        for (slot in 1..6) {
            cards.put(JSONObject()
                .put("slot", slot)
                .put("occupied", true)
                .put("applicationReview", JSONObject()
                    .put("relation", "HOLD")
                    .put("disclaimer", "근거 부족 시 판단을 보류합니다.")
                    .put("missing", JSONArray().put("additional evidence required"))
                    .put("risks", JSONArray())))
        }
        return JSONObject()
            .put("cards", cards)
            .put("summary", JSONObject()
                .put("selected", 6)
                .put("predictionCollected", 6)
                .put("officialCurrentComponentsVerified", 4)
                .put("verifiedConversions", 3))
    }

    @Test
    fun protectedCoreBatchAndPredictionReachRuntimeCompletion() {
        val status = JSONObject().put("jinhakDiagnosticsSummary", JSONObject()
            .put("jinhakV0912ProtectedCoreVerified", 1)
            .put("jinhakBatchStartCount", 1))
        val result = PipelineCompletionModel.build(status, hubWithHolds())
        assertTrue(result.getBoolean("complete"))
        assertEquals("COMPLETE", result.getJSONArray("stages").getJSONObject(0).getString("state"))
    }

    @Test
    fun unverifiedProtectedCoreKeepsLoginStageWaiting() {
        val result = PipelineCompletionModel.build(JSONObject(), hubWithHolds())
        assertFalse(result.getBoolean("complete"))
        assertEquals("WAITING", result.getJSONArray("stages").getJSONObject(0).getString("state"))
    }

    @Test
    fun explicitHoldIsTerminalWithoutProbabilityGeneration() {
        val status = JSONObject().put("jinhakDiagnosticsSummary", JSONObject()
            .put("jinhakV0912ProtectedCoreVerified", 1)
            .put("jinhakBatchStartCount", 1))
        val result = PipelineCompletionModel.build(status, hubWithHolds())
        assertEquals("COMPLETE", result.getJSONArray("stages").getJSONObject(5).getString("state"))
    }
}
