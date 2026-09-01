from pathlib import Path
import re

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
AGENT = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt'
ADAPTER = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 anchor, found {count}')
    return text.replace(old, new, 1)


def at_least_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count < 1:
        raise SystemExit(f'{label}: anchor missing')
    return text.replace(old, new)

# ---------------------------------------------------------------------------
# SnapshotScript: preserve raw mission anchor discovery separately from the
# generic 160-action pool and promote safe same-card anchors into their own
# missionAgentActions channel.
# ---------------------------------------------------------------------------
s = SNAP.read_text()
s = once(s, '  var agentActions=[];\n', '  var agentActions=[];\n  var missionAgentActions=[];\n  var missionAnchorDiscovery=[];\n', 'snapshot action arrays')
s = once(s, '  var seenAgentAction={};\n', '  var seenAgentAction={};\n  var seenMissionAgentAction={};\n  var seenMissionDiscovery={};\n', 'snapshot action dedupe maps')

pattern = re.compile(r'''    var missionLinkBound=false;\n    if\(isJinhakHost && agentActions\.length<160\)\{.*?\n    \}\n\n    var resourceRaw=''', re.S)
match = pattern.search(s)
if not match:
    raise SystemExit('snapshot mission action block not found')
replacement = r'''    var missionLinkBound=false;
    if(isJinhakHost){
      var agentBlocked=/(원서\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)/i;
      var agentAllowed=/(실제\s*합격자|과거\s*입시결과|입시\s*결과|합격\s*예측\s*리포트|모의\s*지원\s*리포트|지원자\s*분포|대학.?학과별\s*합격\s*예측|합격\s*안정성|상세|보기|조회|검색|리포트|대학\s*정보|전형\s*정보|학과\s*정보|합격\s*예측|모의\s*지원|수시\s*저장소|정시\s*저장소|추천\s*대학|성적\s*분석|성적\s*산출|입시\s*전략|입시\s*지식|경쟁률|모집\s*요강|다음|더보기|결과|탭)/i;
      var role=cleanText(a.getAttribute('role')||'');
      var applicationContext=applicationContextForAction(a);
      var missionLink=!!route && String(a.tagName||'').toUpperCase()==='A' && applicationContext.length>0;

      // Stage 1: discovery is deliberately broader than promotion so the export can
      // explain exactly where an anchor was lost before candidate selection.
      if(missionLink && missionAnchorDiscovery.length<160){
        var dk=li+'|'+label+'|'+applicationContext.slice(0,1200);
        if(!seenMissionDiscovery[dk]){
          missionAnchorDiscovery.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:'mission-link-navigation',contextText:applicationContext});
          seenMissionDiscovery[dk]=1;
        }
      }

      var dynamicControl=!route || role==='tab' || a.tagName==='BUTTON' || missionLink;
      if(dynamicControl && label && !agentBlocked.test(label+' '+meta2) && agentAllowed.test(label)){
        var entry={scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:missionLink?'mission-link-navigation':(role==='tab'?'tab-navigation':'read-navigation'),contextText:applicationContext};
        var ak=li+'|'+label+'|'+String(a.tagName||'')+'|'+role;
        if(missionLink && missionAgentActions.length<120 && !seenMissionAgentAction[ak]){
          missionAgentActions.push(entry);
          seenMissionAgentAction[ak]=1;
          missionLinkBound=true;
        }
        // Generic actions remain bounded, but can no longer evict mission anchors.
        if(agentActions.length<160 && !seenAgentAction[ak]){
          agentActions.push(entry);
          seenAgentAction[ak]=1;
        }
      }
    }

    var resourceRaw='''
s = s[:match.start()] + replacement + s[match.end():]
s = once(
    s,
    '    discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length,agentActions:agentActions.length,jinhakDeepPage:jinhakDeepPage},\n',
    '    discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length,agentActions:agentActions.length,missionAgentActions:missionAgentActions.length,missionAnchorDiscovery:missionAnchorDiscovery.length,jinhakDeepPage:jinhakDeepPage},\n',
    'snapshot discovery diagnostics'
)
s = once(
    s,
    '    agentActions:agentActions,\n    resourceLinks:resources\n',
    '    agentActions:agentActions,\n    missionAgentActions:missionAgentActions,\n    missionAnchorDiscovery:missionAnchorDiscovery,\n    resourceLinks:resources\n',
    'snapshot mission arrays export'
)
SNAP.write_text(s)

# ---------------------------------------------------------------------------
# Agent navigator: missionAgentActions are parsed first, deduped against the
# generic pool, and explicitly marked as promoted mission candidates.
# ---------------------------------------------------------------------------
a = AGENT.read_text()
a = once(
    a,
    '        val applicationContext: JinhakApplicationMission.Context?\n    )\n',
    '        val applicationContext: JinhakApplicationMission.Context?,\n        val promotedMissionAction: Boolean = false\n    )\n',
    'agent candidate promoted flag'
)
start = a.index('    fun candidates(snapshot: JSONObject): List<Candidate> {')
end = a.index('    fun key(safeRoute: String, candidate: Candidate): String', start)
new_candidates = r'''    fun candidates(snapshot: JSONObject): List<Candidate> {
        val route = snapshot.optString("url")
        val out = mutableListOf<Candidate>()
        val seen = linkedSetOf<String>()

        fun append(arrayName: String, promoted: Boolean, limit: Int) {
            val array = snapshot.optJSONArray(arrayName) ?: JSONArray()
            for (i in 0 until minOf(array.length(), limit)) {
                val obj = array.optJSONObject(i) ?: continue
                val scanIndex = obj.optInt("scanIndex", -1)
                val label = obj.optString("label").replace(Regex("\\s+"), " ").trim().take(120)
                val tag = obj.optString("tag").take(24)
                val kind = obj.optString("kind", "read-navigation").take(40)
                val contextText = obj.optString("contextText")
                    .replace(Regex("\\s+"), " ").trim().take(2400)
                if (scanIndex < 0 || label.isBlank()) continue
                if (!isSafeReadNavigationLabel(label)) continue
                val app = JinhakApplicationMission.parseCard(contextText)
                val dedupeKey = listOf(scanIndex.toString(), label, kind, app?.identityKey ?: contextText.take(1000)).joinToString("|")
                if (!seen.add(dedupeKey)) continue
                var priority = JinhakSiteTopology.priority(route, label)
                if (app?.identityKey != null) priority += 14
                if (app != null && Regex("(리포트|실제\\s*합격자|모의\\s*지원|합격\\s*예측)").containsMatchIn(label)) priority += 8
                if (kind == "mission-link-navigation" && app?.identityKey != null) priority += 35
                if (promoted && app?.identityKey != null) priority += 45
                out += Candidate(scanIndex, label, tag, kind, priority.coerceIn(0, 220), contextText, app, promoted)
            }
        }

        // Dedicated mission anchors cannot be displaced by the generic action cap.
        append("missionAgentActions", promoted = true, limit = 120)
        append("agentActions", promoted = false, limit = 160)

        return out.sortedWith(
            compareByDescending<Candidate> { it.promotedMissionAction && it.applicationContext?.identityKey != null }
                .thenByDescending { it.kind == "mission-link-navigation" && it.applicationContext?.identityKey != null }
                .thenByDescending { it.applicationContext?.identityKey != null }
                .thenByDescending { it.missionPriority }
                .thenBy { it.scanIndex }
        )
    }

'''
a = a[:start] + new_candidates + a[end:]
a = once(
    a,
    '            candidate.missionPriority.toString(),\n            candidate.applicationContext?.identityKey ?: RecordUtils.sha256(candidate.contextText.take(1200))\n',
    '            candidate.missionPriority.toString(),\n            candidate.promotedMissionAction.toString(),\n            candidate.applicationContext?.identityKey ?: RecordUtils.sha256(candidate.contextText.take(1200))\n',
    'agent key promoted flag'
)
a = once(
    a,
    '    fun executionScript(candidate: Candidate): String {\n',
    '    fun laneForCandidate(candidate: Candidate): String = JinhakMissionLaneSequencer.laneForLabel(candidate.label, candidate.kind)\n\n    fun executionScript(candidate: Candidate): String {\n',
    'agent lane helper'
)
AGENT.write_text(a)

# ---------------------------------------------------------------------------
# MainActivity: seven-stage anchor telemetry, mission-first sequencer, bridge
# confirmation, slow-lane failure classification, and Cloud outstanding count.
# ---------------------------------------------------------------------------
m = MAIN.read_text()
m = once(m, 'import com.admissionhub.collector.jinhak.JinhakReportContextBridge\n', 'import com.admissionhub.collector.jinhak.JinhakReportContextBridge\nimport com.admissionhub.collector.jinhak.JinhakMissionLaneSequencer\n', 'sequencer import')
m = once(
    m,
    '    private val jinhakMissionAnchorDiscoveredKeys = linkedSetOf<String>()\n    private var jinhakMissionAnchorActionsExecuted = 0\n',
    '    private val jinhakMissionAnchorDiscoveredKeys = linkedSetOf<String>()\n    private val jinhakMissionAnchorPromotedKeys = linkedSetOf<String>()\n    private val jinhakMissionAnchorParsedKeys = linkedSetOf<String>()\n    private val jinhakMissionAnchorSelectedKeys = linkedSetOf<String>()\n    private val jinhakMissionAnchorClickedKeys = linkedSetOf<String>()\n    private val jinhakReportConfirmedKeys = linkedSetOf<String>()\n    private var jinhakMissionAnchorActionsExecuted = 0\n',
    'anchor stage declarations'
)
m = once(
    m,
    '    private var jinhakReportBridgeApplied = 0\n    private var jinhakMissionAnchorActionsAttempted = 0\n    private val jinhakAnchorRejectReasons = linkedMapOf<String, Int>()\n',
    '    private var jinhakReportBridgeApplied = 0\n    private var jinhakReportBridgeConfirmed = 0\n    private var jinhakMissionAnchorActionsAttempted = 0\n    private val jinhakAnchorRejectReasons = linkedMapOf<String, Int>()\n    private val jinhakSlowLaneFailureReasons = linkedMapOf<String, Int>()\n',
    'bridge confirmed declarations'
)
m = m.replace('private const val VERSION = "0.8.4"', 'private const val VERSION = "0.8.5"')
m = m.replace('private const val BUILD_CODE = 10840', 'private const val BUILD_CODE = 10850')

m = once(
    m,
    '        jinhakMissionAnchorDiscoveredKeys.clear()\n        jinhakMissionAnchorActionsExecuted = 0\n',
    '        jinhakMissionAnchorDiscoveredKeys.clear()\n        jinhakMissionAnchorPromotedKeys.clear()\n        jinhakMissionAnchorParsedKeys.clear()\n        jinhakMissionAnchorSelectedKeys.clear()\n        jinhakMissionAnchorClickedKeys.clear()\n        jinhakReportConfirmedKeys.clear()\n        jinhakMissionAnchorActionsExecuted = 0\n',
    'anchor stage reset'
)
m = once(
    m,
    '        jinhakReportBridgeApplied = 0\n        jinhakMissionAnchorActionsAttempted = 0\n        jinhakAnchorRejectReasons.clear()\n',
    '        jinhakReportBridgeApplied = 0\n        jinhakReportBridgeConfirmed = 0\n        jinhakMissionAnchorActionsAttempted = 0\n        jinhakAnchorRejectReasons.clear()\n        jinhakSlowLaneFailureReasons.clear()\n',
    'bridge telemetry reset'
)

old_discovery = '''                val actions = snapshot.optJSONArray("agentActions") ?: JSONArray()
                for (ai in 0 until actions.length()) {
                    val a = actions.optJSONObject(ai) ?: continue
                    if (a.optString("kind") != "mission-link-navigation") continue
                    val key = RecordUtils.sha256(listOf(a.optString("label"), a.optString("contextText")).joinToString("|"))
                    jinhakMissionAnchorDiscoveredKeys.add(key)
                }
                val mission = jinhakMissionContext
                val missionKey = mission?.identityKey
'''
new_discovery = '''                val discoveredAnchors = snapshot.optJSONArray("missionAnchorDiscovery") ?: JSONArray()
                for (ai in 0 until discoveredAnchors.length()) {
                    val a = discoveredAnchors.optJSONObject(ai) ?: continue
                    val key = RecordUtils.sha256(listOf(a.optString("label"), a.optString("contextText")).joinToString("|"))
                    jinhakMissionAnchorDiscoveredKeys.add(key)
                }
                val promotedAnchors = snapshot.optJSONArray("missionAgentActions") ?: JSONArray()
                for (ai in 0 until promotedAnchors.length()) {
                    val a = promotedAnchors.optJSONObject(ai) ?: continue
                    val key = RecordUtils.sha256(listOf(a.optString("label"), a.optString("contextText")).joinToString("|"))
                    jinhakMissionAnchorPromotedKeys.add(key)
                }
                JinhakAgentNavigator.candidates(snapshot).filter { it.promotedMissionAction && it.applicationContext?.identityKey != null }.forEach { candidate ->
                    val key = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
                    jinhakMissionAnchorParsedKeys.add(key)
                }
                val mission = JinhakApplicationMission.fromJson(snapshot.optJSONObject("missionApplicationContext")) ?: jinhakMissionContext
                val missionKey = mission?.identityKey
'''
m = once(m, old_discovery, new_discovery, 'anchor discovery pipeline')

old_bridge = '''                    if (JinhakReportContextBridge.isReportPageType(pageTypeForBridge) && missionJson.has("reportBridgeActionToken")) {
                        jinhakReportBridgeApplied += 1
                    }
'''
new_bridge = '''                    if (JinhakReportContextBridge.isReportPageType(pageTypeForBridge) && missionJson.has("reportBridgeActionToken")) {
                        jinhakReportBridgeApplied += 1
                        val bridgeMission = JinhakApplicationMission.fromJson(missionJson)
                        val lane = JinhakApplicationMission.laneForPageType(pageTypeForBridge)
                        val confirmationKey = RecordUtils.sha256(listOf(
                            bridgeMission?.identityKey ?: "",
                            lane,
                            missionJson.optString("reportBridgeActionToken"),
                            runtimeSafePath(snapshot.optString("url"))
                        ).joinToString("|"))
                        if (bridgeMission?.identityKey != null && lane != "reference" && jinhakReportConfirmedKeys.add(confirmationKey)) {
                            jinhakReportBridgeConfirmed += 1
                        }
                    }
'''
m = once(m, old_bridge, new_bridge, 'bridge confirmation')

old_selection = '''        val candidates = JinhakAgentNavigator.candidates(snapshot)
        val currentMissionKey = jinhakMissionContext?.identityKey
        val candidate = candidates.firstOrNull { action ->
            if (jinhakAgentActionSeen.contains(actionKeyFor(action))) return@firstOrNull false
            val actionMissionKey = action.applicationContext?.identityKey
            // While inside a mission report, do not jump directly to a DIFFERENT application card.
            currentMissionKey == null || actionMissionKey == null || actionMissionKey == currentMissionKey
        } ?: return false
        val actionKey = actionKeyFor(candidate)
'''
new_selection = '''        val candidates = JinhakAgentNavigator.candidates(snapshot).filterNot { jinhakAgentActionSeen.contains(actionKeyFor(it)) }
        val currentMissionKey = jinhakMissionContext?.identityKey
        val covered = currentMissionKey?.let { jinhakMissionCoverage[it]?.toSet() }.orEmpty()
        val atMissionOrigin = currentMissionKey != null && jinhakMissionOriginRoute.isNotBlank() &&
            canonicalizeBatchUrl(route) == canonicalizeBatchUrl(jinhakMissionOriginRoute)
        val selection = JinhakMissionLaneSequencer.choose(candidates, currentMissionKey, covered, atMissionOrigin)
        if (selection.missionExhaustedAtOrigin && currentMissionKey != null) {
            recordRuntimeEvent("jinhak-application-mission-lanes-exhausted", JSONObject()
                .put("applicationIdentityHash", currentMissionKey.take(24))
                .put("coverageLanes", covered.size)
                .put("safePath", runtimeSafePath(route)))
            jinhakMissionContext = null
            jinhakReportBridgeContext = null
            jinhakMissionOriginRoute = ""
            jinhakMissionNeedsReturn = false
        }
        val candidate = selection.candidate ?: return false
        if (candidate.kind == "mission-link-navigation") {
            val selectedKey = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
            jinhakMissionAnchorSelectedKeys.add(selectedKey)
        }
        val actionKey = actionKeyFor(candidate)
'''
m = once(m, old_selection, new_selection, 'mission sequencer selection')

m = once(
    m,
    '                if (candidate.kind == "mission-link-navigation") jinhakMissionAnchorActionsExecuted += 1\n',
    '                if (candidate.kind == "mission-link-navigation") {\n                    jinhakMissionAnchorActionsExecuted += 1\n                    val clickedKey = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))\n                    jinhakMissionAnchorClickedKeys.add(clickedKey)\n                }\n',
    'anchor clicked telemetry'
)

old_return_clear = '''        // Clear before navigation so the next storage snapshot cannot inherit the previous application.
        jinhakMissionContext = null
        jinhakReportBridgeContext = null
        jinhakMissionOriginRoute = ""
        jinhakMissionNeedsReturn = false
        currentBatchTarget = origin
'''
new_return_clear = '''        // v0.8.5 keeps the same application mission active while returning to the
        // saved-application origin. The sequencer then selects the next missing lane;
        // only an exhausted origin clears the mission before selecting another card.
        jinhakReportBridgeContext = null
        jinhakMissionNeedsReturn = false
        currentBatchTarget = origin
'''
m = once(m, old_return_clear, new_return_clear, 'mission return persistence')

m = once(
    m,
    '        jinhakSlowLaneFailed += 1\n        batchErrors.put(JSONObject()\n',
    '        jinhakSlowLaneFailed += 1\n        val failureClass = reason.substringBefore(\':\').take(80)\n        jinhakSlowLaneFailureReasons[failureClass] = (jinhakSlowLaneFailureReasons[failureClass] ?: 0) + 1\n        batchErrors.put(JSONObject()\n',
    'slow lane failure classification'
)

# Add diagnostics everywhere the standard block is emitted.
old_diag = '''                        .put("applicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
                        .put("applicationAnchorActionsAttempted", jinhakMissionAnchorActionsAttempted)
                        .put("applicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
                        .put("applicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))
                        .put("reportBridgeArmed", jinhakReportBridgeArmed)
                        .put("reportBridgeApplied", jinhakReportBridgeApplied)
'''
new_diag = '''                        .put("applicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
                        .put("applicationAnchorActionsPromoted", jinhakMissionAnchorPromotedKeys.size)
                        .put("applicationAnchorActionsParsed", jinhakMissionAnchorParsedKeys.size)
                        .put("applicationAnchorActionsSelected", jinhakMissionAnchorSelectedKeys.size)
                        .put("applicationAnchorActionsAttempted", jinhakMissionAnchorActionsAttempted)
                        .put("applicationAnchorActionsClicked", jinhakMissionAnchorClickedKeys.size)
                        .put("applicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
                        .put("applicationAnchorReportConfirmed", jinhakReportConfirmedKeys.size)
                        .put("applicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))
                        .put("reportBridgeArmed", jinhakReportBridgeArmed)
                        .put("reportBridgeApplied", jinhakReportBridgeApplied)
                        .put("reportBridgeConfirmed", jinhakReportBridgeConfirmed)
'''
m = at_least_once(m, old_diag, new_diag, 'anchor diagnostics output')

old_slow_diag = '''                        .put("slowLaneFailed", jinhakSlowLaneFailed)
                        .put("slowLaneUserActionRequired", jinhakSlowLaneUserActionRequired)
'''
new_slow_diag = '''                        .put("slowLaneFailed", jinhakSlowLaneFailed)
                        .put("slowLaneFailureReasons", JSONObject(jinhakSlowLaneFailureReasons as Map<*, *>))
                        .put("slowLaneUserActionRequired", jinhakSlowLaneUserActionRequired)
'''
m = at_least_once(m, old_slow_diag, new_slow_diag, 'slow diagnostics output')

old_cloud_diag = '''                        .put("cloudFrontierClaimed", cloudFrontierClaimed)
                        .put("cloudFrontierCompleted", cloudFrontierCompleted)
                        .put("cloudFrontierCompletionFailed", cloudFrontierCompletionFailed)
'''
new_cloud_diag = '''                        .put("cloudFrontierClaimed", cloudFrontierClaimed)
                        .put("cloudFrontierCompleted", cloudFrontierCompleted)
                        .put("cloudFrontierCompletionFailed", cloudFrontierCompletionFailed)
                        .put("cloudFrontierOutstanding", (cloudFrontierClaimed - cloudFrontierCompleted).coerceAtLeast(0))
'''
m = at_least_once(m, old_cloud_diag, new_cloud_diag, 'cloud outstanding diagnostics')
MAIN.write_text(m)

# ---------------------------------------------------------------------------
# JinhakAdapter: never store an average grade as an applicant count.
# ---------------------------------------------------------------------------
j = ADAPTER.read_text()
old_metric = '''                        h.contains("모의지원자") && h.contains("평균점") -> metrics.put("mockApplicantAverageScore", n)
                        h.contains("적정지원컷") || h.contains("합격예측") && h.contains("컷") -> metrics.put("predictedSupportCut", n)
                        h.contains("모집인원") -> metrics.put("capacity", n)
                        h.contains("지원자") -> metrics.put("applicants", n)
                        h.contains("충원율") -> metrics.put("fillRate", n)
'''
new_metric = '''                        h.contains("모의지원자") && h.contains("평균점") -> metrics.put("mockApplicantAverageScore", n)
                        h.contains("지원자") && h.contains("평균") && h.contains("등급") -> metrics.put("applicantAverageGrade", n)
                        h.contains("적정지원컷") || h.contains("합격예측") && h.contains("컷") -> metrics.put("predictedSupportCut", n)
                        h.contains("모집인원") -> metrics.put("capacity", n)
                        Regex("(모의지원자수|모의지원자 수|모의지원인원|모의지원 인원)").containsMatchIn(h) -> metrics.put("mockApplicants", n)
                        Regex("(지원자수|지원자 수|지원인원|지원 인원|실지원자수|실지원자 수)").containsMatchIn(h) -> metrics.put("applicants", n)
                        h.contains("충원율") -> metrics.put("fillRate", n)
'''
j = once(j, old_metric, new_metric, 'table applicant semantic guard')
ADAPTER.write_text(j)

# ---------------------------------------------------------------------------
# Version metadata.
# ---------------------------------------------------------------------------
g = GRADLE.read_text().replace('versionCode = 10840', 'versionCode = 10850').replace('versionName = "0.8.4"', 'versionName = "0.8.5"')
if 'versionCode = 10850' not in g or 'versionName = "0.8.5"' not in g:
    raise SystemExit('Gradle version patch failed')
GRADLE.write_text(g)

man = MANIFEST.read_text().replace(
    'android:label="Admission Collector v0.8.4 Report Context Bridge"',
    'android:label="Admission Collector v0.8.5 Mission Lane Sequencer"'
)
if 'Admission Collector v0.8.5 Mission Lane Sequencer' not in man:
    raise SystemExit('Manifest label patch failed')
MANIFEST.write_text(man)

print('Applied Admission Collector v0.8.5 Mission Lane Sequencer & Anchor Promotion patch')
