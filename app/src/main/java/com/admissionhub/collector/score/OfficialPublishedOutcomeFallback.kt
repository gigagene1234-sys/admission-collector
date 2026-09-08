package com.admissionhub.collector.score

import com.admissionhub.collector.local.LocalCollectorStore
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/**
 * Small, evidence-pinned fallback registry for the user's current six applications.
 *
 * It is used only when the normal current-session Adiga table materializer has no verified official
 * outcome for an exact application identity. Values come from official university admissions pages
 * or Adiga official university result pages. Jinhak values are never promoted into this registry.
 *
 * The registry can also persist an official 'not published / no prior result' state with null metric
 * value. This is deliberately different from inventing a cut score.
 */
object OfficialPublishedOutcomeFallback {
    const val SCHEMA_VERSION = 1

    fun materializeMissing(store: LocalCollectorStore, sessionId: String, candidates: List<JSONObject>): JSONObject {
        if (sessionId.isBlank() || candidates.isEmpty()) return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION).put("matchedApplications", 0).put("storedRows", 0)

        val summary = store.scoreDecisionSummary(sessionId).optJSONObject("byIdentity") ?: JSONObject()
        var matched = 0
        var stored = 0
        val results = JSONArray()

        for (candidate in candidates) {
            val identity = candidate.optString("applicationIdentityKey").takeIf { it.isNotBlank() } ?: continue
            val existing = summary.optJSONObject(identity)?.optJSONArray("officialOutcomes") ?: JSONArray()
            val hasVerifiedNumeric = (0 until existing.length()).any { i ->
                val row = existing.optJSONObject(i)
                row != null && row.optBoolean("verified", false) && row.has("metricValue") && !row.isNull("metricValue")
            }
            if (hasVerifiedNumeric) continue

            val university = normalize(candidate.optString("university"))
            val department = normalizeDepartment(candidate.optString("department"))
            val admission = normalize(candidate.optString("admission"))
            val applied = JSONArray()

            fun save(
                year: Int, metric: String, value: Double?, scale: String?, max: Double?,
                sourceName: String, sourceUrl: String, detail: JSONObject
            ) {
                val id = store.storeOfficialAdmissionOutcome(
                    applicationIdentityKey = identity,
                    academicYear = year,
                    metricName = metric,
                    metricValue = value,
                    scoreScale = scale,
                    maxScore = max,
                    sourceName = sourceName,
                    sourceUrl = sourceUrl,
                    verified = true,
                    primaryReference = false,
                    detail = JSONObject(detail.toString())
                        .put("sourceClass", "OFFICIAL_PUBLISHED_FALLBACK")
                        .put("applicationIdentityExact", true)
                        .put("bindingInferred", false)
                        .put("probabilityInferred", false)
                        .put("jinhakPromoted", false)
                )
                if (id != null) {
                    stored++
                    applied.put(metric)
                }
            }

            when {
                university.contains("우송") && department == "철도차량시스템" && admission.contains("교과면접") -> {
                    matched++
                    val source = "https://ent.wsu.ac.kr/site/ent/popup/2026susi.pdf"
                    val detail = JSONObject()
                        .put("officialPublisher", "우송대학교 입학종합서비스")
                        .put("publishedTable", "2025학년도 최종등록자 수시모집 결과")
                        .put("recruitmentUnit", "철도차량시스템학과")
                        .put("admissionTrack", "학생부 교과 [면접]")
                        .put("capacity", 30).put("competitionRate", 1.0).put("waitlist", 22)
                    save(2025, "최종등록자 학생부 평균등급", 4.2, "우송대 본교산출 학생부등급", 9.0, "우송대학교 공식 2025 수시 입시결과", source, detail)
                    save(2025, "최종등록자 70% 학생부등급", 4.4, "우송대 본교산출 학생부등급", 9.0, "우송대학교 공식 2025 수시 입시결과", source, detail)
                    save(2025, "최종등록자 100% 학생부등급", 4.8, "우송대 본교산출 학생부등급", 9.0, "우송대학교 공식 2025 수시 입시결과", source, detail)
                }

                (university.contains("한국교통") || university.contains("국립한국교통")) &&
                    department == "철도차량시스템공학" && admission.contains("학생부종합2") -> {
                    matched++
                    val source = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr=2026&unvCd=0000034"
                    val detail = JSONObject()
                        .put("officialPublisher", "대입정보포털 어디가 · 국립한국교통대학교")
                        .put("publishedTable", "2025학년도 나비인재전형Ⅱ 결과")
                        .put("recruitmentUnit", "철도차량시스템공학과")
                        .put("admissionTrack", "나비인재전형Ⅱ (현 학생부종합Ⅱ 명칭 변경 전)")
                        .put("capacity", 15).put("competitionRate", 6.20).put("waitlist", 6)
                        .put("quantitativeSelectionScore", false)
                    save(2025, "최종등록자 50% 학생부등급", 3.21, "참고용 최종등록자 교과성적 학생부등급", 9.0, "어디가 공식 · 국립한국교통대 2025 종합Ⅱ 입시결과", source, detail)
                    save(2025, "최종등록자 70% 학생부등급", 3.41, "참고용 최종등록자 교과성적 학생부등급", 9.0, "어디가 공식 · 국립한국교통대 2025 종합Ⅱ 입시결과", source, detail)
                }

                university.contains("한밭") && department == "자율전공" && admission.contains("교과일반") -> {
                    matched++
                    val source = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr=2026&unvCd=0000039"
                    val detail = JSONObject()
                        .put("officialPublisher", "대입정보포털 어디가 · 국립한밭대학교")
                        .put("publishedTable", "2025학년도 학생부교과(일반) 결과")
                        .put("recruitmentUnit", "자율전공학부").put("admissionTrack", "학생부교과(일반)")
                    save(2025, "최종등록자 50% cut 대학별환산점수", 511.428, "국립한밭대 학생부 총점", 545.0, "어디가 공식 · 국립한밭대 2025 입시결과", source, detail)
                    save(2025, "최종등록자 70% cut 대학별환산점수", 509.692, "국립한밭대 학생부 총점", 545.0, "어디가 공식 · 국립한밭대 2025 입시결과", source, detail)
                    save(2025, "최종등록자 50% 학생부등급", 4.33, "최종등록자 학생부등급", 9.0, "어디가 공식 · 국립한밭대 2025 입시결과", source, detail)
                    save(2025, "최종등록자 70% 학생부등급", 4.25, "최종등록자 학생부등급", 9.0, "어디가 공식 · 국립한밭대 2025 입시결과", source, detail)
                }

                university.contains("한밭") && department == "반도체시스템공학" && admission.contains("지역인재교과") -> {
                    matched++
                    val source = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr=2026&unvCd=0000039"
                    val detail = JSONObject()
                        .put("officialPublisher", "대입정보포털 어디가 · 국립한밭대학교")
                        .put("publishedTable", "2025학년도 지역인재(교과) 결과")
                        .put("recruitmentUnit", "반도체시스템공학과").put("admissionTrack", "지역인재(교과)")
                        .put("capacity", 3).put("competitionRate", 11.00).put("waitlist", 5)
                        .put("availabilityStatus", "officially-suppressed")
                        .put("availabilityReason", "모집인원 3명 이하 모집단위는 입시결과 비공개")
                    save(2025, "공식 입결 공개상태", null, null, null, "어디가 공식 · 국립한밭대 2025 입시결과", source, detail)
                }

                university.contains("우송") && department == "철도자율전공" && admission.contains("교과중심") -> {
                    matched++
                    val source = "https://ent.wsu.ac.kr/site/ent/popup/2026susi.pdf"
                    val detail = JSONObject()
                        .put("officialPublisher", "우송대학교 입학종합서비스")
                        .put("publishedTable", "2025학년도 최종등록자 수시모집 결과")
                        .put("recruitmentUnit", "철도자율전공")
                        .put("availabilityStatus", "new-program-no-prior-result")
                        .put("availabilityReason", "공식 2025 결과표에서 신설학과로 표기되어 수치형 전년도 입결이 없음")
                    save(2025, "공식 입결 공개상태", null, null, null, "우송대학교 공식 2025 수시 입시결과", source, detail)
                }
            }

            if (applied.length() > 0) results.put(JSONObject()
                .put("applicationIdentityKey", identity)
                .put("storedMetrics", applied))
        }

        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("matchedApplications", matched)
            .put("storedRows", stored)
            .put("results", results)
            .put("officialSourcesOnly", true)
            .put("jinhakPromoted", false)
            .put("historicalBindingRelaxed", false)
            .put("slotsMutated", false)
            .put("probabilityInferred", false)
    }

    private fun normalize(value: String): String = value.lowercase(Locale.ROOT)
        .replace("Ⅱ", "2").replace("Ⅰ", "1")
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\)]"), "")
        .replace("전형", "")

    private fun normalizeDepartment(value: String): String = normalize(value)
        .removeSuffix("학과").removeSuffix("학부").removeSuffix("전공")
}
