package com.admissionhub.collector.canonical

enum class CanonicalEntityType {
    UNIVERSITY,
    CAMPUS,
    RECRUITMENT_UNIT,
    ADMISSION_TRACK
}

data class CanonicalEntity(
    val canonicalId: String,
    val entityType: CanonicalEntityType,
    val academicYear: Int?,
    val canonicalName: String,
    val parentCanonicalId: String? = null
)

data class ProviderEntityMapping(
    val provider: String,
    val providerEntityType: String,
    val providerEntityId: String,
    val academicYear: Int?,
    val canonicalEntityId: String,
    val rawLabel: String?,
    val confidence: Double,
    val evidenceObservationId: String?
)

object CanonicalSemantics {
    const val OFFICIAL_CURRENT_ADMISSION = "official-current-admission"
    const val OFFICIAL_HISTORICAL_RESULT = "official-historical-result"
    const val PROVIDER_PUBLIC_REFERENCE = "provider-public-reference"
    const val JINHAK_CURRENT_PREDICTION = "jinhak-current-prediction"
    const val JINHAK_PROVIDER_HISTORICAL_CASE = "jinhak-provider-historical-case"
    const val USER_CALCULATED_SCORE = "user-calculated-score"
    const val HUB_DERIVED_ANALYSIS = "hub-derived-analysis"
}
