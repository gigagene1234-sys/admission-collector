package com.admissionhub.collector.parser

import org.json.JSONArray
import org.json.JSONObject

object RecordUtils {
    fun dedupe(input: JSONArray): JSONArray {
        val out = JSONArray()
        val seen = linkedSetOf<String>()
        for (i in 0 until input.length()) {
            val obj = input.optJSONObject(i) ?: continue
            if (seen.add(key(obj))) out.put(obj)
        }
        return out
    }

    fun appendUniqueRecords(target: JSONArray, incoming: JSONArray) {
        val existing = linkedSetOf<String>()
        for (i in 0 until target.length()) {
            val obj = target.optJSONObject(i) ?: continue
            existing.add(key(obj))
        }
        for (i in 0 until incoming.length()) {
            val obj = incoming.optJSONObject(i) ?: continue
            if (existing.add(key(obj))) target.put(obj)
        }
    }

    private fun key(o: JSONObject): String = listOf(
        o.optString("recordType"),
        o.opt("year")?.toString() ?: "",
        o.opt("university")?.toString() ?: "",
        o.opt("department")?.toString() ?: "",
        o.opt("admission")?.toString() ?: "",
        o.optJSONObject("metrics")?.toString() ?: "",
        o.optString("rawEvidence").take(300)
    ).joinToString("|")

    fun appendUniqueResources(target: JSONArray, incoming: JSONArray) {
        val seen = linkedSetOf<String>()
        for (i in 0 until target.length()) {
            seen.add(target.optJSONObject(i)?.optString("url") ?: "")
        }
        for (i in 0 until incoming.length()) {
            val obj = incoming.optJSONObject(i) ?: continue
            val url = obj.optString("url")
            if (url.isNotBlank() && seen.add(url)) target.put(obj)
        }
    }
}
