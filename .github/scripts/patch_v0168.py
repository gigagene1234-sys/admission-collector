from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


def replace_function(text: str, signature_prefix: str, replacement: str, label: str) -> str:
    start = text.find(signature_prefix)
    if start < 0:
        raise SystemExit(f"{label}: signature not found: {signature_prefix}")
    brace = text.find('{', start)
    if brace < 0:
        raise SystemExit(f"{label}: opening brace not found")
    depth = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    triple = False
    i = brace
    while i < len(text):
        ch = text[i]
        nxt = text[i:i+2]
        tri = text[i:i+3]
        if in_line_comment:
            if ch == '\n': in_line_comment = False
            i += 1; continue
        if in_block_comment:
            if nxt == '*/': in_block_comment = False; i += 2; continue
            i += 1; continue
        if triple:
            if tri == '"""': triple = False; i += 3; continue
            i += 1; continue
        if in_string:
            if ch == '\\': i += 2; continue
            if ch == '"': in_string = False
            i += 1; continue
        if in_char:
            if ch == '\\': i += 2; continue
            if ch == "'": in_char = False
            i += 1; continue
        if nxt == '//': in_line_comment = True; i += 2; continue
        if nxt == '/*': in_block_comment = True; i += 2; continue
        if tri == '"""': triple = True; i += 3; continue
        if ch == '"': in_string = True; i += 1; continue
        if ch == "'": in_char = True; i += 1; continue
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                return text[:start] + replacement.rstrip() + text[end:]
        i += 1
    raise SystemExit(f"{label}: function end not found")


text = MAIN.read_text()

text = replace_once(
    text,
    "import com.admissionhub.collector.jinhak.JinhakHigh3AuthRoute",
    "import com.admissionhub.collector.jinhak.JinhakHigh3AuthRoute\nimport com.admissionhub.collector.jinhak.JinhakAuthEventState",
    "event state import",
)

text = replace_once(
    text,
    "    private var jinhakV0167AuthReturnTarget = \"\"\n    private var jinhakPostMissionClosureFences = 0",
    "    private var jinhakV0167AuthReturnTarget = \"\"\n"
    "    private var jinhakV0168AuthEventsObserved = 0\n"
    "    private var jinhakV0168PassiveMemberWaits = 0\n"
    "    private var jinhakV0168High3Verifications = 0\n"
    "    private var jinhakV0168OtherRouteObservations = 0\n"
    "    private var jinhakV0168LegacyNavigationSuppressions = 0\n"
    "    private var jinhakPostMissionClosureFences = 0",
    "v0168 counters",
)

# Never run session-extension DOM clicking while the identity-provider login page is waiting for the user.
text = replace_once(
    text,
    "                attemptSessionExtension()\n                if (provider == ProviderId.JINHAK) {",
    "                if (!(provider == ProviderId.JINHAK && jinhakV0167AuthWaitActive)) attemptSessionExtension()\n                if (provider == ProviderId.JINHAK) {",
    "keepalive passive auth wait",
)

# The Continue button becomes event-driven: it never hides the WebView or forces protected-core navigation.
text = replace_function(
    text,
    "    private fun resumeAfterLogin()",
    '''    private fun resumeAfterLogin() {
        if (provider != ProviderId.JINHAK) {
            checkSessionState { needsLogin, authenticated ->
                if (authenticated && !needsLogin && batchRunning && batchPausedForLogin) {
                    batchPausedForLogin = false
                    loadNextBatchPage()
                }
            }
            return
        }
        val current = webView.url.orEmpty()
        jinhakV0168AuthEventsObserved += 1
        when (JinhakAuthEventState.action(current)) {
            JinhakAuthEventState.Action.DROP_REQUEST -> hardBlockJinhakLowerGradeNavigation("resume-button", current)
            JinhakAuthEventState.Action.OPEN_CANONICAL_HIGH3_AUTH_ONCE -> {
                jinhakV0168LegacyNavigationSuppressions += 1
                openJinhakDirectHigh3Auth("resume-button-generic-login", currentBatchTarget)
            }
            JinhakAuthEventState.Action.WAIT_FOR_SERVER_RETURN -> {
                jinhakV0168PassiveMemberWaits += 1
                markJinhakDirectAuthWait("resume-button-member-wait", current)
                status.text = "회원 로그인 화면에서는 이동을 강제하지 않습니다. 사이트 로그인 완료 후 서버의 high3 ReturnURL 복귀를 기다립니다."
            }
            JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION -> {
                jinhakV0168High3Verifications += 1
                verifyRecoveredJinhakHigh3AndResume(current)
            }
            JinhakAuthEventState.Action.OBSERVE_WITHOUT_NAVIGATION -> {
                jinhakV0168OtherRouteObservations += 1
                status.text = "진학사 페이지를 관측 중입니다. Collector는 인증 경로를 강제로 이동하지 않습니다."
                persistJinhakAuthDiagnostics("v0168-resume-observe-only")
            }
        }
    }''',
    "resumeAfterLogin",
)

# Collector-owned Jinhak credential UI is disabled. Jinhak uses the site/member login surface only.
needle = "    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {\n        if (credentialAutoLoginInFlight) return"
replacement = '''    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {
        if (which == ProviderId.JINHAK) {
            startupCredentialPromptedProvider = ProviderId.JINHAK
            jinhakV0168LegacyNavigationSuppressions += 1
            val current = webView.url.orEmpty()
            if (JinhakHigh3AuthRoute.isMemberLoginSurface(current)) {
                markJinhakDirectAuthWait("collector-credential-dialog-suppressed", current)
            } else {
                openJinhakDirectHigh3Auth("collector-credential-dialog-suppressed", currentBatchTarget)
            }
            status.text = "진학사는 Collector 계정 입력창을 사용하지 않습니다. 사이트 자체 로그인/Samsung Pass/자동완성을 사용하세요."
            return
        }
        if (credentialAutoLoginInFlight) return'''
text = replace_once(text, needle, replacement, "suppress Jinhak credential dialog")

# Saved credentials may fill/submit the member login once, but must not verify via timers or force high3 load.
text = replace_function(
    text,
    "    private fun attemptSavedCredentialLoginV0912Baseline(reason: String)",
    '''    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val current = webView.url.orEmpty()
        if (!JinhakHigh3AuthRoute.isMemberLoginSurface(current)) {
            if (JinhakHigh3AuthRoute.isGenericProductLogin(current)) {
                openJinhakDirectHigh3Auth("saved-credential-generic-rewrite:$reason", currentBatchTarget)
            }
            return
        }
        val credential = credentialVault.load(ProviderId.JINHAK.wireName)
        if (credential == null) {
            credentialAutoLoginSuppressedNoCredential += 1
            jinhakV0165ManualLoginWaits += 1
            jinhakV0168PassiveMemberWaits += 1
            markJinhakDirectAuthWait("no-local-credential:$reason", current)
            status.text = "진학사 회원 로그인 화면입니다. 기기 자동완성/Samsung Pass로 로그인하세요. Collector는 경로를 재시도하지 않습니다."
            return
        }
        val now = System.currentTimeMillis()
        if (credentialAutoLoginInFlight || now - credentialAutoLoginLastAttemptAtMs < 1500L) return
        credentialAutoLoginInFlight = true
        credentialAutoLoginLastAttemptAtMs = now
        credentialAutoLoginAttempts += 1
        credentialAutoLoginLastProvider = ProviderId.JINHAK.wireName
        credentialAutoLoginLastAtMs = now
        val userJson = JSONObject.quote(credential.username)
        val passJson = JSONObject.quote(credential.password)
        val js = """
            (function(){
              try{
                function visible(el){if(!el)return false;var s=getComputedStyle(el);if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0')return false;var r=el.getBoundingClientRect();return r.width>0&&r.height>0;}
                function setValue(el,v){try{var d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');if(d&&d.set)d.set.call(el,v);else el.value=v;}catch(e){el.value=v;}try{el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}}
                var pass=Array.from(document.querySelectorAll('input[type=password]')).find(visible); if(!pass)return JSON.stringify({submitted:false,reason:'password-missing'});
                var form=pass.form||pass.closest('form')||document;
                var users=Array.from(form.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);
                if(!users.length)return JSON.stringify({submitted:false,reason:'username-missing'});
                var user=users[0]; setValue(user,$userJson); setValue(pass,$passJson);
                var submit=Array.from(form.querySelectorAll('button,input[type=submit],[role=button]')).filter(visible).find(function(el){var t=((el.innerText||el.value||el.textContent||'')+'').replace(/\\s+/g,' ').trim();return /^(로그인|로그인하기|log\\s*in|sign\\s*in)$/i.test(t);});
                if(submit){submit.click();return JSON.stringify({submitted:true,method:'button'});}
                if(pass.form){if(pass.form.requestSubmit)pass.form.requestSubmit();else pass.form.submit();return JSON.stringify({submitted:true,method:'form'});}
                return JSON.stringify({submitted:false,reason:'submit-missing'});
              }catch(e){return JSON.stringify({submitted:false,reason:'script-error'});}
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { raw ->
            credentialAutoLoginInFlight = false
            val decoded = runCatching { JSONTokener(raw).nextValue() as? String }.getOrNull().orEmpty()
            val result = runCatching { JSONObject(decoded) }.getOrDefault(JSONObject())
            if (result.optBoolean("submitted", false)) {
                credentialAutoLoginSubmissions += 1
                jinhakV0912PassiveLoginSubmissions += 1
                credentialAwaitingLoginExitProvider = ProviderId.JINHAK
                credentialAutoLoginLastResult = "v0168-submitted-${result.optString("method", "unknown")}"
                jinhakV0168PassiveMemberWaits += 1
                markJinhakDirectAuthWait("saved-credential-submitted:$reason", webView.url.orEmpty())
                status.text = "진학사 로그인 제출 완료 · 추가 탐색 없이 서버의 high3 ReturnURL 복귀를 기다립니다."
            } else {
                credentialAutoLoginFailures += 1
                credentialAutoLoginLastResult = "v0168-not-submitted-${result.optString("reason", "unknown")}"
                status.text = "자동입력을 완료하지 못했습니다. 현재 사이트 로그인 화면에서 직접 로그인하세요. Collector는 재탐색하지 않습니다."
            }
            persistJinhakAuthDiagnostics("credential-auto-login-v0168-event-driven")
        }
    }''',
    "saved credential event driven",
)

# Startup Jinhak checks enter the protected high3 route directly, never the generic product home/login selector.
text = replace_once(
    text,
    "        webView.loadUrl(which.homeUrl)\n    }\n\n    private fun handleStartupLoginPreflightPageFinished",
    '''        if (which == ProviderId.JINHAK) {
            val core = JinhakGradeRouteFence.protectedHigh3Core()
            if (core.isNotBlank()) webView.loadUrl(core) else openJinhakDirectHigh3Auth("startup-no-core", null)
        } else {
            webView.loadUrl(which.homeUrl)
        }
    }

    private fun handleStartupLoginPreflightPageFinished''',
    "startup direct high3 entry",
)

# Jinhak startup authentication is page-event driven. ADIGA keeps the existing polling implementation.
old_eval_start = "    private fun evaluateStartupLoginState(expectedProvider: ProviderId, generation: Int)"
start = text.find(old_eval_start)
if start < 0: raise SystemExit("evaluateStartupLoginState missing")
# Extract original function to reuse for ADIGA by renaming it.
brace = text.find('{', start)
depth=0; i=brace; in_s=False; in_c=False; line=False; block=False; triple=False
while i < len(text):
    ch=text[i]; nxt=text[i:i+2]; tri=text[i:i+3]
    if line:
        if ch=='\n': line=False
        i+=1; continue
    if block:
        if nxt=='*/': block=False; i+=2; continue
        i+=1; continue
    if triple:
        if tri=='"""': triple=False; i+=3; continue
        i+=1; continue
    if in_s:
        if ch=='\\': i+=2; continue
        if ch=='"': in_s=False
        i+=1; continue
    if in_c:
        if ch=='\\': i+=2; continue
        if ch=="'": in_c=False
        i+=1; continue
    if nxt=='//': line=True; i+=2; continue
    if nxt=='/*': block=True; i+=2; continue
    if tri=='"""': triple=True; i+=3; continue
    if ch=='"': in_s=True; i+=1; continue
    if ch=="'": in_c=True; i+=1; continue
    if ch=='{': depth+=1
    elif ch=='}':
        depth-=1
        if depth==0:
            original_eval=text[start:i+1]
            break
    i+=1
else: raise SystemExit("evaluateStartupLoginState end missing")
legacy_eval = original_eval.replace("private fun evaluateStartupLoginState", "private fun evaluateStartupLoginStateLegacyAdiga", 1)
new_eval = '''    private fun evaluateStartupLoginState(expectedProvider: ProviderId, generation: Int) {
        if (expectedProvider != ProviderId.JINHAK) {
            evaluateStartupLoginStateLegacyAdiga(expectedProvider, generation)
            return
        }
        if (!startupLoginPreflightActive || provider != ProviderId.JINHAK || generation != startupLoginPollGeneration) return
        val current = webView.url.orEmpty()
        jinhakV0168AuthEventsObserved += 1
        when (JinhakAuthEventState.action(current)) {
            JinhakAuthEventState.Action.DROP_REQUEST -> hardBlockJinhakLowerGradeNavigation("startup-event", current)
            JinhakAuthEventState.Action.OPEN_CANONICAL_HIGH3_AUTH_ONCE -> openJinhakDirectHigh3Auth("startup-generic-rewrite", currentBatchTarget)
            JinhakAuthEventState.Action.WAIT_FOR_SERVER_RETURN -> {
                jinhakV0168PassiveMemberWaits += 1
                markJinhakDirectAuthWait("startup-member-wait", current)
            }
            JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION -> {
                jinhakV0168High3Verifications += 1
                verifyRecoveredJinhakHigh3AndResume(current)
            }
            JinhakAuthEventState.Action.OBSERVE_WITHOUT_NAVIGATION -> {
                jinhakV0168OtherRouteObservations += 1
                persistJinhakAuthDiagnostics("v0168-startup-observe-other")
            }
        }
    }

''' + legacy_eval
text = text[:start] + new_eval + text[start+len(original_eval):]

# Startup poll is prohibited for Jinhak; it remains available only for Adiga.
text = replace_function(
    text,
    "    private fun scheduleStartupLoginPoll(expectedProvider: ProviderId, generation: Int)",
    '''    private fun scheduleStartupLoginPoll(expectedProvider: ProviderId, generation: Int) {
        if (expectedProvider == ProviderId.JINHAK) {
            jinhakV0168LegacyNavigationSuppressions += 1
            persistJinhakAuthDiagnostics("v0168-startup-poll-suppressed")
            return
        }
        handler.postDelayed({
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@postDelayed
            evaluateStartupLoginState(expectedProvider, generation)
        }, LOGIN_PREFLIGHT_POLL_MS)
    }''',
    "startup poll Jinhak suppression",
)

# Transition auth gate acts only on the page event that just arrived.
text = replace_function(
    text,
    "    private fun handleJinhakTransitionAuthGate(url: String)",
    '''    private fun handleJinhakTransitionAuthGate(url: String) {
        if (!unifiedRunning || unifiedPhase != "jinhak" || provider != ProviderId.JINHAK || !jinhakTransitionAuthGateActive || batchRunning) return
        runtimeLastSafePath = runtimeSafePath(url)
        jinhakV0168AuthEventsObserved += 1
        when (JinhakAuthEventState.action(url)) {
            JinhakAuthEventState.Action.DROP_REQUEST -> hardBlockJinhakLowerGradeNavigation("transition-event", url)
            JinhakAuthEventState.Action.OPEN_CANONICAL_HIGH3_AUTH_ONCE -> openJinhakDirectHigh3Auth("transition-generic-rewrite", currentBatchTarget)
            JinhakAuthEventState.Action.WAIT_FOR_SERVER_RETURN -> {
                jinhakV0168PassiveMemberWaits += 1
                markJinhakDirectAuthWait("transition-member-wait", url)
            }
            JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION -> {
                jinhakV0168High3Verifications += 1
                verifyRecoveredJinhakHigh3AndResume(url)
            }
            JinhakAuthEventState.Action.OBSERVE_WITHOUT_NAVIGATION -> {
                jinhakV0168OtherRouteObservations += 1
                persistJinhakAuthDiagnostics("v0168-transition-observe-other")
            }
        }
    }''',
    "transition gate event driven",
)

# Real-auth diagnostic is also event-driven. It gets one protected-high3 navigation and then reacts to page events.
text = replace_function(
    text,
    "    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String)",
    '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        if (jinhakRealAuthProbeActive) return
        if (batchRunning) {
            Toast.makeText(this, "진행 중인 진학사 수집이 있어 인증 진단을 시작할 수 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        val core = JinhakGradeRouteFence.protectedHigh3Core()
        if (core.isBlank()) {
            status.text = "진학사 high3 보호경로가 정의되지 않았습니다."
            return
        }
        provider = ProviderId.JINHAK
        jinhakRealAuthProbeActive = true
        jinhakRealAuthProbeAutoContinue = autoContinue
        ++jinhakRealAuthProbeGeneration
        jinhakRealAuthProbeStartedAtMs = System.currentTimeMillis()
        jinhakRealAuthProbeStablePasses = 0
        jinhakRealAuthProbeCoreLoads = 1
        jinhakRealAuthProbeLoginRoutes = 0
        jinhakRealAuthProbeUnexpectedRoutes = 0
        jinhakRealAuthProbeCycleDetections = 0
        jinhakRealAuthProbeResult = "running-event-driven"
        jinhakRealAuthProbeRouteCycleDetected = false
        jinhakRealAuthProbeRouteHistory.clear()
        jinhakRealAuthProbeRouteCounts.clear()
        jinhakRealAuthProbeRouteEvents = JSONArray()
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "v0168-real-auth-event-probe"
        jinhakLastAuthEvidence = "real-auth-event-pending"
        sessionState.text = "△ 진학사 high3 인증 이벤트 확인"
        status.text = "high3 보호경로를 한 번 확인합니다. 로그인으로 이동하면 서버 ReturnURL 복귀를 수동으로 기다립니다."
        recordRuntimeEvent("jinhak-v0168-real-auth-start", JSONObject().put("trigger", trigger.take(80)).put("polling", false).put("uiMaskUsed", false))
        webView.loadUrl(core)
    }''',
    "real auth start",
)

# No timer-based real-auth polling remains.
text = replace_function(
    text,
    "    private fun scheduleJinhakRealAuthProbePoll(generation: Int",
    '''    private fun scheduleJinhakRealAuthProbePoll(generation: Int, delayMs: Long = 0L) {
        if (jinhakRealAuthProbeActive && generation == jinhakRealAuthProbeGeneration) {
            jinhakV0168LegacyNavigationSuppressions += 1
            persistJinhakAuthDiagnostics("v0168-real-auth-poll-suppressed")
        }
    }''',
    "real auth poll suppression",
)

text = replace_function(
    text,
    "    private fun handleJinhakRealAuthProbePageFinished(url: String)",
    '''    private fun handleJinhakRealAuthProbePageFinished(url: String) {
        if (!jinhakRealAuthProbeActive || provider != ProviderId.JINHAK) return
        jinhakV0168AuthEventsObserved += 1
        noteJinhakRealAuthProbeRoute(url, "v0168-page-finished")
        when (JinhakAuthEventState.action(url)) {
            JinhakAuthEventState.Action.DROP_REQUEST -> hardBlockJinhakLowerGradeNavigation("real-auth-event", url)
            JinhakAuthEventState.Action.OPEN_CANONICAL_HIGH3_AUTH_ONCE -> openJinhakDirectHigh3Auth("real-auth-generic-rewrite", currentBatchTarget)
            JinhakAuthEventState.Action.WAIT_FOR_SERVER_RETURN -> {
                jinhakV0168PassiveMemberWaits += 1
                markJinhakDirectAuthWait("real-auth-member-wait", url)
                status.text = "회원 로그인 완료 후 서버가 high3 ReturnURL로 복귀할 때까지 대기합니다. 인증 polling은 실행하지 않습니다."
            }
            JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION -> {
                jinhakV0168High3Verifications += 1
                checkSessionState { needsLogin, authenticated ->
                    if (!jinhakRealAuthProbeActive || provider != ProviderId.JINHAK || webView.url.orEmpty() != url) return@checkSessionState
                    if (authenticated && !needsLogin) finishJinhakRealAuthProbe("protected-core-stable-v0168", success = true)
                    else openJinhakDirectHigh3Auth("real-auth-high3-needs-login", url)
                }
            }
            JinhakAuthEventState.Action.OBSERVE_WITHOUT_NAVIGATION -> {
                jinhakV0168OtherRouteObservations += 1
                status.text = "진학사 인증 중간 페이지를 관측했습니다. 강제 이동 없이 다음 사이트 navigation event를 기다립니다."
                persistJinhakAuthDiagnostics("v0168-real-auth-observe-other")
            }
        }
    }''',
    "real auth page event",
)

# Old manual lower-grade gate, if stale runtime state somehow restores it, may not hide or navigate.
old_manual = '''        if (provider == ProviderId.JINHAK && jinhakLowerGradeManualGateActive) {
            val high3Core = JinhakGradeRouteFence.protectedHigh3Core()'''
if old_manual in text:
    start = text.find(old_manual)
    # Replace only the if-block by scanning braces.
    if_start = start
    brace = text.find('{', start)
    depth = 0; i = brace
    while i < len(text):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                block = text[if_start:end]
                repl = '''        if (provider == ProviderId.JINHAK && jinhakLowerGradeManualGateActive) {
            jinhakLowerGradeManualGateActive = false
            jinhakLowerGradeLoginFenceLatched = false
            jinhakLowerGradeRecoveryInFlight = false
            jinhakV0168LegacyNavigationSuppressions += 1
            val current = webView.url.orEmpty()
            if (JinhakGradeRouteFence.isBlockedLowerGrade(current)) hardBlockJinhakLowerGradeNavigation("legacy-manual-gate-suppressed", current)
            else if (JinhakHigh3AuthRoute.isMemberLoginSurface(current)) markJinhakDirectAuthWait("legacy-manual-gate-member-wait", current)
            else persistJinhakAuthDiagnostics("v0168-legacy-manual-gate-suppressed")
            return
        }'''
                text = text[:if_start] + repl + text[end:]
                break
        i += 1

# Reset and export the v0.16.8 non-secret counters.
text = replace_once(
    text,
    "        jinhakV0167AuthReturnTarget = \"\"\n        // Restore both domain leases",
    "        jinhakV0167AuthReturnTarget = \"\"\n"
    "        jinhakV0168AuthEventsObserved = 0\n"
    "        jinhakV0168PassiveMemberWaits = 0\n"
    "        jinhakV0168High3Verifications = 0\n"
    "        jinhakV0168OtherRouteObservations = 0\n"
    "        jinhakV0168LegacyNavigationSuppressions = 0\n"
    "        // Restore both domain leases",
    "v0168 reset",
)

export_anchor = '                    .put("jinhakV0167AuthReturnTargetSafePath", runtimeSafePath(jinhakV0167AuthReturnTarget))'
if export_anchor in text:
    text = replace_once(
        text,
        export_anchor,
        export_anchor + '\n'
        '                    .put("jinhakV0168AuthEventsObserved", jinhakV0168AuthEventsObserved)\n'
        '                    .put("jinhakV0168PassiveMemberWaits", jinhakV0168PassiveMemberWaits)\n'
        '                    .put("jinhakV0168High3Verifications", jinhakV0168High3Verifications)\n'
        '                    .put("jinhakV0168OtherRouteObservations", jinhakV0168OtherRouteObservations)\n'
        '                    .put("jinhakV0168LegacyNavigationSuppressions", jinhakV0168LegacyNavigationSuppressions)\n'
        '                    .put("jinhakV0168EventDrivenAuth", true)\n'
        '                    .put("jinhakV0168RecursiveAuthPolling", false)\n'
        '                    .put("jinhakV0168DomGradeUiMask", false)',
        "v0168 diagnostics export",
    )
else:
    raise SystemExit("v0168 diagnostics anchor missing")

text = text.replace('private const val VERSION = "0.16.7"', 'private const val VERSION = "0.16.8"')
text = text.replace('private const val BUILD_CODE = 116700', 'private const val BUILD_CODE = 116800')
MAIN.write_text(text)

gradle = GRADLE.read_text()
gradle = gradle.replace('versionCode = 116700', 'versionCode = 116800')
gradle = gradle.replace('versionName = "0.16.7"', 'versionName = "0.16.8"')
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = manifest.replace('Admission Hub v0.16.7 Direct High3 Auth', 'Admission Hub v0.16.8 Event-Driven High3 Auth')
MANIFEST.write_text(manifest)

print("v0.16.8 event-driven Jinhak auth patch applied")
