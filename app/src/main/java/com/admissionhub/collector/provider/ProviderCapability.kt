package com.admissionhub.collector.provider

enum class ProviderCapability {
    PUBLIC_DETERMINISTIC_COLLECTION,
    AUTHENTICATED_USER_WORKFLOW,
    AUTHORIZED_API_SYNC,
    AUTHORIZED_EXPORT_IMPORT,
    AUTHORIZED_REPORT_IMPORT,
    USER_VIEW_CAPTURE_FALLBACK
}

data class ProviderCapabilityProfile(
    val active: Set<ProviderCapability>,
    val discoverable: Set<ProviderCapability> = emptySet()
) {
    fun has(capability: ProviderCapability): Boolean = capability in active
    fun mayDiscover(capability: ProviderCapability): Boolean = capability in discoverable
}

object ProviderCapabilities {
    fun profile(provider: ProviderId): ProviderCapabilityProfile = when (provider) {
        ProviderId.ADIGA -> ProviderCapabilityProfile(
            active = setOf(
                ProviderCapability.PUBLIC_DETERMINISTIC_COLLECTION,
                ProviderCapability.AUTHENTICATED_USER_WORKFLOW
            )
        )
        ProviderId.JINHAK -> ProviderCapabilityProfile(
            active = setOf(
                ProviderCapability.AUTHENTICATED_USER_WORKFLOW,
                ProviderCapability.USER_VIEW_CAPTURE_FALLBACK
            ),
            discoverable = setOf(
                ProviderCapability.AUTHORIZED_API_SYNC,
                ProviderCapability.AUTHORIZED_EXPORT_IMPORT,
                ProviderCapability.AUTHORIZED_REPORT_IMPORT
            )
        )
    }
}
