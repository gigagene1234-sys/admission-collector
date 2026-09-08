package com.admissionhub.collector.hub

import android.app.Activity
import android.os.Bundle
import android.text.method.LinkMovementMethod
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.admissionhub.collector.local.LocalCollectorStore
import com.admissionhub.collector.score.AdigaAutoScoreMaterializer
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/** Read-only, evidence-first dashboard. It never changes the six pinned application slots. */
class HubDashboardActivity : Activity() {
    private lateinit var store: LocalCollectorStore
    private lateinit var root: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = LocalCollectorStore(this)
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(14), dp(16), dp(30)) }
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
        render()
    }

    private fun render() {
        root.removeAllViews()
        title("Admission Hub · 지원 6장 대시보드")
        val latest = store.latestUnifiedSession()
        val canonicalSession = store.latestReusableCanonicalSessionId() ?: latest
        if (canonicalSession.isNullOrBlank()) {
            info("아직 표시할 지원 6장 canonical 세션이 없습니다.")
            button("닫기") { finish() }
            return
        }
        val officialSession = latest?.takeIf { !store.providerRunIdForUnifiedSession(it, "adiga").isNullOrBlank() } ?: canonicalSession
        val profile = store.currentStudentScoreProfile()
        val materialization = runCatching { AdigaAutoScoreMaterializer.materializeSelected(store, officialSession, profile) }
            .getOrElse { JSONObject().put("error", it.javaClass.simpleName) }
        runCatching { store.materializeSelectedPredictions(canonicalSession) }
        val score = store.scoreDecisionSummary(canonicalSession)
        val canonical = store.canonicalHubSummary(canonicalSession)
        val sync = latest?.let { runCatching { store.unifiedStatus(it) }.getOrDefault(JSONObject()) } ?: JSONObject()
        val model = HubDashboardModel.build(canonical, sync, JSONObject(), score)

        val summary = model.optJSONObject("summary") ?: JSONObject()
        val student = model.optJSONObject("studentScoreProfile") ?: JSONObject()
        val auth = sync.optJSONObject("jinhakAuthDiagnosticsSummary") ?: JSONObject()
        val own = if (student.has("ownWeightedGrade") && !student.isNull("ownWeightedGrade")) String.format(Locale.US, "%.3f", student.optDouble("ownWeightedGrade")) else "-"
        section("현재 상태")
        info("학생부: ${student.optString("status", "NOT_IMPORTED")} · ${student.optInt("rowCount", 0)}과목 · 입력 석차등급 가중평균 $own")
        info("공식 환산 ${summary.optInt("verifiedConversions", 0)}/6 · 공식 입결 ${summary.optInt("officialOutcomeAvailable", 0)}/6 · 진학사 구조화 자료 ${summary.optInt("structuredPredictions", 0)}/6")
        info("공식 재결합: 환산 ${materialization.optInt("conversionsVerified", 0)}건 · 엄격 동일행 입결 ${materialization.optInt("directHistoricalRowsFound", 0)}행 · 별칭결합 ${materialization.optJSONObject("historicalAliasFallback")?.optInt("stored", 0) ?: 0}개 지표 · 대학 입학처 fallback ${materialization.optJSONObject("universityOfficialFallback")?.optInt("stored", 0) ?: 0}개 지표")
        info("진학사 인증: ${if (auth.optBoolean("authVerifiedForBatch", false)) "확인됨" else "미확인"} · ${auth.optString("lastAuthEvidence", "근거 없음")} · 재인증 ${auth.optInt("reauthCycles", 0)}회")
        info("출처 정책: 어디가/대학 입학처 = 공식 기준·공식 과거 입결. 진학사 = 사용자 계정에서 열람한 파생 분석·예측. 서로 같은 의미로 취급하지 않습니다.")

        section("지원 6장")
        val cards = model.optJSONArray("cards") ?: JSONArray()
        for (i in 0 until cards.length()) cards.optJSONObject(i)?.let(::card)

        section("수집/품질")
        val quality = canonical.optJSONObject("qualityAudit") ?: JSONObject()
        val blockers = quality.optJSONArray("blockers") ?: JSONArray()
        info("publishState: ${quality.optString("publishState", "확인 필요")} · blocker: ${join(blockers).ifBlank { "없음" }}")
        val warnings = quality.optJSONArray("warnings") ?: JSONArray()
        info("warnings: ${join(warnings).ifBlank { "없음" }}")
        info("HOLD는 데이터 부족/조건 미확정 상태이며 합격확률을 의미하지 않습니다. probabilityInferred=false 정책을 유지합니다.")
        button("새로고침") { render() }
        button("닫기") { finish() }
    }

    private fun card(card: JSONObject) {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(10), dp(12), dp(12)) }
        val slot = card.optInt("slot")
        val heading = if (card.optBoolean("occupied", false)) "$slot. ${card.optString("title")}" else "$slot. 비어 있음"
        box.addView(TextView(this).apply { text = heading; textSize = 18f })
        if (!card.optBoolean("resolvable", false)) {
            box.addView(text("canonical 연결 대기 · ${card.optString("qualityLabel")}"))
            root.addView(box); return
        }
        val decision = card.optJSONObject("scoreDecision") ?: JSONObject()
        val review = card.optJSONObject("applicationReview") ?: JSONObject()
        box.addView(text(card.optString("subtitle")))
        box.addView(text(decision.optString("conversionLabel", "대학 환산: 미확인")))
        box.addView(text(decision.optString("officialOutcomeLabel", "공식 입결: 미확인")))
        box.addView(text(decision.optString("predictionLabel", "진학사 예측: 미확인")))
        box.addView(text("원서 검토: ${review.optString("label", "자료 보완 후 판단")} · relation ${review.optString("relation", review.optString("code", "HOLD"))}"))
        val missing = review.optJSONArray("missing") ?: JSONArray()
        if (missing.length() > 0) box.addView(text("missing: ${join(missing)}"))
        val risks = review.optJSONArray("risks") ?: JSONArray()
        if (risks.length() > 0) box.addView(text("risks: ${join(risks)}"))
        val conversion = decision.optJSONObject("conversion") ?: JSONObject()
        val formulaSource = conversion.optString("formulaSource")
        if (formulaSource.isNotBlank()) box.addView(text("환산 공식 출처: $formulaSource"))
        val outcomes = decision.optJSONArray("officialOutcomes") ?: JSONArray()
        val sourceNames = linkedSetOf<String>()
        for (i in 0 until outcomes.length()) outcomes.optJSONObject(i)?.optString("sourceName")?.takeIf { it.isNotBlank() }?.let(sourceNames::add)
        if (sourceNames.isNotEmpty()) box.addView(text("입결 출처: ${sourceNames.joinToString(" / ")}"))
        root.addView(box)
    }

    private fun text(value: String) = TextView(this).apply { text = value; textSize = 14f; setTextIsSelectable(true); setPadding(0, dp(3), 0, dp(3)); movementMethod = LinkMovementMethod.getInstance() }
    private fun title(value: String) = TextView(this).apply { text = value; textSize = 22f; setPadding(0, 0, 0, dp(8)); root.addView(this) }
    private fun section(value: String) = TextView(this).apply { text = value; textSize = 19f; setPadding(0, dp(14), 0, dp(6)); root.addView(this) }
    private fun info(value: String) = TextView(this).apply { text = value; textSize = 14f; setTextIsSelectable(true); setPadding(0, dp(3), 0, dp(4)); root.addView(this) }
    private fun button(label: String, action: () -> Unit) = Button(this).apply { text = label; gravity = Gravity.CENTER; setOnClickListener { action() }; root.addView(this) }
    private fun join(a: JSONArray): String = (0 until a.length()).map { a.optString(it) }.filter { it.isNotBlank() }.joinToString(", ")
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    override fun onDestroy() { runCatching { store.close() }; super.onDestroy() }
}
