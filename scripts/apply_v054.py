from pathlib import Path
import re

ROOT = Path('.')
MAIN_PATHS = [ROOT/'MainActivity.kt', ROOT/'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
JINHAK = ROOT/'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
GENERIC = ROOT/'app/src/main/java/com/admissionhub/collector/parser/GenericAdmissionParser.kt'
SNAPSHOT = ROOT/'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
GRADLE = ROOT/'app/build.gradle.kts'
MANIFEST = ROOT/'app/src/main/AndroidManifest.xml'


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'missing pattern in {path}: {old[:180]}')
    path.write_text(text.replace(old, new, 1))

for p in MAIN_PATHS:
    replace_once(p, 'private const val VERSION = "0.5.3"', 'private const val VERSION = "0.5.4"')
    replace_once(p, 'private const val BUILD_CODE = 10530', 'private const val BUILD_CODE = 10540')
replace_once(GRADLE, 'versionCode = 10530', 'versionCode = 10540')
replace_once(GRADLE, 'versionName = "0.5.3"', 'versionName = "0.5.4"')
replace_once(MANIFEST, 'Admission Collector v0.5.3 Jinhak', 'Admission Collector v0.5.4 Jinhak')

# Replace v0.5.3's text-only nearest-ancestor capture with scored DOM-root capture.
snap = SNAPSHOT.read_text()
pat = re.compile(r'''  var jinhakCards=\[\];\n  if\(/\(\^\|\\\.\)jinhak\\\.com\$/i\.test\(location\.hostname\)\)\{.*?\n  \}\n\n  var tables=\[\];''', re.S)
new_block = r'''  var jinhakCards=[];
  var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0};
  if(/(^|\.)jinhak\.com$/i.test(location.hostname)){
    var metricRx=/(?:[0-9]{1,2}\s*칸|합격(?:률|확률|가능성)|경쟁률|모의지원|합격예측|지원판정|내\s*순위|모집인원)/i;
    var primaryRx=/(?:[0-9]{1,2}\s*칸|합격(?:률|확률|가능성)|합격예측|지원판정|내\s*순위|예상\s*(?:합격선|컷))/i;
    var exactUniRx=/(?:[가-힣A-Za-z0-9·.()\-]{2,35}(?:대학교|교육대학교|과학기술원))/i;
    var deptRx=/(?:학과|학부|전공|모집단위|자율전공)/i;
    var admissionRx=/(?:지역인재|학생부교과|학생부종합|교과|종합|면접|자기추천|창의인재|학교장추천|고른기회)/i;
    var semanticRx=/(?:^|\s)(?:card|item|result|apply|support|save|univ|college|row)(?:\s|$)/i;
    var metricNodes=document.querySelectorAll('span,em,strong,b,p,td,th,li,div');
    var roots=[];

    function structuredCardText(el,maxLen){
      if(!el) return '';
      var clone=el.cloneNode(true);
      var rm=clone.querySelectorAll('script,style,noscript,template,input,textarea,select,option,form,[type=hidden],[hidden],[aria-hidden=true]');
      for(var ri=0;ri<rm.length;ri++) rm[ri].remove();
      var raw=String(clone.innerText||clone.textContent||'');
      var lines=raw.split(/\n+/).map(function(v){return cleanText(v);}).filter(function(v){return v.length>0;});
      var t=lines.join(' | ').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'[redacted-email]');
      return t.slice(0,maxLen||5000);
    }
    function rootScore(el,text){
      var hits=(text.match(/(?:[0-9]{1,2}\s*칸|합격(?:률|확률|가능성)|경쟁률|모의지원|합격예측|지원판정|내\s*순위|모집인원)/ig)||[]).length;
      var meta=cleanText((el.tagName||'')+' '+(el.id||'')+' '+(el.className||''));
      var score=0;
      if(exactUniRx.test(text)) score+=20;
      if(deptRx.test(text)) score+=12;
      if(admissionRx.test(text)) score+=4;
      if(primaryRx.test(text)) score+=8;
      if(/^(TR|LI|ARTICLE)$/i.test(el.tagName||'') || semanticRx.test(meta)) score+=8;
      if(hits<=4) score+=6; else score-=(hits-4)*7;
      score-=Math.floor(text.length/700);
      return score;
    }
    function overlapIndex(el){
      for(var oi=0;oi<roots.length;oi++){
        var other=roots[oi].el;
        if(other===el || other.contains(el) || el.contains(other)) return oi;
      }
      return -1;
    }

    for(var ji=0;ji<metricNodes.length && roots.length<120;ji++){
      var mn=metricNodes[ji];
      if(!visible(mn)) continue;
      var seed=structuredCardText(mn,420);
      if(!metricRx.test(seed)) continue;
      jinhakCardStats.metricSeeds++;
      var cur=mn, bestEl=null, bestText='', bestScore=-9999;
      for(var depth=0;cur && depth<12;depth++,cur=cur.parentElement){
        if(!visible(cur)) continue;
        var candidate=structuredCardText(cur,5000);
        if(candidate.length<18 || candidate.length>4800 || !metricRx.test(candidate)) continue;
        if(!(exactUniRx.test(candidate)||deptRx.test(candidate)||admissionRx.test(candidate))) continue;
        var score=rootScore(cur,candidate);
        if(score>bestScore){ bestScore=score; bestEl=cur; bestText=candidate; }
      }
      if(!bestEl || bestScore<2) continue;
      jinhakCardStats.candidateRoots++;
      var overlap=overlapIndex(bestEl);
      if(overlap>=0){
        if(bestScore>roots[overlap].score) roots[overlap]={el:bestEl,text:bestText,score:bestScore};
      }else{
        roots.push({el:bestEl,text:bestText,score:bestScore});
      }
    }
    for(var jr=0;jr<roots.length && jinhakCards.length<120;jr++){
      var entry=roots[jr];
      if(!primaryRx.test(entry.text)) continue;
      jinhakCards.push({
        text:entry.text,
        score:entry.score,
        rootTag:String(entry.el.tagName||'').slice(0,20),
        primaryPrediction:true
      });
    }
    jinhakCardStats.uniqueRoots=jinhakCards.length;
  }

  var tables=[];'''
snap, n = pat.subn(new_block, snap, count=1)
if n != 1:
    raise SystemExit(f'jinhak card block replace count={n}')
if 'jinhakCardStats:jinhakCardStats' not in snap:
    snap = snap.replace('    jinhakCards:jinhakCards,\n    tables:tables,', '    jinhakCards:jinhakCards,\n    jinhakCardStats:jinhakCardStats,\n    tables:tables,', 1)
SNAPSHOT.write_text(snap)

# Harden Jinhak early-storage parsing: object cards, primary metric requirement, local context cleaning and logical dedupe.
text = JINHAK.read_text()
old = '''        if (pageType == "jinhak-early-storage") {\n            val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()\n            for (i in 0 until cards.length()) {\n                val evidence = cards.optString(i).replace(Regex("\\s+"), " ").trim().take(5000)\n                if (evidence.isBlank()) continue\n                val local = GenericAdmissionParser.inferContext(evidence)\n                val cardMetrics = predictionMetrics(evidence)\n                if (!cardMetrics.keys().asSequence().any { !cardMetrics.isNull(it) }) continue\n                val record = JSONObject()\n                    .put("recordType", "jinhak-saved-application-prediction")\n                    .put("providerPageType", pageType)\n                    .put("dataScope", "current-prediction")\n                    .put("year", local.year ?: TARGET_YEAR)\n                    .put("university", local.university ?: JSONObject.NULL)\n                    .put("department", local.department ?: JSONObject.NULL)\n                    .put("admission", local.admission ?: JSONObject.NULL)\n                    .put("metrics", cardMetrics)\n                    .put("observedAt", observedAt)\n                    .put("cardIndex", i)\n                    .put("contextSource", "card-local")\n                    .put("confidence", when {\n                        local.university != null && local.department != null && local.admission != null -> "high"\n                        local.university != null && local.department != null -> "medium"\n                        local.department != null -> "low"\n                        else -> "raw"\n                    })\n                    .put("sourcePage", safePath(snapshot.optString("url")))\n                    .put("rawEvidence", evidence)\n                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = true))\n                result.put(record)\n            }\n            return RecordUtils.dedupe(result)\n        }'''
new = '''        if (pageType == "jinhak-early-storage") {\n            val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()\n            val seenLogical = linkedSetOf<String>()\n            for (i in 0 until cards.length()) {\n                val cardObj = cards.optJSONObject(i)\n                val evidence = (cardObj?.optString("text") ?: cards.optString(i))\n                    .replace(Regex("\\s+"), " ").trim().take(5000)\n                if (evidence.isBlank()) continue\n                val local = GenericAdmissionParser.inferContext(evidence)\n                val university = local.university\n                val department = cleanStorageDepartment(local.department)\n                val admission = cleanStorageAdmission(local.admission, evidence)\n                val cardMetrics = predictionMetrics(evidence)\n                val hasPrimaryPrediction = listOf(\n                    "stabilityBars", "predictionProbability", "predictionLabel", "myRank", "predictedCut"\n                ).any { cardMetrics.has(it) && !cardMetrics.isNull(it) }\n                if (!hasPrimaryPrediction) continue\n                val logical = RecordUtils.sha256(listOf(\n                    university ?: "", department ?: "", admission ?: "", cardMetrics.toString()\n                ).joinToString("|"))\n                if (!seenLogical.add(logical)) continue\n                val record = JSONObject()\n                    .put("recordType", "jinhak-saved-application-prediction")\n                    .put("providerPageType", pageType)\n                    .put("dataScope", "current-prediction")\n                    .put("year", local.year ?: TARGET_YEAR)\n                    .put("university", university ?: JSONObject.NULL)\n                    .put("department", department ?: JSONObject.NULL)\n                    .put("admission", admission ?: JSONObject.NULL)\n                    .put("metrics", cardMetrics)\n                    .put("observedAt", observedAt)\n                    .put("cardIndex", i)\n                    .put("contextSource", "scored-card-root")\n                    .put("cardRootScore", cardObj?.optInt("score", 0) ?: 0)\n                    .put("confidence", when {\n                        university != null && department != null && admission != null -> "high"\n                        university != null && department != null -> "medium"\n                        department != null -> "low"\n                        else -> "raw"\n                    })\n                    .put("sourcePage", safePath(snapshot.optString("url")))\n                    .put("rawEvidence", evidence)\n                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = true))\n                result.put(record)\n            }\n            return RecordUtils.dedupe(result)\n        }'''
if old not in text:
    raise SystemExit('early-storage normalize block missing')
text = text.replace(old, new, 1)

anchor = '''    private fun predictionMetrics(text: String): JSONObject {'''
helpers = '''    private fun cleanStorageDepartment(value: String?): String? {\n        val raw = value?.trim()?.takeIf { it.isNotBlank() } ?: return null\n        val cleaned = raw.replace(\n            Regex("^(?:지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\\(면접형\\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)"),\n            ""\n        ).trim()\n        return cleaned.takeIf { it.length >= 2 } ?: raw\n    }\n\n    private fun cleanStorageAdmission(value: String?, evidence: String): String? {\n        val polluted = Regex("(등급|경쟁률|전년도|점수|[0-9]{1,2}\\s*칸|합격률|합격확률)")\n        value?.trim()?.takeIf { it.isNotBlank() && it.length <= 40 && !polluted.containsMatchIn(it) }?.let { return it }\n        val token = Regex("(지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\\(면접형\\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)")\n            .find(evidence)?.groupValues?.getOrNull(1)\n        return token?.trim()?.takeIf { it.isNotBlank() }\n    }\n\n    private fun predictionMetrics(text: String): JSONObject {'''
if anchor not in text:
    raise SystemExit('predictionMetrics anchor missing')
text = text.replace(anchor, helpers, 1)
JINHAK.write_text(text)

# Generic admission context must never accept result prose as an admission name.
g = GENERIC.read_text()
old_noise = '학생부 반영비율|있는 전형|없는 서류|설명|안내|^서류\\s*평가\\s*전형$'
new_noise = '학생부 반영비율|있는 전형|없는 서류|설명|안내|등급|경쟁률|전년도|점수|칸|합격률|^서류\\s*평가\\s*전형$'
if old_noise not in g:
    raise SystemExit('generic admission noise pattern missing')
g = g.replace(old_noise, new_noise, 1)
GENERIC.write_text(g)

# Add compact capture statistics to the diagnostic digest; still no DOM/raw text upload.
for p in MAIN_PATHS:
    m = p.read_text()
    old_digest = '''            .put("detectedStorageCards", snapshot.optJSONArray("jinhakCards")?.length() ?: 0)\n            .put("includedRecords", sanitized.length())'''
    new_digest = '''            .put("detectedStorageCards", snapshot.optJSONArray("jinhakCards")?.length() ?: 0)\n            .put("cardCaptureStats", snapshot.optJSONObject("jinhakCardStats") ?: JSONObject())\n            .put("includedRecords", sanitized.length())'''
    if old_digest not in m:
        raise SystemExit(f'digest stats anchor missing in {p}')
    p.write_text(m.replace(old_digest, new_digest, 1))

if MAIN_PATHS[0].read_text() != MAIN_PATHS[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')
print('v0.5.4 patch applied')
