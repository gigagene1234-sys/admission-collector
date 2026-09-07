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
            val adigaBinding = if (i == 1) {
                JSONObject()
                    .put("officialStructuralCurrent", 1)
                    .put("officialUniversityCurrent", 1)
                    .put("officialRowBoundCurrent", 1)
                    .put("acceptedSignatures", 1)
                    .put("provisionalSignatures", 0)
                    .put("officialAdmissionEvidence", JSONArray().put(JSONObject()
                        .put("recordType", "current-admission-criteria-table")
                        .put("recordYear", 2027)
                        .put("scope", "row-bound-current")
                        .put("departmentMatch", "exact")
                        .put("admissionMatch", "exact")
                        .put("rowEvidence", "대학$i | 전형$i | 학과$i")
                        .put("sourcePage", "https://www.adiga.kr/example")))
                    .put("matches", JSONArray())
            } else {
                JSONObject()
                    .put("officialStructuralCurrent", 0)
                    .put("officialUniversityCurrent", 1)
                    .put("acceptedSignatures", 0)
                    .put("provisionalSignatures", 1)
                    .put("officialAdmissionEvidence", JSONArray().put(JSONObject()
                        .put("recordType", "current-admission-criteria-table")
                        .put("recordYear", 2027)
                        .put("scope", "university-current")
                        .put("departmentMatch", "none")
                        .put("admissionMatch", "related")
                        .put("rowEvidence", "학생부교과 공통 기준")
                        .put("sourcePage", "https://www.adiga.kr/example")))
                    .put("matches", JSONArray().put(JSONObject()
                        .put("departmentMatch", "exact")
                        .put("admissionMatch", "missing")))
            }
            graph.put(JSONObject()
                .put("applicationIdentityKey", identity)
                .put("canonicalApplicationId", "app-$i")
                .put("academicYear", 2027)
                .put("university", "대학$i")
                .put("department", "학과$i")
                .put("admission", "전형$i")
                .put("capacity", 10 + i)
                .put("qualityState", if (i == 1) "accepted" else "provisional")
                .put("coverage", JSONObject().put("coveredCount", 5).put("complete", true).put("missing", JSONArray()))
                .put("adigaBinding", adigaBinding))
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
        val cards = model.getJSONArray("cards")
        assertEquals(6, cards.length())
        assertEquals(6, model.getJSONObject("summary").getInt("resolvable"))
        assertEquals(1, model.getJSONObject("summary").getInt("accepted"))
        assertEquals("accepted", cards.getJSONObject(0).getString("qualityState"))
        assertEquals("provisional", cards.getJSONObject(1).getString("qualityState"))
        assertEquals("어디가: 현재 전형·모집단위 연결 확인 · 과거 입결 직접행 미확인", cards.getJSONObject(0).getString("qualityLabel"))
        assertEquals("어디가: 모집단위 후보 확인 · 전형 결합 근거 없음", cards.getJSONObject(1).getString("qualityLabel"))
        assertEquals("BOUND_CURRENT_ONLY", cards.getJSONObject(0).getJSONObject("officialEvidence").getString("code"))
        assertEquals("DEPARTMENT_FOUND_ADMISSION_MISSING", cards.getJSONObject(1).getJSONObject("officialEvidence").getString("code"))
        assertTrue(cards.getJSONObject(5).getBoolean("coverageComplete"))
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
