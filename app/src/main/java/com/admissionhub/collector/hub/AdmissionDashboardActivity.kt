package com.admissionhub.collector.hub

import android.app.Activity
import android.os.Bundle
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.admissionhub.collector.local.LocalCollectorStore
import com.admissionhub.collector.score.AdigaAutoScoreMaterializer
import org.json.JSONArray
import org.json.JSONObject

/**
 * Evidence-first dashboard for the six pinned applications.
 * It reads persisted score/outcome evidence directly so a failed Jinhak run cannot hide Adiga data.
 */
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
        val scroll = ScrollView(this).apply { addView(root) }
        setContentView(scroll)
        render()
    }

    private fun render() {
        root.removeAllViews()
        title("Admission Hub · 6장 대시보드", 24)
        text("어디가 공식자료와 진학사 사용자 열람 자료를 분리해 표시합니다. HOLD/probabilityInferred=false인 항목은 합격확률로 변환하지 않습니다.", 14)

        val sessionId = store.latestUnifiedSession().orEmpty()
        val reusable = store.latestReusableCanonicalSessionId().orEmpty()
        val effectiveSession = when {
            sessionId.isNotBlank() && store.canonicalApplicationCount(sessionId) > 0 -> sessionId
            reusable.isNotBlank() -> reusable
            else -> sessionId
        }

        val refresh = Button(this).apply {
            text = "공식 환산·입결 다시 계산"
            isAllCaps = false
            setOnClickListener {
                if (sessionId.isNotBlank()) AdigaAutoScoreMaterializer.materializeSelected(store, sessionId)
                render()
            }
        }
        root.addView(refresh, lp(match = true))

        val status = if (sessionId.isNotBlank()) store.unifiedStatus(sessionId) else JSONObject()
        val score = if (effectiveSession.isNotBlank()) store.scoreDecisionSummary(effectiveSession) else JSONObject()
        val hub = if (effectiveSession.isNotBlank()) HubDashboardModel.build(
            store.canonicalHubSummary(effectiveSession), status, JSONObject(), score
        ) else JSONObject()

        section("수집 상태")
        val sync = hub.optJSONObject("sync") ?: JSONObject()
        text("현재 세션: ${sessionId.ifBlank { "없음" }}", 13)
        text("표시 기준 세션: ${effectiveSession.ifBlank { "없음" }}", 13)
        text("${sync.optString("stateLabel", "대기")} · ${sync.optString("progressText", "진행 수치 대기")}", 14, bold = true)

        section("학생부")
        val profile = hub.optJSONObject("studentScoreProfile") ?: JSONObject()
        text(if (profile.optString("status") == "IMPORTED") "학생부 입력 완료 · ${profile.optInt("academicYear", 0)}학년도" else "학생부 입력 확인 필요", 14, bold = true)

        section("지원 6장")
        val cards = hub.optJSONArray("cards") ?: JSONArray()
        for (i in 0 until cards.length()) {
            val card = cards.optJSONObject(i) ?: continue
            card(card)
        }

        section("파이프라인 요약")
        val summary = hub.optJSONObject("summary") ?: JSONObject()
        text("공식 구성요소 연결 ${summary.optInt("officialCurrentComponentsVerified", 0)}/6 · 검증 환산 ${summary.optInt("verifiedConversions", 0)}/6 · 공식 입결 ${summary.optInt("officialOutcomeAvailable", 0)}/6 · 진학사 예측 ${summary.optInt("predictionCollected", 0)}/6", 14, bold = true)
        text("publishState: ${summary.optString("publishState", "unknown")}", 13)
    }

    private fun card(card: JSONObject) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = dp(14).toFloat()
                setStroke(dp(1), 0x33000000)
                setColor(0xFFF8F8F8.toInt())
            }
        }
        val slot = card.optInt("slot")
        val title = card.optString("title", "$slot. 지원안")
        add(box, "$slot · $title", 16, true)
        val subtitle = card.optString("subtitle")
        if (subtitle.isNotBlank()) add(box, subtitle, 13, false)
        add(box, card.optString("qualityLabel", "데이터 품질 확인 필요"), 12, false)

        val decision = card.optJSONObject("scoreDecision") ?: JSONObject()
        add(box, decision.optString("conversionLabel", "대학 환산: 미확인"), 14, true)
        add(box, decision.optString("officialOutcomeLabel", "공식 입결: 미확인"), 14, false)
        add(box, decision.optString("predictionLabel", "진학사 예측: 미확인"), 14, false)
        add(box, decision.optString("decisionLabel", "종합: 판정 보류"), 13, true)

        val review = card.optJSONObject("applicationReview") ?: JSONObject()
        val relation = review.optString("relation", review.optString("code", "HOLD"))
        if (relation == "HOLD") add(box, "HOLD · 근거가 충족되기 전 지원 적정성 결론을 생성하지 않음", 12, true)
        root.addView(box, lp(match = true).apply { topMargin = dp(8) })
    }

    private fun section(label: String) {
        val t = TextView(this).apply {
            text = label
            textSize = 18f
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(18), 0, dp(6))
        }
        root.addView(t)
    }

    private fun title(label: String, size: Int) {
        val t = TextView(this).apply {
            text = label
            textSize = size.toFloat()
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.START
        }
        root.addView(t)
    }

    private fun text(label: String, size: Int, bold: Boolean = false) {
        val t = TextView(this).apply {
            text = label
            textSize = size.toFloat()
            if (bold) setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(3), 0, dp(3))
        }
        root.addView(t)
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
