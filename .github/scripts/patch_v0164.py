from pathlib import Path
import re

MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s = MAIN.read_text()

# Product identity
s = s.replace('private const val VERSION = "0.16.3"', 'private const val VERSION = "0.16.4"', 1)
s = s.replace('private const val BUILD_CODE = 116300', 'private const val BUILD_CODE = 116400', 1)

# Real-device comparison counters next to the existing lower-grade diagnostics.
anchor = '''    private var jinhakLowerGradeManualGateActive = false\n'''
if anchor not in s:
    raise SystemExit('counter anchor missing')
s = s.replace(anchor, anchor + '''    private var jinhakV0912AuthCompatibilityTransitions = 0\n    private var jinhakV0912PassiveLoginSubmissions = 0\n    private var jinhakV0912ProtectedCoreHandoffs = 0\n    private var jinhakV0912ProtectedCoreVerified = 0\n''', 1)

# v0.9.12 had successful real-device Jinhak auth + bootstrap without any grade/product fence.
# Restore that auth boundary: during authentication, Jinhak owns its own redirect chain. The grade
# fence is applied only after the protected high3 core is verified. Auth transitions remain hidden.
old = '''    private fun jinhakHigh3FenceActive(): Boolean = provider == ProviderId.JINHAK &&\n        (unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive || jinhakRealAuthProbeActive)\n'''
new = '''    private fun jinhakAuthCompatibilityWindowActive(): Boolean = provider == ProviderId.JINHAK && (\n        startupLoginPreflightActive ||\n            jinhakTransitionAuthGateActive ||\n            jinhakRealAuthProbeActive ||\n            credentialAwaitingLoginExitProvider == ProviderId.JINHAK ||\n            (batchRunning && batchPausedForLogin) ||\n            (unifiedRunning && unifiedPhase == "jinhak" && !jinhakAuthVerifiedForBatch)\n        )\n\n    private fun jinhakHigh3FenceActive(): Boolean = provider == ProviderId.JINHAK &&\n        (unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive || jinhakRealAuthProbeActive) &&\n        !jinhakAuthCompatibilityWindowActive()\n'''
if old not in s:
    raise SystemExit('high3 fence anchor missing')
s = s.replace(old, new, 1)

# Hide shared-login/lower-grade transitional pages during the compatibility auth window. Unlike
# v0.16.1~0.16.3, do not stop these transitions before Jinhak has established its authenticated
# session. After auth evidence exists we immediately hand off to the protected high3 core.
old = '''                if (jinhakHigh3FenceActive() && provider == ProviderId.JINHAK && isProviderLoginUrl(ProviderId.JINHAK, url)) {\n                    view.visibility = View.INVISIBLE\n                    status.text = "진학사 고3·N수 로그인 컨텍스트 확인 중 · 고1·2 화면은 표시하지 않습니다."\n                }\n'''
new = '''                if (provider == ProviderId.JINHAK && (\n                        isProviderLoginUrl(ProviderId.JINHAK, url) ||\n                            (jinhakAuthCompatibilityWindowActive() && JinhakGradeRouteFence.isBlockedLowerGrade(url))\n                        )) {\n                    view.visibility = View.INVISIBLE\n                    status.text = "진학사 인증 전환 처리 중 · 고1·2 화면은 표시하지 않고 기존 로그인 흐름을 유지합니다."\n                }\n'''
if old not in s:
    raise SystemExit('page-started hide anchor missing')
s = s.replace(old, new, 1)

# Early compatibility handler on page-finished, before newer recovery gates can seize ownership.
old = '''            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n                if (provider == ProviderId.JINHAK && verifyRecoveredJinhakHigh3AndResume(url)) {\n                    return\n                }\n'''
new = '''            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n                if (provider == ProviderId.JINHAK && handleJinhakV0912AuthCompatibilityPage(url)) {\n                    return\n                }\n                if (provider == ProviderId.JINHAK && verifyRecoveredJinhakHigh3AndResume(url)) {\n                    return\n                }\n'''
if old not in s:
    raise SystemExit('page-finished anchor missing')
s = s.replace(old, new, 1)

# Replace v0.16.3 lower-grade recovery state machine with a compatibility handler. A real lower-grade
# route after auth is still fenced; during auth it is allowed to complete invisibly because v0.9.12
# real-device success proves Jinhak's normal login chain can traverse its own member/product routes.
pattern = re.compile(r'''    private fun recoverJinhakLowerGradeLoginContext\(source: String, detail: JSONObject = JSONObject\(\)\) \{.*?(?=    private fun verifyRecoveredJinhakHigh3AndResume)''', re.S)
replacement = r'''    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {
        if (provider != ProviderId.JINHAK || !jinhakAuthCompatibilityWindowActive()) return false
        val loginRoute = isProviderLoginUrl(ProviderId.JINHAK, url)
        val lowerGradeTransition = JinhakGradeRouteFence.isBlockedLowerGrade(url)
        if (!loginRoute && !lowerGradeTransition) return false

        jinhakV0912AuthCompatibilityTransitions += 1
        webView.visibility = View.INVISIBLE
        if (lowerGradeTransition) {
            recordRuntimeEvent("jinhak-v0912-hidden-auth-transition", JSONObject()
                .put("safePath", runtimeSafePath(url))
                .put("transition", jinhakV0912AuthCompatibilityTransitions)
                .put("blockedBeforeAuth", false)
                .put("visibleToUser", false))
        }

        checkSessionState { needsLogin, authenticated ->
            if (provider != ProviderId.JINHAK) return@checkSessionState
            if (authenticated && !needsLogin) {
                val high3Core = JinhakGradeRouteFence.protectedHigh3Core()
                credentialAwaitingLoginExitProvider = null
                jinhakReauthCycles = 0
                jinhakCoreBootstrapState = "v0912-authenticated-handoff-to-protected-core"
                jinhakLastAuthEvidence = "session-authenticated-before-protected-core"
                jinhakV0912ProtectedCoreHandoffs += 1
                if (high3Core.isNotBlank()) {
                    recordRuntimeEvent("jinhak-v0912-protected-core-handoff", JSONObject()
                        .put("sourceSafePath", runtimeSafePath(url))
                        .put("coreSafePath", runtimeSafePath(high3Core))
                        .put("handoff", jinhakV0912ProtectedCoreHandoffs))
                    webView.loadUrl(high3Core)
                    handler.postDelayed({
                        if (provider == ProviderId.JINHAK && jinhakAuthCompatibilityWindowActive()) {
                            scheduleJinhakLoginRecovery("v0912-authenticated-handoff")
                        }
                    }, 320L)
                }
            } else {
                // Keep the real Jinhak login route intact. Only the lower-grade selector is hidden.
                installJinhakHigh3DomProductFence("v0912-passive-login-visual-fence")
                scheduleLoginSurfaceDetection(ProviderId.JINHAK, "v0912-passive-login")
                scheduleJinhakLoginRecovery("v0912-passive-login-wait")
            }
        }
        return true
    }

    private fun recoverJinhakLowerGradeLoginContext(source: String, detail: JSONObject = JSONObject()) {
        if (provider != ProviderId.JINHAK) return
        if (jinhakAuthCompatibilityWindowActive()) {
            // Authentication transitions are handled by the v0.9.12 compatibility path above.
            handleJinhakV0912AuthCompatibilityPage(webView.url.orEmpty())
            return
        }
        val high3Core = JinhakGradeRouteFence.protectedHigh3Core()
        if (high3Core.isBlank()) return
        jinhakLowerGradeNavigationsBlocked += 1
        recordRuntimeEvent("jinhak-post-auth-lower-grade-fenced", JSONObject(detail.toString())
            .put("source", source.take(80))
            .put("high3CoreSafePath", runtimeSafePath(high3Core))
            .put("authVerified", jinhakAuthVerifiedForBatch))
        runCatching { webView.stopLoading() }
        webView.visibility = View.INVISIBLE
        handler.postDelayed({
            if (provider == ProviderId.JINHAK) webView.loadUrl(high3Core)
        }, 120L)
    }

'''
s2, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit(f'recover block replacement mismatch: {n}')
s = s2

# Replace the recovery verifier with the old proven invariant: only a protected high3 route can
# promote authentication; once promoted, resume the preserved target or start Jinhak batch.
pattern = re.compile(r'''    private fun verifyRecoveredJinhakHigh3AndResume\(url: String\): Boolean \{.*?(?=    private fun installJinhakHigh3DomProductFence)''', re.S)
replacement = r'''    private fun verifyRecoveredJinhakHigh3AndResume(url: String): Boolean {
        if (provider != ProviderId.JINHAK || !JinhakGradeRouteFence.isHigh3(url)) return false
        val authGateOwned = jinhakAuthCompatibilityWindowActive() || batchPausedForLogin || jinhakTransitionAuthGateActive || startupLoginPreflightActive
        if (!authGateOwned) return false
        val expectedUrl = url
        webView.visibility = View.INVISIBLE
        checkSessionState { needsLogin, authenticated ->
            if (provider != ProviderId.JINHAK || webView.url.orEmpty() != expectedUrl) return@checkSessionState
            if (!needsLogin && authenticated) {
                jinhakV0912ProtectedCoreVerified += 1
                jinhakLowerGradeHigh3RecoverySuccesses += 1
                jinhakLowerGradeRecoveryInFlight = false
                jinhakLowerGradeManualGateActive = false
                jinhakLowerGradeLoginFenceLatched = false
                jinhakAuthVerifiedForBatch = true
                jinhakReauthCycles = 0
                jinhakCoreBootstrapState = "v0912-protected-core-verified"
                jinhakLastAuthEvidence = "protected-core-stable-v0912-baseline"
                jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
                runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, url, VERSION) }
                recordRuntimeEvent("jinhak-v0912-protected-core-verified", JSONObject()
                    .put("verifiedCount", jinhakV0912ProtectedCoreVerified)
                    .put("batchRunning", batchRunning)
                    .put("batchPausedForLogin", batchPausedForLogin)
                    .put("transitionGate", jinhakTransitionAuthGateActive)
                    .put("startupPreflight", startupLoginPreflightActive))
                webView.visibility = View.VISIBLE
                sessionState.text = "● 진학사 고3·N수 보호경로 인증 확인 · 수집 재개"
                when {
                    batchRunning && batchPausedForLogin -> resumeBatchAfterVerifiedJinhakAuth("v0912-protected-core-verified")
                    unifiedRunning && unifiedPhase == "jinhak" && jinhakTransitionAuthGateActive && !batchRunning -> {
                        jinhakTransitionAuthGateActive = false
                        unifiedPendingJinhakStart = false
                        status.text = "진학사 고3·N수 인증 확인 완료 · 진학사 수집을 시작합니다."
                        handler.postDelayed({
                            if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
                        }, 180L)
                    }
                    startupLoginPreflightActive -> onStartupProviderAuthenticated(ProviderId.JINHAK, startupLoginPollGeneration)
                    else -> status.text = "진학사 고3·N수 보호경로 인증이 확인되었습니다."
                }
            } else {
                jinhakAuthVerifiedForBatch = false
                jinhakCoreBootstrapState = "v0912-protected-core-login-required"
                jinhakLastAuthEvidence = "protected-core-login-required-v0912-baseline"
                installJinhakHigh3DomProductFence("v0912-protected-core-login-required")
                scheduleLoginSurfaceDetection(ProviderId.JINHAK, "v0912-protected-core-login-required")
                scheduleJinhakLoginRecovery("v0912-protected-core-login-required")
            }
        }
        return true
    }

'''
s2, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit(f'verify block replacement mismatch: {n}')
s = s2

# v0.16.x's DOM fence changed product state by clicking the high3 tab. That behavior did not exist in
# the working v0.9.12 path and is the main regression candidate. Keep only a visual/click fence for
# the lower-grade selector; never change Jinhak product state from JavaScript.
pattern = re.compile(r'''    private fun installJinhakHigh3DomProductFence\(reason: String\) \{.*?(?=    private fun attemptSavedCredentialLogin)''', re.S)
replacement = r'''    private fun installJinhakHigh3DomProductFence(reason: String) {
        if (provider != ProviderId.JINHAK || !::webView.isInitialized) return
        val js = """
            (function(){
              try{
                function norm(v){return (v||'').toString().toLowerCase().replace(/\\s+/g,'').replace(/[·ㆍ・\\/,._-]/g,'');}
                function label(el){return ((el&&(el.innerText||el.textContent||el.value||el.getAttribute&&el.getAttribute('aria-label')))||'').toString();}
                function low(el){var n=norm(label(el));return n==='고12'||n==='고1~2'||n.indexOf('고1고2')>=0||n.indexOf('고12학년')>=0;}
                var hidden=0;
                var els=[];try{els=Array.from(document.querySelectorAll('a,button,[role=tab],[role=button],li,span'));}catch(e){}
                for(var i=0;i<els.length;i++){
                  var el=els[i];if(!low(el))continue;
                  try{el.style.setProperty('display','none','important');hidden++;}catch(e){}
                  try{el.setAttribute('aria-hidden','true');el.setAttribute('tabindex','-1');}catch(e){}
                }
                if(!window.__admissionVisualLowerGradeFenceInstalled){
                  window.__admissionVisualLowerGradeFenceInstalled=true;
                  document.addEventListener('click',function(ev){
                    try{var t=ev.target&&ev.target.closest?ev.target.closest('a,button,[role=tab],[role=button],li,span'):ev.target;if(t&&low(t)){ev.preventDefault();ev.stopPropagation();if(ev.stopImmediatePropagation)ev.stopImmediatePropagation();}}catch(e){}
                  },true);
                }
                return JSON.stringify({installed:true,hidden:hidden,productStateChanged:false});
              }catch(e){return JSON.stringify({installed:false,hidden:0,error:String(e),productStateChanged:false});}
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { raw ->
            jinhakDomProductFenceInstalls += 1
            val decoded = runCatching { JSONTokener(raw).nextValue() as? String }.getOrNull().orEmpty()
            val result = runCatching { JSONObject(decoded) }.getOrDefault(JSONObject())
            val hidden = result.optInt("hidden", 0)
            if (hidden > 0) {
                jinhakDomLowerGradeBlocks += hidden
                recordRuntimeEvent("jinhak-lower-grade-selector-hidden", JSONObject()
                    .put("reason", reason.take(80))
                    .put("hidden", hidden)
                    .put("productStateChanged", false))
            }
            val current = webView.url.orEmpty()
            when {
                isProviderLoginUrl(ProviderId.JINHAK, current) -> {
                    webView.visibility = View.VISIBLE
                    status.text = "진학사 공용 로그인 · 고1·2 선택 UI만 숨기고 실제 로그인 흐름은 그대로 사용합니다."
                }
                jinhakAuthCompatibilityWindowActive() && JinhakGradeRouteFence.isBlockedLowerGrade(current) -> {
                    webView.visibility = View.INVISIBLE
                }
                !JinhakGradeRouteFence.isBlockedLowerGrade(current) -> webView.visibility = View.VISIBLE
            }
        }
    }

    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val now = System.currentTimeMillis()
        // Match the proven v0.9.12 passive-login timing instead of the newer product-preflight loop.
        if (credentialAutoLoginInFlight && now - credentialAutoLoginLastAttemptAtMs < 6_000L) return
        if (now - credentialAutoLoginLastAttemptAtMs < 900L) return
        val credential = credentialVault.load(ProviderId.JINHAK.wireName)
        if (credential == null) {
            credentialAutoLoginSuppressedNoCredential += 1
            if (startupCredentialPromptedProvider != ProviderId.JINHAK) {
                startupCredentialPromptedProvider = ProviderId.JINHAK
                showCredentialDialog(ProviderId.JINHAK, continueAfterSave = true)
            }
            return
        }
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
                function roots(doc){var out=[doc];try{var all=doc.querySelectorAll('*');for(var i=0;i<all.length;i++)if(all[i].shadowRoot)out.push(all[i].shadowRoot);}catch(e){}return out;}
                function setValue(el,v){
                  try{var proto=Object.getPrototypeOf(el);var desc=Object.getOwnPropertyDescriptor(proto,'value')||Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');if(desc&&desc.set)desc.set.call(el,v);else el.value=v;}catch(e){el.value=v;}
                  try{el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}
                }
                var docs=[document];try{var fs=document.querySelectorAll('iframe,frame');for(var f=0;f<fs.length;f++)try{if(fs[f].contentDocument)docs.push(fs[f].contentDocument);}catch(e){}}catch(e){}
                for(var d=0;d<docs.length;d++){
                  var rs=roots(docs[d]);
                  for(var r=0;r<rs.length;r++){
                    var root=rs[r],passes=[];try{passes=Array.from(root.querySelectorAll('input[type=password]')).filter(visible);}catch(e){}
                    for(var p=0;p<passes.length;p++){
                      var pass=passes[p],form=pass.form||pass.closest('form'),base=form||root,candidates=[];
                      try{candidates=Array.from(base.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                      if(!candidates.length)continue;
                      function score(el){var meta=((el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.autocomplete||'')).toLowerCase();var n=0;if(/아이디|user|login|member|email|account/.test(meta))n+=60;if((el.autocomplete||'').toLowerCase()==='username')n+=100;if(/search|검색/.test(meta))n-=200;if(form&&el.form===form)n+=100;return n;}
                      candidates.sort(function(a,b){return score(b)-score(a);});
                      var user=candidates[0];if(!user)continue;
                      setValue(user,$userJson);setValue(pass,$passJson);
                      var controls=[];try{controls=Array.from(base.querySelectorAll('button,input[type=submit],input[type=button],[role=button]')).filter(visible);}catch(e){}
                      function label(el){return ((el.innerText||el.value||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\\s+/g,' ').trim();}
                      var submit=controls.find(function(el){return /^(로그인|로그인하기|log\\s*in|sign\\s*in)$/i.test(label(el));})||controls.find(function(el){return (el.type||'').toLowerCase()==='submit';})||null;
                      if(submit){submit.click();return JSON.stringify({submitted:true,method:'button'});}
                      if(form){if(form.requestSubmit)form.requestSubmit();else form.submit();return JSON.stringify({submitted:true,method:'form'});}
                    }
                  }
                }
                return JSON.stringify({submitted:false,reason:'visible-login-fields-missing'});
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
                credentialAutoLoginLastResult = "v0912-submitted-${result.optString("method", "unknown")}"
                status.text = "진학사 로그인 제출 완료 · 사이트의 원래 인증 전환을 숨김 상태로 기다립니다."
                handler.postDelayed({
                    checkSessionState { needsLogin, authenticated ->
                        if (provider != ProviderId.JINHAK) return@checkSessionState
                        if (authenticated && !needsLogin) {
                            credentialAwaitingLoginExitProvider = null
                            credentialAutoLoginSuccesses += 1
                            credentialAutoLoginLastResult = "v0912-success-session-verified"
                            credentialAutoLoginLastAtMs = System.currentTimeMillis()
                            jinhakReauthCycles = 0
                            runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }
                            val high3Core = JinhakGradeRouteFence.protectedHigh3Core()
                            jinhakCoreBootstrapState = "v0912-passive-login-protected-core-handoff"
                            jinhakLastAuthEvidence = "session-authenticated-v0912-passive-login"
                            if (high3Core.isNotBlank()) {
                                jinhakV0912ProtectedCoreHandoffs += 1
                                webView.visibility = View.INVISIBLE
                                webView.loadUrl(high3Core)
                                handler.postDelayed({
                                    if (provider == ProviderId.JINHAK) scheduleJinhakLoginRecovery("v0912-passive-login-success")
                                }, 320L)
                            }
                        } else if (needsLogin) {
                            credentialAutoLoginFailures += 1
                            credentialAutoLoginLastResult = "v0912-login-still-required"
                            credentialAwaitingLoginExitProvider = null
                            installJinhakHigh3DomProductFence("v0912-login-still-required")
                            status.text = "진학사 로그인이 아직 필요합니다. 고1·2 선택 UI는 숨긴 채 공용 로그인에서 인증을 계속합니다."
                        } else {
                            scheduleJinhakLoginRecovery("v0912-login-indeterminate")
                            scheduleLoginSurfaceDetection(ProviderId.JINHAK, "v0912-login-indeterminate")
                        }
                    }
                }, 1_600L)
            } else {
                credentialAutoLoginLastResult = "v0912-not-submitted-${result.optString("reason", "unknown")}"
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                scheduleLoginSurfaceDetection(ProviderId.JINHAK, "v0912-passive-login-retry-$reason")
            }
            persistJinhakAuthDiagnostics("credential-auto-login-v0912-baseline")
        }
    }

'''
s2, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit(f'DOM fence block replacement mismatch: {n}')
s = s2

# Route Jinhak auto-login through the proven passive form flow. Adiga keeps the current path.
old = '''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {\n        if (provider != which) return\n        if (which == ProviderId.JINHAK && jinhakLowerGradeLoginFenceLatched) return\n        if (which == ProviderId.JINHAK) installJinhakHigh3DomProductFence("credential:$reason")\n'''
new = '''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {\n        if (provider != which) return\n        if (which == ProviderId.JINHAK) {\n            installJinhakHigh3DomProductFence("credential-visual-only:$reason")\n            attemptSavedCredentialLoginV0912Baseline(reason)\n            return\n        }\n'''
if old not in s:
    raise SystemExit('attemptSavedCredentialLogin anchor missing')
s = s.replace(old, new, 1)

# Do not suppress login recovery merely because a lower-grade fence flag was latched by an older
# callback. This was a direct source of the v0.16.3 "수집 대기" deadlock.
s = s.replace('''        if (jinhakLowerGradeLoginFenceLatched) return\n        if ((batchRunning || unifiedRunning || jinhakTransitionAuthGateActive || startupLoginPreflightActive) && jinhakReauthCycles >= MAX_JINHAK_REAUTH_CYCLES) {''',
              '''        if (jinhakLowerGradeLoginFenceLatched && !jinhakAuthCompatibilityWindowActive()) return\n        if ((batchRunning || unifiedRunning || jinhakTransitionAuthGateActive || startupLoginPreflightActive) && jinhakReauthCycles >= MAX_JINHAK_REAUTH_CYCLES) {''', 1)

# Reset compatibility counters for each explicit unified run.
old = '''        jinhakLowerGradeHigh3RecoveryAttempts = 0\n        jinhakLowerGradeHigh3RecoverySuccesses = 0\n        jinhakLowerGradeRecoveryInFlight = false\n        jinhakLowerGradeManualGateActive = false\n'''
new = old + '''        jinhakV0912AuthCompatibilityTransitions = 0\n        jinhakV0912PassiveLoginSubmissions = 0\n        jinhakV0912ProtectedCoreHandoffs = 0\n        jinhakV0912ProtectedCoreVerified = 0\n'''
if old not in s:
    raise SystemExit('unified reset anchor missing')
s = s.replace(old, new, 1)

# Export enough evidence to approve/reject the new real-device auth path without credentials/cookies.
old = '''                    .put("jinhakDomLowerGradeBlocks", jinhakDomLowerGradeBlocks)\n'''
new = old + '''                    .put("jinhakV0912AuthCompatibilityTransitions", jinhakV0912AuthCompatibilityTransitions)\n                    .put("jinhakV0912PassiveLoginSubmissions", jinhakV0912PassiveLoginSubmissions)\n                    .put("jinhakV0912ProtectedCoreHandoffs", jinhakV0912ProtectedCoreHandoffs)\n                    .put("jinhakV0912ProtectedCoreVerified", jinhakV0912ProtectedCoreVerified)\n'''
if old not in s:
    raise SystemExit('diagnostics anchor missing')
s = s.replace(old, new, 1)

MAIN.write_text(s)

# Version metadata.
p = Path('app/build.gradle.kts')
g = p.read_text().replace('versionCode = 116300', 'versionCode = 116400', 1).replace('versionName = "0.16.3"', 'versionName = "0.16.4"', 1)
p.write_text(g)

p = Path('app/src/main/AndroidManifest.xml')
m = p.read_text().replace('Admission Hub v0.16.3 High3 Recover', 'Admission Hub v0.16.4 v0.9.12 Auth Baseline', 1)
p.write_text(m)

print('v0.16.4 v0.9.12 auth baseline restore applied')
