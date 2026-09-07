package com.admissionhub.collector.score

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.text.InputType
import android.widget.*
import com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer
import com.admissionhub.collector.local.LocalCollectorStore
import com.admissionhub.collector.hub.HubDashboardModel
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Native, scrollable user flows. Import/edits never write application slots. */
class ScoreReviewUi(
    private val activity: Activity, private val store: LocalCollectorStore,
    private val session: () -> String?, private val changed: () -> Unit,
    private val importFile: () -> Unit
) {
    private fun dp(n: Int) = (n * activity.resources.displayMetrics.density).toInt()
    private fun panel() = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(8), dp(20), dp(10)) }
    private fun text(p: LinearLayout, value: String, large: Boolean = false) = TextView(activity).apply {
        text = value; textSize = if (large) 18f else 14f; setPadding(0, dp(8), 0, dp(6)); setTextIsSelectable(true); p.addView(this)
    }
    private fun button(p: LinearLayout, label: String, action: () -> Unit) = Button(activity).apply { text = label; setOnClickListener { action() }; p.addView(this) }
    private fun field(p: LinearLayout, title: String, value: String = "", numeric: Boolean = false, multiline: Boolean = false): EditText {
        text(p, title)
        return EditText(activity).apply {
            setText(value); textSize = 15f
            inputType = if (numeric) InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL else InputType.TYPE_CLASS_TEXT or if (multiline) InputType.TYPE_TEXT_FLAG_MULTI_LINE else 0
            if (multiline) minLines = 2
            p.addView(this, LinearLayout.LayoutParams(-1, -2))
        }
    }
    private fun dialog(title: String, p: LinearLayout, save: (() -> Unit)? = null) {
        val d = AlertDialog.Builder(activity).setTitle(title).setView(ScrollView(activity).apply { addView(p) })
            .setNegativeButton("닫기", null).apply { if (save != null) setPositiveButton("저장", null) }.create()
        d.show()
        if (save != null) d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            runCatching { save() }.onSuccess { d.dismiss(); changed() }.onFailure { error(it.message ?: "입력 내용을 확인하세요.") }
        }
    }
    private fun error(message: String) { AlertDialog.Builder(activity).setTitle("입력 확인").setMessage(message).setPositiveButton("확인", null).show() }

    fun showProfile(importedText: String? = null) {
        val old = store.currentStudentScoreProfile(); val p = panel()
        text(p, "과목별 성적을 직접 입력하거나 XLSX·CSV·TSV·성적 JSON을 가져오세요. 등급이 없는 과목은 빈칸으로 보존합니다.")
        val defaultYear = session()?.let { store.loadCanonicalApplicationCandidates(it).optJSONObject(0)?.optInt("academicYear") } ?: 2027
        val year = field(p, "지원 학년도", old.optInt("academicYear", defaultYear).toString(), true)
        button(p, "XLSX 파일 가져오기 · 시트/열 미리보기") {
            activity.startActivity(Intent(activity, XlsxImportActivity::class.java).putExtra(XlsxImportActivity.EXTRA_SESSION_ID, session()))
        }
        button(p, "CSV / TSV / 성적 JSON 파일 가져오기", importFile)
        val rows = old.optJSONArray("subjects") ?: JSONArray()
        val existing = buildString {
            append(StudentScoreImport.TEMPLATE)
            for (i in 0 until rows.length()) {
                val r = rows.getJSONObject(i)
                append(listOf("gradeYear", "semester", "group", "subject", "grade", "credits", "achievement").joinToString(",") { k ->
                    val v = if (r.isNull(k)) "" else r.optString(k); "\"${v.replace("\"", "\"\"")}\""
                }).append('\n')
            }
        }
        val editor = field(p, "학년·학기·교과·과목·등급·학점·성취도", importedText ?: existing, multiline = true).apply { minLines = 6; maxLines = 14; setHorizontallyScrolling(true) }
        val complete = CheckBox(activity).apply { text = "판단에 사용할 학생부의 과목·학기 누락을 확인했습니다."; isChecked = importedText == null && old.optBoolean("completeTranscriptConfirmedByUser"); p.addView(this) }
        button(p, "입력 검토 및 저장") {
            runCatching { StudentScoreImport.parse(editor.text.toString(), year.text.toString().toInt(), complete.isChecked) }.onSuccess { profile ->
                val average = if (profile.isNull("ownWeightedGrade")) "산출 보류: 석차등급 과목의 학점을 확인하세요." else String.format(Locale.US, "%.4f", profile.optDouble("ownWeightedGrade"))
                AlertDialog.Builder(activity).setTitle("성적 저장 전 확인")
                    .setMessage("${profile.optInt("rowCount")}과목 · 등급 없음 ${profile.optInt("ungradedRows")}과목\n입력 과목 가중평균: $average\n대학별 환산값은 별도입니다. 성적이 바뀌면 기존 원서 비교는 다시 확인해야 합니다.")
                    .setNegativeButton("돌아가기", null).setPositiveButton("이 성적 저장") { _, _ -> store.saveStudentScoreImport(profile); changed(); Toast.makeText(activity, "성적 프로필 저장 완료", Toast.LENGTH_SHORT).show() }.show()
            }.onFailure { error(it.message ?: "성적 입력을 확인하세요.") }
        }
        dialog("내 성적", p)
    }

    fun showPortfolio() {
        val id = session() ?: return error("지원안을 먼저 선택하세요.")
        val model = HubDashboardModel.build(store.canonicalHubSummary(id), store.unifiedStatus(id), JSONObject(), store.scoreDecisionSummary(id))
        val p = panel(); val portfolio = model.getJSONObject("applicationPortfolio")
        text(p, "원서 적정성 · 선택 ${portfolio.optInt("selected")}/6", true)
        text(p, "어디가 공식근거 연결상태, 공식 참고선과의 성적 비교, 지원조건·일정, 진학사 자료를 분리해 함께 검토합니다. 결과는 입력·확인된 근거에 따른 점검이며 합격확률이 아닙니다.")
        val counts = portfolio.getJSONObject("counts")
        text(p, "검토 가능 ${counts.optInt("REVIEWABLE")} · 성적 위험 ${counts.optInt("SCORE_RISK")} · 조건·일정 재검토 ${counts.optInt("CONDITIONS_RECHECK")} · 자료 보완 ${counts.optInt("HOLD")}")
        val warnings = portfolio.getJSONArray("warnings")
        for (i in 0 until warnings.length()) text(p, "• ${warnings.getString(i)}")
        val cards = model.getJSONArray("cards")
        for (i in 0 until cards.length()) {
            val card = cards.getJSONObject(i); if (!card.optBoolean("occupied")) continue
            text(p, "${card.optInt("slot")}. ${card.optString("title")}\n${card.optString("subtitle")}", true)
            val official = card.optJSONObject("officialEvidence")
            if (official != null) text(p, official.optString("label"))
            text(p, card.optJSONObject("applicationReview")?.optString("label", "자료 보완 후 판단") ?: "자료 보완 후 판단")
            button(p, "근거·부족한 항목 보기") { showCard(card.optString("applicationIdentityKey")) }
        }
        dialog("6장 전체 검토", p)
    }

    fun showCard(identity: String) {
        val id = session() ?: return error("지원안 연결을 확인하세요.")
        val list = store.loadCanonicalApplicationCandidates(id)
        val candidate = (0 until list.length()).map { list.getJSONObject(it) }.firstOrNull { it.optString("applicationIdentityKey") == identity } ?: return error("지원안 연결을 복구하세요.")
        val score = store.scoreDecisionSummary(id).getJSONObject("byIdentity").optJSONObject(identity) ?: return error("현재 선택한 지원안에만 등록할 수 있습니다.")
        val review = score.getJSONObject("applicationReview"); val p = panel()
        val official = AdigaApplicationEvidenceAnalyzer.analyze(candidate)
        text(p, candidate.optString("displayLabel"), true); text(p, review.getString("label"), true)
        text(p, "어디가 공식근거 연결", true)
        text(p, official.optString("label"))
        val officialFacts = official.optJSONArray("facts") ?: JSONArray()
        for (i in 0 until officialFacts.length()) text(p, "• ${officialFacts.getString(i)}")
        val officialMissing = official.optJSONArray("missing") ?: JSONArray()
        if (officialMissing.length() > 0) {
            text(p, "직접 연결에 부족한 근거")
            for (i in 0 until officialMissing.length()) text(p, "• ${officialMissing.getString(i)}")
        }
        text(p, official.optString("nextAction"))
        for ((key, title) in listOf("reasons" to "판단 근거", "risks" to "유의할 항목", "missing" to "더 필요한 자료")) {
            text(p, title, true); val a = review.getJSONArray(key)
            if (a.length() == 0) text(p, "현재 추가 항목 없음")
            for (i in 0 until a.length()) text(p, "• ${a.getString(i)}")
        }
        text(p, SameCardPrediction.label(score.optJSONObject("prediction")))
        val prediction = score.optJSONObject("prediction")
        if (prediction != null) {
            text(p, "진학사 관측시각: ${prediction.optString("observedAt")}\n진학사 수치는 대학의 공식 환산 검증값과 별도입니다.")
            val m = prediction.optJSONObject("metrics") ?: JSONObject()
            for ((k, label) in listOf("mockApplicantAverageScore" to "모의지원자 평균 점수", "mockApplicantAverageGrade" to "모의지원자 평균 등급", "myReflectedGrade" to "내 반영등급")) if (m.has(k)) text(p, "$label: ${m.optDouble(k)}")
        }
        button(p, "성적·공식 입결 근거 등록 / 수정") { editEvidence(candidate, false) }
        button(p, "지원자격·수능최저·서류·일정 확인") { editEvidence(candidate, true) }
        button(p, "수집된 어디가 근거를 연결 수준별로 보기") { showOfficialEvidence(official) }
        dialog("원서별 적정성 검토", p)
    }

    private fun showOfficialEvidence(official: JSONObject) {
        val body = panel()
        text(body, official.optString("label"), true)
        text(body, "대학 단위 자료와 원서 직접 연결 자료를 구분합니다. 전형·모집단위가 같은 행 또는 명시적 동일 표 구간에서 확인되지 않으면 이 원서의 공식 입결로 자동 승격하지 않습니다.")
        fun showArray(title: String, rows: JSONArray) {
            text(body, title, true)
            if (rows.length() == 0) text(body, "없음")
            for (i in 0 until rows.length()) {
                val r = rows.optJSONObject(i) ?: continue
                text(body, "${r.optInt("recordYear")} · ${r.optString("scope")} · 모집단위 ${r.optString("departmentMatch")} · 전형 ${r.optString("admissionMatch")}\n${r.optString("rowEvidence")}\n${r.optString("sourcePage")}")
            }
        }
        showArray("지원년도 직접 연결 근거", official.optJSONArray("currentApplicationBoundEvidence") ?: JSONArray())
        showArray("과거 입결 직접 연결 근거", official.optJSONArray("historicalApplicationBoundEvidence") ?: JSONArray())
        showArray("지원년도 대학/전형 공통 근거 예시", official.optJSONArray("universityCurrentEvidenceSample") ?: JSONArray())
        showArray("과거 공식자료 예시", official.optJSONArray("historicalEvidenceSample") ?: JSONArray())
        text(body, official.optString("nextAction"), true)
        dialog("어디가 공식자료 연결 진단", body)
    }

    private fun editEvidence(candidate: JSONObject, rules: Boolean) {
        val id = session() ?: return; val identity = candidate.getString("applicationIdentityKey")
        val old = store.loadApplicationReviewInput(identity); val input = JSONObject(old.toString()); val p = panel()
        text(p, "${candidate.optInt("academicYear")} ${candidate.optString("displayLabel")}", true)
        val official = AdigaApplicationEvidenceAnalyzer.analyze(candidate)
        text(p, official.optString("label")); text(p, official.optString("nextAction"))
        val edits = linkedMapOf<String, EditText>()
        fun add(key: String, title: String, numeric: Boolean = false, multiline: Boolean = false) {
            val value = if (old.isNull(key)) "" else old.optString(key)
            edits[key] = field(p, title, value, numeric, multiline)
        }
        var sourceCheck: CheckBox? = null; var rulesCheck: CheckBox? = null
        val spinners = mutableMapOf<String, Spinner>()
        if (!rules) {
            text(p, "대학 공식 성적산출 결과와 과거 입결의 동일 지표를 입력하세요. 어디가의 대학 단위 공통자료나 진학사 점수를 공식 환산값으로 자동 승격하지 않습니다.")
            button(p, "대학 공식 자료 열기") {
                val u = candidate.optString("university")
                val url = when { u.contains("우송") -> "https://ent.wsu.ac.kr/board/read.jsp?code=einfo0601&id=267261"; u.contains("한밭") -> "https://www.hanbat.ac.kr/admission/"; u.contains("한국교통") -> "https://www.ut.ac.kr/ipsi.do"; u.contains("충남") -> "https://ipsi.cnu.ac.kr/"; else -> "https://www.adiga.kr/" }
                activity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            }
            add("ownScore", "내 대학 환산값", true); add("maxScore", "같은 척도의 만점 (등급이면 9)", true)
            add("scoreScale", "점수 척도 이름 (예: 해당 대학 반영교과 평균등급)")
            text(p, "어느 방향이 유리한가요?")
            val direction = Spinner(activity).apply { adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, listOf("선택 필요", "낮을수록 유리", "높을수록 유리")); setSelection(when(old.optString("direction")){"lower-is-better"->1;"higher-is-better"->2;else->0});p.addView(this) }
            spinners["direction"] = direction
            add("formulaSource", "공식 환산식 / 성적산출 페이지 URL")
            add("formulaExcerpt", "확인한 산식·반영교과·학기·가산점 근거", multiline = true)
            add("outcomeYear", "공식 입결 학년도", true); add("metricName", "지표 이름 (평균 / 70%컷 / 100%컷 등)")
            add("referenceScore", "해당 공식 지표의 값", true); add("outcomeSource", "공식 입결 URL")
            add("outcomeExcerpt", "같은 행의 대학·전형·모집단위·지표 근거", multiline = true)
            add("methodDescription", "두 값의 반영과목·계산방법이 같은지 확인한 근거", multiline = true)
            val current = store.currentStudentScoreProfile()
            sourceCheck = CheckBox(activity).apply { text = "공식 원문에서 전형·학과·연도와 동일한 계산 기준을 확인했고, 내 값은 현재 입력 성적에 대한 값입니다."; isChecked = old.optBoolean("sourceReviewConfirmed") && old.optString("profileFingerprint") == current.optString("fingerprint") && current.optString("fingerprint").isNotBlank(); p.addView(this) }
        } else {
            text(p, "해당 지원년도의 모집요강을 근거로 확인하세요. 모의평가 최저 충족은 실제 수능최저 충족 확정과 구분하세요.")
            for ((key, label) in ApplicationReviewEngine.checks) { text(p, label); spinners[key] = Spinner(activity).apply { adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, ApplicationReviewEngine.checkStates); setSelection(old.optInt(key).coerceIn(0, 3)); p.addView(this) } }
            add("rulesSource", "지원조건·일정의 공식 모집요강 URL"); add("rulesExcerpt", "관련 전형 규칙과 내가 충족하는 근거", multiline = true)
            val oldDeadline = old.optString("deadline")
            val displayDeadline = runCatching { Instant.parse(oldDeadline).atZone(ZoneId.of("Asia/Seoul")).format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")) }.getOrDefault("")
            edits["deadline"] = field(p, "원서접수 마감 (한국시간 YYYY-MM-DD HH:mm)", displayDeadline)
            add("interviewDate", "면접일 (YYYY-MM-DD, 없으면 빈칸)")
            rulesCheck = CheckBox(activity).apply { text = "해당 연도 공식 규칙과 일정, 준비 상태를 확인했습니다."; isChecked = old.optBoolean("rulesReviewConfirmed"); p.addView(this) }
        }
        add("note", "내 검토 메모", multiline = true)
        dialog(if (rules) "지원조건·일정" else "성적·공식 근거", p) {
            for ((key, e) in edits) input.put(key, e.text.toString().trim())
            for ((key, spinner) in spinners) input.put(key, if (key == "direction") listOf("", "lower-is-better", "higher-is-better")[spinner.selectedItemPosition] else spinner.selectedItemPosition)
            sourceCheck?.let { input.put("sourceReviewConfirmed", it.isChecked) }; rulesCheck?.let { input.put("rulesReviewConfirmed", it.isChecked) }
            if (rules && input.optString("deadline").isNotBlank()) input.put("deadline", LocalDateTime.parse(input.optString("deadline"), DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")).atZone(ZoneId.of("Asia/Seoul")).toInstant().toString())
            // Editing other sections cannot silently refresh a previously confirmed score's profile binding.
            if (rules && old.optString("profileFingerprint") != store.currentStudentScoreProfile().optString("fingerprint")) input.put("sourceReviewConfirmed", false)
            store.saveApplicationReviewInput(id, identity, input)
        }
    }
}
