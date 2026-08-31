package com.admissionhub.collector.jinhak

import com.admissionhub.collector.parser.GenericAdmissionParser
import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/**
 * Converts a rendered Jinhak strategy article into evidence-backed strategy metadata.
 * It does not invent a recommendation. The Hub can later combine these explicit signals
 * with a target application while preserving the article evidence and observed time.
 */
object JinhakStrategyAnalyzer {
    private val universityRegex = Regex("([가-힣A-Za-z0-9·.&()\\-]{2,45}(?:대학교|교육대학교|과학기술원)(?:\\([^)]+\\))?)")

    fun normalize(snapshot: JSONObject, observedAt: String = Instant.now().toString()): JSONArray {
        val title = snapshot.optString("title").replace(Regex("\\s+"), " ").trim().take(500)
        val text = GenericAdmissionParser.collectText(snapshot).replace(Regex("\\s+"), " ").trim()
        if (title.isBlank() && text.isBlank()) return JSONArray()

        val topics = linkedSetOf<String>()
        fun topic(name: String, rx: Regex) { if (rx.containsMatchIn("$title $text")) topics.add(name) }
        topic("admission-result-interpretation", Regex("(입시결과|입결|70%\\s*컷|50%\\s*컷|합격선)"))
        topic("competition", Regex("(경쟁률|실질\\s*경쟁률|충원|추가합격)"))
        topic("student-record", Regex("(학생부|내신|교과성적|석차등급)"))
        topic("holistic", Regex("(학생부종합|학종|서류|정성평가|학업역량|진로역량)"))
        topic("curricular", Regex("(학생부교과|교과전형|교과우수|지역인재)"))
        topic("minimum", Regex("(수능최저|최저학력기준)"))
        topic("interview", Regex("(면접|서류면접|면접평가)"))
        topic("school-type", Regex("(일반고|자사고|특목고|고교유형)"))
        topic("support-strategy", Regex("(상향|적정|안정|소신|지원전략|6장|지원\\s*조합)"))
        topic("mock-support", Regex("(모의지원|지원자\\s*분포|지원경향)"))

        val mentionedUniversities = linkedSetOf<String>()
        universityRegex.findAll("$title $text").take(24).forEach { m ->
            m.groupValues.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() }?.let { mentionedUniversities.add(it) }
        }

        val admissionTypes = linkedSetOf<String>()
        val typeSignals = listOf(
            "학생부교과" to Regex("(학생부교과|교과전형)"),
            "학생부종합" to Regex("(학생부종합|학종)"),
            "지역인재" to Regex("지역인재"),
            "면접" to Regex("면접"),
            "논술" to Regex("논술"),
            "실기" to Regex("실기")
        )
        for ((label, rx) in typeSignals) if (rx.containsMatchIn("$title $text")) admissionTypes.add(label)

        val evidence = JSONArray()
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        val relevance = Regex("(입결|입시결과|70%\\s*컷|50%\\s*컷|경쟁률|충원|수능최저|학생부교과|학생부종합|학종|면접|모의지원|지원전략|합격선|일반고|자사고)")
        for (i in 0 until minOf(blocks.length(), 160)) {
            val block = blocks.optString(i).replace(Regex("\\s+"), " ").trim()
            if (block.length < 20 || !relevance.containsMatchIn(block)) continue
            evidence.put(block.take(1800))
            if (evidence.length() >= 18) break
        }

        val metrics = JSONObject()
            .put("topics", JSONArray(topics.toList()))
            .put("mentionedUniversities", JSONArray(mentionedUniversities.toList()))
            .put("mentionedAdmissionTypes", JSONArray(admissionTypes.toList()))
            .put("evidenceBlocks", evidence)
            .put("evidenceBlockCount", evidence.length())
            .put("hasAdmissionResultInterpretation", topics.contains("admission-result-interpretation"))
            .put("hasCompetitionInterpretation", topics.contains("competition"))
            .put("hasMinimumRequirementDiscussion", topics.contains("minimum"))

        val record = JSONObject()
            .put("recordType", "jinhak-strategy-insight")
            .put("providerPageType", "jinhak-admission-strategy")
            .put("dataScope", "strategy-reference")
            .put("year", inferYear("$title $text") ?: JSONObject.NULL)
            .put("university", if (mentionedUniversities.size == 1) mentionedUniversities.first() else JSONObject.NULL)
            .put("department", JSONObject.NULL)
            .put("admission", if (admissionTypes.size == 1) admissionTypes.first() else JSONObject.NULL)
            .put("metrics", metrics)
            .put("observedAt", observedAt)
            .put("confidence", if (topics.isNotEmpty() && evidence.length() > 0) "medium" else "raw")
            .put("sourcePage", safePath(snapshot.optString("url")))
            .put("rawEvidence", title)
        record.put("sourceRowFingerprint", RecordUtils.sha256(listOf(
            record.optString("sourcePage"), title, metrics.toString()
        ).joinToString("|")))
        return JSONArray().put(record)
    }

    private fun inferYear(text: String): Int? = Regex("(20[0-9]{2})\\s*학년도").find(text)?.groupValues?.getOrNull(1)?.toIntOrNull()
        ?: Regex("(?<![0-9])(20[0-9]{2})(?![0-9])").find(text)?.groupValues?.getOrNull(1)?.toIntOrNull()

    private fun safePath(url: String): String = try {
        val u = java.net.URI(url)
        val host = u.host.orEmpty().lowercase()
        val path = u.path.orEmpty().ifBlank { "/" }
        if (host.isBlank()) path.take(500) else "$host$path".take(500)
    } catch (_: Exception) { url.substringBefore('?').substringBefore('#').take(500) }
}
