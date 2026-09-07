package com.admissionhub.collector.hub

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class HubScoreDecisionPresentationTest {
    @Test
    fun attachesEvidenceSafeScoreDecisionWithoutInventingMissingValues() {
        val identity = "2027|u|d|a"
        val canonical = JSONObject()
            .put("candidateGraph", JSONArray().put(JSONObject()
                .put("applicationIdentityKey", identity)
                .put("canonicalApplicationId", "app-1")
                .put("university", "테스트대")
                .put("department", "기계공")
                .put("admission", "교과")
                .put("qualityState", "provisional")
                .put("coverage", JSONObject().put("coveredCount", 5).put("complete", true).put("missing", JSONArray()))))
            .put("slots", JSONArray().put(JSONObject().put("occupied", true).put("applicationIdentityKey", identity)))
            .put("qualityAudit", JSONObject().put("sixSlots", JSONObject().put("selected", 1).put("resolvable", 1)))
        val score = JSONObject()
            .put("byIdentity", JSONObject().put(identity, JSONObject()
                .put("conversionLabel", "대학 환산: 미확인")
                .put("officialOutcomeLabel", "공식 입결: 미확인")
                .put("predictionLabel", "진학사 예측: 수집됨 · 값 구조화 대기")
                .put("decisionLabel", "종합: 판정 보류")))
            .put("summary", JSONObject().put("decisionHolds", 1).put("predictionCollected", 1))
        val model = HubDashboardModel.build(canonical, JSONObject(), JSONObject(), score)
        val card = model.getJSONArray("cards").getJSONObject(0).getJSONObject("scoreDecision")
        assertEquals("대학 환산: 미확인", card.getString("conversionLabel"))
        assertEquals("종합: 판정 보류", card.getString("decisionLabel"))
        assertEquals(1, model.getJSONObject("summary").getInt("decisionHolds"))
    }
}
