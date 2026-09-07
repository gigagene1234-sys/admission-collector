from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
EVID = ROOT / 'app/src/main/java/com/admissionhub/collector/canonical/AdigaOfficialAdmissionEvidence.kt'
POLICY = ROOT / 'app/src/main/java/com/admissionhub/collector/canonical/AdigaOfficialTableBindingPolicy.kt'
TEST = ROOT / 'app/src/test/java/com/admissionhub/collector/canonical/AdigaOfficialTableBindingPolicyTest.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, found {count}')
    return text.replace(old, new, 1)

main = MAIN.read_text()
store = STORE.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.10.2"',
    'private const val BUILD_CODE = 110020',
    'fun rebuildCanonicalApplicationGraph(sessionId: String): JSONObject',
    'officialRowBoundCurrent',
    'sameRowRequiredForOfficialAccepted',
    'Admission Hub v0.10.2 Auth Ownership Repair',
]:
    if token not in main and token not in store and token not in manifest:
        raise SystemExit('v0.10.2 precondition failed: ' + token)

# ---------------------------------------------------------------------------
# Pure policy: explicit same-official-table scope inheritance only.
# ---------------------------------------------------------------------------
POLICY.parent.mkdir(parents=True, exist_ok=True)
POLICY.write_text(r'''package com.admissionhub.collector.canonical

/**
 * Pure policy for v0.10.3 official-table structural binding.
 *
 * Accepted application binding is still conservative:
 * 1) same row contains both department and admission, OR
 * 2) an explicit scope row such as "모집단위 | <전형>" / "해당전형 | <전형>"
 *    starts a block in the SAME official table and the target department appears before
 *    the next explicit scope row.
 *
 * University-wide mentions without an explicit scope row never propagate to departments.
 */
object AdigaOfficialTableBindingPolicy {
    data class SegmentBinding(
        val scopeRowIndex: Int,
        val departmentRowIndex: Int,
        val admissionMatch: String,
        val departmentMatch: String,
        val scopeLabel: String
    )

    fun findExplicitSegmentBindings(
        rows: List<List<String>>,
        department: String?,
        admission: String?,
        admissionCategory: String?
    ): List<SegmentBinding> {
        val out = mutableListOf<SegmentBinding>()
        val declarationIndexes = rows.indices.filter { isExplicitScopeDeclaration(rows[it]) }
        for ((position, scopeIndex) in declarationIndexes.withIndex()) {
            val scopeCells = rows[scopeIndex]
            val admissionQuality = admissionEvidenceQuality(scopeCells, admission, admissionCategory)
            if (admissionQuality != "exact") continue
            val endExclusive = declarationIndexes.getOrNull(position + 1) ?: rows.size
            for (ri in (scopeIndex + 1) until endExclusive) {
                val deptQuality = departmentEvidenceQuality(rows[ri], department)
                if (deptQuality !in setOf("exact", "suffix-equivalent")) continue
                out += SegmentBinding(
                    scopeRowIndex = scopeIndex,
                    departmentRowIndex = ri,
                    admissionMatch = admissionQuality,
                    departmentMatch = deptQuality,
                    scopeLabel = scopeCells.firstOrNull().orEmpty().trim().take(80)
                )
            }
        }
        return out
    }

    fun isExplicitScopeDeclaration(cells: List<String>): Boolean {
        val first = normalize(cells.firstOrNull())
        if (first.isBlank()) return false
        return first == "모집단위" || first.startsWith("모집단위명") ||
            first == "해당전형" || first == "전형명" || first == "모집전형"
    }

    fun admissionEvidenceQuality(cells: List<String>, admission: String?, category: String?): String {
        var best = "none"
        for (cell in cells) {
            when (cellAdmissionQuality(cell, admission, category)) {
                "exact" -> return "exact"
                "related" -> if (best !in setOf("exact")) best = "related"
                "category-only" -> if (best == "none") best = "category-only"
            }
        }
        return best
    }

    fun departmentEvidenceQuality(cells: List<String>, department: String?): String {
        var best = "none"
        for (cell in cells) {
            when (departmentMatchQuality(department, cell)) {
                "exact" -> return "exact"
                "suffix-equivalent" -> best = "suffix-equivalent"
            }
        }
        return best
    }

    fun departmentMatchQuality(left: String?, right: String?): String {
        val l = normalize(left)
        val r = normalize(right)
        if (l.isBlank() || r.isBlank()) return "missing"
        if (l == r) return "exact"
        val suffixes = listOf("학과", "학부", "전공")
        if (suffixes.any { l + it == r || r + it == l }) return "suffix-equivalent"
        return "none"
    }

    private fun cellAdmissionQuality(cellRaw: String, admission: String?, category: String?): String {
        val target = normalizeAdmission(admission)
        val cell = normalizeAdmission(cellRaw)
        val categoryKey = normalizeAdmission(category)
        if (target.isBlank() && categoryKey.isBlank()) return "none"

        val targetVariants = variantSet(admission.orEmpty())
        val cellVariants = variantSet(cellRaw)
        val variantCompatible = when {
            targetVariants.isEmpty() -> true
            cellVariants.isEmpty() -> false
            cellVariants.size > 1 && targetVariants.size == 1 -> false
            else -> targetVariants.all { it in cellVariants }
        }

        if (target.isNotBlank() && variantCompatible) {
            if (cell == target) return "exact"
            if (target.length >= 3 && cell.contains(target)) return "exact"
            if (semanticAdmissionMatch(admission.orEmpty(), cellRaw)) return "exact"
        }
        if (target.isNotBlank() && (cell.contains(target) || target.contains(cell))) return "related"
        if (sameCategory(admission.orEmpty(), cellRaw) && target.isNotBlank()) return "related"
        if (categoryKey.isNotBlank() && normalize(cellRaw).contains(categoryKey)) return "category-only"
        return "none"
    }

    private fun semanticAdmissionMatch(targetRaw: String, cellRaw: String): Boolean {
        val targetCategory = categoryToken(targetRaw) ?: return false
        val cellCategory = categoryToken(cellRaw) ?: return false
        if (targetCategory != cellCategory) return false

        val targetVariants = variantSet(targetRaw)
        val cellVariants = variantSet(cellRaw)
        if (targetVariants.isNotEmpty()) {
            if (cellVariants.isEmpty() || cellVariants.size > 1 || !targetVariants.all { it in cellVariants }) return false
        }

        val targetModifiers = modifierTokens(targetRaw)
        val cellModifiers = modifierTokens(cellRaw)
        if (targetModifiers.isEmpty()) return targetVariants.isNotEmpty() && targetVariants == cellVariants
        return targetModifiers.all { it in cellModifiers }
    }

    private fun sameCategory(a: String, b: String): Boolean {
        val ca = categoryToken(a) ?: return false
        val cb = categoryToken(b) ?: return false
        return ca == cb
    }

    private fun categoryToken(value: String): String? {
        val n = normalize(value)
        return when {
            "종합" in n -> "종합"
            "교과" in n -> "교과"
            else -> null
        }
    }

    private fun modifierTokens(value: String): Set<String> {
        val n = normalize(value)
        val tokens = linkedSetOf<String>()
        val known = listOf(
            "지역인재", "일반", "면접", "자기추천", "학교장추천", "고른기회",
            "농어촌", "기회균형", "사회기여", "배려", "특성화고", "자율전공",
            "중심", "서류형", "서류"
        )
        for (token in known) if (token in n) tokens += token
        return tokens
    }

    private fun variantSet(value: String): Set<Int> {
        val out = linkedSetOf<Int>()
        if ('Ⅰ' in value) out += 1
        if ('Ⅱ' in value) out += 2
        val upper = value.uppercase()
        if (Regex("(^|[^A-Z])I([^A-Z]|$)").containsMatchIn(upper)) out += 1
        if (Regex("(^|[^A-Z])II([^A-Z]|$)").containsMatchIn(upper)) out += 2
        return out
    }

    private fun normalizeAdmission(value: String?): String = normalize(value)
        .replace("학생부", "")
        .replace("전형", "")

    private fun normalize(value: String?): String = value.orEmpty()
        .trim()
        .lowercase()
        .replace("Ⅰ", "1")
        .replace("Ⅱ", "2")
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\)]"), "")
        .replace(Regex("[^0-9a-z가-힣]"), "")
}
''')

# ---------------------------------------------------------------------------
# JSON evidence adapter: preserve v0.10.1 row-level evidence and add explicit
# same-table segment evidence. No cross-table/page-wide inheritance.
# ---------------------------------------------------------------------------
EVID.write_text(r'''package com.admissionhub.collector.canonical

import org.json.JSONObject

object AdigaOfficialAdmissionEvidence {
    data class AppRef(
        val year: Int,
        val university: String?,
        val department: String?,
        val admission: String?,
        val admissionCategory: String?
    )

    fun inspect(recordType: String, recordYear: Int, record: JSONObject, app: AppRef): List<JSONObject> {
        if (recordType !in setOf("current-admission-criteria-table", "historical-admission-result-table")) return emptyList()
        val metrics = record.optJSONObject("metrics") ?: return emptyList()
        val rowsJson = metrics.optJSONArray("rows") ?: return emptyList()
        val rows = mutableListOf<List<String>>()
        for (ri in 0 until rowsJson.length()) {
            val row = rowsJson.optJSONArray(ri)
            val cells = if (row == null) emptyList() else (0 until row.length())
                .map { row.optString(it).trim() }
                .filter { it.isNotBlank() }
            rows += cells
        }
        val out = mutableListOf<JSONObject>()
        val currentYear = recordType == "current-admission-criteria-table" && recordYear == app.year

        for (ri in rows.indices) {
            val cells = rows[ri]
            if (cells.isEmpty()) continue
            val admissionQuality = AdigaOfficialTableBindingPolicy.admissionEvidenceQuality(cells, app.admission, app.admissionCategory)
            if (admissionQuality == "none") continue
            val departmentQuality = AdigaOfficialTableBindingPolicy.departmentEvidenceQuality(cells, app.department)
            val scope = when {
                currentYear && departmentQuality in setOf("exact", "suffix-equivalent") && admissionQuality == "exact" -> "row-bound-current"
                currentYear && departmentQuality in setOf("exact", "suffix-equivalent") -> "row-bound-current-related"
                currentYear -> "university-current"
                else -> "historical"
            }
            out += baseEvidence(recordType, recordYear, record)
                .put("rowIndex", ri)
                .put("scope", scope)
                .put("departmentMatch", departmentQuality)
                .put("admissionMatch", admissionQuality)
                .put("rowEvidence", cells.joinToString(" | ").take(1200))
                .put("bindingMethod", "same-row-or-university-evidence")
        }

        val segmentBindings = AdigaOfficialTableBindingPolicy.findExplicitSegmentBindings(
            rows, app.department, app.admission, app.admissionCategory
        )
        for (binding in segmentBindings) {
            val scopeCells = rows.getOrElse(binding.scopeRowIndex) { emptyList() }
            val departmentCells = rows.getOrElse(binding.departmentRowIndex) { emptyList() }
            out += baseEvidence(recordType, recordYear, record)
                .put("scope", if (currentYear) "table-segment-current" else "table-segment-historical")
                .put("scopeRowIndex", binding.scopeRowIndex)
                .put("departmentRowIndex", binding.departmentRowIndex)
                .put("scopeLabel", binding.scopeLabel)
                .put("departmentMatch", binding.departmentMatch)
                .put("admissionMatch", binding.admissionMatch)
                .put("scopeRowEvidence", scopeCells.joinToString(" | ").take(1000))
                .put("departmentRowEvidence", departmentCells.joinToString(" | ").take(1000))
                .put("bindingMethod", "same-official-table-explicit-scope-segment")
                .put("sameOfficialTableSegment", true)
        }
        return dedupe(out)
    }

    private fun baseEvidence(recordType: String, recordYear: Int, record: JSONObject): JSONObject = JSONObject()
        .put("recordType", recordType)
        .put("recordYear", recordYear)
        .put("sourcePage", record.optString("sourcePage").take(500))
        .put("sourceRowFingerprint", record.optString("sourceRowFingerprint").take(100))
        .put("officialSource", true)
        .put("bindingInferred", false)

    private fun dedupe(rows: List<JSONObject>): List<JSONObject> {
        val seen = linkedSetOf<String>()
        val out = mutableListOf<JSONObject>()
        for (row in rows) {
            val key = listOf(
                row.optString("scope"), row.optInt("rowIndex", -1).toString(),
                row.optInt("scopeRowIndex", -1).toString(), row.optInt("departmentRowIndex", -1).toString(),
                row.optString("sourceRowFingerprint")
            ).joinToString("|")
            if (seen.add(key)) out += row
        }
        return out
    }
}
''')

TEST.parent.mkdir(parents=True, exist_ok=True)
TEST.write_text(r'''package com.admissionhub.collector.canonical

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AdigaOfficialTableBindingPolicyTest {
    @Test fun explicitScopeHeaderBindsDepartmentInsideSameSegment() {
        val rows = listOf(
            listOf("모집단위", "학생부교과(지역인재전형)"),
            listOf("모집인원", "경쟁률"),
            listOf("반도체시스템공학과", "21", "4.2")
        )
        val matches = AdigaOfficialTableBindingPolicy.findExplicitSegmentBindings(
            rows, "반도체시스템공", "지역인재교과", "교과"
        )
        assertEquals(1, matches.size)
        assertEquals(0, matches[0].scopeRowIndex)
        assertEquals(2, matches[0].departmentRowIndex)
        assertEquals("exact", matches[0].admissionMatch)
        assertEquals("suffix-equivalent", matches[0].departmentMatch)
    }

    @Test fun nextScopeHeaderStopsInheritance() {
        val rows = listOf(
            listOf("모집단위", "학생부교과(일반전형)"),
            listOf("기계공학과", "10"),
            listOf("모집단위", "학생부교과(지역인재전형)"),
            listOf("반도체시스템공학과", "20")
        )
        val matches = AdigaOfficialTableBindingPolicy.findExplicitSegmentBindings(
            rows, "반도체시스템공", "교과일반", "교과"
        )
        assertTrue(matches.isEmpty())
    }

    @Test fun universityWideAdmissionMentionDoesNotPropagate() {
        val rows = listOf(
            listOf("교과면접", "학생부80%", "면접20%"),
            listOf("철도차량시스템학과", "20")
        )
        assertFalse(AdigaOfficialTableBindingPolicy.isExplicitScopeDeclaration(rows[0]))
        val matches = AdigaOfficialTableBindingPolicy.findExplicitSegmentBindings(
            rows, "철도차량시스템", "교과면접", "교과"
        )
        assertTrue(matches.isEmpty())
    }

    @Test fun reorderedRegionAndCategoryTokensStillMatchExact() {
        val q = AdigaOfficialTableBindingPolicy.admissionEvidenceQuality(
            listOf("학생부교과(지역인재전형)"), "지역인재교과", "교과"
        )
        assertEquals("exact", q)
    }

    @Test fun combinedJonghapOneAndTwoIsNotExactForTwo() {
        val q = AdigaOfficialTableBindingPolicy.admissionEvidenceQuality(
            listOf("학생부종합Ⅰ학생부종합Ⅱ"), "학생부종합Ⅱ", "종합"
        )
        assertTrue(q == "related" || q == "category-only")
    }
}
''')

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.10.2"', 'private const val VERSION = "0.10.3"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 110020', 'private const val BUILD_CODE = 110030', 'main build code')
gradle = replace_once(gradle, 'versionCode = 110020', 'versionCode = 110030', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.10.2"', 'versionName = "0.10.3"', 'gradle version name')
manifest = replace_once(manifest, 'Admission Hub v0.10.2 Auth Ownership Repair', 'Admission Hub v0.10.3 Official Table Binding', 'manifest label')

# Stronger Hub status: surface how many of the selected six are officially accepted.
old_hub = '        hubState.text = "지원 6장 $selected/6 · 후보 $candidates · 완전 $completeCandidates · 보강 $repairCandidates · $readyText"\n'
new_hub = '        val selectedAccepted = slots.optInt("accepted", 0)\n        val selectedProvisional = slots.optInt("provisional", 0)\n        hubState.text = "지원 6장 $selected/6 · 후보 $candidates · 완전 $completeCandidates · 공식결합 $selectedAccepted/6 · 확인필요 $selectedProvisional · 보강 $repairCandidates · $readyText"\n'
main = replace_once(main, old_hub, new_hub, 'hub acceptance summary')

# Keep support fingerprints for department records and add exact official-table record fingerprints.
store = replace_once(
    store,
    '        val exactFingerprints = linkedMapOf<String, MutableSet<String>>()\n        val officialAdmissionEvidence = linkedMapOf<String, MutableList<JSONObject>>()\n',
    '        val exactFingerprints = linkedMapOf<String, MutableSet<String>>()\n        val departmentSupportFingerprints = linkedMapOf<String, MutableSet<String>>()\n        val officialStructuralFingerprints = linkedMapOf<String, MutableSet<String>>()\n        val officialAdmissionEvidence = linkedMapOf<String, MutableList<JSONObject>>()\n',
    'canonical fingerprint maps'
)
store = replace_once(
    store,
    '                        val admissionQuality = CanonicalSixApplicationGraph.admissionMatchQuality(app.admission, admission)\n                        if (admissionQuality == "none") continue\n',
    '                        departmentSupportFingerprints.getOrPut(app.identityKey) { linkedSetOf() }.add(c.getString(0))\n                        val admissionQuality = CanonicalSixApplicationGraph.admissionMatchQuality(app.admission, admission)\n                        if (admissionQuality == "none") continue\n',
    'department support fingerprint'
)

old_query = '''            readableDatabase.rawQuery(
                "SELECT COALESCE(year,-1),university,record_type,json FROM records WHERE run_id=? AND record_type IN ('current-admission-criteria-table','historical-admission-result-table') AND university IS NOT NULL",
                arrayOf(adigaRunId)
            ).use { c ->
                while (c.moveToNext()) {
                    val recordYear = c.getInt(0)
                    val university = if (c.isNull(1)) null else c.getString(1)
                    val recordType = c.getString(2)
                    val candidates = byUniversity[CanonicalSixApplicationGraph.normalizeUniversityKey(university)].orEmpty()
                    if (candidates.isEmpty()) continue
                    val record = runCatching { JSONObject(c.getString(3)) }.getOrNull() ?: continue
                    for (app in candidates) {
                        val evidence = AdigaOfficialAdmissionEvidence.inspect(
                            recordType,
                            recordYear,
                            record,
                            AdigaOfficialAdmissionEvidence.AppRef(app.year, app.university, app.department, app.admission, app.admissionCategory)
                        )
                        if (evidence.isNotEmpty()) officialAdmissionEvidence.getOrPut(app.identityKey) { mutableListOf() }.addAll(evidence)
                    }
                }
            }
'''
new_query = '''            readableDatabase.rawQuery(
                "SELECT fingerprint,COALESCE(year,-1),university,record_type,json FROM records WHERE run_id=? AND record_type IN ('current-admission-criteria-table','historical-admission-result-table') AND university IS NOT NULL",
                arrayOf(adigaRunId)
            ).use { c ->
                while (c.moveToNext()) {
                    val recordFingerprint = c.getString(0)
                    val recordYear = c.getInt(1)
                    val university = if (c.isNull(2)) null else c.getString(2)
                    val recordType = c.getString(3)
                    val candidates = byUniversity[CanonicalSixApplicationGraph.normalizeUniversityKey(university)].orEmpty()
                    if (candidates.isEmpty()) continue
                    val record = runCatching { JSONObject(c.getString(4)) }.getOrNull() ?: continue
                    for (app in candidates) {
                        val evidence = AdigaOfficialAdmissionEvidence.inspect(
                            recordType,
                            recordYear,
                            record,
                            AdigaOfficialAdmissionEvidence.AppRef(app.year, app.university, app.department, app.admission, app.admissionCategory)
                        ).onEach { it.put("recordFingerprint", recordFingerprint) }
                        if (evidence.isNotEmpty()) {
                            officialAdmissionEvidence.getOrPut(app.identityKey) { mutableListOf() }.addAll(evidence)
                            if (evidence.any { it.optString("scope") in setOf("row-bound-current", "table-segment-current") }) {
                                officialStructuralFingerprints.getOrPut(app.identityKey) { linkedSetOf() }.add(recordFingerprint)
                            }
                        }
                    }
                }
            }
'''
store = replace_once(store, old_query, new_query, 'official evidence query')

old_counts = '''                val officialEvidenceRows = officialAdmissionEvidence[app.identityKey].orEmpty()
                val rowBoundCurrent = officialEvidenceRows.count { it.optString("scope") == "row-bound-current" }
                val rowBoundRelated = officialEvidenceRows.count { it.optString("scope") == "row-bound-current-related" }
                val currentUniversityEvidence = officialEvidenceRows.count { it.optString("scope") == "university-current" }
                val bindingQuality = when {
                    acceptedSignatures == 1 -> "accepted"
                    acceptedSignatures > 1 -> "provisional"
                    rowBoundCurrent == 1 -> "accepted"
                    rowBoundCurrent > 1 -> "provisional"
                    provisionalSignatures > 0 || rowBoundRelated > 0 || currentUniversityEvidence > 0 -> "provisional"
                    else -> "provider-only"
                }
'''
new_counts = '''                val officialEvidenceRows = officialAdmissionEvidence[app.identityKey].orEmpty()
                val rowBoundCurrent = officialEvidenceRows.count { it.optString("scope") == "row-bound-current" }
                val rowBoundRelated = officialEvidenceRows.count { it.optString("scope") == "row-bound-current-related" }
                val tableSegmentCurrent = officialEvidenceRows.count { it.optString("scope") == "table-segment-current" }
                val tableSegmentHistorical = officialEvidenceRows.count { it.optString("scope") == "table-segment-historical" }
                val currentUniversityEvidence = officialEvidenceRows.count { it.optString("scope") == "university-current" }
                val structuralCurrentEvidence = rowBoundCurrent + tableSegmentCurrent
                val bindingQuality = when {
                    acceptedSignatures == 1 -> "accepted"
                    acceptedSignatures > 1 -> "provisional"
                    structuralCurrentEvidence > 0 -> "accepted"
                    provisionalSignatures > 0 || rowBoundRelated > 0 || currentUniversityEvidence > 0 || tableSegmentHistorical > 0 -> "provisional"
                    else -> "provider-only"
                }
'''
store = replace_once(store, old_counts, new_counts, 'binding quality counts')

old_json = '''                val bindingJson = JSONObject()
                    .put("schemaVersion", 1)
                    .put("officialBaseline", "adiga")
                    .put("bindingQuality", bindingQuality)
                    .put("acceptedSignatures", acceptedSignatures)
                    .put("provisionalSignatures", provisionalSignatures)
                    .put("officialRowBoundCurrent", rowBoundCurrent)
                    .put("officialRowBoundRelated", rowBoundRelated)
                    .put("officialUniversityCurrent", currentUniversityEvidence)
                    .put("officialAdmissionEvidence", JSONArray(officialEvidenceRows.take(24)))
                    .put("matches", JSONArray(matchRows))
                    .put("sameRowRequiredForOfficialAccepted", true)
                    .put("doNotInferMissingBindings", true)
'''
new_json = '''                val bindingJson = JSONObject()
                    .put("schemaVersion", 2)
                    .put("bindingPolicyVersion", "official-structural-v2")
                    .put("officialBaseline", "adiga")
                    .put("bindingQuality", bindingQuality)
                    .put("acceptedSignatures", acceptedSignatures)
                    .put("provisionalSignatures", provisionalSignatures)
                    .put("officialRowBoundCurrent", rowBoundCurrent)
                    .put("officialRowBoundRelated", rowBoundRelated)
                    .put("officialTableSegmentCurrent", tableSegmentCurrent)
                    .put("officialTableSegmentHistorical", tableSegmentHistorical)
                    .put("officialStructuralCurrent", structuralCurrentEvidence)
                    .put("officialUniversityCurrent", currentUniversityEvidence)
                    .put("officialAdmissionEvidence", JSONArray(officialEvidenceRows.take(36)))
                    .put("matches", JSONArray(matchRows))
                    .put("sameRowRequiredForOfficialAccepted", false)
                    .put("sameRowOrExplicitTableScopeRequiredForOfficialAccepted", true)
                    .put("acceptedBindingMethods", JSONArray(listOf("same-row", "same-official-table-explicit-scope-segment")))
                    .put("doNotInferMissingBindings", true)
'''
store = replace_once(store, old_json, new_json, 'binding json v2')

old_mark = '''                if (bindingQuality == "accepted" && !adigaRunId.isNullOrBlank()) {
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
'''
new_mark = '''                if (bindingQuality == "accepted" && !adigaRunId.isNullOrBlank()) {
                    val acceptedEvidenceFingerprints = linkedSetOf<String>().apply {
                        addAll(exactFingerprints[app.identityKey].orEmpty())
                        addAll(departmentSupportFingerprints[app.identityKey].orEmpty())
                        addAll(officialStructuralFingerprints[app.identityKey].orEmpty())
                    }
                    acceptedEvidenceFingerprints.forEach { fp ->
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
'''
store = replace_once(store, old_mark, new_mark, 'accepted evidence record marking')

# Quality audit records the structural binding policy version.
store = replace_once(
    store,
    '            .put("predictionDoesNotOverwriteHistoricalActual", true)\n            .put("doNotInferMissingBindings", true)\n',
    '            .put("predictionDoesNotOverwriteHistoricalActual", true)\n            .put("officialBindingPolicy", "same-row-or-explicit-same-table-scope")\n            .put("doNotInferMissingBindings", true)\n',
    'quality audit binding policy'
)

MAIN.write_text(main)
STORE.write_text(store)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

checks = {
    'version': 'private const val VERSION = "0.10.3"' in main and 'versionCode = 110030' in gradle,
    'policy': POLICY.exists() and 'findExplicitSegmentBindings' in POLICY.read_text(),
    'tests': TEST.exists() and 'nextScopeHeaderStopsInheritance' in TEST.read_text(),
    'structural-evidence': 'table-segment-current' in EVID.read_text(),
    'no-page-wide-inference': 'isExplicitScopeDeclaration' in POLICY.read_text() and 'sameOfficialTableSegment' in EVID.read_text(),
    'store-policy': 'officialTableSegmentCurrent' in store and 'sameRowOrExplicitTableScopeRequiredForOfficialAccepted' in store,
    'hub-ui': '공식결합 $selectedAccepted/6' in main,
}
failed = [k for k, ok in checks.items() if not ok]
if failed:
    raise SystemExit('v0.10.3 postcondition failed: ' + ', '.join(failed))
print('v0.10.3 Official Table Binding patch applied')
