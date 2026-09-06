package com.admissionhub.collector.canonical

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject

/**
 * v0.10.0 canonical application candidate layer.
 *
 * Safety/quality rules:
 * - Jinhak application identity comes only from the already same-card-bound mission context.
 * - Provider labels are normalized only for comparison keys; raw labels are retained.
 * - No missing department/admission is invented.
 * - External collection never selects/reorders the user's six Hub slots.
 */
object CanonicalSixApplicationGraph {
    const val SCHEMA_VERSION = 1
    const val SLOT_COUNT = 6
    val CORE_LANES = listOf(
        "saved-application",
        "current-prediction",
        "mock-support",
        "actual-admit",
        "score-analysis"
    )

    data class MissionApplication(
        val identityKey: String,
        val year: Int,
        val university: String?,
        val campus: String?,
        val department: String?,
        val admission: String?,
        val admissionCategory: String?,
        val capacity: Int?,
        val confidence: String,
        val parseSource: String,
        val coverage: Set<String>
    )

    fun missionApplications(targets: List<JSONObject>, coverageRows: List<JSONObject>): List<MissionApplication> {
        val coverage = linkedMapOf<String, MutableSet<String>>()
        for (row in coverageRows) {
            val identity = row.optString("identityKey").takeIf { it.isNotBlank() && it != "null" } ?: continue
            val lane = row.optString("lane").takeIf { it.isNotBlank() && it != "reference" && it != "null" } ?: continue
            coverage.getOrPut(identity) { linkedSetOf() }.add(lane)
        }
        val contexts = linkedMapOf<String, JSONObject>()
        for (target in targets) {
            val identity = target.optString("identityKey").takeIf { it.isNotBlank() && it != "null" } ?: continue
            val context = target.optJSONObject("applicationContext") ?: continue
            if (context.optString("identityKey") != identity) continue
            val existing = contexts[identity]
            if (existing == null || contextScore(context) > contextScore(existing)) contexts[identity] = context
        }
        return contexts.entries.map { (identity, context) ->
            MissionApplication(
                identityKey = identity,
                year = context.optInt("year", 2027),
                university = nullable(context, "university"),
                campus = nullable(context, "campus"),
                department = nullable(context, "departmentRaw"),
                admission = nullable(context, "admission"),
                admissionCategory = nullable(context, "admissionCategory"),
                capacity = if (context.has("capacity") && !context.isNull("capacity")) context.optInt("capacity").takeIf { it >= 0 } else null,
                confidence = context.optString("confidence", "unknown").ifBlank { "unknown" },
                parseSource = context.optString("parseSource", "mission-context").ifBlank { "mission-context" },
                coverage = coverage[identity]?.toSet() ?: emptySet()
            )
        }.sortedWith(compareBy({ normalizeUniversityKey(it.university) }, { normalizeAdmissionKey(it.admission) }, { normalizeDepartmentKey(it.department) }, { it.identityKey }))
    }

    fun canonicalUniversityId(university: String?): String? = normalizeUniversityKey(university).takeIf { it.isNotBlank() }?.let {
        "uni-" + RecordUtils.sha256(it).take(24)
    }

    fun canonicalCampusId(universityId: String?, campus: String?): String? {
        val c = normalizeLoose(campus)
        return if (universityId.isNullOrBlank() || c.isBlank()) null else "campus-" + RecordUtils.sha256("$universityId|$c").take(24)
    }

    fun canonicalRecruitmentUnitId(universityId: String?, year: Int, department: String?): String? {
        val d = normalizeDepartmentKey(department)
        return if (universityId.isNullOrBlank() || d.isBlank()) null else "unit-" + RecordUtils.sha256("$year|$universityId|$d").take(24)
    }

    fun canonicalAdmissionTrackId(unitId: String?, year: Int, admission: String?, admissionCategory: String?): String? {
        val a = normalizeAdmissionKey(admission)
        val category = normalizeAdmissionKey(admissionCategory)
        return if (unitId.isNullOrBlank() || (a.isBlank() && category.isBlank())) null
        else "track-" + RecordUtils.sha256("$year|$unitId|$category|$a").take(24)
    }

    fun canonicalApplicationId(app: MissionApplication): String {
        val u = canonicalUniversityId(app.university) ?: "unknown-university"
        val c = canonicalCampusId(u, app.campus) ?: "no-campus"
        val d = canonicalRecruitmentUnitId(u, app.year, app.department) ?: "unknown-unit"
        val a = canonicalAdmissionTrackId(d, app.year, app.admission, app.admissionCategory) ?: "unknown-track"
        return "app-" + RecordUtils.sha256("${app.year}|$u|$c|$d|$a|${app.identityKey}").take(28)
    }

    fun normalizeUniversityKey(value: String?): String {
        var s = value.orEmpty().trim().replace(Regex("\\s+"), "")
        s = s.replace(Regex("\\[[^\\]]+\\]$"), "")
        if (s.startsWith("국립")) s = s.removePrefix("국립")
        s = s.replace("교육대학교", "교육대").replace("대학교", "대")
        return s.lowercase()
    }

    fun normalizeDepartmentKey(value: String?): String = normalizeLoose(value)

    fun normalizeAdmissionKey(value: String?): String = normalizeLoose(value)

    fun departmentMatchQuality(jinhak: String?, adiga: String?): String {
        val j = normalizeDepartmentKey(jinhak)
        val a = normalizeDepartmentKey(adiga)
        if (j.isBlank() || a.isBlank()) return "missing"
        if (j == a) return "exact"
        val suffixes = listOf("학과", "학부", "전공")
        if (suffixes.any { j + it == a || a + it == j }) return "suffix-equivalent"
        return "none"
    }

    fun admissionMatchQuality(jinhak: String?, adiga: String?): String {
        val j = normalizeAdmissionKey(jinhak)
        val a = normalizeAdmissionKey(adiga)
        if (j.isBlank() || a.isBlank()) return "missing"
        if (j == a) return "exact"
        if (j.length >= 2 && a.length >= 2 && (j.contains(a) || a.contains(j))) return "related"
        return "none"
    }

    fun displayLabel(university: String?, admission: String?, department: String?, campus: String?): String {
        val pieces = listOfNotNull(
            university?.takeIf { it.isNotBlank() },
            admission?.takeIf { it.isNotBlank() },
            department?.takeIf { it.isNotBlank() },
            campus?.takeIf { it.isNotBlank() }?.let { "[$it]" }
        )
        return pieces.joinToString(" · ").ifBlank { "미확인 지원안" }.take(220)
    }

    fun coverageJson(app: MissionApplication): JSONObject {
        val covered = JSONArray()
        CORE_LANES.filter { it in app.coverage }.forEach(covered::put)
        val missing = JSONArray()
        CORE_LANES.filterNot { it in app.coverage }.forEach(missing::put)
        return JSONObject()
            .put("required", JSONArray(CORE_LANES))
            .put("covered", covered)
            .put("missing", missing)
            .put("coveredCount", CORE_LANES.count { it in app.coverage })
            .put("complete", CORE_LANES.all { it in app.coverage })
    }

    private fun normalizeLoose(value: String?): String = value.orEmpty()
        .trim()
        .lowercase()
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\)]"), "")
        .replace(Regex("[^0-9a-z가-힣]"), "")

    private fun nullable(obj: JSONObject, key: String): String? =
        if (!obj.has(key) || obj.isNull(key)) null else obj.optString(key).trim().takeIf { it.isNotBlank() && it != "null" }

    private fun contextScore(context: JSONObject): Int = listOf("university", "departmentRaw", "admission", "campus")
        .count { key -> nullable(context, key) != null } * 10 +
        when (context.optString("confidence")) { "high" -> 3; "medium" -> 2; "low" -> 1; else -> 0 }
}
