package com.admissionhub.collector.hub

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HubDashboardModelTest {
    @Test
    fun buildsSixResolvableCardsWithoutChangingQualitySemantics() {
        val graph = JSONArray()
        val slots = JSONArray()
        for (i in 1..6) {
            val identity = "id-$i"
            graph.put(JSONObject()
                .put("applicationIdentityKey", identity)
                .put("canonicalApplicationId", "app-$i")
                .put("university", "대학$i")
                .put("department", "학과$i")
                .put("admission", "전형$i")
                .put("capacity", 10 + i)
                .put("qualityState", if (i == 1) "accepted" else "provisional")
                .put("coverage", JSONObject().put("coveredCount", 5).put("complete", true).put("missing", JSONArray()))
                .put("adigaBinding", JSONObject().put("officialStructuralCurrent", if (i == 1) 1 else 0)))
            slots.put(JSONObject().put("slot", i).put("occupied", true).put("applicationIdentityKey", identity).put("displayLabel", "대학$i 학과$i"))
        }
        val canonical = JSONObject()
            .put("candidateGraph", graph)
            .put("slots", slots)
            .put("qualityAudit", JSONObject()
                .put("candidateCount", 27)
                .put("hubReady", true)
                .put("publishState", "READY_WITH_WARNINGS")
                .put("sixSlots", JSONObject()
                    .put("selected", 6).put("resolvable", 6).put("accepted", 1)
                    .put("provisional", 5).put("providerOnly", 0).put("fullCoreCoverage", 6)))
        val model = HubDashboardModel.build(canonical, JSONObject().put("status", "completed").put("phase", "completed"))
        assertEquals(6, model.getJSONArray("cards").length())
        assertEquals(6, model.getJSONObject("summary").getInt("resolvable"))
        assertEquals(1, model.getJSONObject("summary").getInt("accepted"))
        assertEquals("공식 전형 연결 확인", model.getJSONArray("cards").getJSONObject(0).getString("qualityLabel"))
        assertEquals("공식 전형 연결 확인 필요", model.getJSONArray("cards").getJSONObject(1).getString("qualityLabel"))
        assertTrue(model.getJSONArray("cards").getJSONObject(5).getBoolean("coverageComplete"))
    }

    @Test
    fun preservesStaleSlotInsteadOfInventingCandidate() {
        val canonical = JSONObject()
            .put("candidateGraph", JSONArray())
            .put("slots", JSONArray().put(JSONObject()
                .put("slot", 1).put("occupied", true).put("applicationIdentityKey", "missing").put("displayLabel", "과거 지원안")))
            .put("qualityAudit", JSONObject())
        val card = HubDashboardModel.build(canonical, JSONObject()).getJSONArray("cards").getJSONObject(0)
        assertTrue(card.getBoolean("occupied"))
        assertFalse(card.getBoolean("resolvable"))
        assertEquals("stale", card.getString("qualityState"))
    }

    @Test
    fun runtimeLoginAndRecoveryOverridePersistedCompleteState() {
        val canonical = JSONObject().put("candidateGraph", JSONArray()).put("slots", JSONArray()).put("qualityAudit", JSONObject())
        val persisted = JSONObject().put("status", "completed").put("phase", "completed")
        val login = HubDashboardModel.build(canonical, persisted, JSONObject().put("running", true).put("loginRequired", true))
        assertEquals("USER_LOGIN_REQUIRED", login.getJSONObject("sync").getString("state"))
        val recovery = HubDashboardModel.build(canonical, persisted, JSONObject().put("running", true).put("recovering", true))
        assertEquals("RECOVERING", recovery.getJSONObject("sync").getString("state"))
    }

    @Test
    fun jinhakMissionProgressIsExposed() {
        val canonical = JSONObject().put("candidateGraph", JSONArray()).put("slots", JSONArray()).put("qualityAudit", JSONObject())
        val runtime = JSONObject()
            .put("running", true)
            .put("phase", "jinhak")
            .put("mission", JSONObject().put("targets", 27).put("confirmed", 20).put("outstanding", 7))
        val sync = HubDashboardModel.build(canonical, JSONObject().put("status", "running").put("phase", "jinhak"), runtime).getJSONObject("sync")
        assertEquals("SYNCING_JINHAK", sync.getString("state"))
        assertEquals("20/27 완료 · 7 남음", sync.getString("progressText"))
    }
}
