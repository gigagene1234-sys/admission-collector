package com.admissionhub.collector.score

import org.json.JSONObject
import java.net.URI
import java.time.Instant

/** Only the already bound, same-root grammar is promoted. Unbound reports stay unstructured. */
object SameCardPrediction {
    val fields = listOf("stabilityBars", "myCalculatedScore", "universityCalculatedScore", "myReflectedGrade", "mockApplicantAverageScore", "mockApplicantAverageGrade", "previousYearCompetition", "capacity")
    fun extract(candidate: JSONObject, record: JSONObject): JSONObject? {
        if (record.optString("recordType") != "jinhak-saved-application-prediction" ||
            record.optString("contextSource") != "same-card-application-grammar" || record.optString("confidence") != "high") return null
        for (key in listOf("applicationIdentityKey", "university", "department", "admission")) {
            val expected = candidate.optString(key)
            if (expected.isBlank() || expected == "null" || record.optString(key) != expected) return null
        }
        if (record.optInt("year") != candidate.optInt("academicYear")) return null
        if (record.optString("universityContextSource") != "card-root" || record.optInt("universityContextDepth", -1) != 0) return null
        val raw = record.optString("rawEvidence")
        if (raw.contains("대학 변경") || raw.contains("실제지원 대학선택")) return null
        // Some older captures lack department DOM annotations even though the single card's
        // literal prefix spells out every identity component. Re-verify that prefix; never
        // use an adjacent card, a substring elsewhere in the page, or an inferred alias.
        val campus = candidate.optString("campus").takeIf { it.isNotBlank() && it != "null" }
        val prefix = "^(?:닫기)?([0-9]+)칸" + Regex.escape(candidate.getString("university")) +
            "\\[(?:교과|종합)\\]" + Regex.escape(candidate.getString("admission")) +
            (campus?.let { Regex.escape("[$it]") } ?: "") + Regex.escape(candidate.getString("department")) +
            "([0-9]+)명내 점수([0-9]+(?:\\.[0-9]+)?)점"
        val explicit = Regex(prefix).find(raw)
        if (explicit == null) return null
        val url = record.optString("sourcePage")
        val safeSource = runCatching {
            val u = URI(url); val h = u.host.orEmpty().lowercase()
            if (u.scheme != "https" || !(h == "jinhak.com" || h.endsWith(".jinhak.com"))) null else "https://$h${u.path}"
        }.getOrNull() ?: return null
        val at = record.optString("observedAt")
        if (runCatching { Instant.parse(at) }.isFailure || record.optString("sourceRowFingerprint").isBlank()) return null
        val original = record.optJSONObject("metrics") ?: return null
        if (original.optInt("metricSemanticsVersion") != 3) return null
        val metrics = JSONObject()
        for (key in fields) {
            if (!original.has(key) || original.isNull(key)) continue
            val n = original.optDouble(key)
            if (!n.isFinite() || n < 0) continue
            if (key.contains("Grade") && n !in 1.0..9.0) continue
            if (key in listOf("stabilityBars", "capacity") && n % 1.0 != 0.0) continue
            metrics.put(key, n)
        }
        if (explicit != null) {
            val literal = mapOf("stabilityBars" to explicit.groupValues[1].toDouble(), "capacity" to explicit.groupValues[2].toDouble(), "myCalculatedScore" to explicit.groupValues[3].toDouble())
            for ((key, n) in literal) { if (metrics.has(key) && metrics.optDouble(key) != n) return null; metrics.put(key, n) }
            val tail = raw.substring(explicit.range.last + 1)
            val ownGrade = Regex("^ \\((?:반영교과|전교과) ([0-9]+(?:\\.[0-9]+)?)등급\\)").find(tail)?.groupValues?.get(1)?.toDoubleOrNull()
            if (ownGrade != null && ownGrade in 1.0..9.0) {
                if (metrics.has("myReflectedGrade") && metrics.optDouble("myReflectedGrade") != ownGrade) return null
                metrics.put("myReflectedGrade", ownGrade)
            }
        }
        if (metrics.length() == 0) return null
        return metrics.put("sourceUrl", safeSource).put("sourceRowFingerprint", record.optString("sourceRowFingerprint"))
            .put("observedAt", at).put("applicationIdentityKey", candidate.optString("applicationIdentityKey"))
            .put("academicYear", candidate.optInt("academicYear")).put("bindingMethod", if (explicit != null) "same-card-literal-prefix-reverified" else "same-card-application-grammar")
            .put("probabilityInferred", false).put("officialConversionVerified", false)
    }
    fun label(prediction: JSONObject?): String {
        if (prediction == null) return "진학사 예측: 미확인"
        if (!prediction.optBoolean("structured")) return "진학사 예측: 수집됨 · 값 구조화 대기"
        val m = prediction.optJSONObject("metrics") ?: JSONObject()
        val values = mutableListOf<String>()
        if (m.has("stabilityBars")) values += "${m.optInt("stabilityBars")}칸"
        if (m.has("myCalculatedScore")) values += "내 점수 ${m.optDouble("myCalculatedScore") }"
        if (m.has("myReflectedGrade")) values += "반영등급 ${m.optDouble("myReflectedGrade") }"
        return "진학사: ${values.joinToString(" · ").ifBlank { "같은 카드 수치 확인" }}"
    }
}
