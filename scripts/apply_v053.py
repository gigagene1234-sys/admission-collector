from pathlib import Path

ROOT = Path('.')
MAIN_PATHS = [ROOT/'MainActivity.kt', ROOT/'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
JINHAK = ROOT/'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
SNAPSHOT = ROOT/'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
GRADLE = ROOT/'app/build.gradle.kts'
MANIFEST = ROOT/'app/src/main/AndroidManifest.xml'


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'missing pattern in {path}: {old[:160]}')
    path.write_text(text.replace(old, new, 1))

for p in MAIN_PATHS:
    replace_once(p, 'private const val VERSION = "0.5.2"', 'private const val VERSION = "0.5.3"')
    replace_once(p, 'private const val BUILD_CODE = 10520', 'private const val BUILD_CODE = 10530')

replace_once(GRADLE, 'versionCode = 10520', 'versionCode = 10530')
replace_once(GRADLE, 'versionName = "0.5.2"', 'versionName = "0.5.3"')
replace_once(MANIFEST, 'Admission Collector v0.5.2 Jinhak', 'Admission Collector v0.5.3 Jinhak')

# Snapshot: derive compact, local card-like blocks from the authenticated Jinhak page.
insert_before_tables = '''\n  var tables=[];\n  var captureHiddenDetail='''
card_capture = '''\n  var jinhakCards=[];\n  if(/(^|\\.)jinhak\\.com$/i.test(location.hostname)){\n    var metricRx=/(?:[0-9]{1,2}\\s*칸|합격(?:률|확률|가능성)|경쟁률|모의지원|합격예측|지원판정|내\\s*순위|모집인원)/i;\n    var localContextRx=/(?:대학교|교육대|과학기술원|학과|학부|전공|모집단위|전형)/i;\n    var metricNodes=document.querySelectorAll('span,em,strong,b,p,td,th,li,div');\n    var seenJinhakCard={};\n    for(var ji=0;ji<metricNodes.length && jinhakCards.length<120;ji++){\n      var mn=metricNodes[ji];\n      if(!visible(mn)) continue;\n      var seed=safeCloneText(mn,350);\n      if(!metricRx.test(seed)) continue;\n      var cur=mn;\n      var best='';\n      for(var depth=0;cur && depth<7;depth++,cur=cur.parentElement){\n        if(!visible(cur)) continue;\n        var candidate=safeCloneText(cur,2800);\n        if(candidate.length<18 || candidate.length>2600) continue;\n        if(metricRx.test(candidate) && localContextRx.test(candidate)){\n          best=candidate;\n          break;\n        }\n      }\n      if(!best) continue;\n      var key=best.replace(/\\s+/g,' ').trim();\n      if(!seenJinhakCard[key]){\n        seenJinhakCard[key]=1;\n        jinhakCards.push(key);\n      }\n    }\n  }\n\n  var tables=[];\n  var captureHiddenDetail='''
replace_once(SNAPSHOT, insert_before_tables, card_capture)
replace_once(SNAPSHOT, '''    selectionContext:selectionContext,\n    tables:tables,''', '''    selectionContext:selectionContext,\n    jinhakCards:jinhakCards,\n    tables:tables,''')

text = JINHAK.read_text()
# Early-storage must win before generic prediction classification because the page contains prediction terms by design.
old_classify = '''        val dedicatedMinimum = url.contains("esatminuniv") ||\n            (Regex("(수능최저\\\\s*(검색|대학|조건)|최저학력기준\\\\s*(검색|대학))").containsMatchIn(text) && !hasPrediction)\n        return when {\n            Regex("(login|signin|member/login)").containsMatchIn(url) || text.contains("로그인") && text.contains("비밀번호") -> "jinhak-login"\n            hasActual -> "jinhak-actual-admit-report"'''
new_classify = '''        val dedicatedMinimum = url.contains("esatminuniv") ||\n            (Regex("(수능최저\\\\s*(검색|대학|조건)|최저학력기준\\\\s*(검색|대학))").containsMatchIn(text) && !hasPrediction)\n        val earlyStorage = text.contains("수시저장소") || text.contains("저장대학") || url.contains("storage") || url.contains("save")\n        return when {\n            Regex("(login|signin|member/login)").containsMatchIn(url) || text.contains("로그인") && text.contains("비밀번호") -> "jinhak-login"\n            earlyStorage -> "jinhak-early-storage"\n            hasActual -> "jinhak-actual-admit-report"'''
if old_classify not in text:
    raise SystemExit('classify block missing')
text = text.replace(old_classify, new_classify, 1)
# Remove now-unreachable late early-storage branch.
text = text.replace('''            text.contains("수시저장소") || text.contains("저장대학") -> "jinhak-early-storage"\n''', '', 1)

# Card-local early-storage parser: never attach page-global context to an individual saved application.
normalize_anchor = '''        val result = JSONArray()\n\n        val metrics = JSONObject()'''
normalize_insert = '''        val result = JSONArray()\n\n        if (pageType == "jinhak-early-storage") {\n            val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()\n            for (i in 0 until cards.length()) {\n                val evidence = cards.optString(i).replace(Regex("\\\\s+"), " ").trim().take(5000)\n                if (evidence.isBlank()) continue\n                val local = GenericAdmissionParser.inferContext(evidence)\n                val cardMetrics = predictionMetrics(evidence)\n                if (!cardMetrics.keys().asSequence().any { !cardMetrics.isNull(it) }) continue\n                val record = JSONObject()\n                    .put("recordType", "jinhak-saved-application-prediction")\n                    .put("providerPageType", pageType)\n                    .put("dataScope", "current-prediction")\n                    .put("year", local.year ?: TARGET_YEAR)\n                    .put("university", local.university ?: JSONObject.NULL)\n                    .put("department", local.department ?: JSONObject.NULL)\n                    .put("admission", local.admission ?: JSONObject.NULL)\n                    .put("metrics", cardMetrics)\n                    .put("observedAt", observedAt)\n                    .put("cardIndex", i)\n                    .put("contextSource", "card-local")\n                    .put("confidence", when {\n                        local.university != null && local.department != null && local.admission != null -> "high"\n                        local.university != null && local.department != null -> "medium"\n                        local.department != null -> "low"\n                        else -> "raw"\n                    })\n                    .put("sourcePage", safePath(snapshot.optString("url")))\n                    .put("rawEvidence", evidence)\n                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = true))\n                result.put(record)\n            }\n            return RecordUtils.dedupe(result)\n        }\n\n        val metrics = JSONObject()'''
if normalize_anchor not in text:
    raise SystemExit('normalize anchor missing')
text = text.replace(normalize_anchor, normalize_insert, 1)

# Treat early-storage as current prediction in all downstream logic.
text = text.replace('''        "jinhak-prediction-report", "jinhak-mock-support-report", "jinhak-recommended-university" -> "current-prediction"''', '''        "jinhak-prediction-report", "jinhak-mock-support-report", "jinhak-recommended-university", "jinhak-early-storage" -> "current-prediction"''', 1)

helper_anchor = '''    private fun putNumber(obj: JSONObject, key: String, value: String?) {'''
helper = '''    private fun predictionMetrics(text: String): JSONObject {\n        val metrics = JSONObject()\n        putNumber(metrics, "universityCalculatedScore", Regex("(?:대학별\\\\s*)?(?:환산점수|산출점수)\\\\s*[:：]?\\\\s*([0-9]+(?:\\\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))\n        putNumber(metrics, "convertedGrade", Regex("(?:반영\\\\s*평균등급|환산등급|내\\\\s*등급)\\\\s*[:：]?\\\\s*([0-9]+(?:\\\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))\n        putInt(metrics, "stabilityBars", Regex("(?:합격안정성|칸수|칸\\\\s*수)?\\\\s*[:：]?\\\\s*([0-9]{1,2})\\\\s*칸").find(text)?.groupValues?.getOrNull(1))\n        putNumber(metrics, "predictionProbability", Regex("(?:예상\\\\s*)?(?:합격률|합격확률|합격가능성)\\\\s*[:：]?\\\\s*([0-9]{1,3}(?:\\\\.[0-9]+)?)\\\\s*%").find(text)?.groupValues?.getOrNull(1))\n        putText(metrics, "predictionLabel", Regex("(?:합격예측|지원판정|지원전략)?\\\\s*[:：]?\\\\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)").find(text)?.groupValues?.getOrNull(1))\n        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\\\s*[:：]?\\\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))\n        putInt(metrics, "mockApplicants", Regex("(?:모의지원자수|모의지원자 수|모의지원자)\\\\s*[:：]?\\\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))\n        putInt(metrics, "applicants", Regex("(?:현재\\\\s*)?(?:지원자수|지원자 수|실지원자수|실지원자 수)\\\\s*[:：]?\\\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))\n        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\\\s*)?경쟁률\\\\s*[:：]?\\\\s*([0-9]+(?:\\\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))\n        putInt(metrics, "myRank", Regex("(?:내\\\\s*순위|나의\\\\s*순위|현재\\\\s*순위)\\\\s*[:：]?\\\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))\n        putNumber(metrics, "predictedCut", Regex("(?:예상\\\\s*합격선|예상\\\\s*컷|합격예상점수)\\\\s*[:：]?\\\\s*([0-9]+(?:\\\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))\n        putInt(metrics, "additionalAdmits", Regex("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\\\s*[:：]?\\\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))\n        return metrics\n    }\n\n    private fun putNumber(obj: JSONObject, key: String, value: String?) {'''
if helper_anchor not in text:
    raise SystemExit('helper anchor missing')
text = text.replace(helper_anchor, helper, 1)
JINHAK.write_text(text)

# Diagnostic digest: expose only structured card metadata, never raw card text.
for p in MAIN_PATHS:
    text = p.read_text()
    old = '''                .put("observedAt", r.optString("observedAt", collectedAt)))'''
    new = '''                .put("observedAt", r.optString("observedAt", collectedAt))\n                .put("cardIndex", if (r.has("cardIndex")) r.optInt("cardIndex") else JSONObject.NULL)\n                .put("contextSource", r.optString("contextSource")))'''
    if old not in text:
        raise SystemExit(f'digest record anchor missing in {p}')
    text = text.replace(old, new, 1)
    old2 = '''            .put("recordCount", records.length())\n            .put("includedRecords", sanitized.length())'''
    new2 = '''            .put("recordCount", records.length())\n            .put("detectedStorageCards", snapshot.optJSONArray("jinhakCards")?.length() ?: 0)\n            .put("includedRecords", sanitized.length())'''
    if old2 not in text:
        raise SystemExit(f'digest summary anchor missing in {p}')
    text = text.replace(old2, new2, 1)
    p.write_text(text)

if MAIN_PATHS[0].read_text() != MAIN_PATHS[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')
print('v0.5.3 patch applied')
