from pathlib import Path

SNAP = Path('app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt')
AGENT = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt')
MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
GRADLE = Path('app/build.gradle.kts')
MANIFEST = Path('app/src/main/AndroidManifest.xml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


snap = SNAP.read_text()
snap = replace_once(
    snap,
    '  var jinhakCards=[];\n',
    '  var jinhakCards=[];\n  var jinhakCardBindings=[];\n',
    'jinhakCardBindings declaration',
)

old_cards = '''      jinhakCards.push({
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
new_cards = '''      // v0.8.7: retain the exact DOM root that produced the already-structured
      // university/department pair. This object is runtime-only and is never exported as raw DOM.
      jinhakCardBindings.push({
        root:entry.el,
        text:entry.text,
        university:universityCtx.name||'',
        department:departmentCtx.name||''
      });
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
snap = replace_once(snap, old_cards, new_cards, 'structured card binding')

helper_anchor = '  function applicationContextForAction(el){\n'
helper = '''  // v0.8.7: bind an action only to a detected card root that actually contains it.
  // No previous/next sibling lookup and no page-wide nearest-card inference are permitted.
  function applicationBindingForAction(el){
    var result={contextText:'',university:'',department:'',source:'none'};
    if(!isJinhakHost||!el) return result;
    var matches=[];
    for(var bi=0;bi<jinhakCardBindings.length;bi++){
      var binding=jinhakCardBindings[bi];
      if(binding&&binding.root&&binding.root.contains&&binding.root.contains(el)) matches.push(binding);
    }
    if(matches.length){
      // Nested roots may contain the same action. Prefer the smallest structured root.
      matches.sort(function(a,b){return String(a.text||'').length-String(b.text||'').length;});
      var chosen=matches[0];
      result.contextText=String(chosen.text||'').slice(0,3000);
      result.university=String(chosen.university||'').slice(0,80);
      result.department=String(chosen.department||'').slice(0,120);
      result.source='same-card-root';
      return result;
    }
    result.contextText=applicationContextForAction(el);
    if(result.contextText) result.source='ancestor-text';
    return result;
  }

'''
if 'function applicationBindingForAction(el)' not in snap:
    if helper_anchor not in snap:
        raise SystemExit('applicationContextForAction boundary not found')
    snap = snap.replace(helper_anchor, helper + helper_anchor, 1)

snap = replace_once(
    snap,
    "      var applicationContext=applicationContextForAction(a);\n      var missionLink=!!route && String(a.tagName||'').toUpperCase()==='A' && applicationContext.length>0;",
    "      var applicationBinding=applicationBindingForAction(a);\n      var applicationContext=applicationBinding.contextText||'';\n      var missionLink=!!route && String(a.tagName||'').toUpperCase()==='A' && applicationContext.length>0;",
    'action binding selection',
)

snap = replace_once(
    snap,
    "missionAnchorDiscovery.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:'mission-link-navigation',contextText:applicationContext});",
    "missionAnchorDiscovery.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:'mission-link-navigation',contextText:applicationContext,applicationUniversity:applicationBinding.university,applicationDepartment:applicationBinding.department,applicationBindingSource:applicationBinding.source});",
    'missionAnchorDiscovery structured fields',
)

snap = replace_once(
    snap,
    "var entry={scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:missionLink?'mission-link-navigation':(role==='tab'?'tab-navigation':'read-navigation'),contextText:applicationContext};",
    "var entry={scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:missionLink?'mission-link-navigation':(role==='tab'?'tab-navigation':'read-navigation'),contextText:applicationContext,applicationUniversity:applicationBinding.university,applicationDepartment:applicationBinding.department,applicationBindingSource:applicationBinding.source};",
    'mission action structured fields',
)
SNAP.write_text(snap)

agent = AGENT.read_text()
old_parse = '                val app = JinhakApplicationMission.parseCard(contextText)\n'
new_parse = '''                val explicitUniversity = obj.optString("applicationUniversity")
                    .replace(Regex("\\\\s+"), " ").trim().take(80).takeIf { it.isNotBlank() }
                val explicitDepartment = obj.optString("applicationDepartment")
                    .replace(Regex("\\\\s+"), " ").trim().take(120).takeIf { it.isNotBlank() }
                val app = JinhakApplicationMission.parseCard(
                    contextText,
                    explicitUniversity = explicitUniversity,
                    explicitDepartment = explicitDepartment
                )
'''
agent = replace_once(agent, old_parse, new_parse, 'navigator explicit structural parse')
AGENT.write_text(agent)

main = MAIN.read_text()
main = replace_once(main, 'private const val VERSION = "0.8.6"', 'private const val VERSION = "0.8.7"', 'MainActivity version')
main = replace_once(main, 'private const val BUILD_CODE = 10860', 'private const val BUILD_CODE = 10870', 'MainActivity build code')
MAIN.write_text(main)

gradle = GRADLE.read_text()
gradle = replace_once(gradle, 'versionCode = 10860', 'versionCode = 10870', 'Gradle versionCode')
gradle = replace_once(gradle, 'versionName = "0.8.6"', 'versionName = "0.8.7"', 'Gradle versionName')
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'Admission Collector v0.8.6 Persistent Mission Ledger',
    'Admission Collector v0.8.7 Structural Anchor Binding',
    'manifest application label',
)
MANIFEST.write_text(manifest)

print('v0.8.7 structural mission anchor binding patch applied')
