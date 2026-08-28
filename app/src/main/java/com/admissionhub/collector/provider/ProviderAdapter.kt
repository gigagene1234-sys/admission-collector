package com.admissionhub.collector.provider

import org.json.JSONArray
import org.json.JSONObject

interface ProviderAdapter {
    val id: ProviderId
    val supportsBatchCrawl: Boolean

    fun accepts(url: String): Boolean
    fun seedUrls(): List<String> = emptyList()
    fun isBatchNavigable(url: String): Boolean = accepts(url)
    fun isDynamicListPage(url: String): Boolean = false
    fun classify(snapshot: JSONObject): String = "unknown"
    fun normalize(snapshot: JSONObject): JSONArray
}
