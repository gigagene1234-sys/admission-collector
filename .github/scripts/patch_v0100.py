from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
CANON = ROOT / 'app/src/main/java/com/admissionhub/collector/canonical/CanonicalSixApplicationGraph.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)

main = MAIN.read_text()
store = STORE.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.9.26"',
    'private const val BUILD_CODE = 109260',
    'private fun finishUnifiedCollection(reason: String)',
    'fun unifiedStatus(sessionId: String): JSONObject',
    'CREATE TABLE IF NOT EXISTS canonical_entities',
    'CREATE TABLE IF NOT EXISTS jinhak_mission_coverage',
]:
    if token not in main and token not in store:
        raise SystemExit('v0.9.26 precondition failed: ' + token)

# ---------------------------------------------------------------------------
# New pure canonical graph helper. It never auto-selects the user's six slots.
# ---------------------------------------------------------------------------
CANON.write_text(r'''package com.admissionhub.collector.canonical

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
''')

# ---------------------------------------------------------------------------
# Version / label.
# ---------------------------------------------------------------------------
main = replace_once(main, 'private const val VERSION = "0.9.26"', 'private const val VERSION = "0.10.0"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 109260', 'private const val BUILD_CODE = 110000', 'main build code')
gradle = replace_once(gradle, 'versionCode = 109260', 'versionCode = 110000', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.9.26"', 'versionName = "0.10.0"', 'gradle version name')
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.26 Incomplete Coverage Recovery Fence',
    'Admission Hub v0.10.0 Canonical Six Graph',
    'manifest label'
)

# ---------------------------------------------------------------------------
# Local database v7 + canonical application / six-slot / quality audit tables.
# ---------------------------------------------------------------------------
store = replace_once(
    store,
    'import com.admissionhub.collector.canonical.ProviderEntityMapping\n',
    'import com.admissionhub.collector.canonical.ProviderEntityMapping\nimport com.admissionhub.collector.canonical.CanonicalSixApplicationGraph\n',
    'canonical helper import'
)
store = replace_once(store, '    6\n) {', '    7\n) {', 'database version')

schema_anchor = '''        db.execSQL("""\n            CREATE TABLE IF NOT EXISTS jinhak_mission_targets('''
schema_insert = '''        db.execSQL("""
            CREATE TABLE IF NOT EXISTS canonical_applications(
              session_id TEXT NOT NULL,
              application_identity_key TEXT NOT NULL,
              canonical_application_id TEXT NOT NULL,
              academic_year INTEGER NOT NULL,
              canonical_university_id TEXT,
              canonical_campus_id TEXT,
              canonical_recruitment_unit_id TEXT,
              canonical_admission_track_id TEXT,
              university TEXT,
              campus TEXT,
              department TEXT,
              admission TEXT,
              admission_category TEXT,
              capacity INTEGER,
              jinhak_confidence TEXT NOT NULL,
              parse_source TEXT NOT NULL,
              coverage_json TEXT NOT NULL,
              coverage_count INTEGER NOT NULL DEFAULT 0,
              adiga_binding_quality TEXT NOT NULL,
              adiga_match_count INTEGER NOT NULL DEFAULT 0,
              adiga_binding_json TEXT NOT NULL,
              quality_state TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(session_id,application_identity_key)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_canonical_apps_session_quality ON canonical_applications(session_id,quality_state,university,department)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_canonical_apps_canonical_id ON canonical_applications(canonical_application_id)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS hub_application_slots(
              slot INTEGER PRIMARY KEY,
              canonical_application_id TEXT NOT NULL,
              application_identity_key TEXT NOT NULL,
              display_label TEXT NOT NULL,
              user_pinned INTEGER NOT NULL DEFAULT 1,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_hub_slot_identity ON hub_application_slots(application_identity_key)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS hub_quality_audits(
              session_id TEXT PRIMARY KEY,
              audit_json TEXT NOT NULL,
              generated_at TEXT NOT NULL
            )
        """.trimIndent())

'''
store = replace_once(store, schema_anchor, schema_insert + schema_anchor, 'canonical application schema')
store = replace_once(
    store,
    '''        if (oldVersion < 6) {
            ensureFoundationSchema(db)
        }
''',
    '''        if (oldVersion < 6) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 7) {
            ensureFoundationSchema(db)
        }
''',
    'db upgrade v7'
)

methods_anchor = '''    private fun nullableInt(obj: JSONObject, key: String): Int? ='''
methods = r'''    private fun unifiedProviderRunId(sessionId: String, provider: String): String? {
        val column = if (provider == "adiga") "adiga_run_id" else if (provider == "jinhak") "jinhak_run_id" else return null
        return readableDatabase.rawQuery(
            "SELECT $column FROM unified_sessions WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c -> if (c.moveToFirst() && !c.isNull(0)) c.getString(0) else null }
    }

    fun rebuildCanonicalApplicationGraph(sessionId: String): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("error", "missing-session")
        val apps = CanonicalSixApplicationGraph.missionApplications(
            loadJinhakMissionTargets(sessionId),
            loadJinhakMissionCoverage(sessionId)
        )
        val adigaRunId = unifiedProviderRunId(sessionId, "adiga")
        val jinhakRunId = unifiedProviderRunId(sessionId, "jinhak")
        val byUniversity = apps.groupBy { CanonicalSixApplicationGraph.normalizeUniversityKey(it.university) }
        val matches = linkedMapOf<String, LinkedHashMap<String, JSONObject>>()
        val exactFingerprints = linkedMapOf<String, MutableSet<String>>()

        if (!adigaRunId.isNullOrBlank() && apps.isNotEmpty()) {
            readableDatabase.rawQuery(
                "SELECT fingerprint,COALESCE(year,-1),university,department,admission,record_type FROM records WHERE run_id=? AND university IS NOT NULL",
                arrayOf(adigaRunId)
            ).use { c ->
                while (c.moveToNext()) {
                    val university = if (c.isNull(2)) null else c.getString(2)
                    val candidates = byUniversity[CanonicalSixApplicationGraph.normalizeUniversityKey(university)].orEmpty()
                    if (candidates.isEmpty()) continue
                    val year = c.getInt(1)
                    val department = if (c.isNull(3)) null else c.getString(3)
                    val admission = if (c.isNull(4)) null else c.getString(4)
                    val recordType = if (c.isNull(5)) "unknown" else c.getString(5)
                    for (app in candidates) {
                        if (year > 0 && app.year > 0 && year != app.year) continue
                        val deptQuality = CanonicalSixApplicationGraph.departmentMatchQuality(app.department, department)
                        if (deptQuality == "none" || deptQuality == "missing") continue
                        val admissionQuality = CanonicalSixApplicationGraph.admissionMatchQuality(app.admission, admission)
                        if (admissionQuality == "none") continue
                        val matchClass = if (deptQuality == "exact" && admissionQuality == "exact") "accepted" else "provisional"
                        val signature = listOf(
                            CanonicalSixApplicationGraph.normalizeUniversityKey(university),
                            CanonicalSixApplicationGraph.normalizeDepartmentKey(department),
                            CanonicalSixApplicationGraph.normalizeAdmissionKey(admission)
                        ).joinToString("|")
                        val bucket = matches.getOrPut(app.identityKey) { linkedMapOf() }
                        val row = bucket[signature]
                        if (row == null) {
                            bucket[signature] = JSONObject()
                                .put("matchClass", matchClass)
                                .put("university", university ?: JSONObject.NULL)
                                .put("department", department ?: JSONObject.NULL)
                                .put("admission", admission ?: JSONObject.NULL)
                                .put("departmentMatch", deptQuality)
                                .put("admissionMatch", admissionQuality)
                                .put("recordCount", 1)
                                .put("recordTypes", JSONArray().put(recordType))
                        } else {
                            row.put("recordCount", row.optInt("recordCount", 0) + 1)
                            val types = row.optJSONArray("recordTypes") ?: JSONArray().also { row.put("recordTypes", it) }
                            if ((0 until types.length()).none { types.optString(it) == recordType }) types.put(recordType)
                            if (row.optString("matchClass") != "accepted" && matchClass == "accepted") row.put("matchClass", "accepted")
                        }
                        if (matchClass == "accepted") exactFingerprints.getOrPut(app.identityKey) { linkedSetOf() }.add(c.getString(0))
                    }
                }
            }
        }

        val db = writableDatabase
        db.beginTransaction()
        try {
            db.delete("canonical_applications", "session_id=?", arrayOf(sessionId))
            for (app in apps) {
                val universityId = CanonicalSixApplicationGraph.canonicalUniversityId(app.university)
                val campusId = CanonicalSixApplicationGraph.canonicalCampusId(universityId, app.campus)
                val unitId = CanonicalSixApplicationGraph.canonicalRecruitmentUnitId(universityId, app.year, app.department)
                val trackId = CanonicalSixApplicationGraph.canonicalAdmissionTrackId(unitId, app.year, app.admission, app.admissionCategory)
                val canonicalApplicationId = CanonicalSixApplicationGraph.canonicalApplicationId(app)
                val coverage = CanonicalSixApplicationGraph.coverageJson(app)
                val coverageCount = coverage.optInt("coveredCount", 0)
                val fullCoverage = coverage.optBoolean("complete", false)
                val matchRows = matches[app.identityKey]?.values?.toList().orEmpty()
                val acceptedSignatures = matchRows.count { it.optString("matchClass") == "accepted" }
                val provisionalSignatures = matchRows.count { it.optString("matchClass") == "provisional" }
                val bindingQuality = when {
                    acceptedSignatures == 1 -> "accepted"
                    acceptedSignatures > 1 -> "provisional"
                    provisionalSignatures > 0 -> "provisional"
                    else -> "provider-only"
                }
                val qualityState = when {
                    !fullCoverage -> "incomplete"
                    bindingQuality == "accepted" -> "accepted"
                    bindingQuality == "provisional" -> "provisional"
                    else -> "provider-only"
                }
                val bindingJson = JSONObject()
                    .put("schemaVersion", 1)
                    .put("officialBaseline", "adiga")
                    .put("bindingQuality", bindingQuality)
                    .put("acceptedSignatures", acceptedSignatures)
                    .put("provisionalSignatures", provisionalSignatures)
                    .put("matches", JSONArray(matchRows))
                    .put("doNotInferMissingBindings", true)

                if (universityId != null && app.university != null) upsertCanonicalEntity(
                    CanonicalEntity(universityId, com.admissionhub.collector.canonical.CanonicalEntityType.UNIVERSITY, null, app.university),
                    JSONObject().put("source", "jinhak-same-card-mission").put("rawLabelPreserved", true)
                )
                if (campusId != null && app.campus != null) upsertCanonicalEntity(
                    CanonicalEntity(campusId, com.admissionhub.collector.canonical.CanonicalEntityType.CAMPUS, null, app.campus, universityId),
                    JSONObject().put("source", "jinhak-same-card-mission")
                )
                if (unitId != null && app.department != null) upsertCanonicalEntity(
                    CanonicalEntity(unitId, com.admissionhub.collector.canonical.CanonicalEntityType.RECRUITMENT_UNIT, app.year, app.department, campusId ?: universityId),
                    JSONObject().put("source", "jinhak-same-card-mission").put("canonicalization", "comparison-key-only")
                )
                if (trackId != null && app.admission != null) upsertCanonicalEntity(
                    CanonicalEntity(trackId, com.admissionhub.collector.canonical.CanonicalEntityType.ADMISSION_TRACK, app.year, app.admission, unitId),
                    JSONObject().put("source", "jinhak-same-card-mission").put("admissionCategory", app.admissionCategory ?: JSONObject.NULL)
                )

                val cv = ContentValues().apply {
                    put("session_id", sessionId)
                    put("application_identity_key", app.identityKey)
                    put("canonical_application_id", canonicalApplicationId)
                    put("academic_year", app.year)
                    putNullable("canonical_university_id", universityId)
                    putNullable("canonical_campus_id", campusId)
                    putNullable("canonical_recruitment_unit_id", unitId)
                    putNullable("canonical_admission_track_id", trackId)
                    putNullable("university", app.university)
                    putNullable("campus", app.campus)
                    putNullable("department", app.department)
                    putNullable("admission", app.admission)
                    putNullable("admission_category", app.admissionCategory)
                    if (app.capacity == null) putNull("capacity") else put("capacity", app.capacity)
                    put("jinhak_confidence", app.confidence)
                    put("parse_source", app.parseSource)
                    put("coverage_json", coverage.toString())
                    put("coverage_count", coverageCount)
                    put("adiga_binding_quality", bindingQuality)
                    put("adiga_match_count", matchRows.size)
                    put("adiga_binding_json", bindingJson.toString())
                    put("quality_state", qualityState)
                    put("updated_at", Instant.now().toString())
                }
                db.insertOrThrow("canonical_applications", null, cv)

                if (!jinhakRunId.isNullOrBlank()) {
                    val update = ContentValues().apply {
                        put("quality_state", qualityState)
                        putNullable("canonical_university_id", universityId)
                        putNullable("canonical_department_id", unitId)
                        putNullable("canonical_admission_id", trackId)
                    }
                    db.update("records", update, "run_id=? AND application_identity_key=?", arrayOf(jinhakRunId, app.identityKey))
                }
                if (bindingQuality == "accepted" && !adigaRunId.isNullOrBlank()) {
                    exactFingerprints[app.identityKey].orEmpty().forEach { fp ->
                        val update = ContentValues().apply {
                            put("quality_state", "accepted")
                            putNullable("canonical_university_id", universityId)
                            putNullable("canonical_department_id", unitId)
                            putNullable("canonical_admission_id", trackId)
                            put("application_identity_key", app.identityKey)
                        }
                        db.update("records", update, "run_id=? AND fingerprint=?", arrayOf(adigaRunId, fp))
                    }
                }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        val audit = refreshCanonicalQualityAudit(sessionId)
        return canonicalHubSummary(sessionId).put("rebuild", JSONObject()
            .put("missionApplications", apps.size)
            .put("qualityAuditGenerated", true)
            .put("qualityAuditPublishState", audit.optString("publishState")))
    }

    fun loadCanonicalApplicationCandidates(sessionId: String): JSONArray {
        val out = JSONArray()
        if (sessionId.isBlank()) return out
        readableDatabase.rawQuery(
            "SELECT application_identity_key,canonical_application_id,academic_year,university,campus,department,admission,admission_category,capacity,jinhak_confidence,coverage_json,adiga_binding_quality,adiga_match_count,adiga_binding_json,quality_state,updated_at FROM canonical_applications WHERE session_id=? ORDER BY university,admission,department,application_identity_key",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                out.put(JSONObject()
                    .put("applicationIdentityKey", c.getString(0))
                    .put("canonicalApplicationId", c.getString(1))
                    .put("academicYear", c.getInt(2))
                    .put("university", if (c.isNull(3)) JSONObject.NULL else c.getString(3))
                    .put("campus", if (c.isNull(4)) JSONObject.NULL else c.getString(4))
                    .put("department", if (c.isNull(5)) JSONObject.NULL else c.getString(5))
                    .put("admission", if (c.isNull(6)) JSONObject.NULL else c.getString(6))
                    .put("admissionCategory", if (c.isNull(7)) JSONObject.NULL else c.getString(7))
                    .put("capacity", if (c.isNull(8)) JSONObject.NULL else c.getInt(8))
                    .put("jinhakConfidence", c.getString(9))
                    .put("coverage", runCatching { JSONObject(c.getString(10)) }.getOrDefault(JSONObject()))
                    .put("adigaBindingQuality", c.getString(11))
                    .put("adigaMatchCount", c.getInt(12))
                    .put("adigaBinding", runCatching { JSONObject(c.getString(13)) }.getOrDefault(JSONObject()))
                    .put("qualityState", c.getString(14))
                    .put("displayLabel", CanonicalSixApplicationGraph.displayLabel(
                        if (c.isNull(3)) null else c.getString(3),
                        if (c.isNull(6)) null else c.getString(6),
                        if (c.isNull(5)) null else c.getString(5),
                        if (c.isNull(4)) null else c.getString(4)
                    ))
                    .put("updatedAt", c.getString(15)))
            }
        }
        return out
    }

    fun loadHubApplicationSlots(): JSONArray {
        val rows = linkedMapOf<Int, JSONObject>()
        readableDatabase.rawQuery(
            "SELECT slot,canonical_application_id,application_identity_key,display_label,user_pinned,updated_at FROM hub_application_slots ORDER BY slot",
            emptyArray()
        ).use { c ->
            while (c.moveToNext()) rows[c.getInt(0)] = JSONObject()
                .put("slot", c.getInt(0))
                .put("occupied", true)
                .put("canonicalApplicationId", c.getString(1))
                .put("applicationIdentityKey", c.getString(2))
                .put("displayLabel", c.getString(3))
                .put("userPinned", c.getInt(4) != 0)
                .put("updatedAt", c.getString(5))
        }
        val out = JSONArray()
        for (slot in 1..CanonicalSixApplicationGraph.SLOT_COUNT) {
            out.put(rows[slot] ?: JSONObject().put("slot", slot).put("occupied", false).put("userPinned", false))
        }
        return out
    }

    fun setHubApplicationSlot(sessionId: String, slot: Int, identityKey: String): JSONObject {
        require(slot in 1..CanonicalSixApplicationGraph.SLOT_COUNT) { "slot out of range" }
        val candidate = readableDatabase.rawQuery(
            "SELECT canonical_application_id,university,admission,department,campus FROM canonical_applications WHERE session_id=? AND application_identity_key=? LIMIT 1",
            arrayOf(sessionId, identityKey)
        ).use { c ->
            if (!c.moveToFirst()) null else JSONObject()
                .put("canonicalApplicationId", c.getString(0))
                .put("university", if (c.isNull(1)) JSONObject.NULL else c.getString(1))
                .put("admission", if (c.isNull(2)) JSONObject.NULL else c.getString(2))
                .put("department", if (c.isNull(3)) JSONObject.NULL else c.getString(3))
                .put("campus", if (c.isNull(4)) JSONObject.NULL else c.getString(4))
        } ?: return JSONObject().put("ok", false).put("error", "candidate-not-found")

        fun existingSlotRow(db: SQLiteDatabase, targetSlot: Int): JSONObject? = db.rawQuery(
            "SELECT canonical_application_id,application_identity_key,display_label,user_pinned,updated_at FROM hub_application_slots WHERE slot=? LIMIT 1",
            arrayOf(targetSlot.toString())
        ).use { c -> if (!c.moveToFirst()) null else JSONObject()
            .put("canonicalApplicationId", c.getString(0))
            .put("applicationIdentityKey", c.getString(1))
            .put("displayLabel", c.getString(2))
            .put("userPinned", c.getInt(3) != 0)
            .put("updatedAt", c.getString(4)) }

        val db = writableDatabase
        db.beginTransaction()
        try {
            val currentAtTarget = existingSlotRow(db, slot)
            val duplicateSlot = db.rawQuery(
                "SELECT slot FROM hub_application_slots WHERE application_identity_key=? LIMIT 1",
                arrayOf(identityKey)
            ).use { c -> if (c.moveToFirst()) c.getInt(0) else null }
            if (duplicateSlot != null && duplicateSlot != slot) {
                if (currentAtTarget == null) {
                    db.delete("hub_application_slots", "slot=?", arrayOf(duplicateSlot.toString()))
                } else {
                    val moved = ContentValues().apply {
                        put("slot", duplicateSlot)
                        put("canonical_application_id", currentAtTarget.getString("canonicalApplicationId"))
                        put("application_identity_key", currentAtTarget.getString("applicationIdentityKey"))
                        put("display_label", currentAtTarget.getString("displayLabel"))
                        put("user_pinned", 1)
                        put("updated_at", Instant.now().toString())
                    }
                    db.insertWithOnConflict("hub_application_slots", null, moved, SQLiteDatabase.CONFLICT_REPLACE)
                }
            }
            val display = CanonicalSixApplicationGraph.displayLabel(
                candidate.optString("university").takeIf { it.isNotBlank() && it != "null" },
                candidate.optString("admission").takeIf { it.isNotBlank() && it != "null" },
                candidate.optString("department").takeIf { it.isNotBlank() && it != "null" },
                candidate.optString("campus").takeIf { it.isNotBlank() && it != "null" }
            )
            val cv = ContentValues().apply {
                put("slot", slot)
                put("canonical_application_id", candidate.getString("canonicalApplicationId"))
                put("application_identity_key", identityKey)
                put("display_label", display)
                put("user_pinned", 1)
                put("updated_at", Instant.now().toString())
            }
            db.insertWithOnConflict("hub_application_slots", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        val audit = refreshCanonicalQualityAudit(sessionId)
        return JSONObject().put("ok", true).put("slot", slot).put("qualityAudit", audit)
    }

    fun clearHubApplicationSlot(sessionId: String, slot: Int): JSONObject {
        require(slot in 1..CanonicalSixApplicationGraph.SLOT_COUNT) { "slot out of range" }
        writableDatabase.delete("hub_application_slots", "slot=?", arrayOf(slot.toString()))
        return JSONObject().put("ok", true).put("slot", slot).put("qualityAudit", refreshCanonicalQualityAudit(sessionId))
    }

    fun refreshCanonicalQualityAudit(sessionId: String): JSONObject {
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val byIdentity = linkedMapOf<String, JSONObject>()
        var accepted = 0
        var provisional = 0
        var providerOnly = 0
        var incomplete = 0
        var fullCoverage = 0
        for (i in 0 until candidates.length()) {
            val item = candidates.optJSONObject(i) ?: continue
            byIdentity[item.optString("applicationIdentityKey")] = item
            if (item.optJSONObject("coverage")?.optBoolean("complete", false) == true) fullCoverage += 1
            when (item.optString("qualityState")) {
                "accepted" -> accepted += 1
                "provisional" -> provisional += 1
                "provider-only" -> providerOnly += 1
                else -> incomplete += 1
            }
        }
        val slots = loadHubApplicationSlots()
        var selected = 0
        var resolvable = 0
        var selectedFullCoverage = 0
        var selectedAccepted = 0
        var selectedProvisional = 0
        var selectedProviderOnly = 0
        val selectedIdentities = linkedSetOf<String>()
        val staleSlots = JSONArray()
        for (i in 0 until slots.length()) {
            val slot = slots.optJSONObject(i) ?: continue
            if (!slot.optBoolean("occupied", false)) continue
            selected += 1
            val identity = slot.optString("applicationIdentityKey")
            if (identity.isNotBlank()) selectedIdentities += identity
            val candidate = byIdentity[identity]
            if (candidate == null) {
                staleSlots.put(slot.optInt("slot"))
                continue
            }
            resolvable += 1
            if (candidate.optJSONObject("coverage")?.optBoolean("complete", false) == true) selectedFullCoverage += 1
            when (candidate.optString("qualityState")) {
                "accepted" -> selectedAccepted += 1
                "provisional" -> selectedProvisional += 1
                "provider-only" -> selectedProviderOnly += 1
            }
        }
        val blockers = JSONArray()
        if (selected < CanonicalSixApplicationGraph.SLOT_COUNT) blockers.put("six-application-selection-incomplete")
        if (selectedIdentities.size != selected) blockers.put("duplicate-application-slot")
        if (staleSlots.length() > 0) blockers.put("stale-slot-binding")
        if (selectedFullCoverage < selected) blockers.put("selected-application-core-coverage-incomplete")
        val warnings = JSONArray()
        if (selectedProvisional > 0) warnings.put("selected-provisional-adiga-binding")
        if (selectedProviderOnly > 0) warnings.put("selected-provider-only-no-safe-adiga-binding")
        val observations = observationStats(sessionId)
        if (observations.optInt("unknownOrPotential", 0) > 0) warnings.put("unclassified-observations-preserved")
        val hubReady = selected == CanonicalSixApplicationGraph.SLOT_COUNT &&
            selectedIdentities.size == CanonicalSixApplicationGraph.SLOT_COUNT &&
            resolvable == CanonicalSixApplicationGraph.SLOT_COUNT &&
            selectedFullCoverage == CanonicalSixApplicationGraph.SLOT_COUNT
        val publishState = when {
            !hubReady && selected < CanonicalSixApplicationGraph.SLOT_COUNT -> "WAITING_FOR_USER_SELECTION"
            !hubReady -> "BLOCKED_QUALITY"
            selectedProvisional > 0 || selectedProviderOnly > 0 -> "READY_WITH_WARNINGS"
            else -> "READY"
        }
        val audit = JSONObject()
            .put("schemaVersion", 1)
            .put("generatedAt", Instant.now().toString())
            .put("candidateCount", candidates.length())
            .put("fullCoreCoverageCandidates", fullCoverage)
            .put("candidateQuality", JSONObject()
                .put("accepted", accepted)
                .put("provisional", provisional)
                .put("providerOnly", providerOnly)
                .put("incomplete", incomplete))
            .put("sixSlots", JSONObject()
                .put("required", CanonicalSixApplicationGraph.SLOT_COUNT)
                .put("selected", selected)
                .put("uniqueSelected", selectedIdentities.size)
                .put("resolvable", resolvable)
                .put("fullCoreCoverage", selectedFullCoverage)
                .put("accepted", selectedAccepted)
                .put("provisional", selectedProvisional)
                .put("providerOnly", selectedProviderOnly)
                .put("staleSlots", staleSlots)
                .put("userControlled", true)
                .put("externalCollectionMayMutate", false))
            .put("hubReady", hubReady)
            .put("publishState", publishState)
            .put("blockers", blockers)
            .put("warnings", warnings)
            .put("observationCoverage", observations)
            .put("predictionDoesNotOverwriteHistoricalActual", true)
            .put("doNotInferMissingBindings", true)
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            put("audit_json", audit.toString())
            put("generated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("hub_quality_audits", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        return audit
    }

    fun canonicalHubSummary(sessionId: String): JSONObject {
        val candidates = loadCanonicalApplicationCandidates(sessionId)
        val slots = loadHubApplicationSlots()
        val audit = readableDatabase.rawQuery(
            "SELECT audit_json FROM hub_quality_audits WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c ->
            if (c.moveToFirst()) runCatching { JSONObject(c.getString(0)) }.getOrNull() else null
        } ?: refreshCanonicalQualityAudit(sessionId)
        return JSONObject()
            .put("schemaVersion", 1)
            .put("candidateGraph", candidates)
            .put("slots", slots)
            .put("qualityAudit", audit)
            .put("slotPolicy", JSONObject()
                .put("slots", CanonicalSixApplicationGraph.SLOT_COUNT)
                .put("userControlsAddChangeReplaceOrder", true)
                .put("externalCollectionAutoSelection", false))
    }

'''
store = replace_once(store, methods_anchor, methods + methods_anchor, 'canonical graph store methods')

status_anchor = '''        out.put("jinhakDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_CRAWL_DIAGNOSTICS"))
            .put("jinhakAuthDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_AUTH_DIAGNOSTICS"))
            .put("jinhakTerminalSummary", latestSyncStateDetail(sessionId, "JINHAK_TERMINAL_SEAL"))
        return out
'''
status_new = '''        out.put("jinhakDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_CRAWL_DIAGNOSTICS"))
            .put("jinhakAuthDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_AUTH_DIAGNOSTICS"))
            .put("jinhakTerminalSummary", latestSyncStateDetail(sessionId, "JINHAK_TERMINAL_SEAL"))
            .put("canonicalHub", canonicalHubSummary(sessionId))
        return out
'''
store = replace_once(store, status_anchor, status_new, 'unified status canonical hub')
store = store.replace('\\"contractVersion\\":3,\\"purpose\\":\\"assistant-xlsx-dashboard-generation\\"', '\\"contractVersion\\":4,\\"purpose\\":\\"canonical-six-application-hub-generation\\"')
store = store.replace('\\"recommendedWorkbookSheets\\":[\\"Dashboard\\",\\"ApplicationMissions\\",\\"UnifiedRecords\\",\\"JinhakPredictions\\",\\"HistoricalResults\\",\\"Observations\\",\\"Coverage\\",\\"Errors\\"]', '\\"recommendedWorkbookSheets\\":[\\"Dashboard\\",\\"SixApplications\\",\\"CanonicalApplications\\",\\"ApplicationMissions\\",\\"UnifiedRecords\\",\\"JinhakPredictions\\",\\"HistoricalResults\\",\\"Observations\\",\\"Coverage\\",\\"QualityAudit\\",\\"Errors\\"]')

# ---------------------------------------------------------------------------
# Main UI: visible six-slot state + explicit user-managed slot picker.
# ---------------------------------------------------------------------------
main = replace_once(
    main,
    '''    private lateinit var realJinhakAuthProbeButton: Button
''',
    '''    private lateinit var realJinhakAuthProbeButton: Button
    private lateinit var hubState: TextView
    private lateinit var hubManageButton: Button
''',
    'hub ui fields'
)
main = replace_once(
    main,
    '''        buildUi()
        slowLanePool = JinhakSlowLanePool''',
    '''        buildUi()
        handler.postDelayed({ rebuildCanonicalHubFromLatestSessionIfReady("app-start") }, 1800L)
        slowLanePool = JinhakSlowLanePool''',
    'startup hub rebuild'
)

ui_anchor = '''        status = TextView(this).apply {
            text = "Admission Collector v$VERSION 준비 중"
            setPadding(8, 8, 8, 8)
        }
'''
ui_new = '''        val hubRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        hubState = TextView(this).apply {
            text = "지원 6장: 데이터 준비 중"
            setPadding(8, 8, 8, 8)
        }
        hubManageButton = Button(this).apply {
            text = "지원 6장 관리"
            setOnClickListener { showHubSixManager() }
        }
        hubRow.addView(hubState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        hubRow.addView(hubManageButton)

        status = TextView(this).apply {
            text = "Admission Hub v$VERSION 준비 중"
            setPadding(8, 8, 8, 8)
        }
'''
main = replace_once(main, ui_anchor, ui_new, 'hub row')
main = replace_once(
    main,
    '''        root.addView(actions3)
        root.addView(status)
''',
    '''        root.addView(actions3)
        root.addView(hubRow)
        root.addView(status)
''',
    'add hub row'
)

hub_helpers_anchor = '''    @Suppress("SetJavaScriptEnabled")
    private fun configureWebView() {
'''
hub_helpers = r'''    private fun rebuildCanonicalHubFromLatestSessionIfReady(trigger: String) {
        if (unifiedRunning || batchRunning) return
        val sessionId = localStore.latestUnifiedSession()
        if (sessionId.isNullOrBlank()) {
            refreshHubState(null)
            return
        }
        val persisted = localStore.jinhakMissionCoveragePersistenceSummary(sessionId)
        if (persisted.optInt("persistedIdentities", 0) <= 0) {
            refreshHubState(sessionId)
            return
        }
        val summary = runCatching { localStore.rebuildCanonicalApplicationGraph(sessionId) }.getOrElse { error ->
            recordRuntimeEvent("canonical-hub-rebuild-failed", JSONObject()
                .put("trigger", trigger.take(80))
                .put("exceptionClass", error.javaClass.name.take(120)))
            localStore.canonicalHubSummary(sessionId)
        }
        refreshHubState(sessionId, summary)
    }

    private fun refreshHubState(sessionId: String?, supplied: JSONObject? = null) {
        if (!::hubState.isInitialized) return
        if (sessionId.isNullOrBlank()) {
            hubState.text = "지원 6장: 아직 통합 수집 데이터가 없습니다."
            return
        }
        val summary = supplied ?: localStore.canonicalHubSummary(sessionId)
        val audit = summary.optJSONObject("qualityAudit") ?: JSONObject()
        val slots = audit.optJSONObject("sixSlots") ?: JSONObject()
        val selected = slots.optInt("selected", 0)
        val candidates = audit.optInt("candidateCount", 0)
        val publish = audit.optString("publishState", "WAITING_FOR_USER_SELECTION")
        val readyText = when (publish) {
            "READY" -> "Hub 준비 완료"
            "READY_WITH_WARNINGS" -> "Hub 준비 · 일부 결합 확인 필요"
            "BLOCKED_QUALITY" -> "품질 점검 필요"
            else -> "6장 선택 필요"
        }
        hubState.text = "지원 6장 $selected/6 · 후보 $candidates · $readyText"
    }

    private fun showHubSixManager() {
        val sessionId = localStore.latestUnifiedSession()
        if (sessionId.isNullOrBlank()) {
            Toast.makeText(this, "먼저 통합 수집을 완료해주세요.", Toast.LENGTH_LONG).show()
            return
        }
        val summary = if (localStore.canonicalHubSummary(sessionId).optJSONArray("candidateGraph")?.length() == 0) {
            localStore.rebuildCanonicalApplicationGraph(sessionId)
        } else localStore.canonicalHubSummary(sessionId)
        val slots = summary.optJSONArray("slots") ?: JSONArray()
        val items = Array(7) { "" }
        for (slot in 1..6) {
            val row = slots.optJSONObject(slot - 1)
            items[slot - 1] = if (row?.optBoolean("occupied", false) == true) {
                "$slot. ${row.optString("displayLabel")}"
            } else "$slot. — 비어 있음 —"
        }
        items[6] = "품질 재분석 / 상태 새로고침"
        AlertDialog.Builder(this)
            .setTitle("지원 6장 관리 · 수집기가 자동 변경하지 않습니다")
            .setItems(items) { _, which ->
                if (which in 0..5) showHubCandidatePicker(sessionId, which + 1)
                else rebuildCanonicalHubFromLatestSessionIfReady("manual-refresh")
            }
            .setNegativeButton("닫기", null)
            .show()
    }

    private fun showHubCandidatePicker(sessionId: String, slot: Int) {
        val candidates = localStore.loadCanonicalApplicationCandidates(sessionId)
        if (candidates.length() == 0) {
            Toast.makeText(this, "선택 가능한 canonical 지원안이 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        val labels = Array(candidates.length() + 1) { index ->
            if (index == 0) "— 이 슬롯 비우기 —"
            else {
                val item = candidates.optJSONObject(index - 1) ?: JSONObject()
                val quality = item.optString("qualityState", "unknown")
                "${item.optString("displayLabel", "미확인 지원안")} · $quality"
            }
        }
        AlertDialog.Builder(this)
            .setTitle("$slot번 지원안 선택")
            .setItems(labels) { _, which ->
                val result = if (which == 0) {
                    localStore.clearHubApplicationSlot(sessionId, slot)
                } else {
                    val item = candidates.optJSONObject(which - 1) ?: JSONObject()
                    localStore.setHubApplicationSlot(sessionId, slot, item.optString("applicationIdentityKey"))
                }
                val summary = localStore.canonicalHubSummary(sessionId)
                refreshHubState(sessionId, summary)
                publishHubAuditState(sessionId, summary, "slot-$slot")
                if (!result.optBoolean("ok", false)) {
                    Toast.makeText(this, "지원안 변경에 실패했습니다: ${result.optString("error", "unknown")}", Toast.LENGTH_LONG).show()
                } else {
                    handler.postDelayed({ showHubSixManager() }, 120L)
                }
            }
            .setNegativeButton("취소", null)
            .show()
    }

    private fun publishHubAuditState(sessionId: String, summary: JSONObject, trigger: String) {
        val audit = summary.optJSONObject("qualityAudit") ?: return
        val ready = audit.optBoolean("hubReady", false)
        localStore.recordSyncState(
            sessionId,
            UnifiedSyncState.HUB_PUBLISH.name,
            null,
            JSONObject()
                .put("trigger", trigger.take(80))
                .put("publishState", audit.optString("publishState"))
                .put("hubReady", ready)
                .put("sixSlots", audit.optJSONObject("sixSlots") ?: JSONObject())
                .put("externalCollectionAutoSelection", false),
            !ready
        )
        if (ready) {
            localStore.updateUnifiedSession(sessionId, "completed", "completed", "hub-ready-after-user-selection")
            localStore.recordSyncState(
                sessionId,
                UnifiedSyncState.COMPLETE.name,
                null,
                JSONObject().put("trigger", trigger.take(80)).put("hubReady", true),
                false
            )
        }
    }

'''
main = replace_once(main, hub_helpers_anchor, hub_helpers + hub_helpers_anchor, 'hub helper functions')

# Finish flow now performs the roadmap's CANONICAL_MERGE -> QUALITY_AUDIT -> HUB_PUBLISH.
finish_old = '''            localStore.updateUnifiedSession(sessionId, "completed", "completed", reason)
            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit().putBoolean("resumeUnified", false).apply()

            val summary = localStore.unifiedStatus(sessionId)
'''
finish_new = '''            localStore.recordSyncState(
                sessionId,
                UnifiedSyncState.CANONICAL_MERGE.name,
                null,
                JSONObject().put("source", "jinhak-mission-ledger+adiga-official-baseline").put("doNotInferMissingBindings", true),
                false
            )
            val canonicalSummary = localStore.rebuildCanonicalApplicationGraph(sessionId)
            val qualityAudit = canonicalSummary.optJSONObject("qualityAudit") ?: JSONObject()
            localStore.recordSyncState(
                sessionId,
                UnifiedSyncState.QUALITY_AUDIT.name,
                null,
                qualityAudit,
                false
            )
            val hubReady = qualityAudit.optBoolean("hubReady", false)
            localStore.recordSyncState(
                sessionId,
                UnifiedSyncState.HUB_PUBLISH.name,
                null,
                JSONObject()
                    .put("publishState", qualityAudit.optString("publishState"))
                    .put("hubReady", hubReady)
                    .put("sixSlots", qualityAudit.optJSONObject("sixSlots") ?: JSONObject())
                    .put("externalCollectionAutoSelection", false),
                !hubReady
            )
            localStore.updateUnifiedSession(sessionId, if (hubReady) "completed" else "hub-publish", "completed", reason)
            if (hubReady) {
                localStore.recordSyncState(sessionId, UnifiedSyncState.COMPLETE.name, null, JSONObject().put("hubReady", true), false)
            }
            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit().putBoolean("resumeUnified", false).apply()
            refreshHubState(sessionId, canonicalSummary)

            val summary = localStore.unifiedStatus(sessionId)
'''
main = replace_once(main, finish_old, finish_new, 'canonical finish sequence')
main = replace_once(
    main,
    '''            status.text = "통합 수집 종료 완료 · 전체 데이터는 SQLite에 보존됨 · JSON 저장 시 메모리에 올리지 않고 스트리밍합니다."
''',
    '''            val hubAudit = summary.optJSONObject("canonicalHub")?.optJSONObject("qualityAudit") ?: JSONObject()
            val selected = hubAudit.optJSONObject("sixSlots")?.optInt("selected", 0) ?: 0
            status.text = if (hubAudit.optBoolean("hubReady", false)) {
                "통합 수집 + canonical merge + quality audit 완료 · 지원 6장 Hub 준비 완료."
            } else {
                "통합 수집 + canonical merge 완료 · 지원 6장 $selected/6 선택 후 Hub 게시가 완료됩니다."
            }
''',
    'finish status'
)

MAIN.write_text(main)
STORE.write_text(store)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

# Static postconditions.
checks = {
    'version': 'private const val VERSION = "0.10.0"' in main and 'versionName = "0.10.0"' in gradle,
    'build': 'private const val BUILD_CODE = 110000' in main and 'versionCode = 110000' in gradle,
    'canonical helper': CANON.exists() and 'object CanonicalSixApplicationGraph' in CANON.read_text(),
    'db v7': 'CREATE TABLE IF NOT EXISTS canonical_applications' in store and 'CREATE TABLE IF NOT EXISTS hub_application_slots' in store and 'CREATE TABLE IF NOT EXISTS hub_quality_audits' in store,
    'no auto select': 'externalCollectionAutoSelection' in main and 'externalCollectionMayMutate' in store,
    'quality audit': 'fun refreshCanonicalQualityAudit' in store and 'UnifiedSyncState.QUALITY_AUDIT.name' in main,
    'hub ui': '지원 6장 관리' in main and 'showHubCandidatePicker' in main,
}
failed = [k for k, v in checks.items() if not v]
if failed:
    raise SystemExit('v0.10.0 postcondition failure: ' + ', '.join(failed))

print('v0.10.0 canonical six graph patch applied')
