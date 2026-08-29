from pathlib import Path

ROOT = Path('.')
MAIN_PATHS = [
    ROOT / 'MainActivity.kt',
    ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt',
]
ADIGA = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/AdigaAdapter.kt'

# apply_v040.py generates the full v0.4.0 source from the persisted v0.3.9 baseline.
# Keep this fixer narrowly scoped so the first failed build remains reproducible and auditable.
for path in MAIN_PATHS:
    s = path.read_text()
    marker = '    private fun finalizeBatchJson(reason: String) {'
    if marker not in s:
        raise SystemExit(f'finalize marker missing: {path}')
    before, after = s.split(marker, 1)
    # A broad replacement in apply_v040 accidentally changed the earlier Cloud summary,
    # where persistedRecords is out of scope. Restore that section.
    before = before.replace(
        '.put("records", persistedRecords.length())',
        '.put("records", batchRecords.length())'
    )
    # Inside finalizeBatchJson the exported count must describe the full resumed local run.
    if '.put("records", persistedRecords.length())' not in after:
        if '.put("records", batchRecords.length())' not in after:
            raise SystemExit(f'finalize record-count anchor missing: {path}')
        after = after.replace(
            '.put("records", batchRecords.length())',
            '.put("records", persistedRecords.length())',
            1
        )
    path.write_text(before + marker + after)

s = ADIGA.read_text()
start_marker = '    private fun parseAdmissionList(snapshot: JSONObject): JSONArray {'
end_marker = '    private fun parseUniversityDetail(snapshot: JSONObject): JSONArray {'
if start_marker not in s or end_marker not in s:
    raise SystemExit('parseAdmissionList markers missing')
before, rest = s.split(start_marker, 1)
body, after = rest.split(end_marker, 1)
body = body.replace('if (row.length() < 5) continue', 'if (row.length() < 6) continue', 1)
needle = '''            val university = normalizeUniversityCell(row.optString(0))
            val department = row.optString(1).trim()
            if (!looksLikeUniversity(university) || department.isBlank() || department.contains("검색결과가 없습니다")) continue
            val metrics = JSONObject()
'''
replacement = '''            val university = normalizeUniversityCell(row.optString(0))
            val department = row.optString(1).trim()
            if (!looksLikeUniversity(university) || department.isBlank() || department.contains("검색결과가 없습니다")) continue
            val previousCompetition = Regex("[0-9]+(?:\\\\.[0-9]+)?").find(row.optString(3))?.value?.toDoubleOrNull()
            val previousGrade = Regex("[0-9]+(?:\\\\.[0-9]+)?").find(row.optString(5))?.value?.toDoubleOrNull()
            val metrics = JSONObject()
'''
if needle not in body:
    raise SystemExit('parseAdmissionList metric anchor missing')
body = body.replace(needle, replacement, 1)
body = body.replace('numberOrNull(row.optString(3))', 'numberOrNull(previousCompetition)', 1)
body = body.replace('numberOrNull(row.optString(5))', 'numberOrNull(previousGrade)', 1)
s = before + start_marker + body + end_marker + after
ADIGA.write_text(s)

if MAIN_PATHS[0].read_bytes() != MAIN_PATHS[1].read_bytes():
    raise SystemExit('MainActivity copies diverged after compile fix')

checks = {
    MAIN_PATHS[0]: [
        'private fun finalizeBatchJson(reason: String)',
        '.put("records", persistedRecords.length())',
        'private const val VERSION = "0.4.0"',
    ],
    ADIGA: [
        'val previousCompetition = Regex(',
        'val previousGrade = Regex(',
        'numberOrNull(previousCompetition)',
        'numberOrNull(previousGrade)',
    ],
}
for path, needles in checks.items():
    text = path.read_text()
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'missing {needle!r} in {path}')

print('v0.4.0 compile fixes applied')
