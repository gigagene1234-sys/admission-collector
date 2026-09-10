from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "cloudflare/src/competition_v2.js"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


text = PATH.read_text(encoding="utf-8")

text = replace_once(
    text,
    """    if (target.collectionMode === MODE_USER_BROWSER) {\n      results.push({\n""",
    """    if (target.collectionMode === MODE_USER_BROWSER) {\n      await markTargetWaitingForUserBrowser(env, target.id, now);\n      results.push({\n""",
    "clear stale browser-target errors",
)

text = replace_once(
    text,
    """    sourceUpdatedAt: textTimestamp || headerTimestamp,\n""",
    """    sourceUpdatedAt: headerTimestamp || textTimestamp,\n""",
    "prefer last-modified",
)

old_parser = """    let admission = valueAt(cells, header?.admissionIndex) || section;\n    let department = valueAt(cells, header?.departmentIndex);\n    let quota = parseInteger(valueAt(cells, header?.quotaIndex));\n    let applicants = parseInteger(valueAt(cells, header?.applicantsIndex));\n\n    if (!department || isNumericLike(department)) {\n      const textCells = cells.slice(0, ratioIndex).filter((c) => !isNumericLike(c));\n      department = textCells.length ? textCells[textCells.length - 1] : null;\n      if (!admission && textCells.length > 1) admission = textCells[textCells.length - 2];\n    }\n\n    if (quota == null || applicants == null) {\n      const nums = cells.slice(0, ratioIndex).map(parseInteger).filter((x) => x != null);\n      if (nums.length >= 2) {\n        if (quota == null) quota = nums[nums.length - 2];\n        if (applicants == null) applicants = nums[nums.length - 1];\n      }\n    }\n\n    if (!department && quota == null && applicants == null) continue;\n"""

new_parser = """    const beforeRatio = cells.slice(0, ratioIndex);\n    const integerCells = [];\n    for (let i = 0; i < beforeRatio.length; i += 1) {\n      const value = parseInteger(beforeRatio[i]);\n      if (value != null) integerCells.push({ index: i, value });\n    }\n\n    // Uway/Jinhak competition tables can collapse rowspan cells on subsequent rows, so fixed\n    // header indices are not stable. The two right-most integer cells immediately before the\n    // published ratio are the row's 모집인원 and 지원인원. Prefer that structural invariant.\n    let quota = null;\n    let applicants = null;\n    let numericTailStart = ratioIndex;\n    if (integerCells.length >= 2) {\n      const quotaCell = integerCells[integerCells.length - 2];\n      const applicantCell = integerCells[integerCells.length - 1];\n      quota = quotaCell.value;\n      applicants = applicantCell.value;\n      numericTailStart = quotaCell.index;\n    } else {\n      quota = parseInteger(valueAt(cells, header?.quotaIndex));\n      applicants = parseInteger(valueAt(cells, header?.applicantsIndex));\n    }\n\n    const labelCells = beforeRatio.slice(0, numericTailStart).filter((c) => !isNumericLike(c));\n    let department = labelCells.length ? labelCells[labelCells.length - 1] : valueAt(cells, header?.departmentIndex);\n    let admission = section;\n    const indexedAdmission = valueAt(cells, header?.admissionIndex);\n    if (indexedAdmission && !isNumericLike(indexedAdmission) && indexedAdmission !== department) {\n      admission = indexedAdmission;\n    } else if (!admission && labelCells.length > 1) {\n      admission = labelCells[labelCells.length - 2];\n    }\n\n    // Reject structurally inconsistent rows instead of silently persisting shifted columns.\n    if (!ratioMatchesCounts(quota, applicants, ratio)) continue;\n    if (!department && quota == null && applicants == null) continue;\n"""
text = replace_once(text, old_parser, new_parser, "right-aligned numeric parser")

text = replace_once(
    text,
    """async function noteAttempt(env, targetId, now) {\n""",
    """async function markTargetWaitingForUserBrowser(env, targetId, now) {\n  await env.DB.prepare(`\n    UPDATE competition_targets\n       SET last_error = NULL,\n           consecutive_failures = 0,\n           updated_at = ?\n     WHERE target_id = ?\n  `).bind(now.toISOString(), targetId).run();\n}\n\nasync function noteAttempt(env, targetId, now) {\n""",
    "waiting state helper",
)

text = replace_once(
    text,
    """function parseRatio(value) {\n""",
    """function ratioMatchesCounts(quota, applicants, ratio) {\n  if (quota == null || applicants == null || ratio == null) return true;\n  if (quota === 0) return applicants === 0 && Math.abs(ratio) <= 0.005;\n  const expected = applicants / quota;\n  // Published ratios are normally rounded to two decimals. Allow only a narrow rounding margin.\n  return Math.abs(expected - ratio) <= 0.015;\n}\n\nfunction parseRatio(value) {\n""",
    "ratio consistency helper",
)

PATH.write_text(text, encoding="utf-8")
print("competition parser v3 patch applied or already present")
