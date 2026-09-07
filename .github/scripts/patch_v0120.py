from pathlib import Path
import re

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
MODEL = ROOT / 'app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt'
LAYOUT = ROOT / 'app/src/main/java/com/admissionhub/collector/hub/HubFirstLayoutPolicy.kt'
ENGINE = ROOT / 'app/src/main/java/com/admissionhub/collector/score/ScoreDecisionEngine.kt'
ENGINE_TEST = ROOT / 'app/src/test/java/com/admissionhub/collector/score/ScoreDecisionEngineTest.kt'
MODEL_TEST = ROOT / 'app/src/test/java/com/admissionhub/collector/hub/HubScoreDecisionPresentationTest.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)

main = MAIN.read_text()
store = STORE.read_text()
layout = LAYOUT.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.11.1"',
    'private const val BUILD_CODE = 111010',
    'private lateinit var hubDashboardGrid: LinearLayout',
    'private fun renderHubDashboard(model: JSONObject)',
    'fun scoreDecisionSummary' if False else 'private fun refreshHubDashboardFromStore(trigger: String)',
]:
    if token not in main:
        raise SystemExit('v0.11.1 MainActivity precondition failed: ' + token)
if 'versionCode = 111010' not in gradle or 'versionName = "0.11.1"' not in gradle:
    raise SystemExit('v0.11.1 Gradle precondition failed')
if 'Admission Hub v0.11.1 Hub-First Dashboard' not in manifest:
    raise SystemExit('v0.11.1 manifest precondition failed')
if 'admission_collector_local_v1.db' not in store or '\n    8\n) {' not in store:
    raise SystemExit('LocalCollectorStore v8 precondition failed')

ENGINE.parent.mkdir(parents=True, exist_ok=True)
ENGINE_TEST.parent.mkdir(parents=True, exist_ok=True)
MODEL_TEST.parent.mkdir(parents=True, exist_ok=True)

ENGINE.write_text(r'''package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

/**
 * Evidence-safe comparison engine.
 *
 * It never manufactures a university conversion formula, an official cut, or an admission
 * probability. A relation is emitted only when identity binding, formula verification,
 * score scale, comparison direction and one official reference are all explicit.
 */
object ScoreDecisionEngine {
    const val SCHEMA_VERSION = 1

    fun evaluate(
        canonicalQuality: String,
        conversion: JSONObject?,
        officialOutcomes: JSONArray,
        prediction: JSONObject?
    ): JSONObject {
        val base = JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("canonicalQuality", canonicalQuality)
            .put("predictionAvailable", prediction != null)
            .put("predictionStructured", prediction?.optBoolean("structured", false) == true)
            .put("predictionObservedAt", prediction?.optString("observedAt").orEmpty())
            .put("probabilityInferred", false)
            .put("unsupportedThresholdsUsed", false)

        if (conversion == null || !conversion.optBoolean("verified", false) || conversion.optString("status") != "verified") {
            return hold(base, "UNVERIFIED_CONVERSION", "판정 보류 · 대학별 공식 환산 산식 확인 필요")
        }
        if (!conversion.has("scoreValue") || conversion.isNull("scoreValue")) {
            return hold(base, "MISSING_CONVERSION_SCORE", "판정 보류 · 대학 환산점수 없음")
        }
        val scale = conversion.optString("scoreScale").trim()
        if (scale.isBlank()) {
            return hold(base, "MISSING_SCORE_SCALE", "판정 보류 · 점수 척도 미확인")
        }
        val direction = conversion.optString("comparisonDirection").trim()
        if (direction !in setOf("higher-is-better", "lower-is-better")) {
            return hold(base, "UNKNOWN_COMPARISON_DIRECTION", "판정 보류 · 점수 방향성 미확인")
        }
        if (canonicalQuality != "accepted" && !conversion.optBoolean("identityBindingVerified", false)) {
            return hold(base, "UNVERIFIED_APPLICATION_BINDING", "판정 보류 · 공식 전형 연결 확인 필요")
        }

        val comparable = mutableListOf<JSONObject>()
        val conversionMax = conversion.optNullableDouble("maxScore")
        for (i in 0 until officialOutcomes.length()) {
            val outcome = officialOutcomes.optJSONObject(i) ?: continue
            if (!outcome.optBoolean("verified", false)) continue
            if (!outcome.has("metricValue") || outcome.isNull("metricValue")) continue
            if (outcome.optString("scoreScale").trim() != scale) continue
            val outcomeMax = outcome.optNullableDouble("maxScore")
            if (conversionMax != null && outcomeMax != null && abs(conversionMax - outcomeMax) > 1e-9) continue
            comparable += outcome
        }
        if (comparable.isEmpty()) {
            return hold(base, "NO_COMPARABLE_OFFICIAL_OUTCOME", "판정 보류 · 같은 척도의 검증된 공식 입결 없음")
        }
        val primary = comparable.filter { it.optBoolean("primaryReference", false) }
        val reference = when {
            primary.size == 1 -> primary.first()
            primary.size > 1 -> return hold(base, "AMBIGUOUS_PRIMARY_REFERENCE", "판정 보류 · 공식 기준점이 여러 개 지정됨")
            comparable.size == 1 -> comparable.first()
            else -> return hold(base, "AMBIGUOUS_OFFICIAL_REFERENCE", "판정 보류 · 비교할 공식 입결 지표 선택 필요")
        }

        val own = conversion.optDouble("scoreValue")
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
''')

ENGINE_TEST.write_text(r'''package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ScoreDecisionEngineTest {
    @Test
    fun refusesToInventConversion() {
        val result = ScoreDecisionEngine.evaluate("accepted", null, JSONArray(), null)
        assertTrue(result.getBoolean("hold"))
        assertEquals("UNVERIFIED_CONVERSION", result.getString("decisionCode"))
    }

    @Test
    fun provisionalCanonicalBindingBlocksDecisionWithoutIndependentBindingProof() {
        val conversion = verifiedConversion(930.0, "points-1000", "higher-is-better")
        val outcomes = JSONArray().put(verifiedOutcome(920.0, "points-1000", true))
        val result = ScoreDecisionEngine.evaluate("provisional", conversion, outcomes, null)
        assertEquals("UNVERIFIED_APPLICATION_BINDING", result.getString("decisionCode"))
    }

    @Test
    fun comparesOnlyVerifiedSameScaleWithExplicitDirection() {
        val conversion = verifiedConversion(930.0, "points-1000", "higher-is-better")
        val outcomes = JSONArray().put(verifiedOutcome(920.0, "points-1000", true))
        val result = ScoreDecisionEngine.evaluate("accepted", conversion, outcomes, null)
        assertFalse(result.getBoolean("hold"))
        assertEquals("ABOVE_REFERENCE", result.getString("decisionCode"))
        assertEquals(10.0, result.getDouble("advantageMargin"), 1e-9)
    }

    @Test
    fun lowerGradeAverageUsesLowerIsBetterDirection() {
        val conversion = verifiedConversion(2.8, "grade-average", "lower-is-better")
        val outcomes = JSONArray().put(verifiedOutcome(3.1, "grade-average", true))
        val result = ScoreDecisionEngine.evaluate("accepted", conversion, outcomes, null)
        assertEquals("ABOVE_REFERENCE", result.getString("decisionCode"))
        assertEquals(0.3, result.getDouble("advantageMargin"), 1e-9)
    }

    @Test
    fun mismatchedScaleIsNeverCompared() {
        val conversion = verifiedConversion(930.0, "points-1000", "higher-is-better")
        val outcomes = JSONArray().put(verifiedOutcome(3.1, "grade-average", true))
        val result = ScoreDecisionEngine.evaluate("accepted", conversion, outcomes, null)
        assertEquals("NO_COMPARABLE_OFFICIAL_OUTCOME", result.getString("decisionCode"))
    }

    @Test
    fun multipleReferencesRequireExplicitPrimary() {
        val conversion = verifiedConversion(930.0, "points-1000", "higher-is-better")
        val outcomes = JSONArray()
            .put(verifiedOutcome(910.0, "points-1000", false))
            .put(verifiedOutcome(920.0, "points-1000", false))
        val result = ScoreDecisionEngine.evaluate("accepted", conversion, outcomes, null)
        assertEquals("AMBIGUOUS_OFFICIAL_REFERENCE", result.getString("decisionCode"))
    }

    private fun verifiedConversion(value: Double, scale: String, direction: String) = JSONObject()
        .put("verified", true)
        .put("status", "verified")
        .put("scoreValue", value)
        .put("scoreScale", scale)
        .put("comparisonDirection", direction)

    private fun verifiedOutcome(value: Double, scale: String, primary: Boolean) = JSONObject()
        .put("verified", true)
        .put("metricName", "70% cut")
        .put("metricValue", value)
        .put("scoreScale", scale)
        .put("primaryReference", primary)
}
''')

MODEL.write_text(r'''package com.admissionhub.collector.hub

import org.json.JSONArray
import org.json.JSONObject

/** Read-only presentation model over persisted canonical, sync, and score-decision evidence. */
object HubDashboardModel {
    const val SCHEMA_VERSION = 2
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
            .put("qualityState", quality).put("qualityLabel", qualityLabel(quality))
            .put("coverageCount", coverage.optInt("coveredCount", 0)).put("coverageComplete", coverage.optBoolean("complete", false))
            .put("missingLanes", coverage.optJSONArray("missing") ?: JSONArray())
            .put("updatedAt", candidate.optString("updatedAt"))
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
        "accepted" -> "공식 전형 연결 확인"
        "provisional" -> "공식 전형 연결 확인 필요"
        "provider-only" -> "진학사 중심 · 공식 결합 없음"
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
''')

MODEL_TEST.write_text(r'''package com.admissionhub.collector.hub

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
''')

# ---------- LocalCollectorStore v9 score evidence schema ----------
store = replace_once(
    store,
    'import com.admissionhub.collector.sync.LocalRebindPolicy\n',
    'import com.admissionhub.collector.sync.LocalRebindPolicy\nimport com.admissionhub.collector.score.ScoreDecisionEngine\n',
    'score engine import'
)
store = replace_once(store, '\n    8\n) {', '\n    9\n) {', 'database version')

schema_anchor = '''        db.execSQL("""\n            CREATE TABLE IF NOT EXISTS jinhak_mission_targets('''
score_schema = '''        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_student_profiles(
              profile_id TEXT PRIMARY KEY,
              academic_year INTEGER NOT NULL,
              source_type TEXT NOT NULL,
              source_json TEXT NOT NULL,
              verification_state TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_score_profile_year ON score_student_profiles(academic_year,updated_at)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_conversion_results(
              application_identity_key TEXT PRIMARY KEY,
              academic_year INTEGER NOT NULL,
              score_value REAL,
              max_score REAL,
              score_scale TEXT,
              comparison_direction TEXT,
              formula_source TEXT,
              formula_version TEXT,
              identity_binding_verified INTEGER NOT NULL DEFAULT 0,
              verified INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL,
              detail_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_official_outcomes(
              outcome_id TEXT PRIMARY KEY,
              application_identity_key TEXT NOT NULL,
              academic_year INTEGER NOT NULL,
              metric_name TEXT NOT NULL,
              metric_value REAL,
              score_scale TEXT,
              max_score REAL,
              source_name TEXT NOT NULL,
              source_url TEXT,
              verified INTEGER NOT NULL DEFAULT 0,
              primary_reference INTEGER NOT NULL DEFAULT 0,
              detail_json TEXT NOT NULL,
              observed_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_score_outcome_identity ON score_official_outcomes(application_identity_key,academic_year,metric_name)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_prediction_snapshots(
              snapshot_id TEXT PRIMARY KEY,
              application_identity_key TEXT NOT NULL,
              observed_at TEXT NOT NULL,
              provider TEXT NOT NULL,
              structured INTEGER NOT NULL DEFAULT 0,
              metrics_json TEXT NOT NULL,
              source_label TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_score_prediction_identity ON score_prediction_snapshots(application_identity_key,observed_at)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS score_decision_assessments(
              application_identity_key TEXT PRIMARY KEY,
              decision_code TEXT NOT NULL,
              decision_label TEXT NOT NULL,
              confidence TEXT NOT NULL,
              result_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())

'''
if schema_anchor not in store:
    raise SystemExit('score schema anchor not found')
store = store.replace(schema_anchor, score_schema + schema_anchor, 1)
store = replace_once(
    store,
    '''        if (oldVersion < 8) {
            ensureFoundationSchema(db)
        }
''',
    '''        if (oldVersion < 8) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 9) {
            ensureFoundationSchema(db)
        }
''',
    'v9 migration'
)

methods_anchor = '    fun providerRunIdForUnifiedSession(sessionId: String, provider: String): String? = unifiedProviderRunId(sessionId, provider)\n'
score_methods = r'''    fun upsertStudentScoreProfile(
        profileId: String,
        academicYear: Int,
        sourceType: String,
        source: JSONObject,
        verificationState: String
    ) {
        if (profileId.isBlank()) return
        val cv = ContentValues().apply {
            put("profile_id", profileId.take(160))
            put("academic_year", academicYear)
            put("source_type", sourceType.take(80))
            put("source_json", source.toString())
            put("verification_state", verificationState.take(80))
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("score_student_profiles", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun upsertUniversityConversionResult(
        applicationIdentityKey: String,
        academicYear: Int,
        scoreValue: Double?,
        maxScore: Double?,
        scoreScale: String?,
        comparisonDirection: String?,
        formulaSource: String?,
        formulaVersion: String?,
        identityBindingVerified: Boolean,
        verified: Boolean,
        status: String,
        detail: JSONObject = JSONObject()
    ) {
        if (applicationIdentityKey.isBlank()) return
        val cv = ContentValues().apply {
            put("application_identity_key", applicationIdentityKey)
            put("academic_year", academicYear)
            if (scoreValue == null) putNull("score_value") else put("score_value", scoreValue)
            if (maxScore == null) putNull("max_score") else put("max_score", maxScore)
            if (scoreScale.isNullOrBlank()) putNull("score_scale") else put("score_scale", scoreScale.take(120))
            if (comparisonDirection.isNullOrBlank()) putNull("comparison_direction") else put("comparison_direction", comparisonDirection.take(40))
            if (formulaSource.isNullOrBlank()) putNull("formula_source") else put("formula_source", formulaSource.take(500))
            if (formulaVersion.isNullOrBlank()) putNull("formula_version") else put("formula_version", formulaVersion.take(120))
            put("identity_binding_verified", if (identityBindingVerified) 1 else 0)
            put("verified", if (verified) 1 else 0)
            put("status", status.take(80))
            put("detail_json", detail.toString())
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("score_conversion_results", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun storeOfficialAdmissionOutcome(
        applicationIdentityKey: String,
        academicYear: Int,
        metricName: String,
        metricValue: Double?,
        scoreScale: String?,
        maxScore: Double?,
        sourceName: String,
        sourceUrl: String?,
        verified: Boolean,
        primaryReference: Boolean,
        detail: JSONObject = JSONObject()
    ): String? {
        if (applicationIdentityKey.isBlank() || metricName.isBlank() || sourceName.isBlank()) return null
        val observedAt = Instant.now().toString()
        val outcomeId = RecordUtils.sha256(listOf(applicationIdentityKey, academicYear, metricName, metricValue, scoreScale, sourceName, sourceUrl).joinToString("|"))
        val cv = ContentValues().apply {
            put("outcome_id", outcomeId)
            put("application_identity_key", applicationIdentityKey)
            put("academic_year", academicYear)
            put("metric_name", metricName.take(160))
            if (metricValue == null) putNull("metric_value") else put("metric_value", metricValue)
            if (scoreScale.isNullOrBlank()) putNull("score_scale") else put("score_scale", scoreScale.take(120))
            if (maxScore == null) putNull("max_score") else put("max_score", maxScore)
            put("source_name", sourceName.take(240))
            if (sourceUrl.isNullOrBlank()) putNull("source_url") else put("source_url", sourceUrl.take(1000))
            put("verified", if (verified) 1 else 0)
            put("primary_reference", if (primaryReference) 1 else 0)
            put("detail_json", detail.toString())
            put("observed_at", observedAt)
        }
        writableDatabase.insertWithOnConflict("score_official_outcomes", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        return outcomeId
    }

    fun storePredictionSnapshot(
        applicationIdentityKey: String,
        observedAt: String,
        provider: String,
        structured: Boolean,
        metrics: JSONObject,
        sourceLabel: String
    ): String? {
        if (applicationIdentityKey.isBlank() || provider.isBlank() || observedAt.isBlank()) return null
        val snapshotId = RecordUtils.sha256("$applicationIdentityKey|$provider|$observedAt|${RecordUtils.sha256(metrics.toString())}")
        val cv = ContentValues().apply {
            put("snapshot_id", snapshotId)
            put("application_identity_key", applicationIdentityKey)
            put("observed_at", observedAt)
            put("provider", provider.take(80))
            put("structured", if (structured) 1 else 0)
            put("metrics_json", metrics.toString())
            put("source_label", sourceLabel.take(240))
        }
        writableDatabase.insertWithOnConflict("score_prediction_snapshots", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        return snapshotId
    }

    fun scoreDecisionSummary(sessionId: String): JSONObject {
        val db = readableDatabase
        val byIdentity = JSONObject()
        var verifiedConversions = 0
        var officialOutcomeAvailable = 0
        var comparableDecisions = 0
        var decisionHolds = 0
        var predictionCollected = 0
        var structuredPredictions = 0

        val studentProfile = db.rawQuery(
            "SELECT profile_id,academic_year,source_type,verification_state,updated_at FROM score_student_profiles ORDER BY updated_at DESC LIMIT 1",
            emptyArray()
        ).use { c ->
            if (!c.moveToFirst()) JSONObject().put("status", "NOT_IMPORTED")
            else JSONObject()
                .put("status", "IMPORTED")
                .put("profileId", c.getString(0))
                .put("academicYear", c.getInt(1))
                .put("sourceType", c.getString(2))
                .put("verificationState", c.getString(3))
                .put("updatedAt", c.getString(4))
        }

        db.rawQuery(
            "SELECT application_identity_key,quality_state,academic_year FROM canonical_applications WHERE session_id=? ORDER BY application_identity_key",
            arrayOf(sessionId)
        ).use { apps ->
            while (apps.moveToNext()) {
                val identity = apps.getString(0)
                val canonicalQuality = apps.getString(1)
                val academicYear = apps.getInt(2)
                val conversion = db.rawQuery(
                    "SELECT academic_year,score_value,max_score,score_scale,comparison_direction,formula_source,formula_version,identity_binding_verified,verified,status,detail_json,updated_at FROM score_conversion_results WHERE application_identity_key=? LIMIT 1",
                    arrayOf(identity)
                ).use { c ->
                    if (!c.moveToFirst()) null else JSONObject()
                        .put("academicYear", c.getInt(0))
                        .put("scoreValue", if (c.isNull(1)) JSONObject.NULL else c.getDouble(1))
                        .put("maxScore", if (c.isNull(2)) JSONObject.NULL else c.getDouble(2))
                        .put("scoreScale", if (c.isNull(3)) JSONObject.NULL else c.getString(3))
                        .put("comparisonDirection", if (c.isNull(4)) JSONObject.NULL else c.getString(4))
                        .put("formulaSource", if (c.isNull(5)) JSONObject.NULL else c.getString(5))
                        .put("formulaVersion", if (c.isNull(6)) JSONObject.NULL else c.getString(6))
                        .put("identityBindingVerified", c.getInt(7) != 0)
                        .put("verified", c.getInt(8) != 0)
                        .put("status", c.getString(9))
                        .put("detail", runCatching { JSONObject(c.getString(10)) }.getOrDefault(JSONObject()))
                        .put("updatedAt", c.getString(11))
                }
                if (conversion?.optBoolean("verified", false) == true && conversion.optString("status") == "verified") verifiedConversions += 1

                val outcomes = JSONArray()
                db.rawQuery(
                    "SELECT outcome_id,academic_year,metric_name,metric_value,score_scale,max_score,source_name,source_url,verified,primary_reference,detail_json,observed_at FROM score_official_outcomes WHERE application_identity_key=? ORDER BY academic_year DESC,observed_at DESC",
                    arrayOf(identity)
                ).use { c ->
                    while (c.moveToNext()) {
                        outcomes.put(JSONObject()
                            .put("outcomeId", c.getString(0))
                            .put("academicYear", c.getInt(1))
                            .put("metricName", c.getString(2))
                            .put("metricValue", if (c.isNull(3)) JSONObject.NULL else c.getDouble(3))
                            .put("scoreScale", if (c.isNull(4)) JSONObject.NULL else c.getString(4))
                            .put("maxScore", if (c.isNull(5)) JSONObject.NULL else c.getDouble(5))
                            .put("sourceName", c.getString(6))
                            .put("sourceUrl", if (c.isNull(7)) JSONObject.NULL else c.getString(7))
                            .put("verified", c.getInt(8) != 0)
                            .put("primaryReference", c.getInt(9) != 0)
                            .put("detail", runCatching { JSONObject(c.getString(10)) }.getOrDefault(JSONObject()))
                            .put("observedAt", c.getString(11)))
                    }
                }
                if (outcomes.length() > 0) officialOutcomeAvailable += 1

                var prediction: JSONObject? = db.rawQuery(
                    "SELECT observed_at,provider,structured,metrics_json,source_label FROM score_prediction_snapshots WHERE application_identity_key=? ORDER BY observed_at DESC LIMIT 1",
                    arrayOf(identity)
                ).use { c ->
                    if (!c.moveToFirst()) null else JSONObject()
                        .put("observedAt", c.getString(0))
                        .put("provider", c.getString(1))
                        .put("structured", c.getInt(2) != 0)
                        .put("metrics", runCatching { JSONObject(c.getString(3)) }.getOrDefault(JSONObject()))
                        .put("sourceLabel", c.getString(4))
                }
                if (prediction == null) {
                    val collected = db.rawQuery(
                        "SELECT confirmed_at FROM jinhak_mission_coverage WHERE session_id=? AND identity_key=? AND lane='current-prediction' LIMIT 1",
                        arrayOf(sessionId, identity)
                    ).use { c -> if (c.moveToFirst()) c.getString(0) else null }
                    if (!collected.isNullOrBlank()) {
                        prediction = JSONObject()
                            .put("observedAt", collected)
                            .put("provider", "jinhak")
                            .put("structured", false)
                            .put("sourceLabel", "current-prediction mission coverage")
                            .put("status", "COLLECTED_UNSTRUCTURED")
                    }
                }
                if (prediction != null) {
                    predictionCollected += 1
                    if (prediction.optBoolean("structured", false)) structuredPredictions += 1
                }

                val evaluation = ScoreDecisionEngine.evaluate(canonicalQuality, conversion, outcomes, prediction)
                if (evaluation.optBoolean("hold", true)) decisionHolds += 1 else comparableDecisions += 1
                val reference = evaluation.optJSONObject("referenceOutcome")
                val conversionLabel = if (conversion?.optBoolean("verified", false) == true && conversion.has("scoreValue") && !conversion.isNull("scoreValue")) {
                    val value = java.math.BigDecimal.valueOf(conversion.optDouble("scoreValue")).stripTrailingZeros().toPlainString()
                    val max = if (conversion.has("maxScore") && !conversion.isNull("maxScore")) "/${java.math.BigDecimal.valueOf(conversion.optDouble("maxScore")).stripTrailingZeros().toPlainString()}" else ""
                    "대학 환산: $value$max · 검증"
                } else "대학 환산: 미확인"
                val outcomeLabel = when {
                    reference != null -> {
                        val value = java.math.BigDecimal.valueOf(reference.optDouble("metricValue")).stripTrailingZeros().toPlainString()
                        "공식 입결: ${reference.optInt("academicYear", academicYear)} ${reference.optString("metricName", "참고선")} $value"
                    }
                    outcomes.length() > 0 -> "공식 입결: ${outcomes.length()}건 · 비교 기준 미확정"
                    else -> "공식 입결: 미확인"
                }
                val predictionLabel = when {
                    prediction == null -> "진학사 예측: 미확인"
                    prediction.optBoolean("structured", false) -> prediction.optString("displayLabel").takeIf { it.isNotBlank() }
                        ?: "진학사 예측: 구조화 자료 있음"
                    else -> "진학사 예측: 수집됨 · 값 구조화 대기"
                }
                val decisionLabel = "종합: ${evaluation.optString("decisionLabel", "판정 보류")}".replace("종합: 판정 보류 ·", "종합: 판정 보류 ·")
                val row = JSONObject()
                    .put("academicYear", academicYear)
                    .put("canonicalQuality", canonicalQuality)
                    .put("conversion", conversion ?: JSONObject.NULL)
                    .put("officialOutcomes", outcomes)
                    .put("prediction", prediction ?: JSONObject.NULL)
                    .put("evaluation", evaluation)
                    .put("conversionLabel", conversionLabel)
                    .put("officialOutcomeLabel", outcomeLabel)
                    .put("predictionLabel", predictionLabel)
                    .put("decisionLabel", decisionLabel)
                byIdentity.put(identity, row)

                val cv = ContentValues().apply {
                    put("application_identity_key", identity)
                    put("decision_code", evaluation.optString("decisionCode", "UNKNOWN"))
                    put("decision_label", evaluation.optString("decisionLabel", "판정 보류"))
                    put("confidence", evaluation.optString("confidence", "INSUFFICIENT_EVIDENCE"))
                    put("result_json", evaluation.toString())
                    put("updated_at", Instant.now().toString())
                }
                writableDatabase.insertWithOnConflict("score_decision_assessments", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            }
        }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("studentProfile", studentProfile)
            .put("byIdentity", byIdentity)
            .put("summary", JSONObject()
                .put("verifiedConversions", verifiedConversions)
                .put("officialOutcomeAvailable", officialOutcomeAvailable)
                .put("comparableDecisions", comparableDecisions)
                .put("decisionHolds", decisionHolds)
                .put("predictionCollected", predictionCollected)
                .put("structuredPredictions", structuredPredictions)
                .put("probabilityInferred", false)
                .put("missingValuesDefaultToZero", false))
    }

'''
if methods_anchor not in store:
    raise SystemExit('score methods anchor not found')
store = store.replace(methods_anchor, score_methods + methods_anchor, 1)
STORE.write_text(store)

# ---------- MainActivity presentation ----------
main = replace_once(
    main,
    '''    private lateinit var hubDashboardStatus: TextView
    private lateinit var hubDashboardGrid: LinearLayout
''',
    '''    private lateinit var hubDashboardStatus: TextView
    private lateinit var hubDecisionSummary: TextView
    private lateinit var hubDashboardGrid: LinearLayout
''',
    'decision summary field'
)
main = replace_once(main, 'private const val VERSION = "0.11.1"', 'private const val VERSION = "0.12.0"', 'version')
main = replace_once(main, 'private const val BUILD_CODE = 111010', 'private const val BUILD_CODE = 112000', 'build code')

gradle = replace_once(gradle, 'versionCode = 111010', 'versionCode = 112000', 'gradle code')
gradle = replace_once(gradle, 'versionName = "0.11.1"', 'versionName = "0.12.0"', 'gradle name')
manifest = replace_once(manifest, 'android:label="Admission Hub v0.11.1 Hub-First Dashboard"', 'android:label="Admission Hub v0.12 Score Decision"', 'manifest')

banner_block = '''        hubDashboardStatus = TextView(this).apply {
            text = "대시보드 상태를 불러오는 중…"
            textSize = 17f
            gravity = Gravity.CENTER_VERTICAL
            setTextColor(android.graphics.Color.WHITE)
            setBackgroundColor(android.graphics.Color.rgb(37, 52, 78))
            setPadding(dp(16), dp(12), dp(16), dp(12))
            setOnClickListener { refreshHubDashboardFromStore("manual-banner-refresh") }
        }
'''
decision_block = banner_block + '''        hubDecisionSummary = TextView(this).apply {
            text = "성적·판정 데이터 준비 중…"
            textSize = 15f
            setTextColor(android.graphics.Color.rgb(45, 49, 56))
            setBackgroundColor(android.graphics.Color.rgb(241, 244, 248))
            setPadding(dp(16), dp(10), dp(16), dp(10))
        }
'''
main = replace_once(main, banner_block, decision_block, 'decision summary init')
main = replace_once(
    main,
    '''        root.addView(hubDashboardGrid, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(hubAdvancedPanel, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
''',
    '''        root.addView(hubDashboardGrid, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(hubDecisionSummary, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(hubAdvancedPanel, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
''',
    'decision summary root'
)

refresh_old = '''        val sync = runCatching { localStore.unifiedStatus(syncSession ?: canonicalSession) }.getOrDefault(JSONObject())
        val model = HubDashboardModel.build(canonical, sync, runtimeHubDashboardState())
'''
refresh_new = '''        val sync = runCatching { localStore.unifiedStatus(syncSession ?: canonicalSession) }.getOrDefault(JSONObject())
        val scoreDecision = runCatching { localStore.scoreDecisionSummary(canonicalSession) }.getOrDefault(JSONObject())
        val model = HubDashboardModel.build(canonical, sync, runtimeHubDashboardState(), scoreDecision)
'''
main = replace_once(main, refresh_old, refresh_new, 'dashboard score summary source')

render_anchor = '''        hubDashboardStatus.text = "${sync.optString("stateLabel", "대기")} · ${sync.optString("progressText", "진행 수치 대기")}$ageText\n지원 6장 ${summary.optInt("resolvable", 0)}/6 · 핵심자료 ${summary.optInt("fullCoreCoverage", 0)}/6 · $qualityText"
'''
render_extra = render_anchor + '''        if (::hubDecisionSummary.isInitialized) {
            val profile = model.optJSONObject("studentScoreProfile") ?: JSONObject()
            val profileText = if (profile.optString("status") == "IMPORTED") "성적 프로필 등록" else "성적 프로필 미등록"
            hubDecisionSummary.text = "$profileText · 검증 환산 ${summary.optInt("verifiedConversions", 0)}/6 · 공식 입결 ${summary.optInt("officialOutcomeAvailable", 0)}/6 · 비교 가능 ${summary.optInt("comparableDecisions", 0)}/6 · 판정보류 ${summary.optInt("decisionHolds", 0)} · 진학사 예측자료 ${summary.optInt("predictionCollected", 0)}/6"
        }
'''
main = replace_once(main, render_anchor, render_extra, 'decision summary render')

card_old = '''                    val official = card.optString("qualityLabel", "데이터 품질 확인 필요")
                    "${index + 1}. $university\n$department\n$subtitle\n\n$capacity\n$coverage\n$official"
'''
card_new = '''                    val official = card.optString("qualityLabel", "데이터 품질 확인 필요")
                    val scoreDecision = card.optJSONObject("scoreDecision") ?: JSONObject()
                    val conversion = scoreDecision.optString("conversionLabel", "대학 환산: 미확인")
                    val officialOutcome = scoreDecision.optString("officialOutcomeLabel", "공식 입결: 미확인")
                    val prediction = scoreDecision.optString("predictionLabel", "진학사 예측: 미확인")
                    val decision = scoreDecision.optString("decisionLabel", "종합: 판정 보류")
                    "${index + 1}. $university\n$department\n$subtitle\n\n$capacity · $coverage\n$official\n$conversion\n$officialOutcome\n$prediction\n$decision"
'''
main = replace_once(main, card_old, card_new, 'score card text')

show_detail_anchor = '''            append("Adiga 명시적 표 구간 근거: ").append(card.optInt("officialTableSegmentCurrent", 0)).append("건\\n")
            val updated = card.optString("updatedAt")
'''
show_detail_new = '''            append("Adiga 명시적 표 구간 근거: ").append(card.optInt("officialTableSegmentCurrent", 0)).append("건\\n")
            val scoreDecision = card.optJSONObject("scoreDecision") ?: JSONObject()
            append("\\n[성적·판정]\\n")
            append(scoreDecision.optString("conversionLabel", "대학 환산: 미확인")).append('\\n')
            append(scoreDecision.optString("officialOutcomeLabel", "공식 입결: 미확인")).append('\\n')
            append(scoreDecision.optString("predictionLabel", "진학사 예측: 미확인")).append('\\n')
            append(scoreDecision.optString("decisionLabel", "종합: 판정 보류")).append('\\n')
            val evaluation = scoreDecision.optJSONObject("evaluation")
            if (evaluation != null) append("판정 코드: ").append(evaluation.optString("decisionCode", "UNKNOWN")).append('\\n')
            val updated = card.optString("updatedAt")
'''
main = replace_once(main, show_detail_anchor, show_detail_new, 'score card detail')
MAIN.write_text(main)

layout = replace_once(layout, '3 -> 164\n        2 -> 176\n        else -> 188', '3 -> 236\n        2 -> 248\n        else -> 264', 'score card height')
LAYOUT.write_text(layout)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

checks = {
    'version': 'private const val VERSION = "0.12.0"' in main and 'private const val BUILD_CODE = 112000' in main,
    'decision-panel': 'hubDecisionSummary' in main and '검증 환산' in main,
    'score-source': 'localStore.scoreDecisionSummary' in main,
    'score-card': '대학 환산: 미확인' in main and '공식 입결: 미확인' in main and '종합: 판정 보류' in main,
    'db-v9': '\n    9\n) {' in store and 'score_conversion_results' in store and 'score_official_outcomes' in store,
    'engine': ENGINE.exists() and 'unsupportedThresholdsUsed' in ENGINE.read_text(),
    'no-probability-inference': 'probabilityInferred' in ENGINE.read_text() and 'probabilityInferred' in store,
    'responsive-preserved': 'widthDp >= 900 -> 3' in layout,
    'local-rebind-preserved': 'runLocalRebindOnly' in main,
    'selected-six-preserved': 'startSelectedSixRecovery' in main,
}
failed = [k for k, v in checks.items() if not v]
if failed:
    raise SystemExit('v0.12 postcondition failure: ' + ', '.join(failed))
print('v0.12 Score & Decision foundation patch applied')
