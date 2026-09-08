package com.admissionhub.collector.hub

import android.app.Activity
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.admissionhub.collector.local.LocalCollectorStore
import com.admissionhub.collector.score.AdigaAutoScoreMaterializer
import org.json.JSONArray
import org.json.JSONObject

/** Evidence-first dashboard for the six pinned applications. */
class AdmissionDashboardActivity : Activity() {
    private lateinit var store: LocalCollectorStore
    private lateinit var root: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = LocalCollectorStore(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(16), dp(18), dp(28))
        }
        setContentView(ScrollView(this).apply { addView(root) })
        render()
    }

    private fun render() {
        root.removeAllViews()
        title("Admission Hub · 근거 안전 대시보드", 24)
        text("공식(어디가·대학)과 사용자 열람 기반 추정(진학사)을 분리합니다. HOLD 또는 probabilityInferred=false인 항목에 새 합격확률·안정/적정/소신 결론을 만들지 않습니다.", 14)

        val sessionId = store.latestUnifiedSession().orEmpty()
        val reusable = store.latestReusableCanonicalSessionId().orEmpty()
        val effectiveSession = when {
            sessionId.isNotBlank() && store.canonicalApplicationCount(sessionId) > 0 -> sessionId
            reusable.isNotBlank() -> reusable
            else -> sessionId
        }

        root.addView(Button(this).apply {
            text = "공식 환산·입결 다시 계산"
            isAllCaps = false
            setOnClickListener {
                if (sessionId.isNotBlank()) AdigaAutoScoreMaterializer.materializeSelected(store, sessionId)
                render()
            }
        }, lp(true))

        val status = if (sessionId.isNotBlank()) store.unifiedStatus(sessionId) else JSONObject()
        val score = if (effectiveSession.isNotBlank()) store.scoreDecisionSummary(effectiveSession) else JSONObject()
        val hub = if (effectiveSession.isNotBlank()) HubDashboardModel.build(
            store.canonicalHubSummary(effectiveSession), status, JSONObject(), score
        ) else JSONObject()
        val pipeline = PipelineCompletionModel.build(status, hub)

        section("① 세션 상태")
        val sync = hub.optJSONObject("sync") ?: JSONObject()
        text("현재 세션: ${sessionId.ifBlank { "없음" }}", 13)
        text("표시 기준 세션: ${effectiveSession.ifBlank { "없음" }}", 13)
        text("${sync.optString("stateLabel", "대기")} · ${sync.optString("progressText", "진행 수치 대기")}", 14, true)
        val completionReason = sync.optString("completionReason")
        if (completionReason.isNotBlank()) text("상태 사유: $completionReason", 12)

        section("② 파이프라인 완성도")
        val stages = pipeline.optJSONArray("stages") ?: JSONArray()
        for (i in 0 until stages.length()) stageRow(stages.optJSONObject(i) ?: continue)
        text("완료지점: ${if (pipeline.optBoolean("complete", false)) "도달" else "미도달"}", 15, true)
        text(pipeline.optString("completionRule", "완료 규칙 확인 필요"), 12)

        section("학생부")
        val profile = hub.optJSONObject("studentScoreProfile") ?: JSONObject()
        text(
            if (profile.optString("status") == "IMPORTED")
                "학생부 입력 완료 · ${profile.optInt("academicYear", 0)}학년도"
            else "학생부 입력 확인 필요",
            14,
            true
        )

        section("③ HOLD/경고 원인 · 지원 6장")
        val cards = hub.optJSONArray("cards") ?: JSONArray()
        for (i in 0 until cards.length()) card(cards.optJSONObject(i) ?: continue)

        val portfolio = hub.optJSONObject("applicationPortfolio") ?: JSONObject()
        val portfolioWarnings = portfolio.optJSONArray("warnings") ?: JSONArray()
        if (portfolioWarnings.length() > 0) {
            section("포트폴리오 경고")
            for (i in 0 until portfolioWarnings.length()) text("• ${jsonText(portfolioWarnings.opt(i))}", 12)
        }

        section("④ 다음 액션")
        val actions = collectActions(cards, portfolioWarnings, stages)
        if (actions.isEmpty()) text("추가 액션 없음 · 새 실기기 세션에서 완료 조건만 재확인하세요.", 13)
        else actions.forEach { text("• $it", 13) }

        section("수치 요약")
        val summary = hub.optJSONObject("summary") ?: JSONObject()
        text(
            "공식 구성요소 ${summary.optInt("officialCurrentComponentsVerified", 0)}/6 · 검증 환산 ${summary.optInt("verifiedConversions", 0)}/6 · 공식 입결 ${summary.optInt("officialOutcomeAvailable", 0)}/6 · 진학사 예측 ${summary.optInt("predictionCollected", 0)}/6",
            14,
            true
        )
        text("publishState: ${summary.optString("publishState", "unknown")}", 13)
    }

    private fun stageRow(stage: JSONObject) {
        val box = panel()
        val state = stage.optString("state", "WAITING")
        add(box, "${stage.optString("label")} · ${stateLabel(state)}", 15, true)
        add(box, "완료 조건: ${stage.optString("criterion")}", 12, false)
        add(box, "현재 근거: ${stage.optString("evidence")}", 12, false)
        root.addView(box, lp(true).apply { topMargin = dp(6) })
    }

    private fun card(card: JSONObject) {
        val box = panel()
        val slot = card.optInt("slot")
        add(box, "$slot · ${card.optString("title", "$slot. 지원안")}", 16, true)
        val subtitle = card.optString("subtitle")
        if (subtitle.isNotBlank()) add(box, subtitle, 13, false)
        add(box, card.optString("qualityLabel", "데이터 품질 확인 필요"), 12, false)

        val decision = card.optJSONObject("scoreDecision") ?: JSONObject()
        add(box, "공식 · ${decision.optString("conversionLabel", "대학 환산: 미확인")}", 14, true)
        add(box, "공식 · ${decision.optString("officialOutcomeLabel", "공식 입결: 미확인")}", 14, false)
        add(box, "진학사(사용자 열람 추정) · ${decision.optString("predictionLabel", "예측: 미확인")}", 14, false)

        val review = card.optJSONObject("applicationReview") ?: JSONObject()
        val relation = review.optString("relation", review.optString("code", "HOLD"))
        add(box, "relation: $relation", 13, true)
        val inferred = findProbabilityInferred(decision, review)
        add(box, "probabilityInferred: ${inferred?.toString() ?: "필드 미확인"}", 12, false)
        if (relation == "HOLD" || inferred == false) {
            add(box, "판단: Evidence-Safe HOLD/비확률 모드 · 새 합격확률·안정/적정/소신 결론 생성 안 함", 12, true)
        } else {
            add(box, decision.optString("decisionLabel", "종합: 근거 확인 필요"), 13, true)
        }

        val disclaimer = review.optString("disclaimer")
        if (disclaimer.isNotBlank()) add(box, "disclaimer: $disclaimer", 12, false)
        appendArray(box, "missing", review.optJSONArray("missing"))
        appendArray(box, "warnings", review.optJSONArray("warnings"))
        appendArray(box, "risks", review.optJSONArray("risks"))
        appendArray(box, "reasons", review.optJSONArray("reasons"))
        root.addView(box, lp(true).apply { topMargin = dp(8) })
    }

    private fun collectActions(cards: JSONArray, portfolioWarnings: JSONArray, stages: JSONArray): List<String> {
        val out = linkedSetOf<String>()
        for (i in 0 until stages.length()) {
            val stage = stages.optJSONObject(i) ?: continue
            when (stage.optString("state")) {
                "WAITING", "IN_PROGRESS", "READY" -> out += "${stage.optString("label")}: ${stage.optString("criterion")}"
                "HOLD" -> out += "${stage.optString("label")}: HOLD 근거를 해소하거나 공식 비공개/정성평가 등 최종 상태인지 확인"
            }
        }
        for (i in 0 until cards.length()) {
            val card = cards.optJSONObject(i) ?: continue
            if (!card.optBoolean("occupied", false)) continue
            val label = card.optString("title", "${card.optInt("slot")}번")
            val review = card.optJSONObject("applicationReview") ?: JSONObject()
            for (key in listOf("missing", "warnings", "risks")) {
                val arr = review.optJSONArray(key) ?: JSONArray()
                for (j in 0 until arr.length()) out += "$label · $key: ${jsonText(arr.opt(j))}"
            }
        }
        for (i in 0 until portfolioWarnings.length()) out += "포트폴리오 warning: ${jsonText(portfolioWarnings.opt(i))}"
        return out.toList()
    }

    private fun findProbabilityInferred(score: JSONObject, review: JSONObject): Boolean? {
        fun read(o: JSONObject, depth: Int = 0): Boolean? {
            if (o.has("probabilityInferred") && !o.isNull("probabilityInferred")) return o.optBoolean("probabilityInferred")
            if (depth >= 5) return null
            val keys = o.keys()
            while (keys.hasNext()) {
                val v = o.opt(keys.next())
                if (v is JSONObject) {
                    val found = read(v, depth + 1)
                    if (found != null) return found
                }
            }
            return null
        }
        return read(review) ?: read(score)
    }

    private fun appendArray(parent: LinearLayout, key: String, arr: JSONArray?) {
        if (arr == null || arr.length() == 0) return
        for (i in 0 until arr.length()) add(parent, "$key: ${jsonText(arr.opt(i))}", 12, false)
    }

    private fun jsonText(value: Any?): String = when (value) {
        is JSONObject -> value.toString()
        is JSONArray -> value.toString()
        null -> "null"
        else -> value.toString()
    }

    private fun stateLabel(state: String): String = when (state) {
        "COMPLETE" -> "완료"
        "READY" -> "다음 단계 준비"
        "IN_PROGRESS" -> "진행 중"
        "HOLD" -> "HOLD"
        else -> "대기"
    }

    private fun panel() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(14), dp(12), dp(14), dp(12))
        background = android.graphics.drawable.GradientDrawable().apply {
            cornerRadius = dp(14).toFloat()
            setStroke(dp(1), 0x33000000)
            setColor(0xFFF8F8F8.toInt())
        }
    }

    private fun section(label: String) {
        root.addView(TextView(this).apply {
            text = label
            textSize = 18f
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(18), 0, dp(6))
        })
    }

    private fun title(label: String, size: Int) {
        root.addView(TextView(this).apply {
            text = label
            textSize = size.toFloat()
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.START
        })
    }

    private fun text(label: String, size: Int, bold: Boolean = false) {
        root.addView(TextView(this).apply {
            text = label
            textSize = size.toFloat()
            if (bold) setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(3), 0, dp(3))
        })
    }

    private fun add(parent: LinearLayout, label: String, size: Int, bold: Boolean) {
        parent.addView(TextView(this).apply {
            text = label
            textSize = size.toFloat()
            if (bold) setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(2), 0, dp(2))
        })
    }

    private fun lp(match: Boolean = false) = LinearLayout.LayoutParams(
        if (match) LinearLayout.LayoutParams.MATCH_PARENT else LinearLayout.LayoutParams.WRAP_CONTENT,
        LinearLayout.LayoutParams.WRAP_CONTENT
    )

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
