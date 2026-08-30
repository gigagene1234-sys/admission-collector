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
        val hasPrediction = text.contains("합격예측") || text.contains("모의지원") || Regex("[0-9]{1,2}\\s*칸").containsMatchIn(text)
        val hasActual = text.contains("실제합격자") ||
            (text.contains("입시결과") && Regex("(최종등록|합격자|충원|70%|50%)").containsMatchIn(text))
        val dedicatedMinimum = url.contains("esatminuniv") ||
            (Regex("(수능최저\\s*(검색|대학|조건)|최저학력기준\\s*(검색|대학))").containsMatchIn(text) && !hasPrediction)
        return when {
            Regex("(login|signin|member/login)").containsMatchIn(url) || text.contains("로그인") && text.contains("비밀번호") -> "jinhak-login"
            hasActual -> "jinhak-actual-admit-report"
            text.contains("합격예측리포트") || text.contains("합격예측 리포트") || hasPrediction -> "jinhak-prediction-report"
            url.contains("sapplysample") || text.contains("모의지원 리포트") || text.contains("모의지원리포트") -> "jinhak-mock-support-report"
            text.contains("성적산출 리포트") || text.contains("성적산출리포트") -> "jinhak-score-calc-report"
            dedicatedMinimum -> "jinhak-sat-minimum"
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
        val context = GenericAdmissionParser.inferSnapshotContext(snapshot)
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
                .put("confidence", when {
                    context.university != null && context.department != null -> "high"
                    context.university != null || context.department != null || context.admission != null -> "medium"
                    else -> "raw"
                })
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
        val inherited = inferSnapshotContext(snapshot)
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

    fun inferSnapshotContext(snapshot: JSONObject): InferredContext {
        val priority = mutableListOf<String>()
        snapshot.optString("title").trim().takeIf { it.isNotBlank() }?.let(priority::add)
        val context = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until minOf(context.length(), 80)) context.optString(i).trim().takeIf { it.isNotBlank() }?.let(priority::add)
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 30)) blocks.optString(i).trim().takeIf { it.isNotBlank() }?.let(priority::add)
        val first = inferContext(priority.joinToString(" | "))
        if (first.university != null && first.department != null) return first
        val fallback = inferContext(collectText(snapshot).take(12000))
        return InferredContext(
            first.university ?: fallback.university,
            first.department ?: fallback.department,
            first.admission ?: fallback.admission,
            first.year ?: fallback.year
        )
    }

    fun inferContext(text: String): InferredContext {
        val normalized = text.replace(Regex("\\s+"), " ").trim()
        val university = bestUniversity(normalized)
        val department = bestDepartment(normalized)
        val admission = bestAdmission(normalized)
        val year = Regex("(?:^|[^0-9])(20[0-9]{2})(?:학년도|년도|년)?")
            .find(normalized)?.groupValues?.getOrNull(1)?.toIntOrNull()
        return InferredContext(university, department, admission, year)
    }

    private fun bestUniversity(text: String): String? {
        val universityMatches = Regex("([가-힣A-Za-z0-9·.()\\-]{2,35}대학교(?:\\[[^\\]]{1,12}\\])?)")
            .findAll(text).map { cleanCandidate(it.groupValues[1]) }.filter { it.length in 4..45 }.toList()
        universityMatches.firstOrNull()?.let { return it }

        val excludedCollege = Regex("(공과대학|인문대학|사회과학대학|자연과학대학|의과대학|약학대학|간호대학|경상대학|사범대학|예술대학|디자인대학|IT대학|철도대학|보건대학|융합대학|천안공과대학)$")
        return Regex("([가-힣A-Za-z0-9·.()\\-]{2,30}대학)")
            .findAll(text)
            .map { cleanCandidate(it.groupValues[1]) }
            .firstOrNull { it.length in 3..35 && !excludedCollege.containsMatchIn(it) }
    }

    private fun bestDepartment(text: String): String? {
        val noise = Regex("(지원|합격|예측|반영|학생부|전형|대학교|대학검색|모집인원|경쟁률)")
        val suffix = Regex("(학과|학부|전공|모집단위|자율전공)$")
        val segments = text.split('|').map { cleanCandidate(it) }.filter { it.isNotBlank() }
        val candidates = mutableListOf<String>()
        for (segment in segments) {
            val labeled = Regex("(?:학과|학부|모집단위|전공)\\s*[:：]\\s*([가-힣A-Za-z0-9·.()&・\\- ]{2,40})").find(segment)?.groupValues?.getOrNull(1)
            if (!labeled.isNullOrBlank()) candidates += cleanCandidate(labeled)
            Regex("([가-힣A-Za-z0-9·.()&・\\-]{2,35}(?:학과|학부|전공|모집단위))")
                .findAll(segment).forEach { candidates += cleanCandidate(it.groupValues[1]) }
        }
        return candidates
            .filter { it.length in 2..40 && suffix.containsMatchIn(it) && !noise.containsMatchIn(it) }
            .minByOrNull { it.length }
    }

    private fun bestAdmission(text: String): String? {
        val segments = text.split('|').map { cleanCandidate(it) }.filter { it.isNotBlank() }
        val candidates = mutableListOf<String>()
        val known = Regex("((?:학생부교과|학생부종합|교과|종합|지역인재|학교장추천|일반|면접|교과면접|서류|고른기회|농어촌|기회균형)[가-힣A-Za-z0-9·.()_\\- ]{0,24}전형)")
        for (segment in segments) {
            Regex("(?:전형명|전형)\\s*[:：]\\s*([가-힣A-Za-z0-9·.()_\\- ]{2,35}(?:전형)?)")
                .find(segment)?.groupValues?.getOrNull(1)?.let { candidates += cleanCandidate(it) }
            known.findAll(segment).forEach { candidates += cleanCandidate(it.groupValues[1]) }
        }
        return candidates.firstOrNull {
            it.length in 2..40 && !Regex("[①-⑳]|[0-9]+\\)|학생부 반영비율|있는 전형|없는 서류|설명|안내").containsMatchIn(it)
        }
    }

    private fun cleanCandidate(value: String): String = value
        .replace(Regex("^[^가-힣A-Za-z0-9]+|[^가-힣A-Za-z0-9)\\]]+$"), "")
        .replace(Regex("\\s+"), " ")
        .trim()

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
            university != null && department != null -> "high"
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

for p in MAIN_PATHS:
    s = p.read_text()
    s = s.replace('private const val VERSION = "0.5.0"', 'private const val VERSION = "0.5.1"')
    s = s.replace('private const val BUILD_CODE = 10500', 'private const val BUILD_CODE = 10510')
    p.write_text(s)

(ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt').write_text(JINHAK)
(ROOT / 'app/src/main/java/com/admissionhub/collector/parser/GenericAdmissionParser.kt').write_text(GENERIC)

p = ROOT / 'app/build.gradle.kts'
s = p.read_text().replace('versionCode = 10500', 'versionCode = 10510').replace('versionName = "0.5.0"', 'versionName = "0.5.1"')
p.write_text(s)

p = ROOT / 'app/src/main/AndroidManifest.xml'
s = p.read_text().replace('Admission Collector v0.5.0 Jinhak', 'Admission Collector v0.5.1 Jinhak')
p.write_text(s)
