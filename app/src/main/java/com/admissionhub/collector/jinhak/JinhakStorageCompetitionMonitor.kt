package com.admissionhub.collector.jinhak

import org.json.JSONObject
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Strict same-card parser for the competition value shown in the Jinhak early-admission storage.
 * A generic unlabeled `경쟁률` is deliberately NOT promoted to the current application ratio when
 * historical/mock context could be confused with it. Current ratio may be derived only from an
 * explicitly current applicant count and an explicitly labelled capacity on the same card.
 */
object JinhakStorageCompetitionMonitor {
    const val SCHEMA_VERSION = 1

    data class Metric(
        val currentApplicationCompetition: Double?,
        val currentSource: String?,
        val ambiguousGenericCompetition: Double?,
        val previousYearCompetition: Double?,
        val mockCompetition: Double?,
        val currentApplicants: Int?,
        val capacity: Int?,
        val derivedFromExplicitCounts: Boolean
    ) {
        val hasCurrent: Boolean get() = currentApplicationCompetition != null
        val hasAmbiguity: Boolean get() = ambiguousGenericCompetition != null && currentApplicationCompetition == null

        fun toJson(): JSONObject = JSONObject()
            .put("competitionSemanticsVersion", SCHEMA_VERSION)
            .put("currentApplicationCompetition", currentApplicationCompetition ?: JSONObject.NULL)
            .put("currentApplicationCompetitionSource", currentSource ?: JSONObject.NULL)
            .put("currentApplicationCompetitionAmbiguous", hasAmbiguity)
            .put("genericCompetitionUnresolved", ambiguousGenericCompetition ?: JSONObject.NULL)
            .put("previousYearCompetition", previousYearCompetition ?: JSONObject.NULL)
            .put("mockCompetition", mockCompetition ?: JSONObject.NULL)
            .put("currentApplicants", currentApplicants ?: JSONObject.NULL)
            .put("capacity", capacity ?: JSONObject.NULL)
            .put("derivedFromExplicitCounts", derivedFromExplicitCounts)
            .put("sourceClass", "jinhak-user-viewed-storage")
            .put("official", false)
    }

    private val explicitCurrentRatio = Regex(
        """(?:실시간|현재|원서\s*접수|원서접수|수시\s*원서|접수\s*현황)\s*(?:수시\s*)?경쟁률\s*[:：]?\s*([0-9]{1,4}(?:\.[0-9]+)?)(?:\s*(?::|대)\s*1)?""",
        RegexOption.IGNORE_CASE
    )
    private val previousRatio = Regex(
        """(?:전년도|지난해|작년)(?:\s*수시)?\s*경쟁률\s*[:：]?\s*([0-9]{1,4}(?:\.[0-9]+)?)(?:\s*(?::|대)\s*1)?"""
    )
    private val mockRatio = Regex(
        """(?:실시간\s*수시\s*)?모의\s*지원\s*경쟁률\s*[:：]?\s*([0-9]{1,4}(?:\.[0-9]+)?)(?:\s*(?::|대)\s*1)?"""
    )
    private val anyCompetition = Regex(
        """(?<!전년도\s)(?<!지난해\s)(?<!작년\s)(?<!모의지원\s)(?<!모의\s지원\s)경쟁률\s*[:：]?\s*([0-9]{1,4}(?:\.[0-9]+)?)(?:\s*(?::|대)\s*1)?"""
    )
    private val explicitCurrentApplicants = Regex(
        """(?:현재|실시간|원서\s*접수|접수\s*현황)\s*(?:지원자\s*수|지원자수|지원\s*인원|지원인원)\s*[:：]?\s*([0-9,]+)"""
    )
    private val explicitCapacity = Regex(
        """(?:모집\s*인원|모집인원|선발\s*인원|선발인원)\s*[:：]?\s*([0-9,]+)"""
    )

    fun extract(rawText: String): Metric {
        val text = rawText.replace(Regex("""\s+"""), " ").trim().take(8000)
        val previous = previousRatio.find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
        val mock = mockRatio.find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
        val explicit = explicitCurrentRatio.find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
        val applicants = explicitCurrentApplicants.find(text)?.groupValues?.getOrNull(1)
            ?.replace(",", "")?.toIntOrNull()
        val capacity = explicitCapacity.find(text)?.groupValues?.getOrNull(1)
            ?.replace(",", "")?.toIntOrNull()

        var current = explicit
        var source: String? = if (explicit != null) "explicit-current-competition-label" else null
        var derived = false
        if (current == null && applicants != null && capacity != null && applicants >= 0 && capacity > 0) {
            current = BigDecimal(applicants).divide(BigDecimal(capacity), 4, RoundingMode.HALF_UP).toDouble()
            source = "derived-explicit-current-applicants-and-capacity"
            derived = true
        }

        val generic = if (current == null) {
            anyCompetition.findAll(text)
                .mapNotNull { it.groupValues.getOrNull(1)?.toDoubleOrNull() }
                .firstOrNull { value -> value != previous && value != mock }
        } else null

        return Metric(
            currentApplicationCompetition = current,
            currentSource = source,
            ambiguousGenericCompetition = generic,
            previousYearCompetition = previous,
            mockCompetition = mock,
            currentApplicants = applicants,
            capacity = capacity,
            derivedFromExplicitCounts = derived
        )
    }
}
