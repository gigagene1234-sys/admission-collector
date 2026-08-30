from pathlib import Path

ROOT = Path('.')
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# ---- Snapshot probe: preserve v0.5.6 binding logic and add privacy-safe structural department candidates. ----
s = SNAP.read_text()
old_stats = 'var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0,departmentBoundRoots:0,departmentContextRoots:0,departmentMissingRoots:0};'
new_stats = 'var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0,departmentBoundRoots:0,departmentContextRoots:0,departmentMissingRoots:0,departmentProbeCards:0,departmentProbeCandidates:0};'
if old_stats not in s:
    raise SystemExit('v0.5.6 stats anchor missing')
s = s.replace(old_stats, new_stats, 1)

anchor = '''    function universityContextFor(el,rootText){'''
probe_fn = r'''    function departmentProbeFor(el,rootText){
      var out=[];
      var seen={};
      function add(text,relation,depth,distance,node){
        var names=explicitDepartmentNames(text);
        for(var qi=0;qi<names.length&&out.length<14;qi++){
          var n=names[qi];
          var key=n+'|'+relation+'|'+depth+'|'+distance;
          if(seen[key]) continue;
          seen[key]=true;
          out.push({
            name:n,
            relation:relation,
            depth:depth,
            distance:distance,
            tag:String(node&&node.tagName||'').slice(0,20)
          });
        }
      }
      add(rootText,'card-root',0,0,el);
      var cur=el;
      for(var depth=0;cur&&depth<7&&out.length<14;depth++){
        var attrs=cleanText((cur.getAttribute&&cur.getAttribute('aria-label')||'')+' '+(cur.getAttribute&&cur.getAttribute('title')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-dept-name')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-department-name')||''));
        add(attrs,'ancestor-attribute',depth,0,cur);

        var prev=cur.previousElementSibling;
        for(var pi=1;prev&&pi<=8&&out.length<14;pi++,prev=prev.previousElementSibling){
          if(!visible(prev)) continue;
          add(structuredCardText(prev,1000),'previous-sibling',depth,pi,prev);
        }
        var next=cur.nextElementSibling;
        for(var ni=1;next&&ni<=5&&out.length<14;ni++,next=next.nextElementSibling){
          if(!visible(next)) continue;
          add(structuredCardText(next,1000),'next-sibling',depth,ni,next);
        }

        var parent=cur.parentElement;
        if(!parent) break;
        var children=parent.children||[];
        var curIndex=-1;
        for(var ci=0;ci<children.length;ci++){ if(children[ci]===cur){curIndex=ci;break;} }
        if(curIndex>=0){
          var from=Math.max(0,curIndex-6), to=Math.min(children.length-1,curIndex+6);
          for(var xi=from;xi<=to&&out.length<14;xi++){
            if(xi===curIndex) continue;
            var child=children[xi];
            if(!visible(child)) continue;
            add(structuredCardText(child,900),'parent-child',depth+1,xi-curIndex,child);
          }
        }
        cur=parent;
      }
      return out.slice(0,14);
    }

    function universityContextFor(el,rootText){'''
if anchor not in s:
    raise SystemExit('universityContextFor anchor missing')
s = s.replace(anchor, probe_fn, 1)

old_ctx = '''      var universityCtx=universityContextFor(entry.el,entry.text);
      var departmentCtx=departmentContextFor(entry.el,entry.text);'''
new_ctx = '''      var universityCtx=universityContextFor(entry.el,entry.text);
      var departmentCtx=departmentContextFor(entry.el,entry.text);
      var departmentProbe=departmentProbeFor(entry.el,entry.text);
      jinhakCardStats.departmentProbeCards++;
      jinhakCardStats.departmentProbeCandidates+=departmentProbe.length;'''
if old_ctx not in s:
    raise SystemExit('card context anchor missing')
s = s.replace(old_ctx, new_ctx, 1)

old_push = '''        department:departmentCtx.name,
        departmentSource:departmentCtx.source,
        departmentDepth:departmentCtx.depth
      });'''
new_push = '''        department:departmentCtx.name,
        departmentSource:departmentCtx.source,
        departmentDepth:departmentCtx.depth,
        departmentProbe:departmentProbe
      });'''
if old_push not in s:
    raise SystemExit('card push anchor missing')
s = s.replace(old_push, new_push, 1)
SNAP.write_text(s)

# ---- Digest: include only short department-name candidates and structural relation; never raw DOM/text. ----
for p in MAIN_FILES:
    m = p.read_text()
    old_decl = '''        val sanitized = JSONArray()
        var universityBound = 0'''
    new_decl = '''        val sanitized = JSONArray()
        val missingDepartmentCardIndexes = linkedSetOf<Int>()
        var universityBound = 0'''
    if old_decl not in m:
        raise SystemExit(f'digest decl anchor missing: {p}')
    m = m.replace(old_decl, new_decl, 1)

    old_counts = '''            if (hasUniversity) universityBound += 1
            if (hasDepartment) departmentBound += 1
            if (hasAdmission) admissionBound += 1
            if (hasUniversity && hasDepartment && hasAdmission) fullyBound += 1'''
    new_counts = '''            if (hasUniversity) universityBound += 1
            if (hasDepartment) departmentBound += 1
            if (!hasDepartment && r.has("cardIndex")) missingDepartmentCardIndexes += r.optInt("cardIndex")
            if (hasAdmission) admissionBound += 1
            if (hasUniversity && hasDepartment && hasAdmission) fullyBound += 1'''
    if old_counts not in m:
        raise SystemExit(f'digest count anchor missing: {p}')
    m = m.replace(old_counts, new_counts, 1)

    old_return = '''        return JSONObject()
            .put("schemaVersion", 1)'''
    new_return = '''        val departmentProbes = JSONArray()
        val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
        for (cardIndex in missingDepartmentCardIndexes) {
            if (cardIndex < 0 || cardIndex >= cards.length()) continue
            val card = cards.optJSONObject(cardIndex) ?: continue
            val rawProbe = card.optJSONArray("departmentProbe") ?: JSONArray()
            val safeProbe = JSONArray()
            for (pi in 0 until minOf(rawProbe.length(), 14)) {
                val q = rawProbe.optJSONObject(pi) ?: continue
                val name = q.optString("name").replace(Regex("""\\s+"""), " ").trim().take(60)
                if (name.isBlank() || !Regex("""(?:학과|학부|전공|자율전공)$""").containsMatchIn(name)) continue
                safeProbe.put(JSONObject()
                    .put("name", name)
                    .put("relation", q.optString("relation").take(32))
                    .put("depth", q.optInt("depth", -1))
                    .put("distance", q.optInt("distance", 0))
                    .put("tag", q.optString("tag").take(20)))
            }
            departmentProbes.put(JSONObject()
                .put("cardIndex", cardIndex)
                .put("rootTag", card.optString("rootTag").take(20))
                .put("rootScore", card.optInt("score", 0))
                .put("university", card.optString("university").take(60))
                .put("candidates", safeProbe))
        }
        return JSONObject()
            .put("schemaVersion", 1)'''
    if old_return not in m:
        raise SystemExit(f'digest return anchor missing: {p}')
    m = m.replace(old_return, new_return, 1)

    old_probe_insert = '''            .put("bindingStats", JSONObject()
                .put("universityBound", universityBound)
                .put("departmentBound", departmentBound)
                .put("admissionBound", admissionBound)
                .put("fullyBound", fullyBound)
                .put("totalRecords", records.length()))
            .put("includedRecords", sanitized.length())'''
    new_probe_insert = '''            .put("bindingStats", JSONObject()
                .put("universityBound", universityBound)
                .put("departmentBound", departmentBound)
                .put("admissionBound", admissionBound)
                .put("fullyBound", fullyBound)
                .put("totalRecords", records.length()))
            .put("departmentStructureProbe", departmentProbes)
            .put("includedRecords", sanitized.length())'''
    if old_probe_insert not in m:
        raise SystemExit(f'digest probe insertion anchor missing: {p}')
    m = m.replace(old_probe_insert, new_probe_insert, 1)

    m = m.replace('private const val VERSION = "0.5.6"', 'private const val VERSION = "0.5.7"', 1)
    m = m.replace('private const val BUILD_CODE = 10560', 'private const val BUILD_CODE = 10570', 1)
    m = m.replace('structured-admission-metrics-only-no-dom-no-raw-evidence-no-url-no-cookie-no-credential', 'structured-admission-metrics-and-short-department-candidates-only-no-dom-no-raw-evidence-no-url-no-cookie-no-credential', 1)
    p.write_text(m)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')

g = GRADLE.read_text()
g = g.replace('versionCode = 10560', 'versionCode = 10570', 1)
g = g.replace('versionName = "0.5.6"', 'versionName = "0.5.7"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text()
mf = mf.replace('Admission Collector v0.5.6 Jinhak Analysis', 'Admission Collector v0.5.7 Jinhak Context Probe', 1)
MANIFEST.write_text(mf)

print('v0.5.7 Jinhak context probe patch applied')
