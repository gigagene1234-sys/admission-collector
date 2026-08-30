from pathlib import Path

ROOT = Path('.')

MAIN_PATHS = [
    ROOT / 'MainActivity.kt',
    ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt',
]

JINHAK = r'''package com.admissionhub.collector.provider

import com.admissionhub.collector.parser.GenericAdmissionParser
import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.time.Instant
import java.time.temporal.ChronoUnit

object JinhakAdapter : ProviderAdapter {
    override val id = ProviderId.JINHAK
    override val supportsBatchCrawl = false
    private const val TARGET_YEAR = 2027

    override fun accepts(url: String): Boolean {
        return try {
            val host = URI(url).host?.lowercase() ?: return false
            host == "jinhak.com" || host.endsWith(".jinhak.com")
        } catch (_: Exception) { false }
    }

    override fun isBatchNavigable(url: String): Boolean = false

    override fun classify(snapshot: JSONObject): String {
        val url = snapshot.optString("url").lowercase()
        val text = GenericAdmissionParser.collectText(snapshot)
        return when {
            Regex("(login|signin|member/login)").containsMatchIn(url) || text.contains("로그인") && text.contains("비밀번호") -> "jinhak-login"
            url.contains("esatminuniv") || text.contains("수능최저") -> "jinhak-sat-minimum"
            text.contains("실제합격자") || text.contains("입시결과") && Regex("(최종등록|합격자|충원|70%|50%)").containsMatchIn(text) -> "jinhak-actual-admit-report"
            text.contains("합격예측리포트") || text.contains("합격예측 리포트") || text.contains("합격예측") && text.contains("칸") -> "jinhak-prediction-report"
            url.contains("sapplysample") || text.contains("모의지원 리포트") || text.contains("모의지원리포트") -> "jinhak-mock-support-report"
            text.contains("성적산출 리포트") || text.contains("성적산출리포트") -> "jinhak-score-calc-report"
            url.contains("infoview.aspx") -> "jinhak-student-basic"
            url.contains("four-year-university/search") || text.contains("대학검색") -> "jinhak-university-search"
            url.contains("/curation") || text.contains("큐레이션") -> "jinhak-curation"
            text.contains("수시저장소") || text.contains("저장대학") -> "jinhak-early-storage"
            text.contains("추천대학") -> "jinhak-recommended-university"
            else -> "jinhak-other"
        }
    }

    override fun normalize(snapshot: JSONObject): JSONArray {
        val text = GenericAdmissionParser.collectText(snapshot)
        val pageType = classify(snapshot)
        val context = GenericAdmissionParser.inferContext(text)
        val observedAt = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()
        val dataScope = dataScope(pageType)
        val inferredYear = context.year ?: if (dataScope == "current-prediction" || dataScope == "current-admission") TARGET_YEAR else null
        val result = JSONArray()

        val metrics = JSONObject()
        putNumber(metrics, "universityCalculatedScore", Regex("(?:대학별\\s*)?(?:환산점수|산출점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putNumber(metrics, "convertedGrade", Regex("(?:반영\\s*평균등급|환산등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "stabilityBars", Regex("(?:합격안정성|칸수|칸\\s*수)?\\s*[:：]?\\s*([0-9]{1,2})\\s*칸").find(text)?.groupValues?.getOrNull(1))
        putText(metrics, "predictionLabel", Regex("(?:합격예측|지원판정|지원전략)?\\s*[:：]?\\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "mockApplicants", Regex("(?:모의지원자수|모의지원자 수|모의지원자)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "applicants", Regex("(?:현재\\s*)?(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\s*)?경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "myRank", Regex("(?:내\\s*순위|나의\\s*순위|현재\\s*순위)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "predictedCut", Regex("(?:예상\\s*합격선|예상\\s*컷|합격예상점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "additionalAdmits", Regex("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))

        val minimum = Regex("수능최저[^.\\n]{0,100}(충족가능|미충족|불충족|충족)").find(text)?.groupValues?.getOrNull(1)
        if (!minimum.isNullOrBlank()) metrics.put("minimumStatus", minimum)

        if (metrics.keys().asSequence().any { !metrics.isNull(it) }) {
            val summary = JSONObject()
                .put("recordType", if (dataScope == "current-prediction") "jinhak-prediction-snapshot" else "jinhak-page-summary")
                .put("providerPageType", pageType)
                .put("dataScope", dataScope)
                .put("year", inferredYear ?: JSONObject.NULL)
                .put("university", context.university ?: JSONObject.NULL)
                .put("department", context.department ?: JSONObject.NULL)
                .put("admission", context.admission ?: JSONObject.NULL)
                .put("metrics", metrics)
                .put("observedAt", observedAt)
                .put("confidence", if (context.university != null || context.department != null || context.admission != null) "high" else "medium")
                .put("sourcePage", safePath(snapshot.optString("url")))
                .put("rawEvidence", text.take(5000))
            summary.put("sourceRowFingerprint", fingerprint(summary, observedAt, preserveSnapshot = dataScope == "current-prediction"))
            result.put(summary)
        }

        val generic = GenericAdmissionParser.normalize(snapshot)
        for (i in 0 until generic.length()) {
            val row = generic.optJSONObject(i) ?: continue
            row.put("providerPageType", pageType)
                .put("dataScope", dataScope)
                .put("observedAt", observedAt)
            if (row.isNull("year") && inferredYear != null) row.put("year", inferredYear)
            row.put("sourcePage", safePath(snapshot.optString("url")))
            row.put("sourceRowFingerprint", fingerprint(row, observedAt, preserveSnapshot = dataScope == "current-prediction"))
            result.put(row)
        }
        return RecordUtils.dedupe(result)
    }

    private fun dataScope(pageType: String): String = when (pageType) {
        "jinhak-actual-admit-report" -> "historical-result"
        "jinhak-prediction-report", "jinhak-mock-support-report", "jinhak-recommended-university" -> "current-prediction"
        "jinhak-sat-minimum" -> "current-admission"
        "jinhak-score-calc-report", "jinhak-student-basic" -> "student-profile"
        else -> "reference"
    }

    private fun fingerprint(record: JSONObject, observedAt: String, preserveSnapshot: Boolean): String {
        val stable = listOf(
            record.optString("recordType"), record.optString("year"), record.optString("university"),
            record.optString("department"), record.optString("admission"), record.optJSONObject("metrics")?.toString() ?: "",
            record.optString("rawEvidence").take(1000)
        ).joinToString("|")
        val scope = if (preserveSnapshot) observedAt.substring(0, 16) else "stable"
        return RecordUtils.sha256("jinhak|$scope|$stable")
    }

    private fun putNumber(obj: JSONObject, key: String, value: String?) {
        val n = value?.toDoubleOrNull() ?: return
        obj.put(key, n)
    }
    private fun putInt(obj: JSONObject, key: String, value: String?) {
        val n = value?.toIntOrNull() ?: return
        obj.put(key, n)
    }
    private fun putText(obj: JSONObject, key: String, value: String?) {
        value?.trim()?.takeIf { it.isNotBlank() }?.let { obj.put(key, it) }
    }
    private fun safePath(url: String): String = try {
        val uri = URI(url)
        "${uri.scheme ?: "https"}://${uri.host ?: ""}${uri.path ?: "/"}"
    } catch (_: Exception) { url.substringBefore('?').substringBefore('#') }
}
'''

GENERIC = r'''package com.admissionhub.collector.parser

import org.json.JSONArray
import org.json.JSONObject

object GenericAdmissionParser {
    data class InferredContext(
        val university: String?,
        val department: String?,
        val admission: String?,
        val year: Int?
    )

    fun normalize(snapshot: JSONObject): JSONArray {
        val result = JSONArray()
        val inherited = inferContext(collectText(snapshot).take(10000))
        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until tables.length()) {
            val table = tables.optJSONObject(ti) ?: continue
            val caption = table.optString("caption")
            val rows = table.optJSONArray("rows") ?: continue
            for (ri in 0 until rows.length()) {
                val row = rows.optJSONArray(ri) ?: continue
                val cells = mutableListOf<String>()
                for (ci in 0 until row.length()) cells.add(row.optString(ci))
                val evidence = listOf(caption, cells.joinToString(" | ")).filter { it.isNotBlank() }.joinToString(" | ")
                buildRecord(evidence, inherited)?.let { result.put(it) }
            }
        }
        return RecordUtils.dedupe(result)
    }

    fun collectText(snapshot: JSONObject): String {
        val parts = mutableListOf<String>()
        parts += snapshot.optString("title")
        val context = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until context.length()) context.optString(i).trim().takeIf { it.isNotBlank() }?.let(parts::add)
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 120)) blocks.optString(i).trim().takeIf { it.isNotBlank() }?.let(parts::add)
        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until minOf(tables.length(), 120)) {
            val table = tables.optJSONObject(ti) ?: continue
            table.optString("caption").trim().takeIf { it.isNotBlank() }?.let(parts::add)
            val rows = table.optJSONArray("rows") ?: continue
            for (ri in 0 until minOf(rows.length(), 250)) {
                val row = rows.optJSONArray(ri) ?: continue
                val cells = mutableListOf<String>()
                for (ci in 0 until minOf(row.length(), 40)) cells.add(row.optString(ci))
                if (cells.isNotEmpty()) parts += cells.joinToString(" | ")
            }
        }
        return parts.joinToString(" \n ").replace(Regex("\\s+"), " ").take(60000)
    }

    fun inferContext(text: String): InferredContext {
        val universityRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,45}(대학교|대학)(?:\\[(?:본교|분교|제\\d+캠퍼스)\\])?)")
        val deptRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,55}(학과|학부|전공|모집단위))")
        val admissionRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,70}(전형|학생부교과|학생부종합|교과|종합|추천|면접))")
        val yearRegex = Regex("(?:^|[^0-9])(20[0-9]{2})(?:학년도|년도|년)?")
        return InferredContext(
            universityRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            deptRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            admissionRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            yearRegex.find(text)?.groupValues?.getOrNull(1)?.toIntOrNull()
        )
    }

    private fun buildRecord(evidenceRaw: String, inherited: InferredContext): JSONObject? {
        val evidence = evidenceRaw.replace(Regex("\\s+"), " ").trim().take(7000)
        if (evidence.length < 2) return null

        val local = inferContext(evidence)
        val year = local.year ?: inherited.year
        val university = local.university ?: inherited.university
        val department = local.department ?: inherited.department
        val admission = local.admission ?: inherited.admission

        fun findNumber(pattern: String): Double? = Regex(pattern, RegexOption.IGNORE_CASE).find(evidence)?.groupValues?.getOrNull(1)?.replace(",", "")?.toDoubleOrNull()
        fun findInt(pattern: String): Int? = Regex(pattern, RegexOption.IGNORE_CASE).find(evidence)?.groupValues?.getOrNull(1)?.replace(",", "")?.toIntOrNull()

        val competition = Regex("(?:경쟁률)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?(?:\\s*[:대]\\s*1)?)").find(evidence)?.groupValues?.getOrNull(1)
        val judgment = Regex("(?:판정|합격예측|지원판정)\\s*[:：]?\\s*(안정|적정|소신|위험|상향|하향|가능|불안|유리|불리)").find(evidence)?.groupValues?.getOrNull(1)

        val metrics = JSONObject()
            .put("myScore", findNumber("(?:내\\s*(?:환산)?점수|나의\\s*(?:환산)?점수|산출점수|환산점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("grade", findNumber("(?:등급|반영\\s*평균등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("cut50", findNumber("(?:50%\\s*(?:컷|cut|등급|점수)|산출점수\\s*50%)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("cut70", findNumber("(?:70%\\s*(?:컷|cut|등급|점수)|산출점수\\s*70%)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("averageGrade", findNumber("(?:(?:최종등록자|등록자|합격자)\\s*)?(?:평균등급|평균 등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("lowestGrade", findNumber("(?:최저등급|최저 등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)") ?: JSONObject.NULL)
            .put("competition", competition ?: JSONObject.NULL)
            .put("capacity", findInt("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)") ?: JSONObject.NULL)
            .put("applicants", findInt("(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)") ?: JSONObject.NULL)
            .put("additionalAdmits", findInt("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)") ?: JSONObject.NULL)
            .put("jinhakBars", findInt("(?:칸수|칸\\s*수)\\s*[:：]?\\s*([0-9]+)") ?: JSONObject.NULL)
            .put("jinhakJudgment", judgment ?: JSONObject.NULL)

        val hasMetric = metrics.keys().asSequence().any { !metrics.isNull(it) }
        if (!hasMetric) return null

        val confidence = when {
            university != null && department != null && admission != null -> "high"
            university != null || department != null || admission != null -> "medium"
            else -> "raw"
        }

        return JSONObject()
            .put("recordType", "generic-admission-metric")
            .put("year", year ?: JSONObject.NULL)
            .put("university", university ?: JSONObject.NULL)
            .put("department", department ?: JSONObject.NULL)
            .put("admission", admission ?: JSONObject.NULL)
            .put("metrics", metrics)
            .put("confidence", confidence)
            .put("rawEvidence", evidence)
    }
}
'''

(ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt').write_text(JINHAK, encoding='utf-8')
(ROOT / 'app/src/main/java/com/admissionhub/collector/parser/GenericAdmissionParser.kt').write_text(GENERIC, encoding='utf-8')

for path in MAIN_PATHS:
    text = path.read_text(encoding='utf-8')
    text = text.replace('private lateinit var batchCover: TextView\n', 'private lateinit var batchCover: TextView\n    private lateinit var diagnosticButton: Button\n')
    text = text.replace('private var provider: ProviderId = ProviderId.ADIGA\n', 'private var provider: ProviderId = ProviderId.ADIGA\n    private var lastJinhakDigest = JSONObject()\n')
    text = text.replace('private const val VERSION = "0.4.3"', 'private const val VERSION = "0.5.0"')
    text = text.replace('private const val BUILD_CODE = 10430', 'private const val BUILD_CODE = 10500')
    text = text.replace('private const val LOCAL_FIRST_BETA = true\n', 'private const val LOCAL_FIRST_BETA = true\n        private const val ADIGA_RETRY_SUSPENDED = true\n')
    text = text.replace('openProvider(ProviderId.ADIGA)', 'openProvider(ProviderId.JINHAK)', 1)
    text = text.replace('''        val diagnostic = Button(this).apply {
            text = "진단 로그 전송"
            setOnClickListener { sendLatestLocalDiagnostic(manual = true) }
        }
        actions3.addView(diagnostic, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
''', '''        diagnosticButton = Button(this).apply {
            text = "진학사 분석 전송"
            setOnClickListener {
                if (provider == ProviderId.JINHAK) sendLatestJinhakAnalysisDigest() else sendLatestLocalDiagnostic(manual = true)
            }
        }
        actions3.addView(diagnosticButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
''')
    old_open = '''    private fun openProvider(which: ProviderId) {
        if (batchRunning) stopBatch("서비스 전환")
        provider = which
        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        status.text = "${which.displayName} 열기"
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        webView.loadUrl(which.homeUrl)
    }
'''
    new_open = '''    private fun openProvider(which: ProviderId) {
        if (batchRunning) stopBatch("서비스 전환")
        provider = which
        localRunId = localStore.latestResumableRun(which.wireName)
        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        status.text = if (which == ProviderId.JINHAK) "진학사 분석 모드: 로그인 후 원하는 리포트/대학 화면을 여세요." else "어디가 복구 보류: 진학사 분석 이후 한밭대 381쪽부터 재시도 예정"
        batchButton.text = when (which) {
            ProviderId.JINHAK -> "현재 진학사 화면 분석·누적"
            ProviderId.ADIGA -> "어디가 복구 보류"
        }
        diagnosticButton.text = if (which == ProviderId.JINHAK) "진학사 분석 전송" else "어디가 진단 로그 전송"
        webView.loadUrl(which.homeUrl)
    }
'''
    if old_open not in text:
        raise SystemExit(f'openProvider block not found in {path}')
    text = text.replace(old_open, new_open)

    anchor = '''        if (!currentAdapter().supportsBatchCrawl) {
            status.text = "진학사는 사이트 전체 순회 대신 현재 화면을 안전하게 구조화합니다."
            collectCurrentPage()
            return
        }
'''
    replacement = '''        if (provider == ProviderId.ADIGA && ADIGA_RETRY_SUSPENDED) {
            status.text = "어디가 복구는 현재 보류 중입니다. 진학사 분석 버전 검증 후 한밭대 381쪽을 우선 재시도합니다."
            Toast.makeText(this, "어디가 재시도는 진학사 분석 이후 진행합니다.", Toast.LENGTH_LONG).show()
            return
        }

        if (!currentAdapter().supportsBatchCrawl) {
            status.text = "진학사 현재 화면을 분석하고 로컬 이력에 누적합니다."
            collectCurrentPage()
            return
        }
'''
    if anchor not in text:
        raise SystemExit(f'startBatch anchor not found in {path}')
    text = text.replace(anchor, replacement)

    old_collect = '''    private fun collectCurrentPage() {
        status.text = "현재 페이지의 표·헤더·카드·입시정보를 구조적으로 수집 중…"
        collectSnapshot { snapshot ->
            if (snapshot == null) return@collectSnapshot
            val records = normalizeSnapshot(snapshot)
            val out = JSONObject()
                .put("collectorVersion", VERSION)
                .put("provider", provider.wireName)
                .put("collectedAt", Instant.now().toString())
                .put("mode", "single-page")
                .put("session", snapshot.optJSONObject("session") ?: JSONObject())
                .put("records", records)
                .put("snapshots", JSONArray().put(stripNavigationLinksForExport(snapshot)))
                .put("resourceLinks", snapshot.optJSONArray("resourceLinks") ?: JSONArray())
            lastJson = out.toString(2)
            showPreview(lastJson)
            status.text = "현재 페이지 수집 완료: 구조화 레코드 ${records.length()}개"
        }
    }
'''
    new_collect = '''    private fun collectCurrentPage() {
        status.text = if (provider == ProviderId.JINHAK) "진학사 화면의 과거입결·예측·성적지표를 분석 중…" else "현재 페이지의 표·헤더·카드·입시정보를 구조적으로 수집 중…"
        collectSnapshot { snapshot ->
            if (snapshot == null) return@collectSnapshot
            val records = normalizeSnapshot(snapshot)
            val collectedAt = Instant.now().toString()
            var localStats = JSONObject()
            var stored = 0
            if (provider == ProviderId.JINHAK) {
                val runId = localStore.beginOrResume(provider.wireName, VERSION)
                localRunId = runId
                stored = localStore.storeRecords(runId, provider.wireName, records)
                localStore.markDocument(runId, canonicalizeBatchUrl(snapshot.optString("url")), "completed")
                localStats = localStore.stats(runId)
                lastJinhakDigest = buildJinhakDigest(snapshot, records, runId, collectedAt)
            }
            val out = JSONObject()
                .put("collectorVersion", VERSION)
                .put("provider", provider.wireName)
                .put("collectedAt", collectedAt)
                .put("mode", if (provider == ProviderId.JINHAK) "jinhak-analysis" else "single-page")
                .put("session", snapshot.optJSONObject("session") ?: JSONObject())
                .put("localStoredThisCapture", stored)
                .put("localStats", localStats)
                .put("records", records)
                .put("snapshots", JSONArray().put(stripNavigationLinksForExport(snapshot)))
                .put("resourceLinks", snapshot.optJSONArray("resourceLinks") ?: JSONArray())
            lastJson = out.toString(2)
            showPreview(lastJson)
            status.text = if (provider == ProviderId.JINHAK) {
                "진학사 분석·누적 완료: 이번 ${records.length()}개 / 로컬 누적 ${localStats.optInt("records", records.length())}개 / 필요 시 '진학사 분석 전송'"
            } else {
                "현재 페이지 수집 완료: 구조화 레코드 ${records.length()}개"
            }
        }
    }

    private fun buildJinhakDigest(snapshot: JSONObject, records: JSONArray, runId: String, collectedAt: String): JSONObject {
        val sanitized = JSONArray()
        val limit = minOf(records.length(), 120)
        for (i in 0 until limit) {
            val r = records.optJSONObject(i) ?: continue
            sanitized.put(JSONObject()
                .put("recordType", r.optString("recordType"))
                .put("providerPageType", r.optString("providerPageType"))
                .put("dataScope", r.optString("dataScope"))
                .put("year", if (r.isNull("year")) JSONObject.NULL else r.optInt("year"))
                .put("university", if (r.isNull("university")) JSONObject.NULL else r.optString("university"))
                .put("department", if (r.isNull("department")) JSONObject.NULL else r.optString("department"))
                .put("admission", if (r.isNull("admission")) JSONObject.NULL else r.optString("admission"))
                .put("metrics", r.optJSONObject("metrics") ?: JSONObject())
                .put("confidence", r.optString("confidence"))
                .put("observedAt", r.optString("observedAt", collectedAt)))
        }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("type", "jinhak-analysis-digest")
            .put("pageType", snapshot.optString("providerPageType"))
            .put("collectedAt", collectedAt)
            .put("recordCount", records.length())
            .put("includedRecords", sanitized.length())
            .put("truncated", records.length() > sanitized.length())
            .put("localStats", localStore.stats(runId))
            .put("records", sanitized)
            .put("privacy", "structured-admission-metrics-only-no-dom-no-raw-evidence-no-url-no-cookie-no-credential")
    }

    private fun sendLatestJinhakAnalysisDigest() {
        if (lastJinhakDigest.length() == 0) {
            Toast.makeText(this, "먼저 진학사에서 분석할 화면을 열고 '현재 진학사 화면 분석·누적'을 눌러주세요.", Toast.LENGTH_LONG).show()
            return
        }
        status.text = "진학사 구조화 분석 결과 전송 중… DOM·쿠키·로그인 정보는 보내지 않습니다."
        cloudOffload.sendDiagnostic("jinhak", VERSION, JSONObject(lastJinhakDigest.toString()).put("trigger", "manual-analysis")) { result ->
            runOnUiThread {
                if (result.isSuccess) {
                    status.text = "진학사 분석 전송 완료: ${result.getOrNull()?.take(8) ?: "unknown"}…"
                    Toast.makeText(this, "진학사 분석 전송 완료", Toast.LENGTH_SHORT).show()
                } else {
                    status.text = "진학사 분석 전송 실패: ${result.exceptionOrNull()?.message ?: "unknown"}"
                    Toast.makeText(this, "진학사 분석 전송 실패", Toast.LENGTH_LONG).show()
                }
            }
        }
    }
'''
    if old_collect not in text:
        raise SystemExit(f'collectCurrentPage block not found in {path}')
    text = text.replace(old_collect, new_collect)
    path.write_text(text, encoding='utf-8')

# Capture Jinhak report tables even when report tabs are hidden but already loaded in DOM.
snap = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
s = snap.read_text(encoding='utf-8')
old = "  var captureHiddenDetail=/\\/(?:ucp\\/uvt\\/uni\\/univDetailSelection|uct\\/acd\\/ade\\/criteriaAndResultPopup)\\.do$/i.test(location.pathname);"
new = "  var captureHiddenDetail=/(^|\\.)jinhak\\.com$/i.test(location.hostname) || /\\/(?:ucp\\/uvt\\/uni\\/univDetailSelection|uct\\/acd\\/ade\\/criteriaAndResultPopup)\\.do$/i.test(location.pathname);"
if old not in s:
    raise SystemExit('SnapshotScript captureHiddenDetail anchor not found')
snap.write_text(s.replace(old, new), encoding='utf-8')

build = ROOT / 'app/build.gradle.kts'
b = build.read_text(encoding='utf-8').replace('versionCode = 10430', 'versionCode = 10500').replace('versionName = "0.4.3"', 'versionName = "0.5.0"')
build.write_text(b, encoding='utf-8')

manifest = ROOT / 'app/src/main/AndroidManifest.xml'
m = manifest.read_text(encoding='utf-8').replace('android:label="Admission Collector v0.4.3 Local"', 'android:label="Admission Collector v0.5.0 Jinhak Analysis"')
manifest.write_text(m, encoding='utf-8')
