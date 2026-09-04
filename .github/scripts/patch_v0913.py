from pathlib import Path

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
navigator_path = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt')
ledger_path = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionTargetLedger.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
n = navigator_path.read_text()
l = ledger_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

# -----------------------------------------------------------------------------
# v0.9.13 — Same-Card Mission Replay Recovery
# Real-device v0.9.12 proved the bootstrap and persisted ledger now work, but
# 28/30 saved-application current-prediction targets terminated immediately as
# same-card-action-not-found. This patch is deliberately bounded to replaying
# those already-proven same-card read-only targets. It does not add sibling,
# nearest-card, page-wide, cross-card or state-changing navigation.
# -----------------------------------------------------------------------------

# 1) Persist a retryable miss without terminalizing the monotonic target state.
ledger_anchor = '''    fun markFailed(targetId: String?, reason: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
'''
ledger_insert = '''    fun markRetryableFailure(targetId: String?, reason: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        if (target.state != State.PENDING) return false
        target.failureReason = reason.take(100)
        target.updatedAtMs = System.currentTimeMillis()
        notifyMutation(target)
        return true
    }

    fun markFailed(targetId: String?, reason: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
'''
if ledger_anchor not in l:
    raise SystemExit('ledger retry anchor not found')
l = l.replace(ledger_anchor, ledger_insert, 1)

# 2) Replace the execution resolver. The fallback still requires the exact action
# label, but card ownership is reproved using normalized university+department plus
# a local capacity marker (or admission when capacity is unavailable). A candidate
# ancestor spanning more than one card metric or more than one matching action is
# rejected rather than guessed.
start = n.find('    fun executionScript(candidate: Candidate): String {')
end = n.find('    private fun isSafeReadNavigationLabel', start)
if start < 0 or end < 0:
    raise SystemExit('navigator executionScript boundaries not found')
new_execution = r'''    fun executionScript(candidate: Candidate): String {
        val expected = JSONObject.quote(candidate.label)
        val university = JSONObject.quote(candidate.applicationContext?.university.orEmpty().take(80))
        val department = JSONObject.quote(candidate.applicationContext?.departmentRaw.orEmpty().take(120))
        val admission = JSONObject.quote(candidate.applicationContext?.admission.orEmpty().take(100))
        val capacity = candidate.applicationContext?.capacity ?: -1
        val requiresSameCard = candidate.applicationContext?.identityKey != null
        return """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0&&r.height>0;
              }
              function clean(v){return String(v||'').replace(/\s+/g,' ').trim();}
              function norm(v){
                return clean(v).toLowerCase().replace(/[\s\[\](){}·._\-\/:|]/g,'');
              }
              function containsToken(text,token){
                var nt=norm(token);
                return !nt || norm(text).indexOf(nt)>=0;
              }
              var expected=$expected, uni=$university, dept=$department, adm=$admission, capacity=$capacity;
              var requireSameCard=${if (requiresSameCard) "true" else "false"};
              var blocked=/(원서\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)/i;
              var allowed=/(실제\s*합격자|과거\s*입시결과|입시\s*결과|합격\s*예측\s*리포트|모의\s*지원\s*리포트|지원자\s*분포|대학.?학과별\s*합격\s*예측|합격\s*안정성|상세|보기|조회|검색|리포트|대학\s*정보|전형\s*정보|학과\s*정보|합격\s*예측|모의\s*지원|수시\s*저장소|정시\s*저장소|추천\s*대학|성적\s*분석|성적\s*산출|입시\s*전략|입시\s*지식|경쟁률|모집\s*요강|다음|더보기|결과|탭)/i;
              var selector='a,button,[role=button],[role=tab],[onclick],[data-href],[data-url],[data-link],[data-path]';
              var nodes=document.querySelectorAll(selector);
              function labelOf(el){return clean(el&& (el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title')||'')).slice(0,120);}
              function matchingActionCount(scope){
                if(!scope||!scope.querySelectorAll) return 0;
                var all=scope.querySelectorAll(selector), count=0;
                for(var i=0;i<all.length;i++){
                  if(visible(all[i])&&labelOf(all[i])===expected) count++;
                  if(count>1) break;
                }
                return count;
              }
              function cardProof(el){
                if(!requireSameCard) return {ok:true,depth:0,reason:'not-required'};
                var cur=el;
                for(var d=0;cur&&d<10;d++,cur=cur.parentElement){
                  var tag=String(cur.tagName||'').toUpperCase();
                  if(tag==='BODY'||tag==='HTML') break;
                  var t=clean(cur.innerText||cur.textContent||'').slice(0,9000);
                  if(!t||t.length>8500) continue;
                  if(!containsToken(t,uni)||!containsToken(t,dept)) continue;
                  var metricCount=(t.match(/[0-9,]+\s*명\s*(?:\||\s)*내\s*점수/ig)||[]).length;
                  if(metricCount>1) continue;
                  var capacityOk=false;
                  if(capacity>=0){
                    var capRx=new RegExp('(?:^|[^0-9])'+capacity+'\\s*명\\s*(?:\\||\\s)*내\\s*점수','i');
                    capacityOk=capRx.test(t)&&metricCount===1;
                  }
                  var admissionOk=!!adm&&containsToken(t,adm);
                  if(capacity>=0 ? !capacityOk : !admissionOk) continue;
                  if(matchingActionCount(cur)!==1) continue;
                  return {ok:true,depth:d,reason:capacity>=0?'unique-card-capacity':'unique-card-admission'};
                }
                return {ok:false,depth:-1,reason:'bounded-card-proof-missing'};
              }
              function tryClick(el,resolution){
                if(!el) return null;
                if(!visible(el)) return {ok:false,reason:'hidden',resolution:resolution};
                var lab=labelOf(el);
                if(lab!==expected) return {ok:false,reason:'label-changed',resolution:resolution,observedLabel:lab};
                if(blocked.test(lab)||!allowed.test(lab)) return {ok:false,reason:'policy-block',resolution:resolution};
                var proof=cardProof(el);
                if(!proof.ok) return {ok:false,reason:'same-card-context-mismatch',resolution:resolution,proofReason:proof.reason};
                try{
                  var before=location.href;
                  el.click();
                  return {ok:true,label:lab,before:before===location.href?'same-document':'navigation-started',resolution:resolution,matchedSameCard:requireSameCard,contextDepth:proof.depth,proofReason:proof.reason};
                }catch(e){return {ok:false,reason:'click-failed',resolution:resolution};}
              }
              var primary=tryClick(nodes[${candidate.scanIndex}], 'scan-index');
              if(primary&&primary.ok) return JSON.stringify(primary);

              // SPA order may change after the snapshot. Re-resolve only the exact same label and
              // accept it only when bounded card ownership is independently reproved.
              var fallbackReasons=[];
              var sameLabelSeen=0;
              for(var i=0;i<nodes.length;i++){
                var el=nodes[i];
                if(labelOf(el)!==expected) continue;
                sameLabelSeen++;
                var result=tryClick(el,'bounded-context-fallback');
                if(result&&result.ok) return JSON.stringify(result);
                if(result&&result.reason) fallbackReasons.push(result.reason+':'+String(result.proofReason||''));
              }
              return JSON.stringify({
                ok:false,
                reason:requireSameCard?'same-card-action-not-found':'action-not-found',
                primaryReason:primary&&primary.reason?primary.reason:'missing',
                sameLabelSeen:sameLabelSeen,
                fallbackReasons:fallbackReasons.slice(0,12)
              });
            })();
        """.trimIndent()
    }

'''
n = n[:start] + new_execution + n[end:]

# 3) Runtime replay counters and bounded attempt cap.
field_anchor = '    private var jinhakBootstrapFatalNoSuccess = 0\n'
field_new = field_anchor + '''    private var jinhakSameCardReplayRetries = 0
    private var jinhakSameCardReplayRecovered = 0
    private var jinhakSameCardReplayTerminalFailures = 0
    private val jinhakSameCardReplayResolutionCounts = linkedMapOf<String, Int>()
'''
if field_anchor not in m:
    raise SystemExit('MainActivity replay field anchor not found')
m = m.replace(field_anchor, field_new, 1)

const_anchor = '        private const val MAX_JINHAK_BOOTSTRAP_PAGE_RETRIES = 2\n'
const_new = const_anchor + '        private const val MAX_JINHAK_SAME_CARD_REPLAY_ATTEMPTS = 3\n'
if const_anchor not in m:
    raise SystemExit('MainActivity replay const anchor not found')
m = m.replace(const_anchor, const_new, 1)

reset_anchor = '''        jinhakBootstrapRetryAttempts = 0
        jinhakBootstrapFatalNoSuccess = 0
'''
reset_new = reset_anchor + '''        jinhakSameCardReplayRetries = 0
        jinhakSameCardReplayRecovered = 0
        jinhakSameCardReplayTerminalFailures = 0
        jinhakSameCardReplayResolutionCounts.clear()
'''
if reset_anchor not in m:
    raise SystemExit('MainActivity replay reset anchor not found')
m = m.replace(reset_anchor, reset_new, 1)

# 4) First/second same-card misses remain PENDING and are retried from a fresh
# snapshot. The third miss becomes terminal. Every other rejection keeps the old
# one-shot behavior.
old_reject = '''                if (ledgerTargetIdForAction != null) {
                    jinhakMissionTargetLedger.markFailed(ledgerTargetIdForAction, rejectReason)
                    if (jinhakActiveMissionTargetId == ledgerTargetIdForAction) jinhakActiveMissionTargetId = null
                }
                recordRuntimeEvent("jinhak-agent-action-rejected", JSONObject()
'''
new_reject = '''                if (ledgerTargetIdForAction != null) {
                    val targetAttempts = jinhakMissionTargetLedger.target(ledgerTargetIdForAction)?.attempts ?: 0
                    val retryableSameCardMiss = rejectReason == "same-card-action-not-found" &&
                        targetAttempts < MAX_JINHAK_SAME_CARD_REPLAY_ATTEMPTS
                    if (retryableSameCardMiss) {
                        jinhakMissionTargetLedger.markRetryableFailure(ledgerTargetIdForAction, rejectReason)
                        jinhakSameCardReplayRetries += 1
                        recordRuntimeEvent("jinhak-same-card-replay-scheduled", JSONObject()
                            .put("attempt", targetAttempts)
                            .put("maxAttempts", MAX_JINHAK_SAME_CARD_REPLAY_ATTEMPTS)
                            .put("safePath", runtimeSafePath(route)))
                    } else {
                        jinhakMissionTargetLedger.markFailed(ledgerTargetIdForAction, rejectReason)
                        if (rejectReason == "same-card-action-not-found") jinhakSameCardReplayTerminalFailures += 1
                    }
                    if (jinhakActiveMissionTargetId == ledgerTargetIdForAction) jinhakActiveMissionTargetId = null
                    // Execution failure never navigated away from the origin.
                    jinhakMissionNeedsReturn = false
                }
                recordRuntimeEvent("jinhak-agent-action-rejected", JSONObject()
'''
if old_reject not in m:
    raise SystemExit('MainActivity rejection anchor not found')
m = m.replace(old_reject, new_reject, 1)

# Count successful replay resolutions without changing old anchor-counter semantics.
old_success = '''            if (result.optBoolean("ok", false)) {
                if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markClicked(ledgerTargetIdForAction)
                noteJinhakMeaningfulProgress("agent-click", forceDiagnostics = true)
'''
new_success = '''            if (result.optBoolean("ok", false)) {
                if (ledgerTargetIdForAction != null) {
                    val targetAttempts = jinhakMissionTargetLedger.target(ledgerTargetIdForAction)?.attempts ?: 0
                    if (targetAttempts > 1) jinhakSameCardReplayRecovered += 1
                    val resolution = result.optString("resolution", "unknown").ifBlank { "unknown" }.take(60)
                    jinhakSameCardReplayResolutionCounts[resolution] = (jinhakSameCardReplayResolutionCounts[resolution] ?: 0) + 1
                    jinhakMissionTargetLedger.markClicked(ledgerTargetIdForAction)
                }
                noteJinhakMeaningfulProgress("agent-click", forceDiagnostics = true)
'''
if old_success not in m:
    raise SystemExit('MainActivity success anchor not found')
m = m.replace(old_success, new_success, 1)

# 5) Export replay diagnostics in live/final unified summaries.
diag_anchor = '                        .put("applicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))\n'
diag_new = diag_anchor + '''                        .put("sameCardReplayRetries", jinhakSameCardReplayRetries)
                        .put("sameCardReplayRecovered", jinhakSameCardReplayRecovered)
                        .put("sameCardReplayTerminalFailures", jinhakSameCardReplayTerminalFailures)
                        .put("sameCardReplayResolutionCounts", JSONObject(jinhakSameCardReplayResolutionCounts as Map<*, *>))
'''
count = m.count(diag_anchor)
if count < 1:
    raise SystemExit('MainActivity unified diagnostics anchor not found')
m = m.replace(diag_anchor, diag_new)

batch_diag_anchor = '                .put("jinhakApplicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))\n'
batch_diag_new = batch_diag_anchor + '''                .put("jinhakSameCardReplayRetries", jinhakSameCardReplayRetries)
                .put("jinhakSameCardReplayRecovered", jinhakSameCardReplayRecovered)
                .put("jinhakSameCardReplayTerminalFailures", jinhakSameCardReplayTerminalFailures)
                .put("jinhakSameCardReplayResolutionCounts", JSONObject(jinhakSameCardReplayResolutionCounts as Map<*, *>))
'''
if batch_diag_anchor not in m:
    raise SystemExit('MainActivity batch diagnostics anchor not found')
m = m.replace(batch_diag_anchor, batch_diag_new)

# 6) Version metadata.
for old, new in [
    ('private const val VERSION = "0.9.12"', 'private const val VERSION = "0.9.13"'),
    ('private const val BUILD_CODE = 109120', 'private const val BUILD_CODE = 109130'),
]:
    if old not in m:
        raise SystemExit(f'MainActivity version anchor not found: {old}')
    m = m.replace(old, new, 1)

for old, new in [
    ('versionCode = 109120', 'versionCode = 109130'),
    ('versionName = "0.9.12"', 'versionName = "0.9.13"'),
]:
    if old not in g:
        raise SystemExit(f'Gradle version anchor not found: {old}')
    g = g.replace(old, new, 1)

old_label = 'Admission Collector v0.9.12 Jinhak Bootstrap Recovery'
new_label = 'Admission Collector v0.9.13 Same-Card Mission Replay Recovery'
if old_label not in manifest:
    raise SystemExit('Manifest label anchor not found')
manifest = manifest.replace(old_label, new_label, 1)

main_path.write_text(m)
navigator_path.write_text(n)
ledger_path.write_text(l)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('v0.9.13 patch applied')
