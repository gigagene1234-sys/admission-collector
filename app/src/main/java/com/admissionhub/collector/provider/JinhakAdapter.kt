package com.admissionhub.collector.provider

import com.admissionhub.collector.parser.GenericAdmissionParser
import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.time.Instant
import java.time.temporal.ChronoUnit

object JinhakAdapter : ProviderAdapter {
    override val id = ProviderId.JINHAK
    override val supportsBatchCrawl = false
    private const val TARGET_YEAR = 2027

    override fun accepts(url: String): Boolean {
        return try {
            val host = URI(url).host?.lowercase() ?: return false
            host == "jinhak.com" || host.endsWith(".jinhak.com")
        } catch (_: Exception) { false }
    }

    override fun seedUrls(): List<String> = listOf("https://www.jinhak.com/")

    override fun isBatchNavigable(url: String): Boolean = false

    override fun classify(snapshot: JSONObject): String {
        val rawUrl = snapshot.optString("url")
        val url = rawUrl.lowercase()
        val path = runCatching { URI(rawUrl).path?.lowercase() ?: "/" }.getOrDefault("/")
        val rootPage = path.isBlank() || path == "/" || path.endsWith("/index") || path.endsWith("/index.html")
        val headingText = buildString {
            append(snapshot.optString("title"))
            val headings = snapshot.optJSONArray("context") ?: JSONArray()
            for (i in 0 until minOf(headings.length(), 16)) {
                append(' ').append(headings.optString(i))
            }
        }.replace(Regex("\\s+"), " ").trim()
        val pageTitle = snapshot.optString("title").replace(Regex("\\s+"), " ").trim()
        val navigationError = Regex("^(?:302\\s+Found|404\\s+Not\\s+Found|500(?:\\s+Internal\\s+Server\\s+Error)?)$", RegexOption.IGNORE_CASE).matches(pageTitle)
        val universityAdmissionInfo = Regex("^.{2,100}에 대한 모든 입시정보\\s*\\|\\s*대학정보\\s*\\|\\s*진학사$").containsMatchIn(pageTitle)
        val editorialContent = Regex("(학과\\s*심층분석|대학\\s*심층분석|대학학과\\s*심층분석|지도로\\s*보는\\s*대학|대학교\\s*지도|캠퍼스맵)").containsMatchIn(pageTitle)

        // Global menus contain words such as 합격예측/수시저장소 on almost every page.
        // Classification therefore uses URL + title/heading context, never whole-page menu text.
        val mockReport = url.contains("sapplysample") || Regex("모의지원\\s*리포트").containsMatchIn(headingText)
        val hasActual = Regex("(실제합격자\\s*(?:리포트|사례)|합격자\\s*리포트|전년도\\s*입시결과\\s*(?:리포트|상세))").containsMatchIn(headingText) ||
            Regex("(actual|admitreport|resultreport|passcase)").containsMatchIn(url)
        val dedicatedMinimum = url.contains("esatminuniv") || Regex("(수능최저|최저학력기준)").containsMatchIn(headingText)
        val scoreReport = Regex("(score|calc)").containsMatchIn(url) || Regex("성적산출\\s*리포트").containsMatchIn(headingText)
        val earlyStorage = Regex("(storage|save)").containsMatchIn(url) || Regex("(수시|정시)?\\s*저장소|저장대학").containsMatchIn(headingText)
        val universitySearch = url.contains("four-year-university/search") || Regex("대학검색").containsMatchIn(headingText)
        val curation = url.contains("/curation") || Regex("큐레이션").containsMatchIn(headingText)
        val recommended = Regex("추천대학").containsMatchIn(headingText)
        val hasPrediction = Regex("(predict|prediction|possibility|admission-report|support-report)").containsMatchIn(url) ||
            Regex("(합격예측\\s*(?:리포트|결과)|[0-9]{1,2}\\s*칸)").containsMatchIn(headingText)

        return when {
            Regex("(login|signin|member/login)").containsMatchIn(url) || Regex("로그인.*비밀번호").containsMatchIn(headingText) -> "jinhak-login"
            navigationError -> "jinhak-navigation-error"
            universityAdmissionInfo -> "jinhak-university-admission-info"
            editorialContent -> "jinhak-editorial-content"
            rootPage -> "jinhak-home"
            mockReport -> "jinhak-mock-support-report"
            hasActual -> "jinhak-actual-admit-report"
            dedicatedMinimum -> "jinhak-sat-minimum"
            url.contains("infoview.aspx") -> "jinhak-student-basic"
            scoreReport -> "jinhak-score-calc-report"
            earlyStorage -> "jinhak-early-storage"
            universitySearch -> "jinhak-university-search"
            curation -> "jinhak-curation"
            recommended -> "jinhak-recommended-university"
            hasPrediction -> "jinhak-prediction-report"
            else -> "jinhak-other"
        }
    }

    override fun normalize(snapshot: JSONObject): JSONArray {
        val text = GenericAdmissionParser.collectText(snapshot)
        val pageType = classify(snapshot)
        val context = GenericAdmissionParser.inferSnapshotContext(snapshot)
        val observedAt = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()
        val dataScope = dataScope(pageType)
        val inferredYear = context.year ?: if (dataScope == "current-prediction" || dataScope == "current-admission") TARGET_YEAR else null
        val result = JSONArray()

        if (pageType == "jinhak-university-admission-info") {
            return normalizeUniversityAdmissionInfo(snapshot, observedAt)
        }

        if (pageType == "jinhak-early-storage" || pageType == "jinhak-recommended-university") {
            val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
            var hasRicherPredictionCards = false
            for (ci in 0 until cards.length()) {
                val cObj = cards.optJSONObject(ci)
                val cEvidence = (cObj?.optString("text") ?: cards.optString(ci)).replace(Regex("""\s+"""), " ").trim()
                if (cEvidence.isBlank()) continue
                val cMetrics = predictionMetrics(cEvidence)
                if (listOf("mockCompetition", "predictionProbability", "myRank", "predictedCut", "mockApplicants", "applicants").any { cMetrics.has(it) && !cMetrics.isNull(it) }) {
                    hasRicherPredictionCards = true
                    break
                }
            }
            val seenLogical = linkedSetOf<String>()
            for (i in 0 until cards.length()) {
                val cardObj = cards.optJSONObject(i)
                val evidence = (cardObj?.optString("text") ?: cards.optString(i))
                    .replace(Regex("""\s+"""), " ").trim().take(5000)
                if (evidence.isBlank()) continue
                val local = GenericAdmissionParser.inferContext(evidence)
                val compact = if (pageType == "jinhak-recommended-university") compactRecommendationContext(evidence) else null
                if (pageType == "jinhak-recommended-university" && compact == null) continue
                val explicitUniversity = cleanStorageUniversity(cardObj?.optString("university"))
                val explicitDepartment = cleanStorageDepartment(cardObj?.optString("department"))
                val compactUniversity = cleanStorageUniversity(compact?.optString("university"))
                val compactDepartment = cleanStorageDepartment(compact?.optString("department"))
                val compactAdmission = compact?.optString("admission")?.takeIf { it.isNotBlank() }
                val university = compactUniversity ?: cleanStorageUniversity(local.university) ?: explicitUniversity
                val department = compactDepartment ?: cleanStorageDepartment(local.department) ?: explicitDepartment
                val admission = compactAdmission ?: cleanStorageAdmission(local.admission, evidence)
                val universityContextSource = cardObj?.optString("universitySource")
                    ?.takeIf { it.isNotBlank() && it != "missing" }
                val departmentContextSource = cardObj?.optString("departmentSource")
                    ?.takeIf { it.isNotBlank() && it != "missing" }
                val cardMetrics = predictionMetrics(evidence)
                compact?.optString("admissionCategory")?.takeIf { it.isNotBlank() }?.let { cardMetrics.put("admissionCategory", it) }
                compact?.optString("combinedAdmissionDepartmentLabel")?.takeIf { it.isNotBlank() }?.let { cardMetrics.put("combinedAdmissionDepartmentLabel", it) }
                if (evidence.contains("수능최저")) cardMetrics.put("minimumRequirementDisplayed", true)
                val metricKeys = cardMetrics.keys().asSequence().filter { !cardMetrics.isNull(it) }.toList()
                val summaryOnly = metricKeys.size == 1 && metricKeys.firstOrNull() == "stabilityBars"
                if (hasRicherPredictionCards && summaryOnly) continue
                val hasPrimaryPrediction = listOf(
                    "stabilityBars", "predictionProbability", "predictionLabel", "myRank", "predictedCut"
                ).any { cardMetrics.has(it) && !cardMetrics.isNull(it) }
                if (!hasPrimaryPrediction) continue
                val logical = RecordUtils.sha256(listOf(
                    university ?: "", department ?: "", admission ?: "", cardMetrics.toString()
                ).joinToString("|"))
                if (!seenLogical.add(logical)) continue
                val record = JSONObject()
                    .put("recordType", "jinhak-saved-application-prediction")
                    .put("providerPageType", pageType)
                    .put("dataScope", "current-prediction")
                    .put("year", local.year ?: TARGET_YEAR)
                    .put("university", university ?: JSONObject.NULL)
                    .put("department", department ?: JSONObject.NULL)
                    .put("admission", admission ?: JSONObject.NULL)
                    .put("metrics", cardMetrics)
                    .put("observedAt", observedAt)
                    .put("cardIndex", i)
                    .put("contextSource", when {
                        compact != null -> "compact-recommendation-card"
                        local.university == null && explicitUniversity != null && local.department == null && explicitDepartment != null -> "scored-card-root+university+department-context"
                        local.university == null && explicitUniversity != null -> "scored-card-root+explicit-university-context"
                        local.department == null && explicitDepartment != null -> "scored-card-root+explicit-department-context"
                        else -> "scored-card-root"
                    })
                    .put("universityContextSource", universityContextSource ?: JSONObject.NULL)
                    .put("universityContextDepth", cardObj?.optInt("universityDepth", -1) ?: -1)
                    .put("departmentContextSource", departmentContextSource ?: JSONObject.NULL)
                    .put("departmentContextDepth", cardObj?.optInt("departmentDepth", -1) ?: -1)
                    .put("cardRootScore", cardObj?.optInt("score", 0) ?: 0)
                    .put("confidence", when {
                        university != null && department != null && admission != null -> "high"
                        university != null && department != null -> "medium"
                        department != null -> "low"
                        else -> "raw"
                    })
                    .put("sourcePage", safePath(snapshot.optString("url")))
                    .put("rawEvidence", evidence)
                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = true))
                result.put(record)
            }
            return RecordUtils.dedupe(result)
        }

        if (pageType == "jinhak-home" || pageType == "jinhak-university-search" || pageType == "jinhak-curation" ||
            pageType == "jinhak-other" || pageType == "jinhak-editorial-content" || pageType == "jinhak-navigation-error") {
            return result
        }

        val metrics = JSONObject()
        putNumber(metrics, "universityCalculatedScore", Regex("(?:대학별\\s*)?(?:환산점수|산출점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putNumber(metrics, "convertedGrade", Regex("(?:반영\\s*평균등급|환산등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "stabilityBars", Regex("(?:합격안정성|칸수|칸\\s*수)?\\s*[:：]?\\s*([0-9]{1,2})\\s*칸").find(text)?.groupValues?.getOrNull(1))
        putText(metrics, "predictionLabel", Regex("(?:합격예측|지원판정|지원전략)?\\s*[:：]?\\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "mockApplicants", Regex("(?:모의지원자수|모의지원자 수|모의지원자)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "applicants", Regex("(?:현재\\s*)?(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\s*)?경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "myRank", Regex("(?:내\\s*순위|나의\\s*순위|현재\\s*순위)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "predictedCut", Regex("(?:예상\\s*합격선|예상\\s*컷|합격예상점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "additionalAdmits", Regex("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))

        val minimum = Regex("수능최저[^.\\n]{0,100}(충족가능|미충족|불충족|충족)").find(text)?.groupValues?.getOrNull(1)
        if (!minimum.isNullOrBlank()) metrics.put("minimumStatus", minimum)

        if (metrics.keys().asSequence().any { !metrics.isNull(it) }) {
            val summary = JSONObject()
                .put("recordType", if (dataScope == "current-prediction") "jinhak-prediction-snapshot" else "jinhak-page-summary")
                .put("providerPageType", pageType)
                .put("dataScope", dataScope)
                .put("year", inferredYear ?: JSONObject.NULL)
                .put("university", context.university ?: JSONObject.NULL)
                .put("department", context.department ?: JSONObject.NULL)
                .put("admission", context.admission ?: JSONObject.NULL)
                .put("metrics", metrics)
                .put("observedAt", observedAt)
                .put("confidence", when {
                    context.university != null && context.department != null -> "high"
                    context.university != null || context.department != null || context.admission != null -> "medium"
                    else -> "raw"
                })
                .put("sourcePage", safePath(snapshot.optString("url")))
                .put("rawEvidence", text.take(5000))
            summary.put("sourceRowFingerprint", fingerprint(summary, observedAt, preserveSnapshot = dataScope == "current-prediction"))
            result.put(summary)
        }

        val generic = GenericAdmissionParser.normalize(snapshot)
        for (i in 0 until generic.length()) {
            val row = generic.optJSONObject(i) ?: continue
            row.put("providerPageType", pageType)
                .put("dataScope", dataScope)
                .put("observedAt", observedAt)
            if (row.isNull("year") && inferredYear != null) row.put("year", inferredYear)
            row.put("sourcePage", safePath(snapshot.optString("url")))
            row.put("sourceRowFingerprint", fingerprint(row, observedAt, preserveSnapshot = dataScope == "current-prediction"))
            result.put(row)
        }
        return RecordUtils.dedupe(result)
    }

    private fun dataScope(pageType: String): String = when (pageType) {
        "jinhak-actual-admit-report", "jinhak-university-admission-info" -> "historical-result"
        "jinhak-prediction-report", "jinhak-mock-support-report", "jinhak-recommended-university", "jinhak-early-storage" -> "current-prediction"
        "jinhak-sat-minimum" -> "current-admission"
        "jinhak-score-calc-report", "jinhak-student-basic" -> "student-profile"
        "jinhak-home", "jinhak-university-search", "jinhak-curation" -> "reference-navigation"
        else -> "reference"
    }

    private fun fingerprint(record: JSONObject, observedAt: String, preserveSnapshot: Boolean): String {
        val stable = listOf(
            record.optString("recordType"), record.optString("year"), record.optString("university"),
            record.optString("department"), record.optString("admission"), record.optJSONObject("metrics")?.toString() ?: "",
            record.optString("rawEvidence").take(1000)
        ).joinToString("|")
        val scope = if (preserveSnapshot) observedAt.substring(0, 16) else "stable"
        return RecordUtils.sha256("jinhak|$scope|$stable")
    }

    private fun cleanStorageUniversity(value: String?): String? {
        val raw = value?.replace(Regex("""\s+"""), " ")?.trim()?.takeIf { it.isNotBlank() } ?: return null
        val cleaned = raw
            .replace(Regex("""^(?:(?:닫기|열기|보기|상세|선택|삭제)\s*)*(?:[0-9]{1,2}\s*칸\s*)?"""), "")
            .trim()
        if (cleaned.length !in 3..48) return null
        if (Regex("""(등급|경쟁률|합격|예측|지원|전형|모집|학과|학부|전공)""").containsMatchIn(cleaned)) return null
        val full = Regex("""^[가-힣A-Za-z0-9·.()\-]{2,35}(?:대학교|교육대학교|과학기술원)(?:\[[^\]]{1,12}\])?$""")
        val short = Regex("""^[가-힣A-Za-z0-9·.&+\-]{2,24}대(?:\([^)]+\))?$""")
        val shortNoise = setOf("공대", "의대", "법대", "상대", "교대", "사범대", "간호대", "약대", "치대", "한의대", "철도대")
        return when {
            full.matches(cleaned) -> cleaned
            short.matches(cleaned) && cleaned !in shortNoise -> cleaned
            else -> null
        }
    }

    private fun cleanStorageDepartment(value: String?): String? {
        val raw = value?.trim()?.takeIf { it.isNotBlank() } ?: return null
        val cleaned = raw.replace(
            Regex("""^(?:지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\(면접형\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)"""),
            ""
        ).trim()
        return cleaned.takeIf { it.length >= 2 } ?: raw
    }

    private fun cleanStorageAdmission(value: String?, evidence: String): String? {
        val polluted = Regex("""(등급|경쟁률|전년도|점수|[0-9]{1,2}\s*칸|합격률|합격확률)""")
        value?.trim()?.takeIf { it.isNotBlank() && it.length <= 40 && !polluted.containsMatchIn(it) }?.let { return it }
        val token = Regex("""(지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\(면접형\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)""")
            .find(evidence)?.groupValues?.getOrNull(1)
        return token?.trim()?.takeIf { it.isNotBlank() }
    }

    private fun compactRecommendationContext(text: String): JSONObject? {
        val compact = text.replace(Regex("""\s+"""), " ").trim()
        val universityMatch = Regex("""^(?:[0-9]{1,2}\s*칸\s*)?([가-힣A-Za-z0-9·.&+\-]+(?:\([^)]+\))?)(?=\[)""").find(compact) ?: return null
        val university = universityMatch.groupValues.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() } ?: return null
        var tail = compact.substring(universityMatch.range.last + 1)
        val categoryMatch = Regex("""^\[([^\]]{1,20})\]""").find(tail)
        val category = categoryMatch?.groupValues?.getOrNull(1)?.trim()
        if (categoryMatch != null) tail = tail.substring(categoryMatch.range.last + 1)

        val combined = Regex("""^(.+?)(?=[0-9]{1,4}\s*명\s*내\s*점수)""").find(tail)
            ?.groupValues?.getOrNull(1)?.trim().orEmpty()
        if (combined.isBlank()) return null
        val admissionRegex = Regex("""^(지역인재교과|지역인재종합|교과일반|교과우수|교과중심|자기추천|창의인재\(면접형\)|교과면접|학교장추천|고른기회|기회균형|학생부교과|학생부종합|지역인재|자율전공|일반)""")
        val admissionMatch = admissionRegex.find(combined)
        val admission = admissionMatch?.groupValues?.getOrNull(1)?.trim()
        var department = if (admissionMatch != null) combined.substring(admissionMatch.range.last + 1) else combined
        department = department.replace(Regex("""^(?:\[[^\]]{1,30}\])+"""), "").trim()
        if (department.isBlank() || department.length > 100) return null

        return JSONObject()
            .put("university", university)
            .put("department", department)
            .put("admission", admission ?: JSONObject.NULL)
            .put("admissionCategory", category ?: JSONObject.NULL)
            .put("combinedAdmissionDepartmentLabel", combined)
    }

    private fun normalizeUniversityAdmissionInfo(snapshot: JSONObject, observedAt: String): JSONArray {
        val result = JSONArray()
        val title = snapshot.optString("title").replace(Regex("""\s+"""), " ").trim()
        val university = Regex("""^(.+?)에 대한 모든 입시정보\s*\|\s*대학정보\s*\|\s*진학사$""")
            .find(title)?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() } ?: return result
        val tables = snapshot.optJSONArray("tables") ?: return result

        for (ti in 0 until tables.length()) {
            val rows = tables.optJSONObject(ti)?.optJSONArray("rows") ?: continue
            if (rows.length() < 2) continue
            val header = rows.optJSONArray(0) ?: continue
            if (!header.optString(0).replace(" ", "").contains("전형/모집단위")) continue

            val yearColumns = mutableListOf<Pair<Int, Int>>()
            for (ci in 1 until header.length()) {
                val year = Regex("""(20[0-9]{2})\s*학년도""").find(header.optString(ci))
                    ?.groupValues?.getOrNull(1)?.toIntOrNull() ?: continue
                yearColumns += ci to year
            }
            if (yearColumns.isEmpty()) continue

            for (ri in 1 until rows.length()) {
                val row = rows.optJSONArray(ri) ?: continue
                val rowLabel = row.optString(0).replace(Regex("""\s+"""), " ").trim()
                if (rowLabel.isBlank()) continue
                val category = Regex("""^\[([^\]]{1,20})\]""").find(rowLabel)?.groupValues?.getOrNull(1)?.trim()

                for ((ci, year) in yearColumns) {
                    val rawValue = row.optString(ci).replace(Regex("""\s+"""), " ").trim()
                    if (rawValue.isBlank() || rawValue == "-") continue
                    val numeric = Regex("""-?[0-9]+(?:\.[0-9]+)?""").find(rawValue)?.value?.toDoubleOrNull()
                    val metrics = JSONObject()
                        .put("metricType", "competition")
                        .put("combinedAdmissionDepartmentLabel", rowLabel)
                        .put("admissionCategory", category ?: JSONObject.NULL)
                    if (numeric != null) metrics.put("competition", numeric) else metrics.put("rawValue", rawValue.take(120))

                    val record = JSONObject()
                        .put("recordType", "jinhak-historical-competition")
                        .put("providerPageType", "jinhak-university-admission-info")
                        .put("dataScope", "historical-result")
                        .put("year", year)
                        .put("university", university)
                        .put("department", JSONObject.NULL)
                        .put("admission", JSONObject.NULL)
                        .put("metrics", metrics)
                        .put("observedAt", observedAt)
                        .put("confidence", "medium")
                        .put("sourcePage", safePath(snapshot.optString("url")))
                        .put("rawEvidence", "$rowLabel | $year | $rawValue")
                    record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = false))
                    result.put(record)
                }
            }
        }
        return RecordUtils.dedupe(result)
    }

    private fun predictionMetrics(text: String): JSONObject {
        val metrics = JSONObject()
        putNumber(metrics, "universityCalculatedScore", Regex("(?:대학별\\s*)?(?:환산점수|산출점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        if (!metrics.has("universityCalculatedScore")) {
            putNumber(metrics, "universityCalculatedScore", Regex("내\\s*점수\\s*([0-9]+(?:\\.[0-9]+)?)\\s*점").find(text)?.groupValues?.getOrNull(1))
        }
        putNumber(metrics, "convertedGrade", Regex("(?:반영\\s*평균등급|환산등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "stabilityBars", Regex("(?<![0-9.])(?:합격안정성|칸수|칸\\s*수)?\\s*[:：]?\\s*([0-9]{1,2})\\s*칸").find(text)?.groupValues?.getOrNull(1))
        putNumber(metrics, "predictionProbability", Regex("(?:예상\\s*)?(?:합격률|합격확률|합격가능성)\\s*[:：]?\\s*([0-9]{1,3}(?:\\.[0-9]+)?)\\s*%").find(text)?.groupValues?.getOrNull(1))
        putText(metrics, "predictionLabel", Regex("(?:합격예측|합격가능성|지원판정|지원전략)?\\s*[:：]?\\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        if (!metrics.has("capacity")) {
            putInt(metrics, "capacity", Regex("([0-9,]+)\\s*명\\s*내\\s*점수").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        }
        putInt(metrics, "mockApplicants", Regex("(?:모의지원자수|모의지원자 수|모의지원자)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "applicants", Regex("(?:현재\\s*)?(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\s*)?경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "myRank", Regex("(?:내\\s*순위|나의\\s*순위|현재\\s*순위)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "predictedCut", Regex("(?:예상\\s*합격선|예상\\s*컷|합격예상점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "additionalAdmits", Regex("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        return metrics
    }

    private fun putNumber(obj: JSONObject, key: String, value: String?) {
        val n = value?.toDoubleOrNull() ?: return
        obj.put(key, n)
    }
    private fun putInt(obj: JSONObject, key: String, value: String?) {
        val n = value?.toIntOrNull() ?: return
        obj.put(key, n)
    }
    private fun putText(obj: JSONObject, key: String, value: String?) {
        value?.trim()?.takeIf { it.isNotBlank() }?.let { obj.put(key, it) }
    }
    private fun safePath(url: String): String = try {
        val uri = URI(url)
        "${uri.scheme ?: "https"}://${uri.host ?: ""}${uri.path ?: "/"}"
    } catch (_: Exception) { url.substringBefore('?').substringBefore('#') }
}
