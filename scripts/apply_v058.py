from pathlib import Path

ROOT = Path('.')
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# v0.5.8 is deliberately a boundary probe, not a speculative department-binding patch.
# Keep all v0.5.7 parser/binding behavior and enrich only the privacy-safe structural probe.
s = SNAP.read_text()
start_marker = '    function departmentProbeFor(el,rootText){'
end_marker = '    function universityContextFor(el,rootText){'
start = s.find(start_marker)
end = s.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('v0.5.7 department probe anchors missing')

probe_fn = r'''    function departmentProbeFor(el,rootText){
      var out=[];
      var seen={};
      function add(text,relation,depth,distance,node){
        text=String(text||'');
        var names=explicitDepartmentNames(text);
        if(names.length===0) return;
        var unis=explicitUniversityNames(text);
        var nodeMeta=cleanText((node&&node.tagName||'')+' '+(node&&node.id||'')+' '+(node&&node.className||''));
        var hasPrimary=primaryRx.test(text);
        var hasMetric=metricRx.test(text);
        var headerLike=/title|tit|name|dept|major|header|head/i.test(nodeMeta) && !hasPrimary;
        var candidateUniversity=unis.length===1?unis[0]:'';
        var compactLength=cleanText(text).length;
        for(var qi=0;qi<names.length&&out.length<18;qi++){
          var n=names[qi];
          var key=n+'|'+relation+'|'+depth+'|'+distance+'|'+candidateUniversity+'|'+hasPrimary;
          if(seen[key]) continue;
          seen[key]=true;
          out.push({
            name:n,
            relation:relation,
            depth:depth,
            distance:distance,
            tag:String(node&&node.tagName||'').slice(0,20),
            hasPrimaryPrediction:hasPrimary,
            hasMetric:hasMetric,
            headerLike:headerLike,
            textLength:compactLength,
            candidateUniversity:candidateUniversity,
            candidateDepartmentCount:names.length
          });
        }
      }
      add(rootText,'card-root',0,0,el);
      var cur=el;
      for(var depth=0;cur&&depth<7&&out.length<18;depth++){
        var attrs=cleanText((cur.getAttribute&&cur.getAttribute('aria-label')||'')+' '+(cur.getAttribute&&cur.getAttribute('title')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-dept-name')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-department-name')||''));
        add(attrs,'ancestor-attribute',depth,0,cur);

        var prev=cur.previousElementSibling;
        for(var pi=1;prev&&pi<=8&&out.length<18;pi++,prev=prev.previousElementSibling){
          if(!visible(prev)) continue;
          add(structuredCardText(prev,1000),'previous-sibling',depth,pi,prev);
        }
        var next=cur.nextElementSibling;
        for(var ni=1;next&&ni<=5&&out.length<18;ni++,next=next.nextElementSibling){
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
          for(var xi=from;xi<=to&&out.length<18;xi++){
            if(xi===curIndex) continue;
            var child=children[xi];
            if(!visible(child)) continue;
            add(structuredCardText(child,900),'parent-child',depth+1,xi-curIndex,child);
          }
        }
        cur=parent;
      }
      return out.slice(0,18);
    }

'''
s = s[:start] + probe_fn + s[end:]
SNAP.write_text(s)

# Extend only the sanitized diagnostic fields. No DOM/raw text/URL/session data is added.
for p in MAIN_FILES:
    m = p.read_text()
    old = '''            for (pi in 0 until minOf(rawProbe.length(), 14)) {
                val q = rawProbe.optJSONObject(pi) ?: continue
                val name = q.optString("name").replace(Regex("""\\s+"""), " ").trim().take(60)
                if (name.isBlank() || !Regex("""(?:학과|학부|전공|자율전공)$""").containsMatchIn(name)) continue
                safeProbe.put(JSONObject()
                    .put("name", name)
                    .put("relation", q.optString("relation").take(32))
                    .put("depth", q.optInt("depth", -1))
                    .put("distance", q.optInt("distance", 0))
                    .put("tag", q.optString("tag").take(20)))
            }'''
    new = '''            for (pi in 0 until minOf(rawProbe.length(), 18)) {
                val q = rawProbe.optJSONObject(pi) ?: continue
                val name = q.optString("name").replace(Regex("""\\s+"""), " ").trim().take(60)
                if (name.isBlank() || !Regex("""(?:학과|학부|전공|자율전공)$""").containsMatchIn(name)) continue
                val candidateUniversity = q.optString("candidateUniversity")
                    .replace(Regex("""\\s+"""), " ").trim().take(60)
                safeProbe.put(JSONObject()
                    .put("name", name)
                    .put("relation", q.optString("relation").take(32))
                    .put("depth", q.optInt("depth", -1))
                    .put("distance", q.optInt("distance", 0))
                    .put("tag", q.optString("tag").take(20))
                    .put("hasPrimaryPrediction", q.optBoolean("hasPrimaryPrediction", false))
                    .put("hasMetric", q.optBoolean("hasMetric", false))
                    .put("headerLike", q.optBoolean("headerLike", false))
                    .put("textLength", q.optInt("textLength", -1))
                    .put("candidateDepartmentCount", q.optInt("candidateDepartmentCount", 0))
                    .put("candidateUniversity", if (candidateUniversity.isBlank()) JSONObject.NULL else candidateUniversity))
            }'''
    if old not in m:
        raise SystemExit(f'v0.5.7 safe probe anchor missing: {p}')
    m = m.replace(old, new, 1)
    m = m.replace('private const val VERSION = "0.5.7"', 'private const val VERSION = "0.5.8"', 1)
    m = m.replace('private const val BUILD_CODE = 10570', 'private const val BUILD_CODE = 10580', 1)
    m = m.replace(
        'structured-admission-metrics-and-short-department-candidates-only-no-dom-no-raw-evidence-no-url-no-cookie-no-credential',
        'structured-admission-metrics-and-department-boundary-metadata-only-no-dom-no-raw-evidence-no-url-no-cookie-no-credential',
        1,
    )
    p.write_text(m)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')

g = GRADLE.read_text()
if 'versionCode = 10570' not in g or 'versionName = "0.5.7"' not in g:
    raise SystemExit('v0.5.7 Gradle anchors missing')
g = g.replace('versionCode = 10570', 'versionCode = 10580', 1)
g = g.replace('versionName = "0.5.7"', 'versionName = "0.5.8"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text()
if 'Admission Collector v0.5.7 Jinhak Context Probe' not in mf:
    raise SystemExit('v0.5.7 manifest anchor missing')
mf = mf.replace(
    'Admission Collector v0.5.7 Jinhak Context Probe',
    'Admission Collector v0.5.8 Jinhak Department Boundary Probe',
    1,
)
MANIFEST.write_text(mf)

print('v0.5.8 Jinhak department boundary probe patch applied')
