from pathlib import Path

ROOT = Path('.')
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
JINHAK = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

s = SNAP.read_text()
s = s.replace(
    'var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0};',
    'var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0,departmentBoundRoots:0,departmentContextRoots:0,departmentMissingRoots:0};',
    1,
)

anchor = '''    function universityContextFor(el,rootText){'''
insert = r'''    function cleanDepartmentName(value){
      var v=cleanText(value);
      if(!v) return '';
      v=v.replace(/^(?:(?:닫기|열기|보기|상세|선택|삭제)\s*)+/,'');
      v=v.replace(/^(?:지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\(면접형\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)\s*/,'');
      if(v.length<2||v.length>55) return '';
      if(/(?:등급|경쟁률|합격|예측|지원판정|모집인원|[0-9]{1,2}\s*칸)/.test(v)) return '';
      if(!/(?:학과|학부|전공|자율전공)$/.test(v)) return '';
      return v;
    }
    function explicitDepartmentNames(text){
      text=String(text||'');
      var names=[];
      var parts=text.split('|');
      for(var di=0;di<parts.length;di++){
        var part=cleanText(parts[di]);
        var dm=part.match(/([가-힣A-Za-z0-9·.()&・\- ]{2,48}(?:학과|학부|전공|자율전공))/g)||[];
        for(var dj=0;dj<dm.length;dj++){
          var dv=cleanDepartmentName(dm[dj]);
          if(dv&&names.indexOf(dv)<0) names.push(dv);
        }
      }
      return names;
    }
    function departmentContextFor(el,rootText){
      var direct=explicitDepartmentNames(rootText);
      if(direct.length===1) return {name:direct[0],source:'card-root',depth:0};
      var cur=el;
      for(var depth=0;cur&&depth<8;depth++){
        var attrs=cleanText((cur.getAttribute&&cur.getAttribute('aria-label')||'')+' '+(cur.getAttribute&&cur.getAttribute('title')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-dept-name')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-department-name')||''));
        var an=explicitDepartmentNames(attrs);
        if(an.length===1) return {name:an[0],source:'ancestor-attribute',depth:depth};

        var prev=cur.previousElementSibling;
        for(var pi=0;prev&&pi<5;pi++,prev=prev.previousElementSibling){
          if(!visible(prev)) continue;
          var pt=structuredCardText(prev,900);
          if(primaryRx.test(pt)) break;
          var pn=explicitDepartmentNames(pt);
          var pm=cleanText((prev.tagName||'')+' '+(prev.id||'')+' '+(prev.className||''));
          if(pn.length===1 && (pt.length<=220 || /title|tit|name|dept|major|header|head/i.test(pm))){
            return {name:pn[0],source:'preceding-sibling',depth:depth};
          }
        }

        var parent=cur.parentElement;
        if(!parent) break;
        var parentText=structuredCardText(parent,7000);
        var parentNames=explicitDepartmentNames(parentText);
        var parentHits=(parentText.match(/(?:[0-9]{1,2}\s*칸|합격(?:률|확률|가능성)|경쟁률|모의지원|내\s*순위)/ig)||[]).length;
        if(parentNames.length===1 && parentHits<=8){
          return {name:parentNames[0],source:'ancestor-unique',depth:depth+1};
        }
        cur=parent;
      }
      return {name:'',source:'missing',depth:-1};
    }

    function universityContextFor(el,rootText){'''
if anchor not in s:
    raise SystemExit('universityContextFor anchor missing')
s = s.replace(anchor, insert, 1)

old = '''      var universityCtx=universityContextFor(entry.el,entry.text);
      if(universityCtx.name){
        jinhakCardStats.universityBoundRoots++;
        if(universityCtx.source!=='card-root') jinhakCardStats.universityContextRoots++;
      }else{
        jinhakCardStats.universityMissingRoots++;
      }
      jinhakCards.push({
        text:entry.text,
        score:entry.score,
        rootTag:String(entry.el.tagName||'').slice(0,20),
        primaryPrediction:true,
        university:universityCtx.name,
        universitySource:universityCtx.source,
        universityDepth:universityCtx.depth
      });'''
new = '''      var universityCtx=universityContextFor(entry.el,entry.text);
      var departmentCtx=departmentContextFor(entry.el,entry.text);
      if(universityCtx.name){
        jinhakCardStats.universityBoundRoots++;
        if(universityCtx.source!=='card-root') jinhakCardStats.universityContextRoots++;
      }else{
        jinhakCardStats.universityMissingRoots++;
      }
      if(departmentCtx.name){
        jinhakCardStats.departmentBoundRoots++;
        if(departmentCtx.source!=='card-root') jinhakCardStats.departmentContextRoots++;
      }else{
        jinhakCardStats.departmentMissingRoots++;
      }
      jinhakCards.push({
        text:entry.text,
        score:entry.score,
        rootTag:String(entry.el.tagName||'').slice(0,20),
        primaryPrediction:true,
        university:universityCtx.name,
        universitySource:universityCtx.source,
        universityDepth:universityCtx.depth,
        department:departmentCtx.name,
        departmentSource:departmentCtx.source,
        departmentDepth:departmentCtx.depth
      });'''
if old not in s:
    raise SystemExit('card context push anchor missing')
s = s.replace(old, new, 1)
SNAP.write_text(s)

j = JINHAK.read_text()
old_cards = '''            val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
            val seenLogical = linkedSetOf<String>()
            for (i in 0 until cards.length()) {'''
new_cards = '''            val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
            var hasRicherPredictionCards = false
            for (ci in 0 until cards.length()) {
                val cObj = cards.optJSONObject(ci)
                val cEvidence = (cObj?.optString("text") ?: cards.optString(ci)).replace(Regex("""\\s+"""), " ").trim()
                if (cEvidence.isBlank()) continue
                val cMetrics = predictionMetrics(cEvidence)
                if (listOf("mockCompetition", "predictionProbability", "myRank", "predictedCut", "mockApplicants", "applicants").any { cMetrics.has(it) && !cMetrics.isNull(it) }) {
                    hasRicherPredictionCards = true
                    break
                }
            }
            val seenLogical = linkedSetOf<String>()
            for (i in 0 until cards.length()) {'''
if old_cards not in j:
    raise SystemExit('cards loop anchor missing')
j = j.replace(old_cards, new_cards, 1)

old_ctx = '''                val local = GenericAdmissionParser.inferContext(evidence)
                val explicitUniversity = cleanStorageUniversity(cardObj?.optString("university"))
                val university = local.university ?: explicitUniversity
                val department = cleanStorageDepartment(local.department)
                val admission = cleanStorageAdmission(local.admission, evidence)
                val universityContextSource = cardObj?.optString("universitySource")
                    ?.takeIf { it.isNotBlank() && it != "missing" }
                val cardMetrics = predictionMetrics(evidence)'''
new_ctx = '''                val local = GenericAdmissionParser.inferContext(evidence)
                val explicitUniversity = cleanStorageUniversity(cardObj?.optString("university"))
                val explicitDepartment = cleanStorageDepartment(cardObj?.optString("department"))
                val university = cleanStorageUniversity(local.university) ?: explicitUniversity
                val department = cleanStorageDepartment(local.department) ?: explicitDepartment
                val admission = cleanStorageAdmission(local.admission, evidence)
                val universityContextSource = cardObj?.optString("universitySource")
                    ?.takeIf { it.isNotBlank() && it != "missing" }
                val departmentContextSource = cardObj?.optString("departmentSource")
                    ?.takeIf { it.isNotBlank() && it != "missing" }
                val cardMetrics = predictionMetrics(evidence)
                val metricKeys = cardMetrics.keys().asSequence().filter { !cardMetrics.isNull(it) }.toList()
                val summaryOnly = metricKeys.size == 1 && metricKeys.firstOrNull() == "stabilityBars"
                if (hasRicherPredictionCards && summaryOnly) continue'''
if old_ctx not in j:
    raise SystemExit('normalizer context anchor missing')
j = j.replace(old_ctx, new_ctx, 1)

old_record = '''                    .put("contextSource", if (local.university == null && explicitUniversity != null) "scored-card-root+explicit-university-context" else "scored-card-root")
                    .put("universityContextSource", universityContextSource ?: JSONObject.NULL)
                    .put("universityContextDepth", cardObj?.optInt("universityDepth", -1) ?: -1)
                    .put("cardRootScore", cardObj?.optInt("score", 0) ?: 0)'''
new_record = '''                    .put("contextSource", when {
                        local.university == null && explicitUniversity != null && local.department == null && explicitDepartment != null -> "scored-card-root+university+department-context"
                        local.university == null && explicitUniversity != null -> "scored-card-root+explicit-university-context"
                        local.department == null && explicitDepartment != null -> "scored-card-root+explicit-department-context"
                        else -> "scored-card-root"
                    })
                    .put("universityContextSource", universityContextSource ?: JSONObject.NULL)
                    .put("universityContextDepth", cardObj?.optInt("universityDepth", -1) ?: -1)
                    .put("departmentContextSource", departmentContextSource ?: JSONObject.NULL)
                    .put("departmentContextDepth", cardObj?.optInt("departmentDepth", -1) ?: -1)
                    .put("cardRootScore", cardObj?.optInt("score", 0) ?: 0)'''
if old_record not in j:
    raise SystemExit('record context anchor missing')
j = j.replace(old_record, new_record, 1)

old_clean = '''    private fun cleanStorageUniversity(value: String?): String? {
        val raw = value?.replace(Regex("""\\s+"""), " ")?.trim()?.takeIf { it.isNotBlank() } ?: return null
        if (raw.length !in 3..48) return null
        if (Regex("""(등급|경쟁률|합격|예측|지원|전형|모집|학과|학부|전공)""").containsMatchIn(raw)) return null
        val full = Regex("""^[가-힣A-Za-z0-9·.()\\-]{2,35}(?:대학교|교육대학교|과학기술원)(?:\\[[^\\]]{1,12}\\])?$""")
        val short = Regex("""^[가-힣A-Za-z0-9·.()\\-]{2,24}대$""")
        val shortNoise = setOf("공대", "의대", "법대", "상대", "교대", "사범대", "간호대", "약대", "치대", "한의대", "철도대")
        return when {
            full.matches(raw) -> raw
            short.matches(raw) && raw !in shortNoise -> raw
            else -> null
        }
    }'''
new_clean = '''    private fun cleanStorageUniversity(value: String?): String? {
        val raw = value?.replace(Regex("""\\s+"""), " ")?.trim()?.takeIf { it.isNotBlank() } ?: return null
        val cleaned = raw
            .replace(Regex("""^(?:(?:닫기|열기|보기|상세|선택|삭제)\\s*)*(?:[0-9]{1,2}\\s*칸\\s*)?"""), "")
            .trim()
        if (cleaned.length !in 3..48) return null
        if (Regex("""(등급|경쟁률|합격|예측|지원|전형|모집|학과|학부|전공)""").containsMatchIn(cleaned)) return null
        val full = Regex("""^[가-힣A-Za-z0-9·.()\\-]{2,35}(?:대학교|교육대학교|과학기술원)(?:\\[[^\\]]{1,12}\\])?$""")
        val short = Regex("""^[가-힣A-Za-z0-9·.()\\-]{2,24}대$""")
        val shortNoise = setOf("공대", "의대", "법대", "상대", "교대", "사범대", "간호대", "약대", "치대", "한의대", "철도대")
        return when {
            full.matches(cleaned) -> cleaned
            short.matches(cleaned) && cleaned !in shortNoise -> cleaned
            else -> null
        }
    }'''
if old_clean not in j:
    raise SystemExit('cleanStorageUniversity anchor missing')
j = j.replace(old_clean, new_clean, 1)
JINHAK.write_text(j)

for p in MAIN_FILES:
    m = p.read_text()
    old_fields = '''                .put("universityContextSource", if (r.isNull("universityContextSource")) JSONObject.NULL else r.optString("universityContextSource"))
                .put("universityContextDepth", r.optInt("universityContextDepth", -1)))'''
    new_fields = '''                .put("universityContextSource", if (r.isNull("universityContextSource")) JSONObject.NULL else r.optString("universityContextSource"))
                .put("universityContextDepth", r.optInt("universityContextDepth", -1))
                .put("departmentContextSource", if (r.isNull("departmentContextSource")) JSONObject.NULL else r.optString("departmentContextSource"))
                .put("departmentContextDepth", r.optInt("departmentContextDepth", -1)))'''
    if old_fields not in m:
        raise SystemExit(f'digest field anchor missing: {p}')
    m = m.replace(old_fields, new_fields, 1)
    m = m.replace('private const val VERSION = "0.5.5"', 'private const val VERSION = "0.5.6"', 1)
    m = m.replace('private const val BUILD_CODE = 10550', 'private const val BUILD_CODE = 10560', 1)
    p.write_text(m)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')

g = GRADLE.read_text().replace('versionCode = 10550', 'versionCode = 10560', 1).replace('versionName = "0.5.5"', 'versionName = "0.5.6"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text().replace('Admission Collector v0.5.5 Jinhak', 'Admission Collector v0.5.6 Jinhak', 1)
MANIFEST.write_text(mf)

print('v0.5.6 Jinhak binding cleanup patch applied')
