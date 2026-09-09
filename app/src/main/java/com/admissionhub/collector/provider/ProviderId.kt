package com.admissionhub.collector.provider

enum class ProviderId(
    val wireName: String,
    val displayName: String,
    val homeUrl: String
) {
    ADIGA("adiga", "어디가", "https://www.adiga.kr/"),
    // v0.17.4 fail-safe default: every legacy Jinhak home/fallback navigation resolves to a
    // high3-only entry instead of the shared root, so old call sites cannot reopen product routing.
    JINHAK("jinhak", "진학사", "https://www.jinhak.com/jh/high3/early/four-year-university/search")
}
