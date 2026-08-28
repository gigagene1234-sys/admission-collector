package com.admissionhub.collector.provider

enum class ProviderId(
    val wireName: String,
    val displayName: String,
    val homeUrl: String
) {
    ADIGA("adiga", "어디가", "https://www.adiga.kr/"),
    JINHAK("jinhak", "진학사", "https://www.jinhak.com/")
}
