package com.admissionhub.collector.score

import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONObject
import java.util.Locale

/**
 * Exact, frozen official-university fallback for cases where Adiga has the current formula but does
 * not expose a safely bindable historical result row. Only exact supported identities are stored.
 * Values are not predictions and never imply an admission probability.
 */
object UniversityOfficialPublishedFallback {
    const val SCHEMA_VERSION = 1

    fun materialize(store: LocalCollectorStore, candidates: List<JSONObject>): JSONObject {
        var matched = 0
        var stored = 0
        val byIdentity = JSONObject()
        for (candidate in candidates) {
            val identity = candidate.optString("applicationIdentityKey")
            if (identity.isBlank() || candidate.optInt("academicYear") != 2027) continue
            val university = normalize(candidate.optString("university"))
            val admission = normalize(candidate.optString("admission"))
            val department = normalize(candidate.optString("department"))
            val result = when {
                "우송" in university && "교과면접" in admission && departmentMatches(department, "철도차량시스템학과") -> WoosongResult(
                    sourceUrl = "https://ent2.wsu.ac.kr/pass/susi02.php",
                    sourceName = "우송대학교 입학처 공식 · 2026학년도 최종등록자 면접전형",
                    resultYear = 2026,
                    hundredCut = 4.0,
                    seventyCut = 3.5,
                    average = 3.3
                )
                "우송" in university && "교과중심" in admission && departmentMatches(department, "철도자율전공학부") -> WoosongResult(
                    sourceUrl = "https://ent2.wsu.ac.kr/pass/susi01.php",
                    sourceName = "우송대학교 입학처 공식 · 2026학년도 최종등록자 교과중심",
                    resultYear = 2026,
                    hundredCut = 4.6,
                    seventyCut = null,
                    average = 4.1
                )
                else -> null
            } ?: continue
            matched++
            val detail = JSONObject()
                .put("source", "UNIVERSITY_OFFICIAL_PUBLISHED_RESULT")
                .put("publisher", "우송대학교 입학처")
                .put("resultYear", result.resultYear)
                .put("identityExact", true)
                .put("department", candidate.optString("department"))
                .put("admission", candidate.optString("admission"))
                .put("missingPublishedMetricPreservedAsNull", true)
                .put("bindingInferred", false)
                .put("probabilityInferred", false)
            fun save(name: String, value: Double?) {
                if (value == null) return
                val id = store.storeOfficialAdmissionOutcome(
                    applicationIdentityKey = identity,
                    academicYear = result.resultYear,
                    metricName = name,
                    metricValue = value,
                    scoreScale = "우송대 ${result.resultYear} 최종등록자 학생부등급",
                    maxScore = 9.0,
                    sourceName = result.sourceName,
                    sourceUrl = result.sourceUrl,
                    verified = true,
                    primaryReference = false,
                    detail = JSONObject(detail.toString()).put("metricName", name)
                )
                if (id != null) stored++
            }
            save("최종등록자 100% cut 학생부등급", result.hundredCut)
            save("최종등록자 70% 학생부등급", result.seventyCut)
            save("최종등록자 평균 학생부등급", result.average)
            byIdentity.put(identity, JSONObject()
                .put("matched", true).put("resultYear", result.resultYear)
                .put("sourceUrl", result.sourceUrl).put("hundredCut", result.hundredCut ?: JSONObject.NULL)
                .put("seventyCut", result.seventyCut ?: JSONObject.NULL).put("average", result.average))
        }
        return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("matched", matched).put("stored", stored)
            .put("byIdentity", byIdentity).put("networkUsedAtRuntime", false).put("frozenOfficialSnapshot", true)
            .put("slotsMutated", false).put("probabilityInferred", false)
    }

    private data class WoosongResult(
        val sourceUrl: String,
        val sourceName: String,
        val resultYear: Int,
        val hundredCut: Double,
        val seventyCut: Double?,
        val average: Double
    )

    private fun departmentMatches(candidate: String, official: String): Boolean {
        val o = normalize(official)
        return candidate == o || candidate + "학과" == o || candidate + "학부" == o || candidate + "전공" == o ||
            o + "학과" == candidate || o + "학부" == candidate || o + "전공" == candidate
    }

    private fun normalize(raw: String?): String = raw.orEmpty().trim().lowercase(Locale.ROOT)
        .replace("Ⅰ", "1").replace("Ⅱ", "2")
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\):]"), "")
        .replace(Regex("[^0-9a-z가-힣]"), "")
}
