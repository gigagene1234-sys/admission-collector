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
        "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2026",
        "https://www.adiga.kr/ucp/cls/uni/classUnivView.do?menuId=PCCLSINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/cls/uni/classUnivView.do?menuId=PCCLSINF2000&searchSyr=2026",
        "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2027",
        "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2026",
        "https://www.adiga.kr/sco/agu/univScoScaAnlsView.do?menuId=PCSCOAGU2000",
        "https://www.adiga.kr/uct/ces/archiveView.do?menuId=PCUCTCES1000",
        "https://www.adiga.kr/uct/acd/adc/characteristicsView.do?menuId=PCUCTACD1100",
        "https://www.adiga.kr/uct/acd/ueg/univEtenGuideView.do?menuId=PCUCTACD3100",
        "https://www.adiga.kr/uct/acd/ade/criteriaAndResultView.do?menuId=PCUCTACD2000"
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

    override fun classify(snapshot: JSONObject): String {
        val url = snapshot.optString("url")
        return when {
            url.contains("/ucp/uvt/uni/univView.do") -> "adiga-university-list"
            url.contains("/ucp/cls/uni/classUnivView.do") -> "adiga-department-list"
            url.contains("/ucp/prc/uni/admssUnivView.do") -> "adiga-admission-list"
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
                .put("department", JSONObject.NULL)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
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
                .put("department", department)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
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
            val metrics = JSONObject()
                .put("holisticRecruitment", intOrNull(row.optString(1)))
                .put("curriculumRecruitment", intOrNull(row.optString(2)))
                .put("csatRecruitment", intOrNull(row.optString(3)))
                .put("registeredAt", valueOrNull(row.optString(4)))
                .put("columnLabels", JSONArray(labels))
            out.put(indexRecord("criteria-result-index", university, metrics, snapshot, row))
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
                .put("department", JSONObject.NULL)
                .put("admission", "대학별 장애인 전형")
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun indexRecord(type: String, university: String, metrics: JSONObject, snapshot: JSONObject, row: JSONArray): JSONObject = JSONObject()
        .put("recordType", type).put("year", JSONObject.NULL).put("university", university)
        .put("department", JSONObject.NULL).put("admission", JSONObject.NULL).put("metrics", metrics)
        .put("confidence", "high").put("sourcePage", snapshot.optString("url")).put("rawEvidence", rowToEvidence(row))

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

    private fun normalizeUniversityCell(value: String): String = value.replace(Regex("\\s+\\["), "[").replace(Regex("\\s+"), " ").trim()
    private fun looksLikeUniversity(value: String): Boolean {
        if (value.isBlank() || value.contains("대학명을 클릭") || value == "일반대학" || value == "전문대학") return false
        return Regex("(대학교|대학)(?:\\[(?:본교|분교|제\\d+캠퍼스)\\])?$").containsMatchIn(value)
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
