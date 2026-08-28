package com.admissionhub.collector.provider

object ProviderRegistry {
    fun adapter(id: ProviderId): ProviderAdapter = when (id) {
        ProviderId.ADIGA -> AdigaAdapter
        ProviderId.JINHAK -> JinhakAdapter
    }
}
