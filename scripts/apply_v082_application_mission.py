from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
ADAPTER = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one anchor, found {count}')
    return text.replace(old, new, 1)

# ------------------------------------------------------------------
# SnapshotScript: bind agent controls to the closest SAME-card text.
# ------------------------------------------------------------------
s = SNAP.read_text()
anchor = '''  var nav=[];
  var resources=[];
  var pageActions=[];
  var agentActions=[];
'''
insert = r'''  function applicationContextForAction(el){
    if(!isJinhakHost||!el) return '';
    var cur=el;
    for(var depth=0;cur&&depth<8;depth++,cur=cur.parentElement){
      if(!visible(cur)) continue;
      var t=safeCloneText(cur,3000);
      if(!t||t.length<8) continue;
      var bars=(t.match(/[0-9]{1,2}\s*칸/g)||[]).length;
      var capacity=/[0-9,]+\s*명\s*(?:\||\s)*내\s*점수/i.test(t);
      var appSignal=/(학생부교과|학생부종합|지역인재|교과|종합|면접|학교장추천|고른기회)/i.test(t);
      var metricSignal=/(내\s*점수|전년도\s*(?:수시\s*)?경쟁률|모의지원|합격예측|합격안정성)/i.test(t);
      // More than two prediction bars almost certainly means an ancestor spanning cards.
      if((capacity || bars===1) && appSignal && metricSignal && bars<=2 && t.length<=3000) return t;
      if(bars>2 || t.length>5200) break;
    }
    return '';
  }

  var nav=[];
  var resources=[];
  var pageActions=[];
  var agentActions=[];
'''
s = once(s, anchor, insert, 'snapshot application context helper')
old_allowed = r'''      var agentAllowed=/(상세|보기|조회|검색|리포트|대학\s*정보|전형\s*정보|학과\s*정보|합격\s*예측|모의\s*지원|수시\s*저장소|정시\s*저장소|추천\s*대학|성적\s*분석|다음|더보기|결과|탭)/i;'''
new_allowed = r'''      var agentAllowed=/(실제\s*합격자|과거\s*입시결과|입시\s*결과|합격\s*예측\s*리포트|모의\s*지원\s*리포트|지원자\s*분포|대학.?학과별\s*합격\s*예측|합격\s*안정성|상세|보기|조회|검색|리포트|대학\s*정보|전형\s*정보|학과\s*정보|합격\s*예측|모의\s*지원|수시\s*저장소|정시\s*저장소|추천\s*대학|성적\s*분석|입시\s*전략|입시\s*지식|경쟁률|모집\s*요강|다음|더보기|결과|탭)/i;'''
s = once(s, old_allowed, new_allowed, 'snapshot agent allowed labels')
old_push = '''          agentActions.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:role==='tab'?'tab-navigation':'read-navigation'});'''
new_push = '''          agentActions.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:role==='tab'?'tab-navigation':'read-navigation',contextText:applicationContextForAction(a)});'''
s = once(s, old_push, new_push, 'snapshot agent context payload')
SNAP.write_text(s)

# ------------------------------------------------------------------
# JinhakAdapter: semantic v2 metrics + same-card application grammar.
# ------------------------------------------------------------------
a = ADAPTER.read_text()
a = once(a,
'''import com.admissionhub.collector.jinhak.JinhakSiteTopology
import com.admissionhub.collector.jinhak.JinhakStrategyAnalyzer
''',
'''import com.admissionhub.collector.jinhak.JinhakSiteTopology
import com.admissionhub.collector.jinhak.JinhakStrategyAnalyzer
import com.admissionhub.collector.jinhak.JinhakApplicationMission
''', 'adapter mission import')
a = once(a,
'''        "jinhak-admission-strategy",
        "jinhak-admission-feature",
''',
'''        "jinhak-admission-strategy",
        "jinhak-admission-knowledge",
        "jinhak-admission-feature",
''', 'adapter evidence page type')
a = once(a,
'''        val featureRoute = path.contains("/univ-entrance-info/susi-special")
        val mediaRoute = path.contains("/jinhak-tv")
''',
'''        val featureRoute = path.contains("/univ-entrance-info/susi-special")
        val knowledgeRoute = path.contains("/ipsi-knowledge")
        val mediaRoute = path.contains("/jinhak-tv")
''', 'adapter knowledge route flag')
a = once(a,
'''            strategyRoute -> "jinhak-admission-strategy"
            featureRoute -> "jinhak-admission-feature"
            mediaRoute -> "jinhak-media-content"
''',
'''            strategyRoute -> "jinhak-admission-strategy"
            knowledgeRoute -> "jinhak-admission-knowledge"
            featureRoute -> "jinhak-admission-feature"
            mediaRoute -> "jinhak-media-content"
''', 'adapter knowledge classification')
a = once(a,
'''        val context = GenericAdmissionParser.inferSnapshotContext(snapshot)
        val observedAt = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()
''',
'''        val context = GenericAdmissionParser.inferSnapshotContext(snapshot)
        val missionContext = JinhakApplicationMission.fromJson(snapshot.optJSONObject("missionApplicationContext"))
        val observedAt = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()
''', 'adapter carried mission context')
a = once(a,
'''        if (pageType == "jinhak-admission-strategy") {
''',
'''        if (pageType == "jinhak-admission-strategy" || pageType == "jinhak-admission-knowledge") {
''', 'adapter strategy knowledge analyzer')

old_context = '''                val compactUniversity = cleanStorageUniversity(compact?.optString("university"))
                val compactDepartment = cleanStorageDepartment(compact?.optString("department"))
                val compactAdmission = compact?.optString("admission")?.takeIf { it.isNotBlank() }
                val university = compactUniversity ?: cleanStorageUniversity(local.university) ?: explicitUniversity
                val department = compactDepartment ?: cleanStorageDepartment(local.department) ?: explicitDepartment
                val admission = compactAdmission ?: cleanStorageAdmission(local.admission, evidence)
'''
new_context = '''                val compactUniversity = cleanStorageUniversity(compact?.optString("university"))
                val compactDepartment = cleanStorageDepartment(compact?.optString("department"))
                val compactAdmission = compact?.optString("admission")?.takeIf { it.isNotBlank() }
                val mission = JinhakApplicationMission.parseCard(evidence, explicitUniversity, explicitDepartment)
                val university = mission?.university ?: compactUniversity ?: cleanStorageUniversity(local.university) ?: explicitUniversity
                val department = mission?.departmentRaw ?: compactDepartment ?: cleanStorageDepartment(local.department) ?: explicitDepartment
                val admission = mission?.admission ?: compactAdmission ?: cleanStorageAdmission(local.admission, evidence)
'''
a = once(a, old_context, new_context, 'adapter storage mission binding')
old_metrics = '''                val cardMetrics = predictionMetrics(evidence)
                compact?.optString("admissionCategory")?.takeIf { it.isNotBlank() }?.let { cardMetrics.put("admissionCategory", it) }
                compact?.optString("combinedAdmissionDepartmentLabel")?.takeIf { it.isNotBlank() }?.let { cardMetrics.put("combinedAdmissionDepartmentLabel", it) }
'''
new_metrics = '''                val cardMetrics = predictionMetrics(evidence)
                mission?.capacity?.let { if (!cardMetrics.has("capacity")) cardMetrics.put("capacity", it) }
                mission?.admissionCategory?.let { cardMetrics.put("admissionCategory", it) }
                mission?.campus?.let { cardMetrics.put("campus", it) }
                mission?.departmentRaw?.let { cardMetrics.put("rawDepartmentLabel", it) }
                mission?.parseSource?.let { cardMetrics.put("identityParseSource", it) }
                compact?.optString("admissionCategory")?.takeIf { it.isNotBlank() && !cardMetrics.has("admissionCategory") }?.let { cardMetrics.put("admissionCategory", it) }
                compact?.optString("combinedAdmissionDepartmentLabel")?.takeIf { it.isNotBlank() }?.let { cardMetrics.put("combinedAdmissionDepartmentLabel", it) }
'''
a = once(a, old_metrics, new_metrics, 'adapter storage semantic metrics')
a = once(a,
'''                    .put("admission", admission ?: JSONObject.NULL)
                    .put("metrics", cardMetrics)
''',
'''                    .put("admission", admission ?: JSONObject.NULL)
                    .put("applicationIdentityKey", mission?.identityKey ?: JSONObject.NULL)
                    .put("metrics", cardMetrics)
''', 'adapter storage identity')
a = once(a,
'''                    .put("contextSource", when {
                        compact != null -> "compact-recommendation-card"
''',
'''                    .put("contextSource", when {
                        mission?.identityKey != null -> "same-card-application-grammar"
                        compact != null -> "compact-recommendation-card"
''', 'adapter storage context source')
a = once(a,
'''                    .put("confidence", when {
                        university != null && department != null && admission != null -> "high"
''',
'''                    .put("confidence", when {
                        mission != null -> mission.confidence
                        university != null && department != null && admission != null -> "high"
''', 'adapter storage confidence')
a = once(a,
'''                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = true))
                result.put(record)
''',
'''                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = true))
                result.put(record)
                if (mission?.identityKey != null) {
                    result.put(JinhakApplicationMission.missionEvidence(mission, pageType, observedAt, safePath(snapshot.optString("url"))))
                }
''', 'adapter storage mission coverage')

# Knowledge is handled before this return, but keep the type semantically explicit elsewhere.
a = once(a,
'''            pageType == "jinhak-other" || pageType == "jinhak-editorial-content" ||
            pageType == "jinhak-admission-strategy" || pageType == "jinhak-admission-feature" ||
''',
'''            pageType == "jinhak-other" || pageType == "jinhak-editorial-content" ||
            pageType == "jinhak-admission-strategy" || pageType == "jinhak-admission-knowledge" || pageType == "jinhak-admission-feature" ||
''', 'adapter reference return set')

# Report-level semantic metrics must not confuse previous-year with mock competition.
a = once(a, '        val metrics = JSONObject()\n        putNumber(metrics, "universityCalculatedScore",',
'''        val metrics = JinhakApplicationMission.semanticMetrics(text)
        putNumber(metrics, "universityCalculatedScore",''', 'adapter report semantic metrics base')
# Remove the broad competition assignment in report parser only; semanticMetrics already adds explicit mockCompetition.
a = once(a,
'''        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\s*)?경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
''', '', 'adapter broad report competition')

# Bind report summary only to a mission that was opened from that exact application card.
a = once(a,
'''                .put("university", context.university ?: JSONObject.NULL)
                .put("department", context.department ?: JSONObject.NULL)
                .put("admission", context.admission ?: JSONObject.NULL)
''',
'''                .put("university", missionContext?.university ?: context.university ?: JSONObject.NULL)
                .put("department", missionContext?.departmentRaw ?: context.department ?: JSONObject.NULL)
                .put("admission", missionContext?.admission ?: context.admission ?: JSONObject.NULL)
                .put("applicationIdentityKey", missionContext?.identityKey ?: JSONObject.NULL)
''', 'adapter report mission identity fields')
a = once(a,
'''                .put("observedAt", observedAt)
                .put("confidence", when {
                    context.university != null && context.department != null -> "high"
''',
'''                .put("observedAt", observedAt)
                .put("contextSource", if (missionContext?.identityKey != null) "same-application-agent-mission" else "page-context")
                .put("confidence", when {
                    missionContext != null -> missionContext.confidence
                    context.university != null && context.department != null -> "high"
''', 'adapter report mission confidence')
# Add mission evidence after any summary and before generic parsing.
a = once(a,
'''        // Generic page-wide inference is intentionally gated. v0.7.1 produced false
''',
'''        if (missionContext?.identityKey != null && JinhakApplicationMission.laneForPageType(pageType) != "reference") {
            result.put(JinhakApplicationMission.missionEvidence(missionContext, pageType, observedAt, safePath(snapshot.optString("url"))))
        }

        // Generic page-wide inference is intentionally gated. v0.7.1 produced false
''', 'adapter report mission evidence')
# Safely bind generic actual/score rows to the carried application mission only.
a = once(a,
'''            if (row.isNull("year") && inferredYear != null) row.put("year", inferredYear)
            row.put("sourcePage", safePath(snapshot.optString("url")))
''',
'''            if (row.isNull("year") && inferredYear != null) row.put("year", inferredYear)
            if (missionContext?.identityKey != null) {
                if (row.isNull("university") || row.optString("university").isBlank()) row.put("university", missionContext.university ?: JSONObject.NULL)
                if (row.isNull("department") || row.optString("department").isBlank()) row.put("department", missionContext.departmentRaw ?: JSONObject.NULL)
                if (row.isNull("admission") || row.optString("admission").isBlank()) row.put("admission", missionContext.admission ?: JSONObject.NULL)
                row.put("applicationIdentityKey", missionContext.identityKey)
                    .put("contextSource", "same-application-agent-mission")
            }
            row.put("sourcePage", safePath(snapshot.optString("url")))
''', 'adapter generic mission binding')
a = once(a,
'''        "jinhak-admission-strategy", "jinhak-admission-feature", "jinhak-editorial-content", "jinhak-media-content" -> "admission-reference"
''',
'''        "jinhak-admission-strategy", "jinhak-admission-knowledge", "jinhak-admission-feature", "jinhak-editorial-content", "jinhak-media-content" -> "admission-reference"
''', 'adapter knowledge scope')
a = once(a,
'''                        h.contains("전년도") && h.contains("경쟁률") -> metrics.put("previousCompetition", n)
''',
'''                        h.contains("전년도") && h.contains("경쟁률") -> metrics.put("previousYearCompetition", n)
''', 'adapter table previous-year semantics')

# Replace predictionMetrics wholesale up to putNumber helper.
start = a.index('    private fun predictionMetrics(text: String): JSONObject {')
end = a.index('    private fun putNumber(obj: JSONObject, key: String, value: String?) {', start)
new_prediction = r'''    private fun predictionMetrics(text: String): JSONObject {
        val metrics = JinhakApplicationMission.semanticMetrics(text)
        // Additional metrics are only extracted from labels whose semantics are explicit.
        putNumber(metrics, "predictionProbability", Regex("(?:예상\\s*)?(?:합격률|합격확률|합격가능성)\\s*[:：]?\\s*([0-9]{1,3}(?:\\.[0-9]+)?)\\s*%").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        if (!metrics.has("capacity")) {
            putInt(metrics, "capacity", Regex("([0-9,]+)\\s*명\\s*내\\s*점수").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        }
        putInt(metrics, "applicants", Regex("(?:현재\\s*)?(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "additionalAdmits", Regex("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        if (!metrics.has("myCalculatedScore")) {
            putNumber(metrics, "myCalculatedScore", Regex("(?:대학별\\s*)?(?:환산점수|산출점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
            if (metrics.has("myCalculatedScore")) metrics.put("universityCalculatedScore", metrics.optDouble("myCalculatedScore"))
        }
        if (!metrics.has("myReflectedGrade")) {
            putNumber(metrics, "myReflectedGrade", Regex("(?:반영\\s*평균등급|환산등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        }
        val minimum = Regex("수능최저[^.\\n]{0,100}(충족가능|미충족|불충족|충족)").find(text)?.groupValues?.getOrNull(1)
        if (!minimum.isNullOrBlank()) metrics.put("minimumStatus", minimum)
        return metrics
    }

'''
a = a[:start] + new_prediction + a[end:]
ADAPTER.write_text(a)

# ------------------------------------------------------------------
# MainActivity: carry application mission across report navigation and return.
# ------------------------------------------------------------------
m = MAIN.read_text()
m = once(m,
'''import com.admissionhub.collector.jinhak.JinhakSiteTopology
import com.admissionhub.collector.session.SecureSessionVault
''',
'''import com.admissionhub.collector.jinhak.JinhakSiteTopology
import com.admissionhub.collector.jinhak.JinhakApplicationMission
import com.admissionhub.collector.session.SecureSessionVault
''', 'main mission import')
m = once(m,
'''    private var jinhakAgentActionInFlight = false
    private var jinhakAgentActionsExecuted = 0
''',
'''    private var jinhakAgentActionInFlight = false
    private var jinhakAgentActionsExecuted = 0
    private var jinhakMissionContext: JinhakApplicationMission.Context? = null
    private var jinhakMissionOriginRoute = ""
    private var jinhakMissionNeedsReturn = false
    private var jinhakApplicationBoundActions = 0
    private var jinhakApplicationMissionReturns = 0
    private val jinhakMissionCoverage = linkedMapOf<String, MutableSet<String>>()
''', 'main mission state fields')
m = once(m,
'''        private const val VERSION = "0.8.1"
        private const val BUILD_CODE = 10810
''',
'''        private const val VERSION = "0.8.2"
        private const val BUILD_CODE = 10820
''', 'main version')
m = once(m,
'''        jinhakAgentActionInFlight = false
        jinhakAgentActionsExecuted = 0
        cloudFrontierTaskIds.clear()
''',
'''        jinhakAgentActionInFlight = false
        jinhakAgentActionsExecuted = 0
        jinhakMissionContext = null
        jinhakMissionOriginRoute = ""
        jinhakMissionNeedsReturn = false
        jinhakApplicationBoundActions = 0
        jinhakApplicationMissionReturns = 0
        jinhakMissionCoverage.clear()
        cloudFrontierTaskIds.clear()
''', 'main mission reset')
# Mark admission knowledge as a structured/reference type rather than unknown.
m = once(m,
'''        "jinhak-university-search",
        "jinhak-recommended-university",
''',
'''        "jinhak-university-search",
        "jinhak-admission-knowledge",
        "jinhak-recommended-university",
''', 'main knowledge structured type')
# Inject current mission into the snapshot before normalization.
m = once(m,
'''            val plan = if (activeAction == null) currentAdapter().paginationPlan(snapshot) else null
''',
'''            if (provider == ProviderId.JINHAK) {
                jinhakMissionContext?.let { snapshot.put("missionApplicationContext", it.toJson()) }
            }
            val plan = if (activeAction == null) currentAdapter().paginationPlan(snapshot) else null
''', 'main snapshot mission carry')
# Coverage accounting immediately after normalization.
m = once(m,
'''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) jinhakConsecutiveStalls = 0
''',
'''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) {
                jinhakConsecutiveStalls = 0
                val mission = jinhakMissionContext
                val missionKey = mission?.identityKey
                if (missionKey != null) {
                    val lane = JinhakApplicationMission.laneForPageType(snapshot.optString("providerPageType"))
                    if (lane != "reference") jinhakMissionCoverage.getOrPut(missionKey) { linkedSetOf() }.add(lane)
                }
                // Saved-application records themselves seed the coverage ledger even before a report is opened.
                for (ri in 0 until pageRecords.length()) {
                    val r = pageRecords.optJSONObject(ri) ?: continue
                    val key = r.optString("applicationIdentityKey").takeIf { it.isNotBlank() && it != "null" } ?: continue
                    if (r.optString("recordType") == "jinhak-saved-application-prediction") {
                        jinhakMissionCoverage.getOrPut(key) { linkedSetOf() }.add("saved-application")
                    }
                }
            }
''', 'main mission coverage accounting')
# After no agent action, return to application origin before broad URL queue.
m = once(m,
'''            if (provider == ProviderId.JINHAK && activeAction == null && maybeExecuteJinhakAgentAction(snapshot, jinhakExpansionStateKey)) {
                return@collectSnapshot
            }

            status.text = if (activeAction != null) {
''',
'''            if (provider == ProviderId.JINHAK && activeAction == null && maybeExecuteJinhakAgentAction(snapshot, jinhakExpansionStateKey)) {
                return@collectSnapshot
            }
            if (provider == ProviderId.JINHAK && activeAction == null && maybeReturnToJinhakMissionOrigin(snapshot)) {
                return@collectSnapshot
            }

            status.text = if (activeAction != null) {
''', 'main mission return call')
# Replace agent function with application-aware implementation, keeping policy in Navigator.
start = m.index('    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject, expansionStateKey: String?): Boolean {')
end = m.index('    private fun loadNextBatchPage() {', start)
new_agent = r'''    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject, expansionStateKey: String?): Boolean {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return false
        if (jinhakAgentActionInFlight || jinhakAgentActionsExecuted >= MAX_JINHAK_AGENT_ACTIONS) return false
        val route = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        fun actionKeyFor(action: JinhakAgentNavigator.Candidate): String = RecordUtils.sha256(
            "${expansionStateKey ?: runtimeSafePath(route)}|${JinhakAgentNavigator.key(route, action)}"
        )
        val candidates = JinhakAgentNavigator.candidates(snapshot)
        val currentMissionKey = jinhakMissionContext?.identityKey
        val candidate = candidates.firstOrNull { action ->
            if (jinhakAgentActionSeen.contains(actionKeyFor(action))) return@firstOrNull false
            val actionMissionKey = action.applicationContext?.identityKey
            // While inside a mission report, do not jump directly to a DIFFERENT application card.
            currentMissionKey == null || actionMissionKey == null || actionMissionKey == currentMissionKey
        } ?: return false
        val actionKey = actionKeyFor(candidate)
        jinhakAgentActionSeen.add(actionKey)

        val actionMission = candidate.applicationContext
        if (actionMission?.identityKey != null) {
            if (jinhakMissionContext?.identityKey != actionMission.identityKey) {
                jinhakMissionContext = actionMission
                jinhakMissionOriginRoute = route
            }
            jinhakMissionNeedsReturn = true
            jinhakApplicationBoundActions += 1
            jinhakMissionCoverage.getOrPut(actionMission.identityKey) { linkedSetOf() }.add("saved-application")
            recordRuntimeEvent("jinhak-application-mission-start", JSONObject()
                .put("applicationIdentityHash", actionMission.identityKey.take(24))
                .put("missionPriority", candidate.missionPriority)
                .put("safePath", runtimeSafePath(route)))
        } else if (jinhakMissionContext?.identityKey != null) {
            // A report tab may not repeat the application card. The already-bound mission stays active.
            jinhakMissionNeedsReturn = true
        }

        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
        currentBatchTarget = route.ifBlank { currentBatchTarget }
        status.text = "진학사 지원안 미션 ${jinhakAgentActionsExecuted}/$MAX_JINHAK_AGENT_ACTIONS · ${candidate.label.take(48)}"
        recordRuntimeEvent("jinhak-agent-action", JSONObject()
            .put("safePath", runtimeSafePath(route))
            .put("label", candidate.label.take(80))
            .put("kind", candidate.kind)
            .put("applicationBound", jinhakMissionContext?.identityKey != null))
        webView.evaluateJavascript(JinhakAgentNavigator.executionScript(candidate)) { encoded ->
            val result = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull() ?: JSONObject()
            jinhakAgentActionInFlight = false
            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
            if (result.optBoolean("ok", false)) {
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin || batchCollecting) return@postDelayed
                    scheduleBatchSnapshot()
                }, 1100L)
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 120L)
            }
        }
        return true
    }

    private fun maybeReturnToJinhakMissionOrigin(snapshot: JSONObject): Boolean {
        val mission = jinhakMissionContext ?: return false
        if (!jinhakMissionNeedsReturn || mission.identityKey == null || jinhakMissionOriginRoute.isBlank()) return false
        val origin = jinhakMissionOriginRoute
        val current = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        jinhakApplicationMissionReturns += 1
        recordRuntimeEvent("jinhak-application-mission-return", JSONObject()
            .put("applicationIdentityHash", mission.identityKey.take(24))
            .put("fromSafePath", runtimeSafePath(current))
            .put("toSafePath", runtimeSafePath(origin))
            .put("coverageLanes", jinhakMissionCoverage[mission.identityKey]?.size ?: 0))
        // Clear before navigation so the next storage snapshot cannot inherit the previous application.
        jinhakMissionContext = null
        jinhakMissionOriginRoute = ""
        jinhakMissionNeedsReturn = false
        currentBatchTarget = origin
        status.text = "지원안 리포트 탐색 종료: 수시저장소 카드로 복귀해 다음 미션을 계속합니다."
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin) return@postDelayed
            if (webView.canGoBack() && current != origin) webView.goBack() else webView.loadUrl(origin)
        }, 180L)
        return true
    }

'''
m = m[:start] + new_agent + m[end:]
# Clear stale mission context when broad queue changes page after all mission returns.
m = once(m,
'''            currentBatchTarget = next
            status.text = "다음 입시정보 페이지 탐색: ${safeDisplayUrl(next)}"
''',
'''            jinhakMissionContext = null
            jinhakMissionOriginRoute = ""
            jinhakMissionNeedsReturn = false
            currentBatchTarget = next
            status.text = "다음 입시정보 페이지 탐색: ${safeDisplayUrl(next)}"
''', 'main clear mission before broad queue')
# Add privacy-safe application coverage counts to diagnostics.
m = once(m,
'''                        .put("agentActionsExecuted", jinhakAgentActionsExecuted)
                        .put("cloudFrontierPublished", cloudFrontierPublished)
''',
'''                        .put("agentActionsExecuted", jinhakAgentActionsExecuted)
                        .put("applicationBoundAgentActions", jinhakApplicationBoundActions)
                        .put("applicationMissionReturns", jinhakApplicationMissionReturns)
                        .put("applicationMissionIdentities", jinhakMissionCoverage.size)
                        .put("applicationMissionCoverage", JSONObject().apply {
                            val lanes = listOf("saved-application", "current-prediction", "mock-support", "actual-admit", "university-result", "score-analysis", "strategy")
                            for (lane in lanes) put(lane, jinhakMissionCoverage.values.count { it.contains(lane) })
                            put("fourOrMoreLanes", jinhakMissionCoverage.values.count { it.size >= 4 })
                            put("sixOrMoreLanes", jinhakMissionCoverage.values.count { it.size >= 6 })
                        })
                        .put("cloudFrontierPublished", cloudFrontierPublished)
''', 'main mission diagnostics')
# Batch JSON summary too.
m = once(m,
'''                .put("jinhakAgentActionsExecuted", jinhakAgentActionsExecuted)
                .put("jinhakUniqueNavigationStates", jinhakUniqueNavigationStates)
''',
'''                .put("jinhakAgentActionsExecuted", jinhakAgentActionsExecuted)
                .put("jinhakApplicationBoundActions", jinhakApplicationBoundActions)
                .put("jinhakApplicationMissionReturns", jinhakApplicationMissionReturns)
                .put("jinhakApplicationMissionIdentities", jinhakMissionCoverage.size)
                .put("jinhakUniqueNavigationStates", jinhakUniqueNavigationStates)
''', 'main batch mission summary')
MAIN.write_text(m)

# ------------------------------------------------------------------
# Analysis-ready export contract v3: application mission is first-class.
# ------------------------------------------------------------------
st = STORE.read_text()
st = once(st,
'''\"analysisReady\":{\"contractVersion\":2,\"purpose\":\"assistant-xlsx-dashboard-generation\",\"authoritativeLayers\":[\"sources.adiga.records\",\"sources.jinhak.records\",\"sources.jinhak.pageAnalyses\",\"observationEvidence\",\"errorEvidence\",\"syncDiagnostics\"],\"recommendedWorkbookSheets\":[\"Dashboard\",\"UnifiedRecords\",\"JinhakPredictions\",\"HistoricalResults\",\"Observations\",\"Coverage\",\"Errors\"],\"rowKeyFields\":[\"provider\",\"year\",\"university\",\"department\",\"admission\",\"recordType\",\"observedAt\"],''',
'''\"analysisReady\":{\"contractVersion\":3,\"purpose\":\"assistant-xlsx-dashboard-generation\",\"authoritativeLayers\":[\"sources.adiga.records\",\"sources.jinhak.records\",\"sources.jinhak.pageAnalyses\",\"observationEvidence\",\"errorEvidence\",\"syncDiagnostics\"],\"recommendedWorkbookSheets\":[\"Dashboard\",\"ApplicationMissions\",\"UnifiedRecords\",\"JinhakPredictions\",\"HistoricalResults\",\"Observations\",\"Coverage\",\"Errors\"],\"rowKeyFields\":[\"provider\",\"year\",\"university\",\"department\",\"admission\",\"applicationIdentityKey\",\"recordType\",\"observedAt\"],''', 'store analysis contract v3')
STORE.write_text(st)

# ------------------------------------------------------------------
# Version metadata.
# ------------------------------------------------------------------
g = GRADLE.read_text()
g = once(g, 'versionCode = 10810', 'versionCode = 10820', 'gradle code')
g = once(g, 'versionName = "0.8.1"', 'versionName = "0.8.2"', 'gradle name')
GRADLE.write_text(g)

mf = MANIFEST.read_text()
mf = once(mf, 'android:label="Admission Collector v0.8.1 Jinhak Mission Analyst"',
          'android:label="Admission Collector v0.8.2 Application Mission Closure"', 'manifest label')
MANIFEST.write_text(mf)

print('Applied v0.8.2 Application Mission Closure patch')
