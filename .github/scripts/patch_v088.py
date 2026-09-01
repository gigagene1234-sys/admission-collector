from pathlib import Path

SNAP = Path('app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt')
MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
GRADLE = Path('app/build.gradle.kts')
MANIFEST = Path('app/src/main/AndroidManifest.xml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


# SnapshotScript: preserve v0.8.7 direct containment, then permit a structurally
# unique shared container containing exactly one detected application card root.
snap = SNAP.read_text()
start = snap.find('  function applicationBindingForAction(el){')
end_marker = '\n\n  function applicationContextForAction(el){'
end = snap.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('applicationBindingForAction block not found')
new_binding = r'''  function applicationBindingForAction(el){
    var result={contextText:'',university:'',department:'',source:'none'};
    if(!isJinhakHost||!el) return result;

    function useBinding(binding,source){
      result.contextText=String(binding.text||'').slice(0,3000);
      result.university=String(binding.university||'').slice(0,80);
      result.department=String(binding.department||'').slice(0,120);
      result.source=source;
      return result;
    }

    // Gate A1: strongest ownership proof — the action itself is inside one detected card root.
    var direct=[];
    for(var bi=0;bi<jinhakCardBindings.length;bi++){
      var binding=jinhakCardBindings[bi];
      if(binding&&binding.root&&binding.root.contains&&binding.root.contains(el)) direct.push(binding);
    }
    if(direct.length){
      direct.sort(function(a,b){return String(a.text||'').length-String(b.text||'').length;});
      return useBinding(direct[0],'same-card-root');
    }

    // Gate A2: some Jinhak layouts render the report toolbar as a sibling of the metric/card
    // body. Walk ancestors only. The first bounded ancestor may own the action only when it
    // contains exactly ONE non-overlapping detected card root. If two cards enter the same
    // container, binding is rejected rather than guessed. No previous/next sibling or nearest
    // card inference is used.
    var cur=el.parentElement;
    for(var depth=0;cur&&depth<8;depth++,cur=cur.parentElement){
      var tag=String(cur.tagName||'').toUpperCase();
      if(tag==='BODY'||tag==='HTML') break;
      var contained=[];
      for(var ci=0;ci<jinhakCardBindings.length;ci++){
        var cb=jinhakCardBindings[ci];
        if(cb&&cb.root&&cur.contains&&cur.contains(cb.root)) contained.push(cb);
      }
      if(contained.length>1) break;
      if(contained.length===1){
        var only=contained[0];
        if(only.university&&only.department){
          var containerText=safeCloneText(cur,9000);
          if(containerText && containerText.length<=8500){
            return useBinding(only,'unique-card-container');
          }
        }
        break;
      }
    }

    // Evidence-only fallback. It can help page analysis, but without a structurally bound
    // university+department pair Kotlin will not manufacture an application identity.
    result.contextText=applicationContextForAction(el);
    if(result.contextText) result.source='ancestor-text';
    return result;
  }'''
snap = snap[:start] + new_binding + snap[end:]
snap = snap.replace('// v0.8.7: bind an action only to a detected card root that actually contains it.\n  // No previous/next sibling lookup and no page-wide nearest-card inference are permitted.\n',
                    '// v0.8.8: bind report actions by direct card containment or by a bounded ancestor that contains exactly one detected card root.\n  // No sibling traversal and no nearest-card inference are permitted.\n', 1)
SNAP.write_text(snap)


main = MAIN.read_text()
main = replace_once(
    main,
    '    private var jinhakAgentActionsExecuted = 0\n',
    '    private var jinhakAgentActionsExecuted = 0\n'
    '    private var jinhakMissionActionsExecuted = 0\n'
    '    private var jinhakGenericActionsExecuted = 0\n',
    'mission/generic counters'
)
main = replace_once(
    main,
    '    private val jinhakMissionAnchorParsedKeys = linkedSetOf<String>()\n',
    '    private val jinhakMissionAnchorParsedKeys = linkedSetOf<String>()\n'
    '    private val jinhakMissionAnchorStructuredKeys = linkedSetOf<String>()\n'
    '    private val jinhakMissionBindingSourceKeys = linkedSetOf<String>()\n'
    '    private val jinhakMissionBindingSourceCounts = linkedMapOf<String, Int>()\n',
    'binding diagnostics fields'
)
main = replace_once(
    main,
    '        private const val MAX_JINHAK_AGENT_ACTIONS = 260\n',
    '        private const val MAX_JINHAK_GENERIC_ACTIONS = 180\n'
    '        private const val MAX_JINHAK_MISSION_ACTIONS = 220\n',
    'separate action limits'
)
main = replace_once(
    main,
    '        private const val VERSION = "0.8.7"\n        private const val BUILD_CODE = 10870\n',
    '        private const val VERSION = "0.8.8"\n        private const val BUILD_CODE = 10880\n',
    'main version'
)
main = replace_once(
    main,
    '        jinhakAgentActionsExecuted = 0\n',
    '        jinhakAgentActionsExecuted = 0\n'
    '        jinhakMissionActionsExecuted = 0\n'
    '        jinhakGenericActionsExecuted = 0\n',
    'reset action counters'
)
main = replace_once(
    main,
    '        jinhakMissionAnchorParsedKeys.clear()\n',
    '        jinhakMissionAnchorParsedKeys.clear()\n'
    '        jinhakMissionAnchorStructuredKeys.clear()\n'
    '        jinhakMissionBindingSourceKeys.clear()\n'
    '        jinhakMissionBindingSourceCounts.clear()\n',
    'reset binding diagnostics'
)

old_promoted = '''                val promotedAnchors = snapshot.optJSONArray("missionAgentActions") ?: JSONArray()
                for (ai in 0 until promotedAnchors.length()) {
                    val a = promotedAnchors.optJSONObject(ai) ?: continue
                    val key = RecordUtils.sha256(listOf(a.optString("label"), a.optString("contextText")).joinToString("|"))
                    jinhakMissionAnchorPromotedKeys.add(key)
                }
'''
new_promoted = '''                val promotedAnchors = snapshot.optJSONArray("missionAgentActions") ?: JSONArray()
                for (ai in 0 until promotedAnchors.length()) {
                    val a = promotedAnchors.optJSONObject(ai) ?: continue
                    val key = RecordUtils.sha256(listOf(a.optString("label"), a.optString("contextText")).joinToString("|"))
                    jinhakMissionAnchorPromotedKeys.add(key)
                    val bindingSource = a.optString("applicationBindingSource", "unknown").ifBlank { "unknown" }.take(40)
                    val sourceKey = RecordUtils.sha256("$key|$bindingSource")
                    if (jinhakMissionBindingSourceKeys.add(sourceKey)) {
                        jinhakMissionBindingSourceCounts[bindingSource] = (jinhakMissionBindingSourceCounts[bindingSource] ?: 0) + 1
                    }
                    val structuredUniversity = a.optString("applicationUniversity").trim()
                    val structuredDepartment = a.optString("applicationDepartment").trim()
                    if (structuredUniversity.isNotBlank() && structuredDepartment.isNotBlank()) {
                        jinhakMissionAnchorStructuredKeys.add(key)
                    }
                }
'''
main = replace_once(main, old_promoted, new_promoted, 'promoted anchor diagnostics')

old_global_limit = '''        if (jinhakAgentActionsExecuted >= MAX_JINHAK_AGENT_ACTIONS) {
            if (jinhakMissionTargetLedger.hasActionablePending()) {
                jinhakMissionTargetLedger.failAllPending("agent-action-limit")
                recordRuntimeEvent("jinhak-mission-target-limit", JSONObject()
                    .put("limit", MAX_JINHAK_AGENT_ACTIONS)
                    .put("ledger", jinhakMissionTargetLedger.summary()))
            }
            return false
        }

'''
main = replace_once(main, old_global_limit, '', 'remove shared action limit')

old_budget_anchor = '''        val candidate = selection.candidate ?: return false
        val ledgerTargetIdForAction = ledgerTarget?.targetId
        jinhakActiveMissionTargetId = ledgerTargetIdForAction
        if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markAttempted(ledgerTargetIdForAction)
'''
new_budget_anchor = '''        val candidate = selection.candidate ?: return false
        val ledgerTargetIdForAction = ledgerTarget?.targetId
        val missionBudgetedAction = ledgerTargetIdForAction != null || candidate.applicationContext?.identityKey != null
        if (missionBudgetedAction) {
            if (jinhakMissionActionsExecuted >= MAX_JINHAK_MISSION_ACTIONS) {
                jinhakMissionTargetLedger.failAllPending("mission-action-limit")
                recordRuntimeEvent("jinhak-mission-target-limit", JSONObject()
                    .put("missionLimit", MAX_JINHAK_MISSION_ACTIONS)
                    .put("missionExecuted", jinhakMissionActionsExecuted)
                    .put("genericExecuted", jinhakGenericActionsExecuted)
                    .put("ledger", jinhakMissionTargetLedger.summary()))
                return false
            }
        } else if (jinhakGenericActionsExecuted >= MAX_JINHAK_GENERIC_ACTIONS) {
            return false
        }
        jinhakActiveMissionTargetId = ledgerTargetIdForAction
        if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markAttempted(ledgerTargetIdForAction)
'''
main = replace_once(main, old_budget_anchor, new_budget_anchor, 'reserved mission budget')

main = replace_once(
    main,
    '        jinhakAgentActionsExecuted += 1\n',
    '        jinhakAgentActionsExecuted += 1\n'
    '        if (missionBudgetedAction) jinhakMissionActionsExecuted += 1 else jinhakGenericActionsExecuted += 1\n',
    'action budget increment'
)
main = replace_once(
    main,
    '        status.text = "진학사 지원안 미션 ${jinhakAgentActionsExecuted}/$MAX_JINHAK_AGENT_ACTIONS · ${candidate.label.take(48)} · ledger ${jinhakMissionTargetLedger.pendingCount()}대기"\n',
    '        status.text = "진학사 미션 ${jinhakMissionActionsExecuted}/$MAX_JINHAK_MISSION_ACTIONS · 일반 ${jinhakGenericActionsExecuted}/$MAX_JINHAK_GENERIC_ACTIONS · ${candidate.label.take(48)} · ledger ${jinhakMissionTargetLedger.pendingCount()}대기"\n',
    'status action budgets'
)

# Front summary diagnostics.
main = replace_once(
    main,
    '                        .put("agentActionsExecuted", jinhakAgentActionsExecuted)\n',
    '                        .put("agentActionsExecuted", jinhakAgentActionsExecuted)\n'
    '                        .put("missionActionsExecuted", jinhakMissionActionsExecuted)\n'
    '                        .put("genericActionsExecuted", jinhakGenericActionsExecuted)\n'
    '                        .put("missionActionLimit", MAX_JINHAK_MISSION_ACTIONS)\n'
    '                        .put("genericActionLimit", MAX_JINHAK_GENERIC_ACTIONS)\n',
    'front summary action diagnostics'
)
main = replace_once(
    main,
    '                        .put("applicationAnchorActionsPromoted", jinhakMissionAnchorPromotedKeys.size)\n                        .put("applicationAnchorActionsParsed", jinhakMissionAnchorParsedKeys.size)\n',
    '                        .put("applicationAnchorActionsPromoted", jinhakMissionAnchorPromotedKeys.size)\n'
    '                        .put("applicationAnchorStructuredBindings", jinhakMissionAnchorStructuredKeys.size)\n'
    '                        .put("applicationAnchorBindingSources", JSONObject(jinhakMissionBindingSourceCounts as Map<*, *>))\n'
    '                        .put("applicationAnchorActionsParsed", jinhakMissionAnchorParsedKeys.size)\n',
    'front summary binding diagnostics'
)

# Batch summary keeps backward-compatible total plus the separated budgets.
main = replace_once(
    main,
    '                .put("jinhakAgentActionsExecuted", jinhakAgentActionsExecuted)\n',
    '                .put("jinhakAgentActionsExecuted", jinhakAgentActionsExecuted)\n'
    '                .put("jinhakMissionActionsExecuted", jinhakMissionActionsExecuted)\n'
    '                .put("jinhakGenericActionsExecuted", jinhakGenericActionsExecuted)\n',
    'batch summary action diagnostics'
)

MAIN.write_text(main)


gradle = GRADLE.read_text()
gradle = replace_once(gradle, '        versionCode = 10870\n        versionName = "0.8.7"\n',
                      '        versionCode = 10880\n        versionName = "0.8.8"\n', 'gradle version')
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = replace_once(manifest,
                        'android:label="Admission Collector v0.8.7 Structural Anchor Binding"',
                        'android:label="Admission Collector v0.8.8 Unique Container Mission Binding"',
                        'manifest label')
MANIFEST.write_text(manifest)

print('v0.8.8 patch applied')
