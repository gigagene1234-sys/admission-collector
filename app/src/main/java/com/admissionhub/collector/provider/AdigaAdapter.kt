package com.admissionhub.collector.provider

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.net.URLDecoder

object AdigaAdapter : ProviderAdapter {
    override val id = ProviderId.ADIGA
    override val supportsBatchCrawl = true

    override fun accepts(url: String): Boolean {
        return try {
            val host = URI(url).host?.lowercase() ?: return false
            host == "adiga.kr" || host.endsWith(".adiga.kr")
        } catch (_: Exception) { false }
    }

    override fun seedUrls(): List<String> = listOf(
        // 2027 current admissions + university codes/details. 2027 university detail pages
        // contain the 2026 actual result section.
        "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/cls/uni/classUnivView.do?menuId=PCCLSINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2027",
        // 2026 university/admission views expose 2025 actual results. The huge 2026
        // department list is intentionally omitted because it duplicated the 2027 list
        // in prior device runs and is not needed to obtain the 2025 historical result.
        "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2026",
        "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2026",
        "https://www.adiga.kr/uct/acd/ade/criteriaAndResultView.do?menuId=PCUCTACD2000&searchSyr=2027",
        "https://www.adiga.kr/uct/acd/ade/criteriaAndResultView.do?menuId=PCUCTACD2000&searchSyr=2026",
        "https://www.adiga.kr/uct/acd/adc/characteristicsView.do?menuId=PCUCTACD1100",
        "https://www.adiga.kr/uct/acd/ueg/univEtenGuideView.do?menuId=PCUCTACD3100"
    )

    override fun isBatchNavigable(url: String): Boolean {
        if (!accepts(url)) return false
        return try {
            val uri = URI(url)
            val host = uri.host?.lowercase() ?: return false
            if (host == "m.adiga.kr") return false
            val path = uri.path ?: return false
            path.startsWith("/ucp/") ||
                path.startsWith("/sco/") ||
                path.startsWith("/uct/acd/") ||
                path.startsWith("/uct/ces/")
        } catch (_: Exception) { false }
    }

    override fun isDynamicListPage(url: String): Boolean =
        url.contains("/ucp/uvt/uni/univView.do") ||
            url.contains("/ucp/cls/uni/classUnivView.do") ||
            url.contains("/ucp/prc/uni/admssUnivView.do")

    override fun paginationPlan(snapshot: JSONObject): PaginationPlan? {
        val url = snapshot.optString("url")
        if (!isDynamicListPage(url)) return null
        // Dynamic admission lists are year-scoped. A missing year after a login
        // redirect must never create a second Cloudflare checkpoint namespace (-1).
        // MainActivity restores the expected year before asking for a plan; if that
        // recovery fails, skip pagination rather than mislabel data.
        val requestedYear = queryYear(url) ?: return null
        val meta = snapshot.optJSONObject("listMeta") ?: return null
        val totalItems = meta.optInt("totalItems", -1)
        val pageSize = meta.optInt("visibleDataRows", 0)
        if (totalItems <= 0 || pageSize <= 0) return null
        val totalPages = ((totalItems + pageSize - 1) / pageSize).coerceIn(1, 600)
        val rows = firstTableRows(snapshot) ?: return null
        val fingerprint = RecordUtils.sha256("$totalItems|${rows}")
        return PaginationPlan(
            familyKey = listFamilyKey(url),
            totalItems = totalItems,
            pageSize = pageSize,
            totalPages = totalPages,
            requestedYear = requestedYear,
            firstPageFingerprint = fingerprint
        )
    }

    override fun paginationScript(page: Int): String? {
        if (page <= 1 || page > 600) return null
        return "(function(){try{if(typeof window.fnSearch!=='function')return false;window.fnSearch($page);return true;}catch(e){return false;}})();"
    }

    override fun classify(snapshot: JSONObject): String {
        val url = snapshot.optString("url")
        return when {
            url.contains("/ucp/uvt/uni/univView.do") -> "adiga-university-list"
            url.contains("/ucp/cls/uni/classUnivView.do") -> "adiga-department-list"
            url.contains("/ucp/prc/uni/admssUnivView.do") -> "adiga-admission-list"
            url.contains("/ucp/uvt/uni/univDetailSelection.do") -> "adiga-university-detail"
            url.contains("/uct/acd/ade/criteriaAndResultPopup.do") -> "adiga-criteria-result-detail"
            url.contains("/uct/acd/adc/characteristicsView.do") -> "adiga-university-characteristics"
            url.contains("/uct/acd/ueg/univEtenGuideView.do") -> "adiga-university-guide"
            url.contains("/uct/acd/ade/criteriaAndResultView.do") -> "adiga-criteria-result"
            url.contains("/uct/acd/dia/disabledAdmssView.do") -> "adiga-disabled-admission"
            url.contains("/sco/") -> "adiga-score-analysis"
            else -> "adiga-other"
        }
    }

    override fun normalize(snapshot: JSONObject): JSONArray {
        val url = snapshot.optString("url")
        val out = when {
            url.contains("/ucp/uvt/uni/univView.do") -> parseUniversityList(snapshot)
            url.contains("/ucp/cls/uni/classUnivView.do") -> parseDepartmentList(snapshot)
            url.contains("/ucp/prc/uni/admssUnivView.do") -> parseAdmissionList(snapshot)
            url.contains("/ucp/uvt/uni/univDetailSelection.do") -> parseUniversityDetail(snapshot)
            url.contains("/uct/acd/ade/criteriaAndResultPopup.do") -> parseUniversityDetail(snapshot)
            url.contains("/uct/acd/adc/characteristicsView.do") -> parseCharacteristicsIndex(snapshot)
            url.contains("/uct/acd/ueg/univEtenGuideView.do") -> parseGuideIndex(snapshot)
            url.contains("/uct/acd/ade/criteriaAndResultView.do") -> parseCriteriaIndex(snapshot)
            url.contains("/uct/acd/dia/disabledAdmssView.do") -> parseDisabledAdmissionsIndex(snapshot)
            else -> JSONArray()
        }
        return RecordUtils.dedupe(out)
    }

    private fun firstTableRows(snapshot: JSONObject): JSONArray? {
        val tables = snapshot.optJSONArray("tables") ?: return null
        if (tables.length() == 0) return null
        return tables.optJSONObject(0)?.optJSONArray("rows")
    }

    private fun parseUniversityList(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstTableRows(snapshot) ?: return out
        if (rows.length() < 2) return out
        val header = rows.optJSONArray(0) ?: return out
        val pageYear = queryYear(snapshot.optString("url"))
        val competitionYear = Regex("(20\\d{2})\\s*경쟁률").find(header.optString(2))?.groupValues?.getOrNull(1)?.toIntOrNull()
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 6) continue
            val university = normalizeUniversityCell(row.optString(0))
            if (!looksLikeUniversity(university)) continue
            val (early, regular) = parseCompetition(row.optString(2))
            val metrics = JSONObject()
                .put("region", valueOrNull(row.optString(1)))
                .put("earlyCompetition", numberOrNull(early))
                .put("regularCompetition", numberOrNull(regular))
                .put("competitionYear", competitionYear ?: JSONObject.NULL)
                .put("enrollmentCapacity", intOrNull(row.optString(3)))
                .put("departmentCount", intOrNull(row.optString(4)))
                .put("admissionCount", intOrNull(row.optString(5)))
            out.put(JSONObject()
                .put("recordType", "university-summary")
                .put("year", pageYear ?: JSONObject.NULL)
                .put("university", university)
                .put("campus", extractCampus(university) ?: JSONObject.NULL)
                .put("department", JSONObject.NULL)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                .put("sourceRowOrdinal", sourceRowOrdinal(snapshot, ri))
                .put("sourceRowFingerprint", scopedRowFingerprint("university-summary", pageYear, row))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun parseDepartmentList(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstTableRows(snapshot) ?: return out
        if (rows.length() < 2) return out
        val header = rows.optJSONArray(0) ?: return out
        val pageYear = queryYear(snapshot.optString("url"))
        val competitionYear = Regex("(20\\d{2})\\s*경쟁률").find(header.optString(3))?.groupValues?.getOrNull(1)?.toIntOrNull()
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 5) continue
            val department = row.optString(0).trim()
            val university = normalizeUniversityCell(row.optString(1))
            if (department.isBlank() || department.contains("검색결과가 없습니다") || !looksLikeUniversity(university)) continue
            val (early, regular) = parseCompetition(row.optString(3))
            val metrics = JSONObject()
                .put("region", valueOrNull(row.optString(2)))
                .put("earlyCompetition", numberOrNull(early))
                .put("regularCompetition", numberOrNull(regular))
                .put("competitionYear", competitionYear ?: JSONObject.NULL)
                .put("enrollmentCapacity", intOrNull(row.optString(4)))
                .put("hasAdmissionResult", row.optString(5).contains("입시결과"))
            out.put(JSONObject()
                .put("recordType", "department-summary")
                .put("year", pageYear ?: JSONObject.NULL)
                .put("university", university)
                .put("campus", extractCampus(university) ?: JSONObject.NULL)
                .put("department", department)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                .put("sourceRowOrdinal", sourceRowOrdinal(snapshot, ri))
                .put("sourceRowFingerprint", scopedRowFingerprint("department-summary", pageYear, row))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun parseAdmissionList(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstTableRows(snapshot) ?: return out
        if (rows.length() < 2) return out
        val pageYear = queryYear(snapshot.optString("url"))
        val previousYear = pageYear?.minus(1)
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 6) continue
            val university = normalizeUniversityCell(row.optString(0))
            val department = row.optString(1).trim()
            if (!looksLikeUniversity(university) || department.isBlank() || department.contains("검색결과가 없습니다")) continue
            val previousCompetition = Regex("[0-9]+(?:\\.[0-9]+)?").find(row.optString(3))?.value?.toDoubleOrNull()
            val previousGrade = Regex("[0-9]+(?:\\.[0-9]+)?").find(row.optString(5))?.value?.toDoubleOrNull()
            val metrics = JSONObject()
                .put("region", valueOrNull(row.optString(2)))
                .put("previousCompetition", numberOrNull(previousCompetition))
                .put("competitionYear", previousYear ?: JSONObject.NULL)
                .put("capacity", intOrNull(row.optString(4)))
                .put("previousAdmissionGrade", numberOrNull(previousGrade))
                .put("historicalResultYear", previousYear ?: JSONObject.NULL)
            out.put(JSONObject()
                .put("recordType", "admission-search-summary")
                .put("year", pageYear ?: JSONObject.NULL)
                .put("university", university)
                .put("campus", extractCampus(university) ?: JSONObject.NULL)
                .put("department", department)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                .put("sourceRowOrdinal", sourceRowOrdinal(snapshot, ri))
                .put("sourceRowFingerprint", scopedRowFingerprint("admission-search-summary", pageYear, row))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun parseUniversityDetail(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val url = snapshot.optString("url")
        val admissionYear = queryYear(url)
        val resultYear = admissionYear?.minus(1)
        val universityCode = queryParam(url, "unvCd")
        val university = inferUniversityFromSnapshot(snapshot)
        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until tables.length()) {
            val table = tables.optJSONObject(ti) ?: continue
            val rows = table.optJSONArray("rows") ?: continue
            if (rows.length() == 0) continue
            val evidence = rows.toString()
            val historical = resultYear != null && (
                evidence.contains("${resultYear}학년도") ||
                    Regex("(경쟁률|충원|최종등록|등록자|50%|70%|입시결과|전형 결과)").containsMatchIn(evidence)
                )
            val recordYear = if (historical) resultYear else admissionYear
            val recordType = if (historical) "historical-admission-result-table" else "current-admission-criteria-table"
            val metrics = JSONObject()
                .put("admissionYear", admissionYear ?: JSONObject.NULL)
                .put("historicalResultYear", resultYear ?: JSONObject.NULL)
                .put("universityCode", universityCode ?: JSONObject.NULL)
                .put("tableIndex", ti)
                .put("caption", valueOrNull(table.optString("caption")))
                .put("rows", rows)
            out.put(JSONObject()
                .put("recordType", recordType)
                .put("year", recordYear ?: JSONObject.NULL)
                .put("university", university ?: JSONObject.NULL)
                .put("campus", university?.let { extractCampus(it) } ?: JSONObject.NULL)
                .put("department", JSONObject.NULL)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", if (university != null && recordYear != null) "high" else "medium")
                .put("sourcePage", url)
                .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                .put("sourceRowFingerprint", scopedRowFingerprint(recordType, recordYear, rows))
                .put("rawEvidence", evidence.take(12000)))
        }
        if (out.length() == 0) {
            val evidence = buildString {
                val context = snapshot.optJSONArray("context") ?: JSONArray()
                for (i in 0 until context.length()) append(context.optString(i)).append(' ')
                val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
                for (i in 0 until minOf(blocks.length(), 80)) append(blocks.optString(i)).append(' ')
            }.trim()
            if (evidence.isNotBlank()) {
                out.put(JSONObject()
                    .put("recordType", "university-detail-text")
                    .put("year", admissionYear ?: JSONObject.NULL)
                    .put("university", university ?: JSONObject.NULL)
                    .put("campus", university?.let { extractCampus(it) } ?: JSONObject.NULL)
                    .put("department", JSONObject.NULL)
                    .put("admission", JSONObject.NULL)
                    .put("metrics", JSONObject()
                        .put("admissionYear", admissionYear ?: JSONObject.NULL)
                        .put("historicalResultYear", resultYear ?: JSONObject.NULL)
                        .put("universityCode", universityCode ?: JSONObject.NULL))
                    .put("confidence", "medium")
                    .put("sourcePage", url)
                    .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                    .put("sourceRowFingerprint", RecordUtils.sha256("${admissionYear ?: "na"}|$evidence"))
                    .put("rawEvidence", evidence.take(12000)))
            }
        }
        return out
    }

    private fun inferUniversityFromSnapshot(snapshot: JSONObject): String? {
        val candidates = mutableListOf<String>()
        val context = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until context.length()) candidates += context.optString(i)
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 60)) candidates += blocks.optString(i)
        val regex = Regex("([가-힣A-Za-z0-9·()\\- ]+(?:대학교|대학)(?:\\[[^]]+])?)")
        for (candidate in candidates) {
            val match = regex.find(candidate)?.groupValues?.getOrNull(1)?.trim() ?: continue
            val normalized = normalizeUniversityCell(match)
            if (looksLikeUniversity(normalized)) return normalized
        }
        return null
    }

    private fun parseCharacteristicsIndex(snapshot: JSONObject): JSONArray {
        val out = JSONArray(); val rows = firstTableRows(snapshot) ?: return out
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 3) continue
            val university = normalizeUniversityCell(row.optString(0)); if (!looksLikeUniversity(university)) continue
            val metrics = JSONObject().put("recruitmentTotal", intOrNull(row.optString(1))).put("registeredAt", valueOrNull(row.optString(2)))
            out.put(indexRecord("university-characteristics-index", university, metrics, snapshot, row))
        }
        return out
    }

    private fun parseGuideIndex(snapshot: JSONObject): JSONArray {
        val out = JSONArray(); val rows = firstTableRows(snapshot) ?: return out
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 2) continue
            val university = normalizeUniversityCell(row.optString(0)); if (!looksLikeUniversity(university)) continue
            out.put(indexRecord("university-guide-index", university, JSONObject().put("registeredAt", valueOrNull(row.optString(1))), snapshot, row))
        }
        return out
    }

    private fun parseCriteriaIndex(snapshot: JSONObject): JSONArray {
        val out = JSONArray(); val rows = firstTableRows(snapshot) ?: return out
        if (rows.length() < 2) return out
        var labels = listOf("학생부위주(종합)", "학생부위주(교과)", "수능위주")
        val maybeLabels = rows.optJSONArray(1)
        if (maybeLabels != null && maybeLabels.length() >= 3 && (0 until minOf(3, maybeLabels.length())).all { maybeLabels.optString(it).contains("위주") }) {
            labels = (0 until 3).map { maybeLabels.optString(it) }
        }
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 5) continue
            val university = normalizeUniversityCell(row.optString(0)); if (!looksLikeUniversity(university)) continue
            val admissionYear = queryYear(snapshot.optString("url"))
            val metrics = JSONObject()
                .put("holisticRecruitment", intOrNull(row.optString(1)))
                .put("curriculumRecruitment", intOrNull(row.optString(2)))
                .put("csatRecruitment", intOrNull(row.optString(3)))
                .put("registeredAt", valueOrNull(row.optString(4)))
                .put("columnLabels", JSONArray(labels))
                .put("admissionYear", admissionYear ?: JSONObject.NULL)
                .put("historicalResultYear", admissionYear?.minus(1) ?: JSONObject.NULL)
            out.put(indexRecord("criteria-result-index", university, metrics, snapshot, row, admissionYear))
        }
        return out
    }

    private fun parseDisabledAdmissionsIndex(snapshot: JSONObject): JSONArray {
        val out = JSONArray(); val rows = firstTableRows(snapshot) ?: return out
        val header = if (rows.length() > 0) rows.optJSONArray(0) else null
        val year = header?.let { Regex("(20\\d{2})").find(it.optString(1))?.groupValues?.getOrNull(1)?.toIntOrNull() }
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 2) continue
            val university = normalizeUniversityCell(row.optString(0).replace("상세정보", "").trim()); if (!looksLikeUniversity(university)) continue
            val metrics = JSONObject().put("admittedStudents", intOrNull(row.optString(1)))
            out.put(JSONObject()
                .put("recordType", "disabled-admissions-index")
                .put("year", year ?: JSONObject.NULL)
                .put("university", university)
                .put("campus", extractCampus(university) ?: JSONObject.NULL)
                .put("department", JSONObject.NULL)
                .put("admission", "대학별 장애인 전형")
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
                .put("sourceRowFingerprint", scopedRowFingerprint("disabled-admissions-index", year, row))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun indexRecord(type: String, university: String, metrics: JSONObject, snapshot: JSONObject, row: JSONArray, year: Int? = null): JSONObject = JSONObject()
        .put("recordType", type).put("year", year ?: JSONObject.NULL).put("university", university)
        .put("campus", extractCampus(university) ?: JSONObject.NULL)
        .put("department", JSONObject.NULL).put("admission", JSONObject.NULL).put("metrics", metrics)
        .put("confidence", "high").put("sourcePage", snapshot.optString("url"))
        .put("sourcePageNumber", snapshot.optInt("collectionPage", 1))
        .put("sourceRowFingerprint", scopedRowFingerprint(type, year, row))
        .put("rawEvidence", rowToEvidence(row))

    private fun queryYear(url: String): Int? = queryParam(url, "searchSyr")?.toIntOrNull()

    private fun queryParam(url: String, key: String): String? {
        return try {
            val query = URI(url).rawQuery ?: return null
            query.split('&').asSequence().mapNotNull { part ->
                val split = part.split('=', limit = 2)
                if (split.isEmpty()) null else {
                    val k = URLDecoder.decode(split[0], "UTF-8")
                    val v = if (split.size > 1) URLDecoder.decode(split[1], "UTF-8") else ""
                    k to v
                }
            }.firstOrNull { it.first == key }?.second
        } catch (_: Exception) { null }
    }

    private fun normalizeUniversityCell(value: String): String = value
        .replace(Regex("\\s+(?=[(\\[])") , "")
        .replace(Regex("\\s+"), " ")
        .trim()

    private fun looksLikeUniversity(value: String): Boolean {
        if (value.isBlank() || value.contains("대학명을 클릭") || value == "일반대학" || value == "전문대학") return false
        return Regex("(?:대학교|대학)(?:\\([^()]{1,60}\\))?(?:\\[(?:본교|분교|제\\d+캠퍼스)\\])?$").containsMatchIn(value)
    }

    private fun extractCampus(university: String): String? =
        Regex("\\[((?:본교|분교|제\\d+캠퍼스))\\]$").find(university)?.groupValues?.getOrNull(1)

    private fun sourceRowOrdinal(snapshot: JSONObject, rowIndex: Int): Any {
        val page = snapshot.optInt("collectionPage", 1).coerceAtLeast(1)
        val pagination = snapshot.optJSONObject("collectionPagination")
        val plannedPageSize = pagination?.optInt("pageSize", 0) ?: 0
        val visiblePageSize = snapshot.optJSONObject("listMeta")?.optInt("visibleDataRows", 0) ?: 0
        val pageSize = if (plannedPageSize > 0) plannedPageSize else visiblePageSize
        if (pageSize <= 0) return JSONObject.NULL
        return (page - 1) * pageSize + rowIndex
    }

    private fun scopedRowFingerprint(type: String, year: Int?, row: JSONArray): String =
        "yr:${year ?: "na"}:${rowFingerprint(type, row)}"

    private fun rowFingerprint(type: String, row: JSONArray): String =
        RecordUtils.sha256("$type|${rowToEvidence(row)}")

    private fun listFamilyKey(url: String): String {
        return try {
            val uri = URI(url)
            val menuId = queryParam(url, "menuId")
            buildString {
                append(uri.path ?: "")
                if (!menuId.isNullOrBlank()) append("?menuId=").append(menuId)
            }
        } catch (_: Exception) {
            url.substringBefore('?')
        }
    }
    private fun parseCompetition(value: String): Pair<Double?, Double?> {
        val early = Regex("수시\\s*([0-9]+(?:\\.[0-9]+)?)").find(value)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
        val regular = Regex("정시\\s*([0-9]+(?:\\.[0-9]+)?)").find(value)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
        return early to regular
    }
    private fun intOrNull(value: String): Any = value.replace(",", "").trim().toIntOrNull() ?: JSONObject.NULL
    private fun numberOrNull(value: Double?): Any = value ?: JSONObject.NULL
    private fun valueOrNull(value: String): Any = value.trim().takeIf { it.isNotBlank() } ?: JSONObject.NULL
    private fun rowToEvidence(row: JSONArray): String {
        val values = mutableListOf<String>(); for (i in 0 until row.length()) values.add(row.optString(i))
        return values.joinToString(" | ").take(3000)
    }
}
