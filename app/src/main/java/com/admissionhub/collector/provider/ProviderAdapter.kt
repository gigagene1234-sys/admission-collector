package com.admissionhub.collector.provider

import org.json.JSONArray
import org.json.JSONObject

data class PaginationPlan(
    val familyKey: String,
    val totalItems: Int,
    val pageSize: Int,
    val totalPages: Int,
    val requestedYear: Int?,
    val firstPageFingerprint: String
)

interface ProviderAdapter {
    val id: ProviderId
    val supportsBatchCrawl: Boolean

    fun accepts(url: String): Boolean
    fun seedUrls(): List<String> = emptyList()
    fun isBatchNavigable(url: String): Boolean = accepts(url)
    fun isDynamicListPage(url: String): Boolean = false
    fun classify(snapshot: JSONObject): String = "unknown"
    fun normalize(snapshot: JSONObject): JSONArray

    /**
     * Provider-specific pagination plan. Returning null means the current page
     * should not be automatically paged.
     */
    fun paginationPlan(snapshot: JSONObject): PaginationPlan? = null

    /** Returns JavaScript that safely moves the current provider list to page N. */
    fun paginationScript(page: Int): String? = null
}
