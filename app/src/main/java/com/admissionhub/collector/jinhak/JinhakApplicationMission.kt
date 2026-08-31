package com.admissionhub.collector.jinhak

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONObject

/**
 * Application-centric identity and metric parser for the authenticated Jinhak workflow.
 *
 * Safety invariant: a department is never inferred from a neighbouring card or page-wide text.
 * We accept a raw recruitment-unit label without a normal 학과/학부 suffix only when it is
 * structurally bounded inside the SAME prediction card by admission/campus context and the
 * card's capacity marker ("N명 내 점수"). Canonical official names are resolved later against
 * Adiga/provider mappings; the raw Jinhak label is never silently expanded.
 */
object JinhakApplicationMission {
    const val SEMANTICS_VERSION = 2

    data class Context(
        val year: Int = 2027,
        val university: String?,
        val admissionCategory: String?,
        val admission: String?,
        val campus: String?,
        val departmentRaw: String?,
        val capacity: Int?,
        val identityKey: String?,
        val parseSource: String,
        val confidence: String,
        val rawCombinedLabel: String?
    ) {
        fun toJson(): JSONObject = JSONObject()
            .put("year", year)
            .put("university", university ?: JSONObject.NULL)
            .put("admissionCategory", admissionCategory ?: JSONObject.NULL)
            .put("admission", admission ?: JSONObject.NULL)
            .put("campus", campus ?: JSONObject.NULL)
            .put("departmentRaw", departmentRaw ?: JSONObject.NULL)
            .put("capacity", capacity ?: JSONObject.NULL)
            .put("identityKey", identityKey ?: JSONObject.NULL)
            .put("parseSource", parseSource)
            .put("confidence", confidence)
            .put("rawCombinedLabel", rawCombinedLabel ?: JSONObject.NULL)
    }

    fun fromJson(obj: JSONObject?): Context? {
        obj ?: return null
        val university = obj.optString("university").takeIf { it.isNotBlank() && it != "null" }
        val admissionCategory = obj.optString("admissionCategory").takeIf { it.isNotBlank() && it != "null" }
        val admission = obj.optString("admission").takeIf { it.isNotBlank() && it != "null" }
        val campus = obj.optString("campus").takeIf { it.isNotBlank() && it != "null" }
        val department = obj.optString("departmentRaw").takeIf { it.isNotBlank() && it != "null" }
        val identityKey = obj.optString("identityKey").takeIf { it.isNotBlank() && it != "null" }
        val capacity = if (obj.has("capacity") && !obj.isNull("capacity")) obj.optInt("capacity").takeIf { it >= 0 } else null
        if (university == null && department == null && admission == null && identityKey == null) return null
        return Context(
            year = obj.optInt("year", 2027),
            university = university,
            admissionCategory = admissionCategory,
            admission = admission,
            campus = campus,
            departmentRaw = department,
            capacity = capacity,
            identityKey = identityKey,
            parseSource = obj.optString("parseSource", "mission-json").ifBlank { "mission-json" },
            confidence = obj.optString("confidence", "medium").ifBlank { "medium" },
            rawCombinedLabel = obj.optString("rawCombinedLabel").takeIf { it.isNotBlank() && it != "null" }
        )
    }

    private val universityPrefix = Regex(
        """^(?:[0-9]{1,2}\s*칸\s*)?([가-힣A-Za-z0-9·.&+()\-]{2,45}?(?:대학교|교육대학교|과학기술원|대(?:\([^)]+\))?))(?=\s*\[)"""
    )
    private val category = Regex("""^\s*\[([^\]]{1,24})\]\s*""")
    private val campus = Regex("""^\s*\[([^\]]{1,30})\]\s*""")
    private val capacityBoundary = Regex("""([0-9,]+)\s*명\s*(?:\||\s)*내\s*점수""")

    // Longest/most specific tokens first. This list identifies an admission boundary only;
    // unmatched text is kept as raw evidence rather than force-split.
    private val admissionAtStart = Regex(
        """^(학생부종합Ⅱ|학생부종합Ⅰ|학생부종합II|학생부종합I|지역인재기회균형대상자|창의인재\(면접형\)|학교장추천인재|지역인재교과|지역인재종합|학생부교과|학생부종합|교과성적우수자|교과우수|교과일반|교과중심|교과면접|자기추천|학교장추천|고른기회|기회균형|사회통합|지역인재|일반전형|일반)"""
    )

    fun parseCard(
        rawText: String,
        explicitUniversity: String? = null,
        explicitDepartment: String? = null
    ): Context? {
        val text = rawText.replace(Regex("""\s+"""), " ").trim().take(6000)
        if (text.isBlank()) return null

        val capacityMatch = capacityBoundary.find(text)
        val capacity = capacityMatch?.groupValues?.getOrNull(1)?.replace(",", "")?.toIntOrNull()
        val boundaryEnd = capacityMatch?.range?.first

        var university = cleanUniversity(explicitUniversity)
        var workingStart = 0
        val uniMatch = universityPrefix.find(text)
        if (uniMatch != null) {
            university = cleanUniversity(uniMatch.groupValues.getOrNull(1)) ?: university
            workingStart = uniMatch.range.last + 1
        }

        var working = text.substring(workingStart).trim()
        val categoryMatch = category.find(working)
        val admissionCategory = categoryMatch?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() }
        if (categoryMatch != null) working = working.substring(categoryMatch.range.last + 1).trim()

        val admissionMatch = admissionAtStart.find(working)
        val admission = admissionMatch?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() }
        if (admissionMatch != null) working = working.substring(admissionMatch.range.last + 1).trim()

        val campusMatch = campus.find(working)
        val campusLabel = campusMatch?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() }
        if (campusMatch != null) working = working.substring(campusMatch.range.last + 1).trim()

        // Use the local "N명 내 점수" marker as the right boundary. Recompute in the remaining
        // text so labels such as 철도차량시스템공 are accepted without inventing "학과".
        val localCapacity = capacityBoundary.find(working)
        val boundedDepartment = localCapacity?.let { m ->
            working.substring(0, m.range.first)
                .replace(Regex("""^[|·:\-\s]+|[|·:\-\s]+$"""), "")
                .trim()
                .takeIf { validRawDepartment(it) }
        }
        val explicit = cleanDepartment(explicitDepartment)
        val department = boundedDepartment ?: explicit
        val parseSource = when {
            boundedDepartment != null -> "same-card-admission-capacity-boundary"
            explicit != null -> "same-card-explicit-department"
            else -> "identity-partial"
        }

        val rawCombined = if (capacityMatch != null && boundaryEnd != null) {
            text.substring(workingStart, boundaryEnd).trim().take(500)
        } else null

        val key = if (university != null && department != null) {
            RecordUtils.sha256(listOf(yearToken(text), university, admission ?: "", campusLabel ?: "", department).joinToString("|"))
        } else null
        val confidence = when {
            university != null && department != null && admission != null -> "high"
            university != null && department != null -> "medium"
            university != null -> "low"
            else -> "raw"
        }

        if (university == null && department == null && admission == null && capacity == null) return null
        return Context(
            year = yearToken(text),
            university = university,
            admissionCategory = admissionCategory,
            admission = admission,
            campus = campusLabel,
            departmentRaw = department,
            capacity = capacity,
            identityKey = key,
            parseSource = parseSource,
            confidence = confidence,
            rawCombinedLabel = rawCombined
        )
    }

    fun semanticMetrics(textRaw: String): JSONObject {
        val text = textRaw.replace(Regex("""\s+"""), " ").trim()
        val out = JSONObject().put("metricSemanticsVersion", SEMANTICS_VERSION)

        number(text, Regex("""내\s*점수\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*점"""))?.let {
            out.put("myCalculatedScore", it)
            // Backward-compatible alias with explicit provenance; Hub should prefer myCalculatedScore.
            out.put("universityCalculatedScore", it)
        }
        number(text, Regex("""내\s*점수.{0,100}?(?:전교과|반영(?:평균)?등급)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*등급"""))?.let {
            out.put("myReflectedGrade", it)
        }
        number(text, Regex("""모의지원자\s*평균(?:점|점수)?\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*점?"""))?.let {
            out.put("mockApplicantAverageScore", it)
        }
        number(text, Regex("""모의지원자\s*평균.{0,120}?(?:전교과\s*)?([0-9]+(?:\.[0-9]+)?)\s*등급"""))?.let {
            out.put("mockApplicantAverageGrade", it)
        }
        number(text, Regex("""전년도(?:\s*수시)?\s*경쟁률\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)"""))?.let {
            out.put("previousYearCompetition", it)
        }
        number(text, Regex("""(?:실시간\s*수시\s*)?모의지원\s*경쟁률\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)"""))?.let {
            out.put("mockCompetition", it)
        }
        number(text, Regex("""모의지원자\s*(?:수|인원)\s*[:：]?\s*([0-9,]+)"""))?.toInt()?.let {
            out.put("mockApplicants", it)
        }
        number(text, Regex("""(?:내\s*순위|나의\s*순위|현재\s*순위)\s*[:：]?\s*([0-9,]+)"""))?.toInt()?.let {
            out.put("myRank", it)
        }
        number(text, Regex("""(?:예상\s*합격선|예상\s*컷|합격예상점수|적정지원컷)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)"""))?.let {
            out.put("predictedCut", it)
        }
        Regex("""(?<![0-9.])(?:합격안정성|칸수|칸\s*수)?\s*[:：]?\s*([0-9]{1,2})\s*칸""")
            .find(text)?.groupValues?.getOrNull(1)?.toIntOrNull()?.let { out.put("stabilityBars", it) }
        Regex("""(?:합격예측|합격가능성|지원판정|지원전략)?\s*[:：]?\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)""")
            .find(text)?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() }?.let { out.put("predictionLabel", it) }
        return out
    }

    fun laneForPageType(pageType: String): String = when (pageType) {
        "jinhak-early-storage" -> "saved-application"
        "jinhak-prediction-report" -> "current-prediction"
        "jinhak-mock-support-report" -> "mock-support"
        "jinhak-actual-admit-report" -> "actual-admit"
        "jinhak-university-admission-info" -> "university-result"
        "jinhak-score-calc-report", "jinhak-sat-minimum" -> "score-analysis"
        "jinhak-admission-strategy", "jinhak-admission-knowledge" -> "strategy"
        else -> "reference"
    }

    fun missionEvidence(context: Context, pageType: String, observedAt: String, sourcePage: String): JSONObject {
        val lane = laneForPageType(pageType)
        return JSONObject()
            .put("recordType", "jinhak-application-mission-evidence")
            .put("providerPageType", pageType)
            .put("dataScope", "application-mission-coverage")
            .put("year", context.year)
            .put("university", context.university ?: JSONObject.NULL)
            .put("department", context.departmentRaw ?: JSONObject.NULL)
            .put("admission", context.admission ?: JSONObject.NULL)
            .put("applicationIdentityKey", context.identityKey ?: JSONObject.NULL)
            .put("metrics", JSONObject()
                .put("missionLane", lane)
                .put("covered", true)
                .put("admissionCategory", context.admissionCategory ?: JSONObject.NULL)
                .put("campus", context.campus ?: JSONObject.NULL)
                .put("capacity", context.capacity ?: JSONObject.NULL)
                .put("rawDepartmentLabel", context.departmentRaw ?: JSONObject.NULL)
                .put("identityParseSource", context.parseSource)
                .put("metricSemanticsVersion", SEMANTICS_VERSION))
            .put("observedAt", observedAt)
            .put("confidence", context.confidence)
            .put("contextSource", "same-application-agent-mission")
            .put("sourcePage", sourcePage)
            .put("sourceRowFingerprint", RecordUtils.sha256(listOf(context.identityKey ?: "partial", lane, observedAt.substring(0, 16)).joinToString("|")))
    }

    private fun yearToken(text: String): Int = Regex("""(?<![0-9])(20[0-9]{2})(?:학년도)?(?![0-9])""")
        .find(text)?.groupValues?.getOrNull(1)?.toIntOrNull() ?: 2027

    private fun cleanUniversity(value: String?): String? {
        val s = value?.replace(Regex("""\s+"""), " ")?.trim()?.takeIf { it.length in 2..60 } ?: return null
        if (Regex("""(경쟁률|합격|예측|지원|전형|모집|학과|학부|전공|점수|등급)""").containsMatchIn(s)) return null
        return s
    }

    private fun cleanDepartment(value: String?): String? {
        val s = value?.replace(Regex("""\s+"""), " ")?.trim()?.takeIf { it.length in 2..120 } ?: return null
        if (Regex("""(경쟁률|합격|예측|내\s*점수|모의지원|전년도)""").containsMatchIn(s)) return null
        return s
    }

    private fun validRawDepartment(value: String): Boolean {
        if (value.length !in 2..120) return false
        if (Regex("""(경쟁률|합격|예측|내\s*점수|모의지원|전년도|지원자|평균점)""").containsMatchIn(value)) return false
        if (Regex("""^[0-9.,:%\s]+$""").matches(value)) return false
        return true
    }

    private fun number(text: String, regex: Regex): Double? = regex.find(text)?.groupValues?.getOrNull(1)
        ?.replace(",", "")?.toDoubleOrNull()
}
