from pathlib import Path
import re

ROOT=Path('.')
MAIN=[ROOT/'MainActivity.kt',ROOT/'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
JINHAK=ROOT/'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
GENERIC=ROOT/'app/src/main/java/com/admissionhub/collector/parser/GenericAdmissionParser.kt'
SNAP=ROOT/'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
GRADLE=ROOT/'app/build.gradle.kts'
MANIFEST=ROOT/'app/src/main/AndroidManifest.xml'

def rep(path,old,new):
    t=path.read_text()
    if old not in t: raise SystemExit(f'missing {old} in {path}')
    path.write_text(t.replace(old,new,1))

for p in MAIN:
    rep(p,'private const val VERSION = "0.5.3"','private const val VERSION = "0.5.4"')
    rep(p,'private const val BUILD_CODE = 10530','private const val BUILD_CODE = 10540')
rep(GRADLE,'versionCode = 10530','versionCode = 10540')
rep(GRADLE,'versionName = "0.5.3"','versionName = "0.5.4"')
rep(MANIFEST,'Admission Collector v0.5.3 Jinhak','Admission Collector v0.5.4 Jinhak')

snap=SNAP.read_text()
spat=re.compile(r'  var jinhakCards=\[\];\n  if\(/\(\^\|\\\.\)jinhak\\\.com\$/i\.test\(location\.hostname\)\)\{.*?\n  \}\n\n  var tables=\[\];',re.S)
snew=r'''  var jinhakCards=[];
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
      if(/^(TR|LI|ARTICLE)$/i.test(el.tagName||'')||semanticRx.test(meta)) score+=8;
      if(hits<=4) score+=6; else score-=(hits-4)*7;
      score-=Math.floor(text.length/700);
      return score;
    }
    function overlapIndex(el){
      for(var oi=0;oi<roots.length;oi++){
        var other=roots[oi].el;
        if(other===el||other.contains(el)||el.contains(other)) return oi;
      }
      return -1;
    }
    for(var ji=0;ji<metricNodes.length&&roots.length<120;ji++){
      var mn=metricNodes[ji];
      if(!visible(mn)) continue;
      var seed=structuredCardText(mn,420);
      if(!metricRx.test(seed)) continue;
      jinhakCardStats.metricSeeds++;
      var cur=mn,bestEl=null,bestText='',bestScore=-9999;
      for(var depth=0;cur&&depth<12;depth++,cur=cur.parentElement){
        if(!visible(cur)) continue;
        var candidate=structuredCardText(cur,5000);
        if(candidate.length<18||candidate.length>4800||!metricRx.test(candidate)) continue;
        if(!(exactUniRx.test(candidate)||deptRx.test(candidate)||admissionRx.test(candidate))) continue;
        var score=rootScore(cur,candidate);
        if(score>bestScore){bestScore=score;bestEl=cur;bestText=candidate;}
      }
      if(!bestEl||bestScore<2) continue;
      jinhakCardStats.candidateRoots++;
      var overlap=overlapIndex(bestEl);
      if(overlap>=0){if(bestScore>roots[overlap].score) roots[overlap]={el:bestEl,text:bestText,score:bestScore};}
      else roots.push({el:bestEl,text:bestText,score:bestScore});
    }
    for(var jr=0;jr<roots.length&&jinhakCards.length<120;jr++){
      var entry=roots[jr];
      if(!primaryRx.test(entry.text)) continue;
      jinhakCards.push({text:entry.text,score:entry.score,rootTag:String(entry.el.tagName||'').slice(0,20),primaryPrediction:true});
    }
    jinhakCardStats.uniqueRoots=jinhakCards.length;
  }

  var tables=[];'''
snap,n=spat.subn(lambda _m:snew,snap,count=1)
if n!=1: raise SystemExit(f'snapshot card block count={n}')
if 'jinhakCardStats:jinhakCardStats' not in snap:
    snap=snap.replace('    jinhakCards:jinhakCards,\n    tables:tables,','    jinhakCards:jinhakCards,\n    jinhakCardStats:jinhakCardStats,\n    tables:tables,',1)
SNAP.write_text(snap)

j=JINHAK.read_text()
jpat=re.compile(r'        if \(pageType == "jinhak-early-storage"\) \{.*?\n        \}\n\n        val metrics = JSONObject\(\)',re.S)
jnew='''        if (pageType == "jinhak-early-storage") {
            val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
            val seenLogical = linkedSetOf<String>()
            for (i in 0 until cards.length()) {
                val cardObj = cards.optJSONObject(i)
                val evidence = (cardObj?.optString("text") ?: cards.optString(i))
                    .replace(Regex("\\s+"), " ").trim().take(5000)
                if (evidence.isBlank()) continue
                val local = GenericAdmissionParser.inferContext(evidence)
                val university = local.university
                val department = cleanStorageDepartment(local.department)
                val admission = cleanStorageAdmission(local.admission, evidence)
                val cardMetrics = predictionMetrics(evidence)
                val hasPrimaryPrediction = listOf(
                    "stabilityBars", "predictionProbability", "predictionLabel", "myRank", "predictedCut"
                ).any { cardMetrics.has(it) && !cardMetrics.isNull(it) }
                if (!hasPrimaryPrediction) continue
                val logical = RecordUtils.sha256(listOf(
                    university ?: "", department ?: "", admission ?: "", cardMetrics.toString()
                ).joinToString("|"))
                if (!seenLogical.add(logical)) continue
                val record = JSONObject()
                    .put("recordType", "jinhak-saved-application-prediction")
                    .put("providerPageType", pageType)
                    .put("dataScope", "current-prediction")
                    .put("year", local.year ?: TARGET_YEAR)
                    .put("university", university ?: JSONObject.NULL)
                    .put("department", department ?: JSONObject.NULL)
                    .put("admission", admission ?: JSONObject.NULL)
                    .put("metrics", cardMetrics)
                    .put("observedAt", observedAt)
                    .put("cardIndex", i)
                    .put("contextSource", "scored-card-root")
                    .put("cardRootScore", cardObj?.optInt("score", 0) ?: 0)
                    .put("confidence", when {
                        university != null && department != null && admission != null -> "high"
                        university != null && department != null -> "medium"
                        department != null -> "low"
                        else -> "raw"
                    })
                    .put("sourcePage", safePath(snapshot.optString("url")))
                    .put("rawEvidence", evidence)
                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = true))
                result.put(record)
            }
            return RecordUtils.dedupe(result)
        }

        val metrics = JSONObject()'''
j,n=jpat.subn(lambda _m:jnew,j,count=1)
if n!=1: raise SystemExit(f'early-storage normalize count={n}')
anchor='    private fun predictionMetrics(text: String): JSONObject {'
helpers='''    private fun cleanStorageDepartment(value: String?): String? {
        val raw = value?.trim()?.takeIf { it.isNotBlank() } ?: return null
        val cleaned = raw.replace(
            Regex("^(?:지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\\(면접형\\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)"),
            ""
        ).trim()
        return cleaned.takeIf { it.length >= 2 } ?: raw
    }

    private fun cleanStorageAdmission(value: String?, evidence: String): String? {
        val polluted = Regex("(등급|경쟁률|전년도|점수|[0-9]{1,2}\\s*칸|합격률|합격확률)")
        value?.trim()?.takeIf { it.isNotBlank() && it.length <= 40 && !polluted.containsMatchIn(it) }?.let { return it }
        val token = Regex("(지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\\(면접형\\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)")
            .find(evidence)?.groupValues?.getOrNull(1)
        return token?.trim()?.takeIf { it.isNotBlank() }
    }

    private fun predictionMetrics(text: String): JSONObject {'''
if anchor not in j: raise SystemExit('prediction helper anchor missing')
j=j.replace(anchor,helpers,1)
JINHAK.write_text(j)

# Generic admission filtering is secondary; strengthen it when the exact fragment is present,
# but never fail the build because of formatting/escaping differences in this helper parser.
g=GENERIC.read_text()
if '설명|안내|' in g and '설명|안내|등급|경쟁률|전년도|점수|칸|합격률|' not in g:
    g=g.replace('설명|안내|','설명|안내|등급|경쟁률|전년도|점수|칸|합격률|',1)
GENERIC.write_text(g)

for p in MAIN:
    m=p.read_text()
    old='''            .put("detectedStorageCards", snapshot.optJSONArray("jinhakCards")?.length() ?: 0)
            .put("includedRecords", sanitized.length())'''
    new='''            .put("detectedStorageCards", snapshot.optJSONArray("jinhakCards")?.length() ?: 0)
            .put("cardCaptureStats", snapshot.optJSONObject("jinhakCardStats") ?: JSONObject())
            .put("includedRecords", sanitized.length())'''
    if old not in m: raise SystemExit(f'digest anchor missing {p}')
    p.write_text(m.replace(old,new,1))

if MAIN[0].read_text()!=MAIN[1].read_text(): raise SystemExit('MainActivity mirrors diverged')
print('v0.5.4b patch applied')
