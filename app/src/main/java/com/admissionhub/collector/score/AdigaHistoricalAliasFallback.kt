package com.admissionhub.collector.score

import com.admissionhub.collector.canonical.AdigaHistoricalOutcomeExtractor
import com.admissionhub.collector.canonical.CanonicalSixApplicationGraph
import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/**
 * Bounded fallback for official Adiga historical tables whose published historical admission name
 * differs from the current candidate label. Every fallback still requires the same university,
 * same/suffix-equivalent recruitment unit, an explicit historical table scope, and verified headers.
 */
object AdigaHistoricalAliasFallback {
    const val SCHEMA_VERSION = 1

    fun materialize(store: LocalCollectorStore, sessionId: String, candidates: List<JSONObject>): JSONObject {
        val runId = store.providerRunIdForUnifiedSession(sessionId, "adiga")
            ?: return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("stored", 0).put("error", "missing-adiga-run")
        val knutAliasVerified = verifyKnutNameTransition(store, runId)
        var recordsScanned = 0
        var aliasTablesMatched = 0
        var rowsMatched = 0
        var stored = 0
        val perIdentity = JSONObject()

        store.readableDatabase.rawQuery(
            "SELECT year,university,json FROM records WHERE run_id=? AND provider='adiga' AND record_type='historical-admission-result-table' ORDER BY year DESC,updated_at",
            arrayOf(runId)
        ).use { cursor ->
            while (cursor.moveToNext()) {
                recordsScanned++
                val recordYear = if (cursor.isNull(0)) 0 else cursor.getInt(0)
                val university = if (cursor.isNull(1)) "" else cursor.getString(1)
                val universityKey = CanonicalSixApplicationGraph.normalizeUniversityKey(university)
                val record = runCatching { JSONObject(cursor.getString(2)) }.getOrNull() ?: continue
                val metrics = record.optJSONObject("metrics") ?: continue
                val rowsJson = metrics.optJSONArray("rows") ?: continue
                val rows = (0 until rowsJson.length()).map { ri ->
                    val row = rowsJson.optJSONArray(ri) ?: JSONArray()
                    (0 until row.length()).map { row.optString(it).trim() }
                }
                if (rows.size < 3) continue

                for (candidate in candidates) {
                    val identity = candidate.optString("applicationIdentityKey")
                    if (identity.isBlank()) continue
                    if (CanonicalSixApplicationGraph.normalizeUniversityKey(candidate.optString("university")) != universityKey) continue
                    if (recordYear !in 2000 until candidate.optInt("academicYear", 0)) continue

                    val scopeIndex = rows.indices.firstOrNull { ri ->
                        aliasAdmissionMatch(candidate, rows[ri], recordYear, knutAliasVerified)
                    } ?: continue
                    if (!hasHistoricalMetricHeaders(rows)) continue
                    aliasTablesMatched++
                    val departmentIndex = ((scopeIndex + 1) until rows.size).firstOrNull { ri ->
                        if (ri != scopeIndex + 1 && isNewExplicitScope(rows[ri])) return@firstOrNull false
                        safeDepartmentMatch(candidate.optString("department"), rows[ri])
                    } ?: continue
                    rowsMatched++

                    val outcome = AdigaHistoricalOutcomeExtractor.extract(rows, scopeIndex, departmentIndex, metrics, recordYear) ?: continue
                    if (!outcome.optBoolean("headersVerified", false)) continue
                    val sourceUrl = record.optString("sourcePage").takeIf { it.isNotBlank() }
                    val detail = JSONObject()
                        .put("source", "ADIGA_OFFICIAL_HISTORICAL_ALIAS_FALLBACK")
                        .put("aliasPolicy", aliasPolicy(candidate, rows[scopeIndex], recordYear, knutAliasVerified))
                        .put("scopeRow", JSONArray(rows[scopeIndex]))
                        .put("departmentRow", JSONArray(rows[departmentIndex]))
                        .put("headersVerified", true)
                        .put("bindingInferred", false)
                        .put("probabilityInferred", false)

                    fun save(metricName: String, key: String, scale: String, max: Double?) {
                        val value = numeric(outcome, key) ?: return
                        val id = store.storeOfficialAdmissionOutcome(
                            applicationIdentityKey = identity,
                            academicYear = outcome.optInt("historicalResultYear", recordYear),
                            metricName = metricName,
                            metricValue = value,
                            scoreScale = scale,
                            maxScore = max,
                            sourceName = "어디가 공식 과거 입결 · 검증된 전형명 별칭 결합",
                            sourceUrl = sourceUrl,
                            verified = true,
                            primaryReference = false,
                            detail = JSONObject(detail.toString()).put("metricKey", key)
                        )
                        if (id != null) stored++
                    }
                    val resultYear = outcome.optInt("historicalResultYear", recordYear)
                    val convertedMax = numeric(outcome, "convertedMax")
                    save("최종등록자 50% cut 대학별환산점수", "converted50", "어디가 $resultYear 대학별환산 총점", convertedMax)
                    save("최종등록자 70% cut 대학별환산점수", "converted70", "어디가 $resultYear 대학별환산 총점", convertedMax)
                    save("최종등록자 50% 학생부등급", "grade50", "어디가 $resultYear 최종등록자 학생부등급", 9.0)
                    save("최종등록자 70% 학생부등급", "grade70", "어디가 $resultYear 최종등록자 학생부등급", 9.0)
                    perIdentity.put(identity, JSONObject()
                        .put("matched", true).put("recordYear", resultYear)
                        .put("aliasPolicy", aliasPolicy(candidate, rows[scopeIndex], recordYear, knutAliasVerified))
                        .put("numericMetricsStored", listOf("converted50","converted70","grade50","grade70").count { numeric(outcome, it) != null }))
                }
            }
        }
        return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("recordsScanned", recordsScanned)
            .put("aliasTablesMatched", aliasTablesMatched).put("departmentRowsMatched", rowsMatched).put("stored", stored)
            .put("knutHistoricalNameTransitionVerified", knutAliasVerified).put("byIdentity", perIdentity)
            .put("networkUsed", false).put("slotsMutated", false).put("probabilityInferred", false)
    }

    private fun aliasAdmissionMatch(candidate: JSONObject, row: List<String>, recordYear: Int, knutAliasVerified: Boolean): Boolean {
        val u = normalize(candidate.optString("university")); val a = normalize(candidate.optString("admission")); val rowText = normalize(row.joinToString(" "))
        return when {
            "한밭" in u && "교과일반" in a -> rowText.contains("학생부교과일반전형") || rowText.contains("교과일반전형")
            "한밭" in u && "지역인재교과" in a -> rowText.contains("지역인재교과전형")
            "한국교통" in u && "학생부종합2" in a && recordYear <= 2025 && knutAliasVerified -> rowText.contains("나비인재전형2") || rowText.contains("나비인재2")
            "충남" in u && "교과일반" in a -> rowText == "모집단위일반전형" || rowText == "일반전형"
            else -> false
        }
    }

    private fun aliasPolicy(candidate: JSONObject, row: List<String>, recordYear: Int, knutAliasVerified: Boolean): String {
        val u = normalize(candidate.optString("university")); val a = normalize(candidate.optString("admission"))
        return when {
            "한밭" in u && "교과일반" in a -> "한밭:교과일반↔학생부교과(일반)전형"
            "한밭" in u && "지역인재교과" in a -> "한밭:지역인재교과↔지역인재(교과)전형"
            "한국교통" in u && "학생부종합2" in a && recordYear <= 2025 && knutAliasVerified -> "한국교통:공식명칭변경근거-나비인재Ⅱ↔학생부종합Ⅱ"
            "충남" in u && "교과일반" in a -> "충남:교과일반↔일반전형(교과결과표)"
            else -> "unsupported"
        }
    }

    private fun safeDepartmentMatch(targetRaw: String, row: List<String>): Boolean {
        val target = normalizeDepartment(targetRaw)
        if (target.isBlank()) return false
        return row.any { cell ->
            val value = normalizeDepartment(cell)
            value == target || value == target + "학과" || value == target + "학부" || value == target + "전공" ||
                target == value + "학과" || target == value + "학부" || target == value + "전공"
        }
    }

    private fun normalizeDepartment(raw: String): String {
        var n = normalize(raw)
        // Official tables sometimes append the architecture program length: 건축학과(5).
        n = n.replace(Regex("(학과|학부|전공)[0-9]+$"), "$1")
        return n
    }

    private fun hasHistoricalMetricHeaders(rows: List<List<String>>): Boolean {
        val first = rows.take(6).joinToString(" ") { it.joinToString(" ") }
        val n = normalize(first)
        return ("50cut" in n || "70cut" in n || "50" in n || "70" in n) &&
            ("학생부등급" in n || "교과성적" in n || "대학별환산" in n)
    }

    private fun isNewExplicitScope(row: List<String>): Boolean {
        val first = normalize(row.firstOrNull().orEmpty())
        return first in setOf("모집단위", "해당전형", "전형명", "모집전형")
    }

    private fun verifyKnutNameTransition(store: LocalCollectorStore, runId: String): Boolean {
        store.readableDatabase.rawQuery(
            "SELECT json FROM records WHERE run_id=? AND provider='adiga' AND record_type='current-admission-criteria-table' AND university LIKE '%한국교통%'",
            arrayOf(runId)
        ).use { cursor ->
            var hasNew = false; var hasOld = false
            while (cursor.moveToNext()) {
                val text = normalize(cursor.getString(0))
                if ("학생부종합2" in text) hasNew = true
                if ("나비인재2" in text) hasOld = true
                if (hasNew && hasOld) return true
            }
        }
        return false
    }

    private fun numeric(obj: JSONObject, key: String): Double? {
        if (!obj.has(key) || obj.isNull(key)) return null
        return obj.optDouble(key).takeIf { it.isFinite() }
    }

    private fun normalize(raw: String?): String = raw.orEmpty().trim().lowercase(Locale.ROOT)
        .replace("Ⅰ", "1").replace("Ⅱ", "2")
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\):]"), "")
        .replace(Regex("[^0-9a-z가-힣]"), "")
}
