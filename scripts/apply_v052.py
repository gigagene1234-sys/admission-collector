from pathlib import Path
import re

ROOT = Path('.')
MAIN_PATHS = [ROOT/'MainActivity.kt', ROOT/'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
GENERIC_PATH = ROOT/'app/src/main/java/com/admissionhub/collector/parser/GenericAdmissionParser.kt'
SNAPSHOT_PATH = ROOT/'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
GRADLE_PATH = ROOT/'app/build.gradle.kts'
MANIFEST_PATH = ROOT/'app/src/main/AndroidManifest.xml'


def replace_all(path, pairs):
    text = path.read_text()
    for old, new in pairs:
        if old not in text:
            raise SystemExit(f'missing pattern in {path}: {old[:120]}')
        text = text.replace(old, new)
    path.write_text(text)

for p in MAIN_PATHS:
    replace_all(p, [
        ('private const val VERSION = "0.5.1"', 'private const val VERSION = "0.5.2"'),
        ('private const val BUILD_CODE = 10510', 'private const val BUILD_CODE = 10520'),
    ])

replace_all(GRADLE_PATH, [
    ('versionCode = 10510', 'versionCode = 10520'),
    ('versionName = "0.5.1"', 'versionName = "0.5.2"'),
])
replace_all(MANIFEST_PATH, [
    ('Admission Collector v0.5.1 Jinhak', 'Admission Collector v0.5.2 Jinhak'),
])

replace_all(SNAPSHOT_PATH, [(
'''  var tables=[];\n  var captureHiddenDetail=''',
'''  var selectionContext=[];\n  var selectedNodes=document.querySelectorAll('select option:checked,[aria-selected=true],.selected,.active,[class*=selected],[class*=active]');\n  for(var si=0;si<selectedNodes.length && selectionContext.length<80;si++){\n    var se=selectedNodes[si];\n    if(se.tagName!=='OPTION' && !visible(se)) continue;\n    var st=safeCloneText(se,500);\n    if(st.length>=2 && admissionTerms.test(st) && !forbidden.test(st) && !loginSensitive.test(st)) selectionContext.push(st);\n  }\n\n  var tables=[];\n  var captureHiddenDetail='''
),(
'''    context:context,\n    tables:tables,''',
'''    context:context,\n    selectionContext:selectionContext,\n    tables:tables,'''
)])

text = GENERIC_PATH.read_text()
needle = '''        snapshot.optString("title").trim().takeIf { it.isNotBlank() }?.let(priority::add)\n        val context = snapshot.optJSONArray("context") ?: JSONArray()'''
replacement = '''        val selected = snapshot.optJSONArray("selectionContext") ?: JSONArray()\n        for (i in 0 until minOf(selected.length(), 80)) selected.optString(i).trim().takeIf { it.isNotBlank() }?.let(priority::add)\n        snapshot.optString("title").trim().takeIf { it.isNotBlank() }?.let(priority::add)\n        val context = snapshot.optJSONArray("context") ?: JSONArray()'''
if needle not in text:
    raise SystemExit('snapshot context priority block missing')
text = text.replace(needle, replacement)

# Remove the permissive bare-*대학 fallback. It produced false institutions such as "면접(20)대학".
pattern = re.compile(
    r'''\n        val excludedCollege = Regex\([^\n]+\)\n        return Regex\([^\n]+대학[^\n]+\)\n            \.findAll\(text\)\n            \.map \{ cleanCandidate\(it\.groupValues\[1\]\) \}\n            \.firstOrNull \{ it\.length in 3\.\.35 && !excludedCollege\.containsMatchIn\(it\) \}'''
)
new_uni = '''\n        // Bare "대학" is usually a college/faculty or prose fragment on Jinhak pages.\n        // Prefer a missing university over attaching prediction metrics to a false institution.\n        return Regex("([가-힣A-Za-z0-9·.()\\-]{2,35}(?:교육대학교|과학기술원))")\n            .findAll(text)\n            .map { cleanCandidate(it.groupValues[1]) }\n            .firstOrNull { it.length in 4..45 }'''
text2, count = pattern.subn(new_uni, text, count=1)
if count != 1:
    raise SystemExit(f'university fallback replace count={count}')
text = text2

old_noise = '''            it.length in 2..40 && !Regex("[①-⑳]|[0-9]+\\)|학생부 반영비율|있는 전형|없는 서류|설명|안내").containsMatchIn(it)'''
new_noise = '''            it.length in 2..40 && !Regex("[①-⑳]|[0-9]+\\)|학생부 반영비율|있는 전형|없는 서류|설명|안내|^서류\\s*평가\\s*전형$|^서류\\s*전형$|^면접\\s*전형$").containsMatchIn(it)'''
if old_noise not in text:
    raise SystemExit('admission noise filter missing')
text = text.replace(old_noise, new_noise)
GENERIC_PATH.write_text(text)

if MAIN_PATHS[0].read_text() != MAIN_PATHS[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')
print('v0.5.2 patch applied')
