from pathlib import Path

ROOT = Path('.')
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
JINHAK = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
MAIN_FILES = [
    ROOT / 'MainActivity.kt',
    ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt',
]
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# ---- Snapshot: keep v0.5.4 card roots, add explicit university-context binding. ----
s = SNAP.read_text()
s = s.replace(
    'var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0};',
    'var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0};',
    1,
)
old_loop = r'''    for(var jr=0;jr<roots.length&&jinhakCards.length<120;jr++){
      var entry=roots[jr];
      if(!primaryRx.test(entry.text)) continue;
      jinhakCards.push({text:entry.text,score:entry.score,rootTag:String(entry.el.tagName||'').slice(0,20),primaryPrediction:true});
    }
    jinhakCardStats.uniqueRoots=jinhakCards.length;'''
new_loop = r'''    function explicitUniversityNames(text){
      text=cleanText(text);
      var names=[];
      var full=/([가-힣A-Za-z0-9·.()\-]{2,35}(?:대학교|교육대학교|과학기술원)(?:\[[^\]]{1,12}\])?)/ig;
      var fm;
      while((fm=full.exec(text))!==null){
        var fv=cleanText(fm[1]);
        if(fv && names.indexOf(fv)<0) names.push(fv);
      }
      // Jinhak sometimes renders a university as a short name such as "한밭대".
      // Accept only a concise, explicit token and reject generic college abbreviations.
      var short=/(?:^|[\s|])([가-힣A-Za-z0-9·.()\-]{2,24}대)(?=$|[\s|\[\](),·/])/g;
      var sm;
      var shortNoise=/^(?:공대|의대|법대|상대|교대|사범대|간호대|약대|치대|한의대|철도대)$/;
      while((sm=short.exec(text))!==null){
        var sv=cleanText(sm[1]);
        if(!sv||shortNoise.test(sv)||/(지원|합격|예측|전형|모집|학부|학과)/.test(sv)) continue;
        if(names.indexOf(sv)<0) names.push(sv);
      }
      return names;
    }
    function universityContextFor(el,rootText){
      var direct=explicitUniversityNames(rootText);
      if(direct.length===1) return {name:direct[0],source:'card-root',depth:0};
      var cur=el;
      for(var depth=0;cur&&depth<9;depth++){
        var attrs=cleanText((cur.getAttribute&&cur.getAttribute('aria-label')||'')+' '+(cur.getAttribute&&cur.getAttribute('title')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-univ-name')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-university-name')||''));
        var an=explicitUniversityNames(attrs);
        if(an.length===1) return {name:an[0],source:'ancestor-attribute',depth:depth};

        var prev=cur.previousElementSibling;
        for(var pi=0;prev&&pi<6;pi++,prev=prev.previousElementSibling){
          if(!visible(prev)) continue;
          var pt=structuredCardText(prev,1000);
          var pn=explicitUniversityNames(pt);
          var pm=cleanText((prev.tagName||'')+' '+(prev.id||'')+' '+(prev.className||''));
          if(pn.length===1 && (pt.length<=260 || /title|tit|name|univ|college|header|head/i.test(pm))){
            return {name:pn[0],source:'preceding-sibling',depth:depth};
          }
          if(depth===0 && primaryRx.test(pt)) break;
        }

        var next=cur.nextElementSibling;
        for(var ni=0;next&&ni<3;ni++,next=next.nextElementSibling){
          if(!visible(next)) continue;
          var nt=structuredCardText(next,700);
          if(primaryRx.test(nt)) break;
          var nn=explicitUniversityNames(nt);
          var nm=cleanText((next.tagName||'')+' '+(next.id||'')+' '+(next.className||''));
          if(nn.length===1 && (nt.length<=180 || /title|tit|name|univ|college|header|head/i.test(nm))){
            return {name:nn[0],source:'following-sibling',depth:depth};
          }
        }

        var parent=cur.parentElement;
        if(!parent) break;
        var parentText=structuredCardText(parent,10000);
        var parentNames=explicitUniversityNames(parentText);
        if(parentNames.length===1){
          return {name:parentNames[0],source:'ancestor-unique',depth:depth+1};
        }
        cur=parent;
      }
      return {name:'',source:'missing',depth:-1};
    }
    for(var jr=0;jr<roots.length&&jinhakCards.length<120;jr++){
      var entry=roots[jr];
      if(!primaryRx.test(entry.text)) continue;
      var universityCtx=universityContextFor(entry.el,entry.text);
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
      });
    }
    jinhakCardStats.uniqueRoots=jinhakCards.length;'''
if old_loop not in s:
    raise SystemExit('Snapshot v0.5.4 card loop anchor missing')
s = s.replace(old_loop, new_loop, 1)
SNAP.write_text(s)

# ---- Jinhak normalizer: use only explicit DOM university evidence; never infer from dept/admission. ----
j = JINHAK.read_text()
old_ctx = '''                val local = GenericAdmissionParser.inferContext(evidence)
                val university = local.university
                val department = cleanStorageDepartment(local.department)
                val admission = cleanStorageAdmission(local.admission, evidence)'''
new_ctx = '''                val local = GenericAdmissionParser.inferContext(evidence)
                val explicitUniversity = cleanStorageUniversity(cardObj?.optString("university"))
                val university = local.university ?: explicitUniversity
                val department = cleanStorageDepartment(local.department)
                val admission = cleanStorageAdmission(local.admission, evidence)
                val universityContextSource = cardObj?.optString("universitySource")
                    ?.takeIf { it.isNotBlank() && it != "missing" }'''
if old_ctx not in j:
    raise SystemExit('Jinhak local context anchor missing')
j = j.replace(old_ctx, new_ctx, 1)

old_record_ctx = '''                    .put("cardIndex", i)
                    .put("contextSource", "scored-card-root")
                    .put("cardRootScore", cardObj?.optInt("score", 0) ?: 0)'''
new_record_ctx = '''                    .put("cardIndex", i)
                    .put("contextSource", if (local.university == null && explicitUniversity != null) "scored-card-root+explicit-university-context" else "scored-card-root")
                    .put("universityContextSource", universityContextSource ?: JSONObject.NULL)
                    .put("universityContextDepth", cardObj?.optInt("universityDepth", -1) ?: -1)
                    .put("cardRootScore", cardObj?.optInt("score", 0) ?: 0)'''
if old_record_ctx not in j:
    raise SystemExit('Jinhak record context anchor missing')
j = j.replace(old_record_ctx, new_record_ctx, 1)

helper_anchor = '''    private fun cleanStorageDepartment(value: String?): String? {'''
helper = r'''    private fun cleanStorageUniversity(value: String?): String? {
        val raw = value?.replace(Regex("""\s+"""), " ")?.trim()?.takeIf { it.isNotBlank() } ?: return null
        if (raw.length !in 3..48) return null
        if (Regex("""(등급|경쟁률|합격|예측|지원|전형|모집|학과|학부|전공)""").containsMatchIn(raw)) return null
        val full = Regex("""^[가-힣A-Za-z0-9·.()\-]{2,35}(?:대학교|교육대학교|과학기술원)(?:\[[^\]]{1,12}\])?$""")
        val short = Regex("""^[가-힣A-Za-z0-9·.()\-]{2,24}대$""")
        val shortNoise = setOf("공대", "의대", "법대", "상대", "교대", "사범대", "간호대", "약대", "치대", "한의대", "철도대")
        return when {
            full.matches(raw) -> raw
            short.matches(raw) && raw !in shortNoise -> raw
            else -> null
        }
    }

    private fun cleanStorageDepartment(value: String?): String? {'''
if helper_anchor not in j:
    raise SystemExit('Jinhak helper anchor missing')
j = j.replace(helper_anchor, helper, 1)
JINHAK.write_text(j)

# ---- Digest: expose field-binding quality without DOM/raw evidence. ----
for p in MAIN_FILES:
    m = p.read_text()
    old_start = '''        val sanitized = JSONArray()
        val limit = minOf(records.length(), 120)
        for (i in 0 until limit) {'''
    new_start = '''        val sanitized = JSONArray()
        var universityBound = 0
        var departmentBound = 0
        var admissionBound = 0
        var fullyBound = 0
        for (i in 0 until records.length()) {
            val r = records.optJSONObject(i) ?: continue
            val hasUniversity = !r.isNull("university") && r.optString("university").isNotBlank()
            val hasDepartment = !r.isNull("department") && r.optString("department").isNotBlank()
            val hasAdmission = !r.isNull("admission") && r.optString("admission").isNotBlank()
            if (hasUniversity) universityBound += 1
            if (hasDepartment) departmentBound += 1
            if (hasAdmission) admissionBound += 1
            if (hasUniversity && hasDepartment && hasAdmission) fullyBound += 1
        }
        val limit = minOf(records.length(), 120)
        for (i in 0 until limit) {'''
    if old_start not in m:
        raise SystemExit(f'digest start anchor missing: {p}')
    m = m.replace(old_start, new_start, 1)

    old_fields = '''                .put("cardIndex", if (r.has("cardIndex")) r.optInt("cardIndex") else JSONObject.NULL)
                .put("contextSource", r.optString("contextSource")))'''
    new_fields = '''                .put("cardIndex", if (r.has("cardIndex")) r.optInt("cardIndex") else JSONObject.NULL)
                .put("contextSource", r.optString("contextSource"))
                .put("universityContextSource", if (r.isNull("universityContextSource")) JSONObject.NULL else r.optString("universityContextSource"))
                .put("universityContextDepth", r.optInt("universityContextDepth", -1)))'''
    if old_fields not in m:
        raise SystemExit(f'digest fields anchor missing: {p}')
    m = m.replace(old_fields, new_fields, 1)

    old_return = '''            .put("cardCaptureStats", snapshot.optJSONObject("jinhakCardStats") ?: JSONObject())
            .put("includedRecords", sanitized.length())'''
    new_return = '''            .put("cardCaptureStats", snapshot.optJSONObject("jinhakCardStats") ?: JSONObject())
            .put("bindingStats", JSONObject()
                .put("universityBound", universityBound)
                .put("departmentBound", departmentBound)
                .put("admissionBound", admissionBound)
                .put("fullyBound", fullyBound)
                .put("totalRecords", records.length()))
            .put("includedRecords", sanitized.length())'''
    if old_return not in m:
        raise SystemExit(f'digest return anchor missing: {p}')
    m = m.replace(old_return, new_return, 1)
    m = m.replace('private const val VERSION = "0.5.4"', 'private const val VERSION = "0.5.5"', 1)
    m = m.replace('private const val BUILD_CODE = 10540', 'private const val BUILD_CODE = 10550', 1)
    p.write_text(m)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')

g = GRADLE.read_text()
g = g.replace('versionCode = 10540', 'versionCode = 10550', 1)
g = g.replace('versionName = "0.5.4"', 'versionName = "0.5.5"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text()
mf = mf.replace('Admission Collector v0.5.4 Jinhak', 'Admission Collector v0.5.5 Jinhak', 1)
MANIFEST.write_text(mf)

print('v0.5.5 university-context binding patch applied')
