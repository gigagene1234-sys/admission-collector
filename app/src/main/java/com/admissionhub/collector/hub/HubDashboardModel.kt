package com.admissionhub.collector.hub

import org.json.JSONArray
import org.json.JSONObject
import com.admissionhub.collector.score.ApplicationReviewEngine

/** Read-only presentation model over persisted canonical, sync, and score-decision evidence. */
object HubDashboardModel {
    const val SCHEMA_VERSION = 3
    const val SLOT_COUNT = 6

    fun build(
        canonicalHub: JSONObject,
        syncStatus: JSONObject,
        runtime: JSONObject = JSONObject(),
        scoreDecisionSummary: JSONObject = JSONObject()
    ): JSONObject {
        val graph = canonicalHub.optJSONArray("candidateGraph") ?: JSONArray()
        val slots = canonicalHub.optJSONArray("slots") ?: JSONArray()
        val audit = canonicalHub.optJSONObject("qualityAudit") ?: JSONObject()
        val auditSlots = audit.optJSONObject("sixSlots") ?: JSONObject()
        val scoreByIdentity = scoreDecisionSummary.optJSONObject("byIdentity") ?: JSONObject()

        val byIdentity = linkedMapOf<String, JSONObject>()
        for (i in 0 until graph.length()) {
            val item = graph.optJSONObject(i) ?: continue
            val identity = item.optString("applicationIdentityKey")
            if (identity.isNotBlank()) byIdentity[identity] = item
        }

        val cards = JSONArray()
        for (slot in 1..SLOT_COUNT) {
            val slotRow = slots.optJSONObject(slot - 1)
            val occupied = slotRow?.optBoolean("occupied", false) == true
            val identity = slotRow?.optString("applicationIdentityKey").orEmpty()
            val candidate = if (identity.isBlank()) null else byIdentity[identity]
            val score = if (identity.isBlank()) null else scoreByIdentity.optJSONObject(identity)
            cards.put(buildCard(slot, occupied, slotRow, candidate, score))
        }

        val sync = buildSync(syncStatus, runtime)
        val selected = auditSlots.optInt("selected", cards.countOccupied())
        val resolvable = auditSlots.optInt("resolvable", cards.countResolvable())
        val accepted = auditSlots.optInt("accepted", cards.countQuality("accepted"))
        val provisional = auditSlots.optInt("provisional", cards.countQuality("provisional"))
        val providerOnly = auditSlots.optInt("providerOnly", cards.countQuality("provider-only"))
        val fullCoverage = auditSlots.optInt("fullCoreCoverage", cards.countFullCoverage())
        val scoreSummary = scoreDecisionSummary.optJSONObject("summary") ?: JSONObject()

        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("cards", cards)
            .put("applicationPortfolio", ApplicationReviewEngine.portfolio(cards))
            .put("sync", sync)
            .put("studentScoreProfile", scoreDecisionSummary.optJSONObject("studentProfile") ?: JSONObject().put("status", "NOT_IMPORTED"))
            .put("summary", JSONObject()
                .put("selected", selected)
                .put("resolvable", resolvable)
                .put("accepted", accepted)
                .put("provisional", provisional)
                .put("providerOnly", providerOnly)
                .put("fullCoreCoverage", fullCoverage)
                .put("verifiedConversions", scoreSummary.optInt("verifiedConversions", 0))
                .put("officialOutcomeAvailable", scoreSummary.optInt("officialOutcomeAvailable", 0))
                .put("comparableDecisions", scoreSummary.optInt("comparableDecisions", 0))
                .put("decisionHolds", scoreSummary.optInt("decisionHolds", cards.countResolvable()))
                .put("predictionCollected", scoreSummary.optInt("predictionCollected", 0))
                .put("structuredPredictions", scoreSummary.optInt("structuredPredictions", 0))
                .put("hubReady", audit.optBoolean("hubReady", false))
                .put("publishState", audit.optString("publishState", "WAITING_FOR_USER_SELECTION"))
                .put("candidateCount", audit.optInt("candidateCount", graph.length())))
    }

    private fun buildCard(slot: Int, occupied: Boolean, slotRow: JSONObject?, candidate: JSONObject?, score: JSONObject?): JSONObject {
        if (!occupied) {
            return JSONObject()
                .put("slot", slot).put("occupied", false).put("resolvable", false)
                .put("title", "$slot. 비어 있음").put("qualityState", "empty")
                .put("qualityLabel", "지원안 미선택").put("coverageCount", 0)
                .put("coverageComplete", false).put("scoreDecision", JSONObject().put("decisionLabel", "종합: 판정 보류"))
        }
        if (candidate == null) {
            return JSONObject()
                .put("slot", slot).put("occupied", true).put("resolvable", false)
                .put("applicationIdentityKey", slotRow?.optString("applicationIdentityKey").orEmpty())
                .put("title", "$slot. ${slotRow?.optString("displayLabel", "연결 확인 필요")}")
                .put("qualityState", "stale").put("qualityLabel", "canonical 연결 복구 필요")
                .put("coverageCount", 0).put("coverageComplete", false)
                .put("scoreDecision", JSONObject().put("decisionLabel", "종합: 판정 보류"))
        }

        val coverage = candidate.optJSONObject("coverage") ?: JSONObject()
        val binding = candidate.optJSONObject("adigaBinding") ?: JSONObject()
        val official = com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer.analyze(candidate)
        val university = candidate.nullableString("university")
        val department = candidate.nullableString("department")
        val admission = candidate.nullableString("admission")
        val campus = candidate.nullableString("campus")
        val capacity = if (candidate.has("capacity") && !candidate.isNull("capacity")) candidate.optInt("capacity", -1).takeIf { it >= 0 } else null
        val quality = candidate.optString("qualityState", candidate.optString("adigaBindingQuality", "unknown"))
        return JSONObject()
            .put("slot", slot).put("occupied", true).put("resolvable", true)
            .put("applicationIdentityKey", candidate.optString("applicationIdentityKey"))
            .put("canonicalApplicationId", candidate.optString("canonicalApplicationId"))
            .put("university", university ?: JSONObject.NULL).put("department", department ?: JSONObject.NULL)
            .put("admission", admission ?: JSONObject.NULL).put("campus", campus ?: JSONObject.NULL)
            .put("capacity", capacity ?: JSONObject.NULL)
            .put("title", listOfNotNull(university, department).joinToString(" · ").ifBlank { "$slot. 지원안" })
            .put("subtitle", listOfNotNull(admission, campus?.let { "[$it]" }).joinToString(" · "))
            .put("qualityState", quality).put("qualityLabel", official.optString("label", qualityLabel(quality)))
            .put("officialEvidence", official)
            .put("coverageCount", coverage.optInt("coveredCount", 0)).put("coverageComplete", coverage.optBoolean("complete", false))
            .put("missingLanes", coverage.optJSONArray("missing") ?: JSONArray())
            .put("updatedAt", candidate.optString("updatedAt"))
            .put("academicYear", candidate.optInt("academicYear"))
            .put("applicationReview", score?.optJSONObject("applicationReview") ?: JSONObject().put("code", "HOLD").put("label", "자료 보완 후 판단"))
            .put("officialStructuralCurrent", binding.optInt("officialStructuralCurrent", 0))
            .put("officialRowBoundCurrent", binding.optInt("officialRowBoundCurrent", 0))
            .put("officialTableSegmentCurrent", binding.optInt("officialTableSegmentCurrent", 0))
            .put("adigaMatchCount", candidate.optInt("adigaMatchCount", 0))
            .put("scoreDecision", score ?: JSONObject()
                .put("conversionLabel", "대학 환산: 미확인")
                .put("officialOutcomeLabel", "공식 입결: 미확인")
                .put("predictionLabel", "진학사 예측: 미확인")
                .put("decisionLabel", "종합: 판정 보류"))
    }

    private fun buildSync(syncStatus: JSONObject, runtime: JSONObject): JSONObject {
        val persistedStatus = syncStatus.optString("status", "unknown")
        val persistedPhase = syncStatus.optString("phase", "idle")
        val requiresUserAction = syncStatus.optBoolean("requiresUserAction", false)
        val runtimeRunning = runtime.optBoolean("running", false)
        val runtimePhase = runtime.optString("phase", persistedPhase)
        val loginRequired = runtime.optBoolean("loginRequired", false)
        val loginChecking = runtime.optBoolean("loginChecking", false)
        val recovering = runtime.optBoolean("recovering", false)
        val state = when {
            loginRequired -> "USER_LOGIN_REQUIRED"
            loginChecking -> "LOGIN_CHECK"
            recovering -> "RECOVERING"
            runtimeRunning && runtimePhase == "adiga" -> "SYNCING_ADIGA"
            runtimeRunning && runtimePhase == "jinhak" -> "SYNCING_JINHAK"
            runtimeRunning -> "SYNCING"
            requiresUserAction -> "USER_ACTION_REQUIRED"
            persistedStatus == "completed" && syncStatus.optString("completionReason").contains("error", ignoreCase = true) -> "COMPLETE_WITH_WARNINGS"
            persistedStatus == "completed" -> "COMPLETE"
            persistedStatus == "running" -> when (persistedPhase) {
                "adiga" -> "SYNCING_ADIGA"
                "jinhak" -> "SYNCING_JINHAK"
                else -> "SYNCING"
            }
            else -> "IDLE"
        }
        val mission = runtime.optJSONObject("mission")
            ?: syncStatus.optJSONObject("jinhakDiagnosticsSummary")?.optJSONObject("missionTargetLedger")
            ?: JSONObject()
        val totalTargets = mission.optInt("targets", 0)
        val confirmed = mission.optInt("confirmed", mission.optJSONObject("states")?.optInt("confirmed", 0) ?: 0)
        val outstanding = mission.optInt("outstanding", 0)
        val progressText = when {
            totalTargets > 0 -> "$confirmed/$totalTargets 완료${if (outstanding > 0) " · $outstanding 남음" else ""}"
            state == "COMPLETE" || state == "COMPLETE_WITH_WARNINGS" -> "수집 완료"
            else -> "진행 수치 대기"
        }
        return JSONObject()
            .put("state", state).put("stateLabel", syncStateLabel(state))
            .put("phase", if (runtimeRunning) runtimePhase else persistedPhase)
            .put("progressText", progressText).put("targets", totalTargets)
            .put("confirmed", confirmed).put("outstanding", outstanding)
            .put("updatedAt", syncStatus.optString("updatedAt"))
            .put("completionReason", syncStatus.optString("completionReason"))
            .put("lastProgressAgeSeconds", runtime.optLong("lastProgressAgeSeconds", -1L))
    }

    fun qualityLabel(state: String): String = when (state) {
        "accepted" -> "공식 전형·모집단위 직접 연결"
        "provisional" -> "공식자료 연결 근거를 항목별로 확인하세요"
        "provider-only" -> "진학사 중심 · 어디가 직접 결합 없음"
        "incomplete" -> "수집 보강 필요"
        "stale" -> "canonical 연결 복구 필요"
        "empty" -> "지원안 미선택"
        else -> "데이터 품질 확인 필요"
    }

    fun syncStateLabel(state: String): String = when (state) {
        "USER_LOGIN_REQUIRED" -> "로그인 필요"
        "LOGIN_CHECK" -> "로그인 확인 중"
        "RECOVERING" -> "복구 중"
        "SYNCING_ADIGA" -> "어디가 공식정보 수집 중"
        "SYNCING_JINHAK" -> "진학사 정보 수집 중"
        "SYNCING" -> "통합 수집 중"
        "USER_ACTION_REQUIRED" -> "사용자 조치 필요"
        "COMPLETE_WITH_WARNINGS" -> "완료 · 일부 오류 있음"
        "COMPLETE" -> "완료"
        else -> "대기"
    }

    private fun JSONObject.nullableString(key: String): String? =
        if (!has(key) || isNull(key)) null else optString(key).trim().takeIf { it.isNotBlank() && it != "null" }
    private fun JSONArray.countOccupied(): Int = (0 until length()).count { optJSONObject(it)?.optBoolean("occupied", false) == true }
    private fun JSONArray.countResolvable(): Int = (0 until length()).count { optJSONObject(it)?.optBoolean("resolvable", false) == true }
    private fun JSONArray.countFullCoverage(): Int = (0 until length()).count { optJSONObject(it)?.optBoolean("coverageComplete", false) == true }
    private fun JSONArray.countQuality(state: String): Int = (0 until length()).count { optJSONObject(it)?.optString("qualityState") == state }
}
