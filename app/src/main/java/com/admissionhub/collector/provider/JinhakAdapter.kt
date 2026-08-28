package com.admissionhub.collector.provider

import com.admissionhub.collector.parser.GenericAdmissionParser
import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI

object JinhakAdapter : ProviderAdapter {
    override val id = ProviderId.JINHAK
    override val supportsBatchCrawl = false

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
            url.contains("infoview.aspx") -> "jinhak-student-basic"
            url.contains("four-year-university/search") || text.contains("대학검색") -> "jinhak-university-search"
            url.contains("/curation") || text.contains("큐레이션") -> "jinhak-curation"
            text.contains("수시저장소") || text.contains("저장대학") -> "jinhak-early-storage"
            text.contains("실제합격자") -> "jinhak-actual-admit-report"
            text.contains("합격예측리포트") || text.contains("합격예측 리포트") -> "jinhak-prediction-report"
            url.contains("sapplysample") || text.contains("모의지원 리포트") || text.contains("모의지원리포트") -> "jinhak-mock-support-report"
            text.contains("성적산출 리포트") || text.contains("성적산출리포트") -> "jinhak-score-calc-report"
            text.contains("추천대학") -> "jinhak-recommended-university"
            else -> "jinhak-other"
        }
    }

    override fun normalize(snapshot: JSONObject): JSONArray {
        val text = GenericAdmissionParser.collectText(snapshot)
        val pageType = classify(snapshot)
        val context = GenericAdmissionParser.inferContext(text)
        val metrics = JSONObject()

        putNumber(metrics, "universityCalculatedScore", Regex("(?:대학별\\s*)?(?:환산점수|산출점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putNumber(metrics, "convertedGrade", Regex("(?:반영\\s*평균등급|환산등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "stabilityBars", Regex("(?:합격안정성|칸수|칸\\s*수)?\\s*[:：]?\\s*([0-9]{1,2})\\s*칸").find(text)?.groupValues?.getOrNull(1))
        putText(metrics, "predictionLabel", Regex("(?:합격예측|지원판정|지원전략)?\\s*[:：]?\\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "mockApplicants", Regex("(?:모의지원자수|모의지원자 수|모의지원자)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\s*)?경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "myRank", Regex("(?:내\\s*순위|나의\\s*순위)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))

        val minimum = Regex("수능최저[^.\\n]{0,80}(충족|미충족|충족가능|불충족)").find(text)?.groupValues?.getOrNull(1)
        if (!minimum.isNullOrBlank()) metrics.put("minimumStatus", minimum)

        val hasMetric = metrics.keys().asSequence().any { !metrics.isNull(it) }
        if (!hasMetric) return GenericAdmissionParser.normalize(snapshot)

        val record = JSONObject()
            .put("recordType", "jinhak-page-summary")
            .put("providerPageType", pageType)
            .put("year", context.year ?: JSONObject.NULL)
            .put("university", context.university ?: JSONObject.NULL)
            .put("department", context.department ?: JSONObject.NULL)
            .put("admission", context.admission ?: JSONObject.NULL)
            .put("metrics", metrics)
            .put("confidence", if (context.university != null || context.department != null || context.admission != null) "high" else "medium")
            .put("sourcePage", safePath(snapshot.optString("url")))
            .put("rawEvidence", text.take(3000))
        return RecordUtils.dedupe(JSONArray().put(record))
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
