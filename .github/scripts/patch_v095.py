from pathlib import Path

main_p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle_p = Path('app/build.gradle.kts')
manifest_p = Path('app/src/main/AndroidManifest.xml')
main = main_p.read_text()
gradle = gradle_p.read_text()
manifest = manifest_p.read_text()


def must_replace(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing replacement anchor: {label}')
    return text.replace(old, new, 1)

main = must_replace(main, 'private const val VERSION = "0.9.4"', 'private const val VERSION = "0.9.5"', 'version')
main = must_replace(main, 'private const val BUILD_CODE = 10940', 'private const val BUILD_CODE = 10950', 'build')
gradle = must_replace(gradle, 'versionCode = 10940', 'versionCode = 10950', 'gradle-code')
gradle = must_replace(gradle, 'versionName = "0.9.4"', 'versionName = "0.9.5"', 'gradle-name')
manifest = must_replace(manifest, 'Admission Collector v0.9.4 Auth Guard Web Bridge', 'Admission Collector v0.9.5 Passive Login Surface Auto Login', 'manifest-label')

main = must_replace(
    main,
    '    private var startupCredentialPromptedProvider: ProviderId? = null\n',
    '''    private var startupCredentialPromptedProvider: ProviderId? = null
    private var credentialLoginSurfaceGeneration = 0
    private var credentialLoginSurfaceKey = ""
    private var credentialLoginSurfaceAttempts = 0
    private var credentialAwaitingLoginExitProvider: ProviderId? = null
    private var credentialLoginSurfaceSeenProvider: ProviderId? = null
    private var credentialLoginSurfaceSeenAtMs = 0L
    private var startupAuthIndeterminatePolls = 0
''',
    'login-state-vars'
)

old_pf = '''                if (isProviderLoginUrl(provider, url) && credentialVault.has(provider.wireName)) {
                    handler.postDelayed({ attemptSavedCredentialLogin(provider, "page-finished") }, 220L)
                }
'''
new_pf = '''                // v0.9.5: never navigate to login proactively. Probe the rendered DOM after
                // every navigation and auto-login only when an actual login surface is visible.
                scheduleLoginSurfaceDetection(provider, "page-finished")
'''
main = must_replace(main, old_pf, new_pf, 'page-finished-login-probe')

old_save = '''                        if (continueAfterSave) {
                            credentialAutoLoginInFlight = false
                            credentialAutoLoginLastAttemptAtMs = 0L
                            webView.loadUrl(providerLoginUrl(which))
                        }
'''
new_save = '''                        if (continueAfterSave) {
                            credentialAutoLoginInFlight = false
                            credentialAutoLoginLastAttemptAtMs = 0L
                            credentialLoginSurfaceAttempts = 0
                            // Do not force a login URL. If the site has already rendered a login
                            // surface, the passive detector will fill and submit it immediately.
                            scheduleLoginSurfaceDetection(which, "credential-saved")
                        }
'''
main = must_replace(main, old_save, new_save, 'credential-save-no-force')

# Replace refresh + session detector together. This removes the old code path that clicked
# a login link or loaded provider.homeUrl when the auth result was uncertain.
refresh_start = main.index('    private fun refreshSessionOrOpenLogin()')
check_start = main.index('    private fun checkSessionState', refresh_start)
runtime_start = main.index('    private fun runtimeSafePath', check_start)
new_refresh_check = r'''    private fun refreshSessionOrOpenLogin() {
        checkSessionState { needsLogin, authenticated ->
            if (authenticated) {
                sessionState.text = "● 로그인 유지됨"
                if (batchRunning && batchPausedForLogin) resumeAfterLogin()
                return@checkSessionState
            }
            // v0.9.5: refresh means re-probe only. It must never click a login link,
            // navigate to a login URL, or bounce the user back to provider.homeUrl.
            scheduleLoginSurfaceDetection(provider, "session-refresh")
            sessionState.text = if (needsLogin) "○ 로그인 필요 감지 · 로그인 화면 대기" else "△ 로그인 상태 재확인 중 · 현재 화면 유지"
            status.text = if (needsLogin) {
                "로그인이 필요한 상태가 감지되었습니다. 현재 화면을 유지하며 로그인 폼이 렌더링되면 저장 계정으로 자동 로그인합니다."
            } else {
                "로그인 상태가 확정되지 않았습니다. 화면 이동 없이 현재 페이지에서 다시 확인합니다."
            }
        }
    }

    private fun checkSessionState(callback: ((Boolean, Boolean) -> Unit)? = null) {
        val js = """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0 && r.height>0;
              }
              function roots(doc){
                var out=[doc];
                try{
                  var all=doc.querySelectorAll('*');
                  for(var i=0;i<all.length;i++) if(all[i].shadowRoot) out.push(all[i].shadowRoot);
                }catch(e){}
                return out;
              }
              var docs=[document];
              try{
                var frames=document.querySelectorAll('iframe,frame');
                for(var f=0;f<frames.length;f++) try{ if(frames[f].contentDocument) docs.push(frames[f].contentDocument); }catch(e){}
              }catch(e){}
              var loginSurface=false;
              var bodyText='';
              var logoutControl=false;
              for(var d=0;d<docs.length;d++){
                var doc=docs[d];
                try{ bodyText += ' ' + ((doc.body&&doc.body.innerText)||''); }catch(e){}
                var rs=roots(doc);
                var visiblePassword=false;
                var visibleUser=false;
                for(var r=0;r<rs.length;r++){
                  var root=rs[r];
                  try{
                    var pw=root.querySelectorAll('input[type=password]');
                    for(var p=0;p<pw.length;p++) if(visible(pw[p])) { visiblePassword=true; break; }
                    var us=root.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])');
                    for(var u=0;u<us.length;u++){
                      if(!visible(us[u])) continue;
                      var meta=((us[u].name||'')+' '+(us[u].id||'')+' '+(us[u].placeholder||'')+' '+(us[u].autocomplete||'')).toLowerCase();
                      if(/아이디|user|login|member|email|account|id/.test(meta) && !/search|검색/.test(meta)) { visibleUser=true; break; }
                    }
                    var controls=root.querySelectorAll('a,button,[role=button],input[type=submit],input[type=button]');
                    for(var c=0;c<controls.length;c++){
                      var node=controls[c]; if(!visible(node)) continue;
                      var label=(node.innerText||node.value||node.textContent||node.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
                      if(/^(로그아웃|log\s*out|sign\s*out)$/i.test(label)){ logoutControl=true; break; }
                    }
                  }catch(e){}
                }
                if(visiblePassword && visibleUser) loginSurface=true;
              }
              var loginRequired=/(로그인이\s*필요|로그인\s*후\s*(?:이용|사용)|로그인해\s*주세요|로그인해주세요|회원만\s*이용|서비스\s*이용을\s*위해\s*로그인)/i.test(bodyText.slice(0,24000));
              return JSON.stringify({needsLogin:(loginSurface||loginRequired)&&!logoutControl,authenticated:logoutControl,loginSurface:loginSurface,loginRequired:loginRequired,urlLooksLogin:/(\/member\/login|\/mbs\/log\/|mbslogview)/i.test(location.href)});
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            try {
                val obj = JSONObject(decodeJsString(encoded))
                val needsLogin = obj.optBoolean("needsLogin", false)
                var authenticated = obj.optBoolean("authenticated", false)
                val loginSurface = obj.optBoolean("loginSurface", false)
                val now = System.currentTimeMillis()
                if (loginSurface) {
                    credentialLoginSurfaceSeenProvider = provider
                    credentialLoginSurfaceSeenAtMs = now
                }
                // A submitted credential login is considered successful only after the
                // actual login surface disappears and no explicit login-required state remains.
                if (!authenticated && !needsLogin && !loginSurface && credentialAwaitingLoginExitProvider == provider) {
                    authenticated = true
                    credentialAwaitingLoginExitProvider = null
                    credentialLoginSurfaceKey = ""
                    credentialLoginSurfaceAttempts = 0
                }
                sessionState.text = when {
                    authenticated -> "● 로그인 유지됨 · 보안 세션 lease 갱신"
                    loginSurface -> "○ 로그인 화면 감지 · 자동 로그인 준비"
                    needsLogin -> "○ 로그인 필요 상태 감지"
                    else -> "△ 로그인 상태 미확정 · 현재 화면 유지"
                }
                if (authenticated) {
                    val currentUrl = webView.url.orEmpty()
                    if (currentUrl.isNotBlank()) runCatching { sessionVault.captureAuthenticated(provider.wireName, currentUrl, VERSION) }
                }
                callback?.invoke(needsLogin, authenticated)
            } catch (_: Exception) {
                sessionState.text = "△ 로그인 상태 확인 불가 · 현재 화면 유지"
                callback?.invoke(false, false)
            }
        }
    }

'''
main = main[:refresh_start] + new_refresh_check + main[runtime_start:]

# Replace login surface/autofill implementation with a DOM-first detector that works regardless
# of the current URL and retries after SPA/React hydration. It never exports field values.
auto_start = main.index('    private fun attemptSavedCredentialLogin')
auto_end = main.index('    private fun startAutomaticLoginAndCollectionSequence', auto_start)
new_auto = r'''    private fun probeLoginSurface(which: ProviderId, callback: (JSONObject) -> Unit) {
        if (provider != which) { callback(JSONObject().put("detected", false)); return }
        val js = """
            (function(){
              try{
                function visible(el){ if(!el) return false; var s=getComputedStyle(el); if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false; var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
                function roots(doc){ var out=[doc]; try{var all=doc.querySelectorAll('*'); for(var i=0;i<all.length;i++) if(all[i].shadowRoot) out.push(all[i].shadowRoot);}catch(e){} return out; }
                var docs=[document]; try{var fs=document.querySelectorAll('iframe,frame'); for(var f=0;f<fs.length;f++) try{if(fs[f].contentDocument) docs.push(fs[f].contentDocument);}catch(e){}}catch(e){}
                var best=null;
                for(var d=0;d<docs.length;d++){
                  var rs=roots(docs[d]);
                  for(var r=0;r<rs.length;r++){
                    var root=rs[r], passes=[]; try{passes=Array.from(root.querySelectorAll('input[type=password]')).filter(visible);}catch(e){}
                    for(var p=0;p<passes.length;p++){
                      var pass=passes[p], form=pass.form||pass.closest('form'), candidates=[];
                      var base=form||root;
                      try{candidates=Array.from(base.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                      if(!candidates.length) try{candidates=Array.from(root.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                      function score(el){ var meta=((el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.autocomplete||'')).toLowerCase(); var n=0; if(/아이디|user|login|member|email|account/.test(meta)) n+=50; if(/\bid\b/.test(meta)) n+=25; if((el.autocomplete||'').toLowerCase()==='username') n+=80; if((el.type||'').toLowerCase()==='email') n+=10; if(/search|검색/.test(meta)) n-=120; if(form&&el.form===form) n+=100; return n; }
                      candidates.sort(function(a,b){return score(b)-score(a);});
                      var user=candidates[0]||null;
                      var controls=[]; try{controls=Array.from((form||root).querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                      if(!controls.length) try{controls=Array.from(root.querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                      function label(el){return ((el.innerText||el.value||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\s+/g,' ').trim();}
                      var submit=controls.find(function(el){return /^(로그인|로그인하기|log\s*in|sign\s*in)$/i.test(label(el));})||null;
                      if(user){ best={user:true,pass:true,submit:!!submit,form:!!form}; break; }
                    }
                    if(best) break;
                  }
                  if(best) break;
                }
                var text=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,20000);
                var credentialError=/(아이디\s*(?:또는|나)\s*비밀번호.*(?:확인|일치|오류)|비밀번호.*일치하지|잘못된\s*비밀번호|로그인에\s*실패)/i.test(text);
                return JSON.stringify({detected:!!best,hasUser:!!(best&&best.user),hasPassword:!!(best&&best.pass),hasSubmit:!!(best&&best.submit),hasForm:!!(best&&best.form),credentialError:credentialError,urlLooksLogin:/(\/member\/login|\/mbs\/log\/|mbslogview)/i.test(location.href)});
              }catch(e){return JSON.stringify({detected:false,error:'probe-error'});}
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { encoded ->
            val obj = runCatching { JSONObject(decodeJsString(encoded)) }.getOrElse { JSONObject().put("detected", false).put("error", "decode-error") }
            if (obj.optBoolean("detected", false)) {
                credentialLoginSurfaceSeenProvider = which
                credentialLoginSurfaceSeenAtMs = System.currentTimeMillis()
            }
            callback(obj)
        }
    }

    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {
        if (provider != which) return
        val generation = ++credentialLoginSurfaceGeneration
        val delays = longArrayOf(100L, 420L, 1_050L, 2_300L)
        delays.forEach { delay ->
            handler.postDelayed({
                if (provider != which || generation != credentialLoginSurfaceGeneration) return@postDelayed
                probeLoginSurface(which) { probe ->
                    if (provider != which || generation != credentialLoginSurfaceGeneration) return@probeLoginSurface
                    if (!probe.optBoolean("detected", false)) return@probeLoginSurface
                    sessionState.text = "○ ${which.displayName} 로그인 화면 감지"
                    status.text = "${which.displayName} 로그인 폼을 실제 DOM에서 감지했습니다. 저장된 계정이 있으면 현재 화면에서 자동 로그인합니다."
                    if (credentialVault.has(which.wireName)) {
                        attemptSavedCredentialLogin(which, reason)
                    } else if (startupCredentialPromptedProvider != which) {
                        startupCredentialPromptedProvider = which
                        showCredentialDialog(which, continueAfterSave = true)
                    }
                }
            }, delay)
        }
    }

    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (provider != which) return
        val now = System.currentTimeMillis()
        if (credentialAutoLoginInFlight && now - credentialAutoLoginLastAttemptAtMs < 6_000L) return
        if (now - credentialAutoLoginLastAttemptAtMs < 900L) return
        val credentials = runCatching { credentialVault.load(which.wireName) }.getOrNull() ?: return

        probeLoginSurface(which) { probe ->
            if (!probe.optBoolean("detected", false)) return@probeLoginSurface
            val surfaceKey = which.wireName + "|" + runtimeSafePath(webView.url)
            if (surfaceKey != credentialLoginSurfaceKey) {
                credentialLoginSurfaceKey = surfaceKey
                credentialLoginSurfaceAttempts = 0
            }
            if (probe.optBoolean("credentialError", false) && credentialLoginSurfaceAttempts > 0) {
                sessionState.text = "△ ${which.displayName} 저장 계정 로그인 오류 감지"
                status.text = "저장된 계정으로 로그인한 뒤 오류 문구가 감지되어 반복 제출을 중지했습니다. 계정 설정을 확인해주세요."
                return@probeLoginSurface
            }
            if (credentialLoginSurfaceAttempts >= 2) {
                sessionState.text = "△ ${which.displayName} 자동 로그인 재시도 한도 도달"
                return@probeLoginSurface
            }

            credentialAutoLoginInFlight = true
            credentialAutoLoginLastAttemptAtMs = System.currentTimeMillis()
            credentialAutoLoginAttempts += 1
            credentialLoginSurfaceAttempts += 1
            credentialAwaitingLoginExitProvider = which
            val userJs = JSONObject.quote(credentials.username)
            val passJs = JSONObject.quote(credentials.password)
            val script = """
                (function(){
                  try {
                    function visible(el){ if(!el) return false; var s=getComputedStyle(el); if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false; var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
                    function setValue(el,value){
                      var proto=Object.getPrototypeOf(el), d=null;
                      while(proto&&!d){d=Object.getOwnPropertyDescriptor(proto,'value');proto=Object.getPrototypeOf(proto);}
                      if(d&&d.set) d.set.call(el,value); else el.value=value;
                      el.focus();
                      ['input','change','keyup','blur'].forEach(function(t){el.dispatchEvent(new Event(t,{bubbles:true}));});
                    }
                    function roots(doc){var out=[doc];try{var all=doc.querySelectorAll('*');for(var i=0;i<all.length;i++)if(all[i].shadowRoot)out.push(all[i].shadowRoot);}catch(e){}return out;}
                    var docs=[document]; try{var fs=document.querySelectorAll('iframe,frame');for(var f=0;f<fs.length;f++)try{if(fs[f].contentDocument)docs.push(fs[f].contentDocument);}catch(e){}}catch(e){}
                    var selected=null;
                    for(var d=0;d<docs.length&&!selected;d++){
                      var rs=roots(docs[d]);
                      for(var r=0;r<rs.length&&!selected;r++){
                        var root=rs[r], passes=[];try{passes=Array.from(root.querySelectorAll('input[type=password]')).filter(visible);}catch(e){}
                        for(var p=0;p<passes.length&&!selected;p++){
                          var pass=passes[p], form=pass.form||pass.closest('form'), base=form||root, users=[];
                          try{users=Array.from(base.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                          if(!users.length)try{users=Array.from(root.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                          function score(el){var meta=((el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.autocomplete||'')).toLowerCase(),n=0;if(/아이디|user|login|member|email|account/.test(meta))n+=50;if(/\bid\b/.test(meta))n+=25;if((el.autocomplete||'').toLowerCase()==='username')n+=80;if(/search|검색/.test(meta))n-=120;if(form&&el.form===form)n+=100;return n;}
                          users.sort(function(a,b){return score(b)-score(a);}); var user=users[0]||null; if(!user)continue;
                          var controls=[];try{controls=Array.from((form||root).querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                          if(!controls.length)try{controls=Array.from(root.querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                          function label(el){return ((el.innerText||el.value||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\s+/g,' ').trim();}
                          var submit=controls.find(function(el){return /^(로그인|로그인하기|log\s*in|sign\s*in)$/i.test(label(el));})||null;
                          selected={user:user,pass:pass,form:form,submit:submit};
                        }
                      }
                    }
                    if(!selected) return 'fields-not-found';
                    setValue(selected.user,$userJs); setValue(selected.pass,$passJs);
                    // Jinhak's current login is UI-driven; prefer the rendered login control
                    // before native form submission so framework click handlers execute.
                    if(selected.submit){ selected.submit.focus(); selected.submit.click(); return 'submitted-click'; }
                    if(selected.form&&typeof selected.form.requestSubmit==='function'){ selected.form.requestSubmit(); return 'submitted-form'; }
                    try{selected.pass.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));selected.pass.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));return 'submitted-enter';}catch(e){}
                    return 'submit-not-found';
                  } catch(e) { return 'error'; }
                })();
            """.trimIndent()
            webView.evaluateJavascript(script) { encoded ->
                credentialAutoLoginInFlight = false
                val result = decodeJsString(encoded).take(80)
                recordRuntimeEvent("credential-auto-login-attempt", JSONObject()
                    .put("provider", which.wireName)
                    .put("reason", reason.take(40))
                    .put("result", result)
                    .put("loginSurfaceDetected", true)
                    .put("attemptOnSurface", credentialLoginSurfaceAttempts)
                    .put("credentialStored", true)
                    .put("credentialExported", false))
                sessionState.text = if (result.startsWith("submitted")) "● ${which.displayName} 자동 로그인 제출됨" else "△ ${which.displayName} 자동 로그인: $result"
                if (!result.startsWith("submitted")) credentialAwaitingLoginExitProvider = null
                handler.postDelayed({
                    checkSessionState { needsLogin, authenticated ->
                        if (authenticated) {
                            credentialLoginSurfaceAttempts = 0
                            val url = webView.url.orEmpty()
                            if (url.isNotBlank()) runCatching { sessionVault.captureAuthenticated(which.wireName, url, VERSION) }
                            if (batchRunning && batchPausedForLogin) resumeAfterLogin()
                            if (startupLoginPreflightActive && provider == which) {
                                val generation = startupLoginPollGeneration
                                onStartupProviderAuthenticated(which, generation)
                            }
                        } else if (needsLogin) {
                            scheduleLoginSurfaceDetection(which, "post-submit")
                        }
                    }
                }, 1_100L)
            }
        }
    }

'''
main = main[:auto_start] + new_auto + main[auto_end:]

# Reset indeterminate counter whenever a provider preflight begins.
main = must_replace(
    main,
    '        startupLoginOpenAttempted = false\n        startupLoginPollGeneration += 1\n        val generation = startupLoginPollGeneration\n',
    '        startupLoginOpenAttempted = false\n        startupAuthIndeterminatePolls = 0\n        startupLoginPollGeneration += 1\n        val generation = startupLoginPollGeneration\n',
    'preflight-reset'
)

# Replace startup auth evaluation + old login-link opener. No proactive navigation remains.
eval_start = main.index('    private fun evaluateStartupLoginState')
sched_start = main.index('    private fun scheduleStartupLoginPoll', eval_start)
new_eval = r'''    private fun evaluateStartupLoginState(expectedProvider: ProviderId, generation: Int) {
        if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return
        checkSessionState { needsLogin, authenticated ->
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@checkSessionState
            if (authenticated) {
                onStartupProviderAuthenticated(expectedProvider, generation)
                return@checkSessionState
            }
            probeLoginSurface(expectedProvider) { probe ->
                if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@probeLoginSurface
                if (probe.optBoolean("detected", false)) {
                    startupAuthIndeterminatePolls = 0
                    sessionState.text = "○ ${expectedProvider.displayName} 로그인 화면 감지"
                    if (credentialVault.has(expectedProvider.wireName)) {
                        status.text = "${expectedProvider.displayName} 로그인 화면이 실제로 감지되어 저장 계정으로 자동 로그인합니다."
                        attemptSavedCredentialLogin(expectedProvider, "startup-login-surface")
                    } else if (startupCredentialPromptedProvider != expectedProvider) {
                        startupCredentialPromptedProvider = expectedProvider
                        status.text = "${expectedProvider.displayName} 로그인 화면이 감지되었습니다. 자동로그인 정보를 한 번 저장해주세요."
                        showCredentialDialog(expectedProvider, continueAfterSave = true)
                    }
                    scheduleStartupLoginPoll(expectedProvider, generation)
                    return@probeLoginSurface
                }

                // No rendered login surface: never navigate to login just because the auth
                // classifier is uncertain. After two stable probes, continue bootstrap and
                // let protected pages naturally redirect; the global surface detector then logs in.
                startupAuthIndeterminatePolls += 1
                if (!needsLogin && startupAuthIndeterminatePolls >= 2) {
                    recordRuntimeEvent("startup-login-provider-deferred", JSONObject()
                        .put("provider", expectedProvider.wireName)
                        .put("reason", "no-rendered-login-surface")
                        .put("forcedNavigation", false))
                    startupLoginPollGeneration += 1
                    startupLoginOpenAttempted = false
                    if (expectedProvider == ProviderId.ADIGA) {
                        sessionState.text = "△ 어디가 로그인 화면 없음 · 현재 화면 유지"
                        status.text = "어디가 로그인 화면을 강제로 열지 않고 진학사 확인으로 넘어갑니다. 보호 페이지에서 로그인 화면이 나타나면 자동 로그인합니다."
                        handler.postDelayed({ if (startupLoginPreflightActive) beginStartupLoginProvider(ProviderId.JINHAK) }, 200L)
                    } else {
                        sessionState.text = "△ 진학사 로그인 화면 없음 · 수집 중 감지 대기"
                        startupLoginPreflightActive = false
                        startupLoginPreflightVerified = true
                        startupLoginStage = "passive-login-surface-ready"
                        status.text = "로그인 화면 강제 이동 없이 통합 수집을 시작합니다. 수집 중 로그인 화면이 감지되는 즉시 자동 로그인합니다."
                        handler.postDelayed({ if (!unifiedRunning && !batchRunning) startUnifiedCollectionAuthenticated() }, 250L)
                    }
                    return@probeLoginSurface
                }
                sessionState.text = if (needsLogin) "○ 로그인 필요 신호 감지 · 로그인 폼 렌더링 대기" else "△ 로그인 상태 확인 중 · 현재 화면 유지"
                status.text = "${expectedProvider.displayName} 현재 화면을 유지합니다. 실제 로그인 폼이 감지될 때만 자동 로그인을 실행합니다."
                scheduleStartupLoginPoll(expectedProvider, generation)
            }
        }
    }

'''
main = main[:eval_start] + new_eval + main[sched_start:]

# scheduleStartupLoginPoll previously only checked authenticated and recursively polled; it now also
# re-runs the full state/surface evaluation, so a login form appearing later is caught.
old_sched = '''    private fun scheduleStartupLoginPoll(expectedProvider: ProviderId, generation: Int) {
        handler.postDelayed({
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@postDelayed
            checkSessionState { _, authenticated ->
                if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@checkSessionState
                if (authenticated) {
                    onStartupProviderAuthenticated(expectedProvider, generation)
                } else {
                    scheduleStartupLoginPoll(expectedProvider, generation)
                }
            }
        }, LOGIN_PREFLIGHT_POLL_MS)
    }
'''
new_sched = '''    private fun scheduleStartupLoginPoll(expectedProvider: ProviderId, generation: Int) {
        handler.postDelayed({
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@postDelayed
            evaluateStartupLoginState(expectedProvider, generation)
        }, LOGIN_PREFLIGHT_POLL_MS)
    }
'''
main = must_replace(main, old_sched, new_sched, 'startup-poll-surface-aware')

# No production code may proactively load a provider login URL after this patch.
if 'webView.loadUrl(providerLoginUrl' in main:
    raise SystemExit('forced provider login navigation still present')
if 'openStartupLoginPage(' in main:
    raise SystemExit('legacy startup login opener still present')

main_p.write_text(main)
gradle_p.write_text(gradle)
manifest_p.write_text(manifest)
print('v0.9.5 passive login surface patch applied')
