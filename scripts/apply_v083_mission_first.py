from pathlib import Path
import re

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
MISSION = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakApplicationMission.kt'
ADAPTER = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
AGENT = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt'
SYNC = ROOT / 'app/src/main/java/com/admissionhub/collector/sync/UnifiedSyncState.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected exactly one anchor, found {n}')
    return text.replace(old, new, 1)


def sub_once(text: str, pattern: str, repl: str, label: str, flags=0) -> str:
    out, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise SystemExit(f'{label}: expected exactly one regex anchor, found {n}')
    return out

# ---------------------------------------------------------------------------
# Version metadata
# ---------------------------------------------------------------------------
gradle = GRADLE.read_text()
gradle = replace_once(gradle, 'versionCode = 10820', 'versionCode = 10830', 'gradle versionCode')
gradle = replace_once(gradle, 'versionName = "0.8.2"', 'versionName = "0.8.3"', 'gradle versionName')
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Collector v0.8.2 Application Mission Closure"',
    'android:label="Admission Collector v0.8.3 Mission-First Report Recovery"',
    'manifest label'
)
MANIFEST.write_text(manifest)

# ---------------------------------------------------------------------------
# Sync-state contract: visible provider consent is a real user-action state.
# ---------------------------------------------------------------------------
sync = SYNC.read_text()
sync = replace_once(
    sync,
    '    JINHAK_AUTONOMOUS_CRAWL,\n    JINHAK_USER_VIEW_FALLBACK,',
    '    JINHAK_AUTONOMOUS_CRAWL,\n    JINHAK_USER_CONSENT_REQUIRED,\n    JINHAK_USER_VIEW_FALLBACK,',
    'sync enum consent state'
)
sync = replace_once(
    sync,
    '        UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL to setOf(\n            UnifiedSyncState.CANONICAL_MERGE,\n            UnifiedSyncState.AUTH_REQUIRED,\n            UnifiedSyncState.FAILED\n        ),',
    '        UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL to setOf(\n            UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED,\n            UnifiedSyncState.CANONICAL_MERGE,\n            UnifiedSyncState.AUTH_REQUIRED,\n            UnifiedSyncState.FAILED\n        ),\n        UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED to setOf(\n            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\n            UnifiedSyncState.CANONICAL_MERGE,\n            UnifiedSyncState.AUTH_REQUIRED,\n            UnifiedSyncState.FAILED\n        ),',
    'sync transitions consent state'
)
sync = replace_once(
    sync,
    '            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,',
    '            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\n            UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED,\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,',
    'auth transition consent state'
)
SYNC.write_text(sync)

# ---------------------------------------------------------------------------
# Jinhak application identity grammar.
# - strip UI-only close/bar prefixes from identity material, not raw evidence
# - skip repeated admission-category brackets before campus
# ---------------------------------------------------------------------------
mission = MISSION.read_text()
mission = replace_once(mission, '    const val SEMANTICS_VERSION = 2', '    const val SEMANTICS_VERSION = 3', 'mission semantics version')
mission = replace_once(
    mission,
    '    private val universityPrefix = Regex(\n        """^(?:[0-9]{1,2}\\s*칸\\s*)?([가-힣A-Za-z0-9·.&+()\\-]{2,45}?(?:대학교|교육대학교|과학기술원|대(?:\\([^)]+\\))?))(?=\\s*\\[)"""\n    )',
    '    private val universityPrefix = Regex(\n        """^([가-힣A-Za-z0-9·.&+()\\-]{2,45}?(?:대학교|교육대학교|과학기술원|대(?:\\([^)]+\\))?))(?=\\s*\\[)"""\n    )',
    'mission university prefix'
)
mission = replace_once(
    mission,
    '        val text = rawText.replace(Regex("""\\s+"""), " ").trim().take(6000)\n        if (text.isBlank()) return null',
    '        val rawVisibleText = rawText.replace(Regex("""\\s+"""), " ").trim().take(6000)\n        val text = stripCardUiPrefix(rawVisibleText)\n        if (text.isBlank()) return null',
    'mission text normalization'
)
mission = replace_once(
    mission,
    '        val campusMatch = campus.find(working)\n        val campusLabel = campusMatch?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() }\n        if (campusMatch != null) working = working.substring(campusMatch.range.last + 1).trim()',
    '''        var campusLabel: String? = null
        // Some cards repeat the admission category after the admission name, e.g.
        // [교과]일반[교과][대전]안경광학.  The repeated [교과] is metadata, not campus.
        while (true) {
            val bracket = campus.find(working) ?: break
            val token = bracket.groupValues.getOrNull(1)?.trim().orEmpty()
            working = working.substring(bracket.range.last + 1).trim()
            if (isAdmissionMetaBracket(token, admissionCategory)) continue
            campusLabel = token.takeIf { it.isNotBlank() }
            break
        }''',
    'mission repeated bracket campus parsing'
)
mission = replace_once(
    mission,
    '    private fun cleanUniversity(value: String?): String? {\n        val s = value?.replace(Regex("""\\s+"""), " ")?.trim()?.takeIf { it.length in 2..60 } ?: return null',
    '    private fun cleanUniversity(value: String?): String? {\n        val s = value?.let(::stripCardUiPrefix)?.replace(Regex("""\\s+"""), " ")?.trim()?.takeIf { it.length in 2..60 } ?: return null',
    'mission clean university'
)
insert_anchor = '    private fun yearToken(text: String): Int = Regex("""(?<![0-9])(20[0-9]{2})(?:학년도)?(?![0-9])""")\n'
insert_code = '''    private fun stripCardUiPrefix(value: String): String {
        var s = value.replace(Regex("""\\s+"""), " ").trim()
        // UI chrome observed in storage cards: "닫기7칸건국대...".  These tokens are
        // display controls/prediction badges and must never participate in university identity.
        s = s.replace(Regex("""^(?:(?:닫기|열기)\\s*)+"""), "").trim()
        s = s.replace(Regex("""^(?:[0-9]{1,2}\\s*칸\\s*)+"""), "").trim()
        s = s.replace(Regex("""^(?:(?:닫기|열기)\\s*)+"""), "").trim()
        return s
    }

    private fun isAdmissionMetaBracket(token: String, category: String?): Boolean {
        val t = token.replace(Regex("""\\s+"""), "").trim()
        if (t.isBlank()) return true
        if (category != null && t.equals(category.replace(Regex("""\\s+"""), ""), ignoreCase = true)) return true
        return Regex("""^(?:교과|종합|논술|실기|실적|학생부교과|학생부종합|수시|정시)$""").matches(t)
    }

'''
mission = replace_once(mission, insert_anchor, insert_code + insert_anchor, 'mission helper insertion')
MISSION.write_text(mission)

# ---------------------------------------------------------------------------
# Saved-application normalization: a partial identity remains an observation,
# never a structured prediction with a page-wide/fallback department.
# ---------------------------------------------------------------------------
adapter = ADAPTER.read_text()
adapter = replace_once(
    adapter,
    '                if (!hasPrimaryPrediction) continue\n                val logical = RecordUtils.sha256(listOf(',
    '''                if (!hasPrimaryPrediction) continue

                if (pageType == "jinhak-early-storage" && mission?.identityKey == null) {
                    val unboundMetrics = JSONObject(cardMetrics.toString())
                        .put("identityParseSource", mission?.parseSource ?: "unbound-no-same-card-identity")
                        .put("unboundReason", "same-card-application-identity-incomplete")
                    val unbound = JSONObject()
                        .put("recordType", "jinhak-application-unbound-observation")
                        .put("providerPageType", pageType)
                        .put("dataScope", "current-prediction-unbound")
                        .put("year", mission?.year ?: local.year ?: TARGET_YEAR)
                        .put("university", mission?.university ?: compactUniversity ?: explicitUniversity ?: JSONObject.NULL)
                        .put("department", JSONObject.NULL)
                        .put("admission", mission?.admission ?: compactAdmission ?: JSONObject.NULL)
                        .put("applicationIdentityKey", JSONObject.NULL)
                        .put("metrics", unboundMetrics)
                        .put("observedAt", observedAt)
                        .put("cardIndex", i)
                        .put("contextSource", "unbound-observation-preserved-no-department-inference")
                        .put("confidence", "raw")
                        .put("sourcePage", safePath(snapshot.optString("url")))
                        .put("rawEvidence", evidence)
                    unbound.put("sourceRowFingerprint", fingerprint(unbound, observedAt, preserveSnapshot = true))
                    result.put(unbound)
                    continue
                }

                val logical = RecordUtils.sha256(listOf(''',
    'adapter unbound observation split'
)
ADAPTER.write_text(adapter)

# ---------------------------------------------------------------------------
# Agent safety: consent is never an automated action.
# ---------------------------------------------------------------------------
agent = AGENT.read_text()
agent = agent.replace(
    '(원서\\\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰)',
    '(원서\\\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)',
)
if '쿠폰|동의|미동의' not in agent:
    raise SystemExit('agent consent safety replacement did not apply')
AGENT.write_text(agent)

# ---------------------------------------------------------------------------
# Snapshot: detect consent gate and promote same-card direct anchor report links
# to mission-bound actions.  Such mission links are not also put in generic nav.
# ---------------------------------------------------------------------------
snap = SNAP.read_text()
snap = replace_once(
    snap,
    "  var bodyText=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,16000);",
    '''  var bodyText=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,16000);
  var jinhakProviderHost=/(^|\\.)jinhak\\.com$/i.test(location.hostname);
  var jinhakAiConsentRequired=jinhakProviderHost &&
    /학생부\\s*AI진단\\s*점수\\s*활용\\s*동의/i.test(bodyText) &&
    /(?:^|\\s)동의(?:\\s|$)/i.test(bodyText) && /미동의/i.test(bodyText);
  var interactionGate={
    requiresUserAction:jinhakAiConsentRequired,
    type:jinhakAiConsentRequired?'jinhak-ai-diagnosis-consent':'',
    safeLabel:jinhakAiConsentRequired?'학생부 AI진단 점수 활용 동의':''
  };''',
    'snapshot consent gate'
)
old_agent_block = '''    if(isJinhakHost && agentActions.length<160){
      var agentBlocked=/(원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰)/i;
      var agentAllowed=/(실제\\s*합격자|과거\\s*입시결과|입시\\s*결과|합격\\s*예측\\s*리포트|모의\\s*지원\\s*리포트|지원자\\s*분포|대학.?학과별\\s*합격\\s*예측|합격\\s*안정성|상세|보기|조회|검색|리포트|대학\\s*정보|전형\\s*정보|학과\\s*정보|합격\\s*예측|모의\\s*지원|수시\\s*저장소|정시\\s*저장소|추천\\s*대학|성적\\s*분석|입시\\s*전략|입시\\s*지식|경쟁률|모집\\s*요강|다음|더보기|결과|탭)/i;
      var role=cleanText(a.getAttribute('role')||'');
      var dynamicControl=!route || role==='tab' || a.tagName==='BUTTON';
      if(dynamicControl && label && !agentBlocked.test(label+' '+meta2) && agentAllowed.test(label)){
        var ak=li+'|'+label+'|'+String(a.tagName||'')+'|'+role;
        if(!seenAgentAction[ak]){
          agentActions.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:role==='tab'?'tab-navigation':'read-navigation',contextText:applicationContextForAction(a)});
          seenAgentAction[ak]=1;
        }
      }
    }
'''
new_agent_block = '''    var missionLinkBound=false;
    if(isJinhakHost && agentActions.length<160){
      var agentBlocked=/(원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)/i;
      var agentAllowed=/(실제\\s*합격자|과거\\s*입시결과|입시\\s*결과|합격\\s*예측\\s*리포트|모의\\s*지원\\s*리포트|지원자\\s*분포|대학.?학과별\\s*합격\\s*예측|합격\\s*안정성|상세|보기|조회|검색|리포트|대학\\s*정보|전형\\s*정보|학과\\s*정보|합격\\s*예측|모의\\s*지원|수시\\s*저장소|정시\\s*저장소|추천\\s*대학|성적\\s*분석|입시\\s*전략|입시\\s*지식|경쟁률|모집\\s*요강|다음|더보기|결과|탭)/i;
      var role=cleanText(a.getAttribute('role')||'');
      var applicationContext=applicationContextForAction(a);
      var missionLink=!!route && String(a.tagName||'').toUpperCase()==='A' && applicationContext.length>0;
      var dynamicControl=!route || role==='tab' || a.tagName==='BUTTON' || missionLink;
      if(dynamicControl && label && !agentBlocked.test(label+' '+meta2) && agentAllowed.test(label)){
        var ak=li+'|'+label+'|'+String(a.tagName||'')+'|'+role;
        if(!seenAgentAction[ak]){
          agentActions.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:missionLink?'mission-link-navigation':(role==='tab'?'tab-navigation':'read-navigation'),contextText:applicationContext});
          seenAgentAction[ak]=1;
          missionLinkBound=missionLink;
        }
      }
    }
'''
snap = replace_once(snap, old_agent_block, new_agent_block, 'snapshot mission anchor action')
snap = replace_once(
    snap,
    '    if(!route) continue;\n    var ru;',
    '    if(missionLinkBound) continue;\n    if(!route) continue;\n    var ru;',
    'snapshot suppress generic mission navigation'
)
snap = replace_once(
    snap,
    '    pageState:{isError:pageError,errorType:errorType},\n    listMeta:',
    '    pageState:{isError:pageError,errorType:errorType},\n    interactionGate:interactionGate,\n    listMeta:',
    'snapshot interaction gate export'
)
SNAP.write_text(snap)

# ---------------------------------------------------------------------------
# Main runtime orchestration.
# ---------------------------------------------------------------------------
main = MAIN.read_text()
main = replace_once(main, 'private const val VERSION = "0.8.2"', 'private const val VERSION = "0.8.3"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 10820', 'private const val BUILD_CODE = 10830', 'main build code')
main = replace_once(main, '            text = "로그인 갱신 후 계속"', '            text = "로그인/동의 후 계속"', 'resume button label')
main = replace_once(
    main,
    '    private val jinhakMissionCoverage = linkedMapOf<String, MutableSet<String>>()\n    private val cloudFrontierTaskIds',
    '''    private val jinhakMissionCoverage = linkedMapOf<String, MutableSet<String>>()
    private val jinhakMissionAnchorDiscoveredKeys = linkedSetOf<String>()
    private var jinhakMissionAnchorActionsExecuted = 0
    private var jinhakConsentGatePending = false
    private var jinhakConsentResumePending = false
    private var jinhakConsentGatesEncountered = 0
    private var jinhakConsentGatesResolved = 0
    private var jinhakMissionBootstrapStartedAtMs = 0L
    private var jinhakFirstPopulatedStorageAtMs = 0L
    private var jinhakUnboundSavedApplicationObservations = 0
    private val cloudFrontierTaskIds''',
    'main mission runtime fields'
)
main = replace_once(
    main,
    '        jinhakApplicationMissionReturns = 0\n        jinhakMissionCoverage.clear()\n        cloudFrontierTaskIds.clear()',
    '''        jinhakApplicationMissionReturns = 0
        jinhakMissionCoverage.clear()
        jinhakMissionAnchorDiscoveredKeys.clear()
        jinhakMissionAnchorActionsExecuted = 0
        jinhakConsentGatePending = false
        jinhakConsentResumePending = false
        jinhakConsentGatesEncountered = 0
        jinhakConsentGatesResolved = 0
        jinhakMissionBootstrapStartedAtMs = if (provider == ProviderId.JINHAK) System.currentTimeMillis() else 0L
        jinhakFirstPopulatedStorageAtMs = 0L
        jinhakUnboundSavedApplicationObservations = 0
        cloudFrontierTaskIds.clear()''',
    'main runtime reset'
)
main = replace_once(
    main,
    '        currentBatchTarget = canonicalizeBatchUrl(url)\n        batchButton.text = "일괄 수집 중지"',
    '''        currentBatchTarget = if (provider == ProviderId.JINHAK) {
            canonicalizeBatchUrl(currentAdapter().seedUrls().firstOrNull() ?: url)
        } else canonicalizeBatchUrl(url)
        batchButton.text = "일괄 수집 중지"''',
    'main mission-first bootstrap target'
)
# Resume flow: consent is separate from authentication and never selects a provider choice.
resume_anchor = '''    private fun resumeAfterLogin() {
        if (!batchRunning || !batchPausedForLogin) {
            checkSessionState()
            return
        }
'''
resume_repl = '''    private fun resumeAfterLogin() {
        if (provider == ProviderId.JINHAK && batchRunning && batchPausedForLogin && jinhakConsentGatePending) {
            // User must choose consent/decline and confirm inside the provider UI.  This button
            // only resumes observation; it never clicks or selects either provider choice.
            jinhakConsentGatePending = false
            jinhakConsentResumePending = true
            batchPausedForLogin = false
            showBatchCover()
            sessionState.text = "△ 진학사 동의 선택 확인 중"
            status.text = "사용자 선택 후 진학사 화면을 다시 확인합니다. 선택값은 Collector가 읽거나 변경하지 않습니다."
            handler.postDelayed({
                if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK && !batchCollecting) scheduleBatchSnapshot()
            }, 650L)
            return
        }
        if (!batchRunning || !batchPausedForLogin) {
            checkSessionState()
            return
        }
'''
main = replace_once(main, resume_anchor, resume_repl, 'main consent resume branch')

# Consent gate handler and mission action diagnostics.
insert_before = '    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject, expansionStateKey: String?): Boolean {'
consent_function = '''    private fun pauseJinhakForConsent(snapshot: JSONObject) {
        if (provider != ProviderId.JINHAK || !batchRunning) return
        if (!jinhakConsentGatePending) jinhakConsentGatesEncountered += 1
        jinhakConsentGatePending = true
        jinhakConsentResumePending = false
        batchPausedForLogin = true
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        disarmBatchNavigationWatchdog()
        hideBatchCover()
        sessionState.text = "○ 진학사 사용자 동의 선택 필요"
        status.text = "진학사에서 학생부 AI진단 점수 활용 동의를 직접 선택하고 확인한 뒤 '로그인/동의 후 계속'을 누르세요. Collector는 동의/미동의를 자동 선택하지 않습니다."
        unifiedSessionId?.let { sessionId ->
            localStore.recordSyncState(
                sessionId,
                UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED.name,
                ProviderId.JINHAK.wireName,
                JSONObject()
                    .put("gateType", snapshot.optJSONObject("interactionGate")?.optString("type") ?: "provider-consent")
                    .put("safePath", runtimeSafePath(snapshot.optString("url")))
                    .put("missionBound", jinhakMissionContext?.identityKey != null),
                true
            )
        }
        recordRuntimeEvent("jinhak-user-consent-required", JSONObject()
            .put("safePath", runtimeSafePath(snapshot.optString("url")))
            .put("missionBound", jinhakMissionContext?.identityKey != null))
    }

'''
main = replace_once(main, insert_before, consent_function + insert_before, 'main consent handler insertion')

main = replace_once(
    main,
    '        jinhakAgentActionInFlight = true\n        jinhakAgentActionsExecuted += 1',
    '        jinhakAgentActionInFlight = true\n        jinhakAgentActionsExecuted += 1\n        if (candidate.kind == "mission-link-navigation") jinhakMissionAnchorActionsExecuted += 1',
    'main mission anchor executed counter'
)

# Detect gate after auth check, before normalization/mission navigation.
gate_anchor = '''            batchSessionSyncRetries = 0

            if (provider == ProviderId.JINHAK) {
                jinhakMissionContext?.let { snapshot.put("missionApplicationContext", it.toJson()) }
            }
'''
gate_repl = '''            batchSessionSyncRetries = 0

            if (provider == ProviderId.JINHAK) {
                val gate = snapshot.optJSONObject("interactionGate") ?: JSONObject()
                if (gate.optBoolean("requiresUserAction", false)) {
                    pauseJinhakForConsent(snapshot)
                    return@collectSnapshot
                }
                if (jinhakConsentResumePending) {
                    jinhakConsentResumePending = false
                    jinhakConsentGatesResolved += 1
                    unifiedSessionId?.let { sessionId ->
                        localStore.recordSyncState(
                            sessionId,
                            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL.name,
                            ProviderId.JINHAK.wireName,
                            JSONObject().put("resumedAfterUserConsentGate", true),
                            false
                        )
                    }
                    recordRuntimeEvent("jinhak-user-consent-resolved", JSONObject()
                        .put("safePath", runtimeSafePath(snapshot.optString("url"))))
                }
                jinhakMissionContext?.let { snapshot.put("missionApplicationContext", it.toJson()) }
            }
'''
main = replace_once(main, gate_anchor, gate_repl, 'main consent gate check')

# Populate bootstrap/anchor/unbound diagnostics after normalization.
records_anchor = '''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) {
                jinhakConsecutiveStalls = 0
'''
records_repl = '''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) {
                jinhakConsecutiveStalls = 0
                val pageTypeNow = snapshot.optString("providerPageType")
                if (pageTypeNow == "jinhak-early-storage" && jinhakFirstPopulatedStorageAtMs == 0L) {
                    var populated = false
                    for (ri in 0 until pageRecords.length()) {
                        val r = pageRecords.optJSONObject(ri) ?: continue
                        if (r.optString("recordType") == "jinhak-saved-application-prediction" &&
                            r.optString("applicationIdentityKey").isNotBlank() && r.optString("applicationIdentityKey") != "null") {
                            populated = true
                            break
                        }
                    }
                    if (populated) jinhakFirstPopulatedStorageAtMs = System.currentTimeMillis()
                }
                val actions = snapshot.optJSONArray("agentActions") ?: JSONArray()
                for (ai in 0 until actions.length()) {
                    val a = actions.optJSONObject(ai) ?: continue
                    if (a.optString("kind") != "mission-link-navigation") continue
                    val key = RecordUtils.sha256(listOf(a.optString("label"), a.optString("contextText")).joinToString("|"))
                    jinhakMissionAnchorDiscoveredKeys.add(key)
                }
'''
main = replace_once(main, records_anchor, records_repl, 'main mission bootstrap diagnostics')

# Count unbound preserved observations in the same loop that seeds mission coverage.
main = replace_once(
    main,
    '                    if (r.optString("recordType") == "jinhak-saved-application-prediction") {\n                        jinhakMissionCoverage.getOrPut(key) { linkedSetOf() }.add("saved-application")\n                    }',
    '''                    if (r.optString("recordType") == "jinhak-saved-application-prediction") {
                        jinhakMissionCoverage.getOrPut(key) { linkedSetOf() }.add("saved-application")
                    }
                    if (r.optString("recordType") == "jinhak-application-unbound-observation") {
                        jinhakUnboundSavedApplicationObservations += 1
                    }''',
    'main unbound observation counter'
)
# Above loop currently skips rows with null key before recordType inspection; correct by adding a
# second strict unbound count just after the loop so null-key observations are counted too.
main = replace_once(
    main,
    '                }\n            }\n            var jinhakExpansionStateKey: String? = null',
    '''                }
                jinhakUnboundSavedApplicationObservations += (0 until pageRecords.length()).count { idx ->
                    pageRecords.optJSONObject(idx)?.optString("recordType") == "jinhak-application-unbound-observation"
                }
            }
            var jinhakExpansionStateKey: String? = null''',
    'main null-key unbound count'
)
# Remove the unreachable per-row increment introduced inside the key-required loop to avoid double count.
main = main.replace(
    '''                    if (r.optString("recordType") == "jinhak-application-unbound-observation") {
                        jinhakUnboundSavedApplicationObservations += 1
                    }
''',
    ''
)

# Add v0.8.3 diagnostics to unified session state.
diag_anchor = '''                        .put("applicationMissionIdentities", jinhakMissionCoverage.size)
                        .put("applicationMissionCoverage", JSONObject().apply {'''
diag_repl = '''                        .put("applicationMissionIdentities", jinhakMissionCoverage.size)
                        .put("missionBootstrapAtMs", jinhakMissionBootstrapStartedAtMs)
                        .put("secondsToFirstPopulatedStorage", if (jinhakMissionBootstrapStartedAtMs > 0L && jinhakFirstPopulatedStorageAtMs > 0L) (jinhakFirstPopulatedStorageAtMs - jinhakMissionBootstrapStartedAtMs) / 1000.0 else JSONObject.NULL)
                        .put("applicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
                        .put("applicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
                        .put("consentGatesEncountered", jinhakConsentGatesEncountered)
                        .put("consentGatesResolved", jinhakConsentGatesResolved)
                        .put("unboundSavedApplicationObservations", jinhakUnboundSavedApplicationObservations)
                        .put("applicationMissionCoverage", JSONObject().apply {'''
main = replace_once(main, diag_anchor, diag_repl, 'main unified diagnostics v083')

summary_anchor = '''                .put("jinhakApplicationMissionIdentities", jinhakMissionCoverage.size)
                .put("jinhakUniqueNavigationStates", jinhakUniqueNavigationStates)'''
summary_repl = '''                .put("jinhakApplicationMissionIdentities", jinhakMissionCoverage.size)
                .put("jinhakApplicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
                .put("jinhakApplicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
                .put("jinhakConsentGatesEncountered", jinhakConsentGatesEncountered)
                .put("jinhakConsentGatesResolved", jinhakConsentGatesResolved)
                .put("jinhakUnboundSavedApplicationObservations", jinhakUnboundSavedApplicationObservations)
                .put("jinhakSecondsToFirstPopulatedStorage", if (jinhakMissionBootstrapStartedAtMs > 0L && jinhakFirstPopulatedStorageAtMs > 0L) (jinhakFirstPopulatedStorageAtMs - jinhakMissionBootstrapStartedAtMs) / 1000.0 else JSONObject.NULL)
                .put("jinhakUniqueNavigationStates", jinhakUniqueNavigationStates)'''
main = replace_once(main, summary_anchor, summary_repl, 'main batch summary v083')
MAIN.write_text(main)

# ---------------------------------------------------------------------------
# Static postconditions before CI even starts the Android compiler.
# ---------------------------------------------------------------------------
checks = {
    'main v0.8.3': 'private const val VERSION = "0.8.3"' in MAIN.read_text(),
    'mission anchor action': 'mission-link-navigation' in SNAP.read_text(),
    'generic mission nav suppressed': 'if(missionLinkBound) continue;' in SNAP.read_text(),
    'consent gate': 'jinhak-ai-diagnosis-consent' in SNAP.read_text(),
    'consent state': 'JINHAK_USER_CONSENT_REQUIRED' in SYNC.read_text(),
    'unbound observation': 'jinhak-application-unbound-observation' in ADAPTER.read_text(),
    'ui normalization': 'stripCardUiPrefix' in MISSION.read_text(),
    'semantic split preserved': 'previousYearCompetition' in MISSION.read_text() and 'mockCompetition' in MISSION.read_text(),
}
failed = [k for k, v in checks.items() if not v]
if failed:
    raise SystemExit('v0.8.3 postconditions failed: ' + ', '.join(failed))
print('v0.8.3 mission-first source transformation complete')
