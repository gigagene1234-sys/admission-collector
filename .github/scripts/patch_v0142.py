from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    assert count == 1, f"{label}: expected 1 literal, found {count}"
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    compiled = re.compile(pattern, re.S)
    out, count = compiled.subn(lambda _match: replacement, text, count=1)
    assert count == 1, f"{label}: expected 1 regex match, found {count}"
    return out

root = Path('app/src/main/java/com/admissionhub/collector')
main_path = root / 'MainActivity.kt'
main = main_path.read_text()
main = replace_once(main, 'private const val VERSION = "0.14.1"', 'private const val VERSION = "0.14.2"', 'Main version')
main = replace_once(main, 'private const val BUILD_CODE = 114100', 'private const val BUILD_CODE = 114200', 'Main build')

show_dialog = r'''    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {
        if (credentialAutoLoginInFlight) return
        val existing = credentialVault.load(which.wireName)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 20, 48, 0)
        }
        val intro = TextView(this).apply {
            text = "${which.displayName} 로그인 정보를 이 기기의 Android Keystore로 암호화해 저장하면, 세션이 만료되어도 로그인 화면이 실제로 감지될 때만 자동 입력합니다. 계정정보는 내보내기·로그·클라우드 수집에 포함하지 않습니다."
            textSize = 14f
            setPadding(0, 0, 0, 16)
        }
        val user = EditText(this).apply {
            hint = "아이디 / 이메일"
            setSingleLine(true)
            setText(existing?.username.orEmpty())
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
        }
        val pass = EditText(this).apply {
            hint = "비밀번호"
            setSingleLine(true)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val remember = android.widget.CheckBox(this).apply {
            text = "이 기기에 암호화 저장하여 다음부터 자동 로그인"
            isChecked = true
        }
        container.addView(intro)
        container.addView(user)
        container.addView(pass)
        container.addView(remember)
        hubAdvancedPanel.visibility = View.VISIBLE
        hubAdvancedToggle.text = "고급 도구 닫기"
        sessionState.text = "○ ${which.displayName} 로그인 정보 필요"
        status.text = "한 번 저장하면 이후에는 기존 WebView 세션을 우선 사용하고, 세션 만료 시에만 자동 로그인합니다."

        val dialog = AlertDialog.Builder(this)
            .setTitle("${which.displayName} 자동 로그인")
            .setView(container)
            .setNegativeButton("직접 로그인") { _, _ ->
                credentialVault.clear(which.wireName)
                status.text = "저장 계정을 사용하지 않습니다. 현재 공식 사이트에서 직접 로그인하세요."
                if (!continueAfterSave) webView.loadUrl(providerLoginUrl(which))
            }
            .setNeutralButton("저장 계정 삭제") { _, _ ->
                credentialVault.clear(which.wireName)
                status.text = "${which.displayName} 기기 저장 계정을 삭제했습니다. WebView 자체 로그인 세션은 유지됩니다."
            }
            .setPositiveButton("저장 후 로그인", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val username = user.text.toString().trim()
                val password = pass.text.toString()
                if (username.isBlank() || password.isBlank()) {
                    Toast.makeText(this, "아이디와 비밀번호를 입력하세요.", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                runCatching { credentialVault.save(which.wireName, username, password) }
                    .onFailure {
                        Toast.makeText(this, "기기 암호화 저장에 실패했습니다.", Toast.LENGTH_SHORT).show()
                        return@setOnClickListener
                    }
                startupCredentialPromptedProvider = which
                dialog.dismiss()
                status.text = "${which.displayName} 로그인 화면에서 저장 계정을 자동 입력합니다."
                attemptSavedCredentialLogin(which, "credential-dialog")
                if (!remember.isChecked) handler.postDelayed({ credentialVault.clear(which.wireName) }, 4_000L)
            }
        }
        dialog.show()
    }

    private fun probeLoginSurface'''
main = regex_once(
    main,
    r'    private fun showCredentialDialog\(which: ProviderId, continueAfterSave: Boolean\) \{.*?\n    \}\n\n    private fun probeLoginSurface',
    show_dialog,
    'showCredentialDialog'
)

auto_login = r'''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (provider != which) return
        val now = System.currentTimeMillis()
        if (credentialAutoLoginInFlight) {
            credentialAutoLoginSuppressedInFlight += 1
            return
        }
        if (now - credentialAutoLoginLastAttemptAtMs < 2_500L) {
            credentialAutoLoginSuppressedThrottle += 1
            return
        }
        val credential = credentialVault.load(which.wireName)
        if (credential == null) {
            credentialAutoLoginSuppressedNoCredential += 1
            if (startupCredentialPromptedProvider != which) {
                startupCredentialPromptedProvider = which
                showCredentialDialog(which, continueAfterSave = true)
            }
            return
        }
        credentialAutoLoginInFlight = true
        credentialAutoLoginLastAttemptAtMs = now
        credentialAutoLoginAttempts += 1
        credentialAutoLoginLastProvider = which.wireName
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
                      function label(el){return ((el.innerText||el.value||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\s+/g,' ').trim();}
                      var submit=controls.find(function(el){return /^(로그인|로그인하기|log\s*in|sign\s*in)$/i.test(label(el));})||controls.find(function(el){return (el.type||'').toLowerCase()==='submit';})||null;
                      if(submit){submit.click();return JSON.stringify({submitted:true,method:'button'});}
                      if(form){if(form.requestSubmit)form.requestSubmit();else form.submit();return JSON.stringify({submitted:true,method:'form'});}
                      return JSON.stringify({submitted:false,reason:'submit-control-missing'});
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
                credentialAwaitingLoginExitProvider = which
                credentialAutoLoginLastResult = "submitted-${result.optString("method", "unknown")}"
                status.text = "${which.displayName} 자동 로그인 제출 완료 · 실제 보호 페이지 인증을 확인 중입니다."
                handler.postDelayed({
                    checkSessionState { needsLogin, authenticated ->
                        if (provider != which) return@checkSessionState
                        if (authenticated) {
                            credentialAwaitingLoginExitProvider = null
                            credentialAutoLoginSuccesses += 1
                            credentialAutoLoginLastResult = "success-session-verified"
                            credentialAutoLoginLastAtMs = System.currentTimeMillis()
                            runCatching { sessionVault.captureAuthenticated(which.wireName, webView.url.orEmpty(), VERSION) }
                            CookieManager.getInstance().flush()
                            status.text = "${which.displayName} 자동 로그인 확인 완료 · 통합 수집을 이어갑니다."
                        } else if (needsLogin) {
                            credentialAutoLoginFailures += 1
                            credentialAutoLoginLastResult = "failed-login-still-required"
                            credentialAwaitingLoginExitProvider = null
                            status.text = "${which.displayName} 자동 로그인 확인에 실패했습니다. 로그인 폼/추가 인증을 확인하세요."
                        }
                    }
                }, 1_800L)
            } else {
                credentialAutoLoginFailures += 1
                credentialAutoLoginLastResult = "not-submitted-${result.optString("reason", "unknown")}"
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                scheduleLoginSurfaceDetection(which, "auto-login-retry-$reason")
            }
            persistJinhakAuthDiagnostics("credential-auto-login")
        }
    }
'''
main = regex_once(
    main,
    r'    private fun attemptSavedCredentialLogin\(which: ProviderId, reason: String\) \{.*?\n    \}\n',
    auto_login,
    'attemptSavedCredentialLogin'
)
main = main.replace('.put("passwordStored", false)', '.put("passwordStored", credentialVault.has(ProviderId.ADIGA.wireName) || credentialVault.has(ProviderId.JINHAK.wireName))')
main_path.write_text(main)

score_path = root / 'score/ScoreReviewUi.kt'
score = score_path.read_text()
score = replace_once(
    score,
    'button(p, "XLS / XLS / XLSX 파일 가져오기 · 시트/열 미리보기") {\n            activity.startActivity(Intent(activity, XlsxImportActivity::class.java).putExtra(XlsxImportActivity.EXTRA_SESSION_ID, session()))\n        }',
    'button(p, "Excel 자동 분석 · 바로 입력") {\n            activity.startActivity(Intent(activity, UnifiedExcelScoreActivity::class.java).putExtra(UnifiedExcelScoreActivity.EXTRA_SESSION_ID, session()))\n        }',
    'ScoreReview Excel launch'
)
score_path.write_text(score)

manifest_path = Path('app/src/main/AndroidManifest.xml')
manifest = manifest_path.read_text()
manifest = replace_once(manifest, 'android:label="Admission Hub v0.14.1 Excel + Adiga Score"', 'android:label="Admission Hub v0.14.2 Unified Auto"', 'Manifest label')
manifest = replace_once(
    manifest,
    '        <activity\n            android:name=".score.XlsxImportActivity"\n            android:exported="false" />',
    '        <activity\n            android:name=".score.UnifiedExcelScoreActivity"\n            android:exported="false" />\n        <activity\n            android:name=".score.XlsxImportActivity"\n            android:exported="false" />',
    'Manifest unified Excel activity'
)
manifest_path.write_text(manifest)

build_path = Path('app/build.gradle.kts')
build = build_path.read_text()
build = replace_once(build, 'versionCode = 114100', 'versionCode = 114200', 'Gradle versionCode')
build = replace_once(build, 'versionName = "0.14.1"', 'versionName = "0.14.2"', 'Gradle versionName')
build_path.write_text(build)

print('v0.14.2 background product patch applied')
