from pathlib import Path

MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
GRADLE = Path('app/build.gradle.kts')
MANIFEST = Path('app/src/main/AndroidManifest.xml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


main = MAIN.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

# v0.9.3: device-local encrypted ID/PW vault + actual form auto-login.
main = replace_once(main,
    'import android.os.Looper\n',
    'import android.os.Looper\nimport android.text.InputType\n',
    'InputType import')
main = replace_once(main,
    'import android.widget.Button\n',
    'import android.widget.Button\nimport android.widget.EditText\n',
    'EditText import')
main = replace_once(main,
    'import com.admissionhub.collector.session.SecureSessionVault\n',
    'import com.admissionhub.collector.session.SecureSessionVault\nimport com.admissionhub.collector.session.CredentialVault\n',
    'credential vault import')

main = replace_once(main,
    '    private lateinit var sessionVault: SecureSessionVault\n',
    '    private lateinit var sessionVault: SecureSessionVault\n    private lateinit var credentialVault: CredentialVault\n',
    'credential vault field')
main = replace_once(main,
    '        sessionVault = SecureSessionVault(this)\n        buildUi()\n',
    '        sessionVault = SecureSessionVault(this)\n        credentialVault = CredentialVault(this)\n        buildUi()\n',
    'credential vault init')

main = replace_once(main,
    '    private var startupSessionPreflightBypassed = false\n',
    '    private var startupSessionPreflightBypassed = false\n'
    '    private var credentialAutoLoginInFlight = false\n'
    '    private var credentialAutoLoginLastAttemptAtMs = 0L\n'
    '    private var credentialAutoLoginAttempts = 0\n'
    '    private var startupCredentialPromptedProvider: ProviderId? = null\n',
    'credential auto-login state')

main = replace_once(main,
    '        private const val VERSION = "0.9.2"\n        private const val BUILD_CODE = 10920\n',
    '        private const val VERSION = "0.9.3"\n        private const val BUILD_CODE = 10930\n',
    'main version')
gradle = replace_once(gradle,
    '        versionCode = 10920\n        versionName = "0.9.2"\n',
    '        versionCode = 10930\n        versionName = "0.9.3"\n',
    'gradle version')
manifest = replace_once(manifest,
    'android:label="Admission Collector v0.9.2 Persistent Session Bundle"',
    'android:label="Admission Collector v0.9.3 Local Credential Auto Login"',
    'manifest label')

main = replace_once(main,
    '            text = "로그인 세션 저장/갱신"\n            setOnClickListener { refreshSessionOrOpenLogin() }\n',
    '            text = "계정 자동로그인 설정"\n            setOnClickListener { showCredentialDialog(provider, continueAfterSave = false) }\n',
    'credential button')

# Whenever a true provider login page finishes loading, use the saved local credentials.
main = replace_once(main,
    '            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n                if (startupLoginPreflightActive) {\n',
    '            override fun onPageFinished(view: WebView, url: String) {\n'
    '                CookieManager.getInstance().flush()\n'
    '                if (isProviderLoginUrl(provider, url) && credentialVault.has(provider.wireName)) {\n'
    '                    handler.postDelayed({ attemptSavedCredentialLogin(provider, "page-finished") }, 220L)\n'
    '                }\n'
    '                if (startupLoginPreflightActive) {\n',
    'auto login on page finished')

# Prevent the startup orchestrator from forcing the login page for a user who has
# not yet saved credentials. If credentials exist, navigate only because auth was
# actually judged absent, then auto-submit them.
main = replace_once(main,
    '            if (!startupLoginOpenAttempted) {\n                startupLoginOpenAttempted = true\n                startupLoginStage = if (expectedProvider == ProviderId.ADIGA) "adiga-wait-login" else "jinhak-wait-login"\n',
    '            if (credentialVault.has(expectedProvider.wireName)) {\n'
    '                if (!startupLoginOpenAttempted) {\n'
    '                    startupLoginOpenAttempted = true\n'
    '                    startupLoginStage = if (expectedProvider == ProviderId.ADIGA) "adiga-auto-login" else "jinhak-auto-login"\n'
    '                    sessionState.text = "● ${expectedProvider.displayName} 저장 계정으로 자동 로그인"\n'
    '                    status.text = "${expectedProvider.displayName} 세션이 만료되어 저장된 계정으로 자동 로그인합니다."\n'
    '                    webView.loadUrl(providerLoginUrl(expectedProvider))\n'
    '                } else if (isProviderLoginUrl(expectedProvider, webView.url.orEmpty())) {\n'
    '                    attemptSavedCredentialLogin(expectedProvider, "startup-preflight")\n'
    '                }\n'
    '                scheduleStartupLoginPoll(expectedProvider, generation)\n'
    '                return@checkSessionState\n'
    '            }\n'
    '            if (!startupLoginOpenAttempted && startupCredentialPromptedProvider != expectedProvider) {\n'
    '                startupLoginOpenAttempted = true\n'
    '                startupCredentialPromptedProvider = expectedProvider\n'
    '                sessionState.text = "○ ${expectedProvider.displayName} 자동로그인 정보 필요"\n'
    '                status.text = "${expectedProvider.displayName} 계정정보를 한 번 저장하면 이후 로그인은 자동 처리됩니다."\n'
    '                showCredentialDialog(expectedProvider, continueAfterSave = true)\n'
    '                scheduleStartupLoginPoll(expectedProvider, generation)\n'
    '                return@checkSessionState\n'
    '            }\n'
    '            if (!startupLoginOpenAttempted) {\n'
    '                startupLoginOpenAttempted = true\n'
    '                startupLoginStage = if (expectedProvider == ProviderId.ADIGA) "adiga-wait-login" else "jinhak-wait-login"\n',
    'startup credential branch')

# Safe telemetry only: booleans/counts, never username/password.
main = replace_once(main,
    '                    .put("sessionSecretExported", false)),\n',
    '                    .put("sessionSecretExported", false)\n'
    '                    .put("adigaCredentialStored", credentialVault.has(ProviderId.ADIGA.wireName))\n'
    '                    .put("jinhakCredentialStored", credentialVault.has(ProviderId.JINHAK.wireName))\n'
    '                    .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)),\n',
    'credential telemetry')

# Insert the credential UI and form auto-submit helpers before startup orchestration.
marker = '    private fun startAutomaticLoginAndCollectionSequence(trigger: String) {\n'
if marker not in main:
    raise SystemExit('startup marker not found')
helpers = r'''    private fun providerLoginUrl(which: ProviderId): String = when (which) {
        ProviderId.JINHAK -> "https://www.jinhak.com/jh/member/login"
        ProviderId.ADIGA -> "https://www.adiga.kr/mbs/log/mbsLogView.do?menuId=PCMBSLOG1000"
    }

    private fun isProviderLoginUrl(which: ProviderId, rawUrl: String): Boolean {
        val url = rawUrl.lowercase()
        if (url.isBlank()) return false
        return when (which) {
            ProviderId.JINHAK -> url.contains("jinhak.com/") && (url.contains("/member/login") || url.contains("signin") || url.contains("login"))
            ProviderId.ADIGA -> url.contains("adiga.kr/") && (url.contains("/mbs/log/") || url.contains("mbslogview") || url.contains("login"))
        }
    }

    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {
        val existing = runCatching { credentialVault.load(which.wireName) }.getOrNull()
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val p = (18 * resources.displayMetrics.density).toInt()
            setPadding(p, p / 2, p, 0)
        }
        val username = EditText(this).apply {
            hint = "${which.displayName} 아이디"
            inputType = InputType.TYPE_CLASS_TEXT
            setText(existing?.username.orEmpty())
            setSelection(text.length)
        }
        val password = EditText(this).apply {
            hint = if (existing != null) "비밀번호 변경 시에만 다시 입력" else "비밀번호"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        layout.addView(username)
        layout.addView(password)

        val dialog = AlertDialog.Builder(this)
            .setTitle("${which.displayName} 자동로그인")
            .setMessage("이 기기 안에 Android Keystore로 암호화 저장합니다. 계정정보는 수집 JSON·로그·Cloud·웹 대시보드로 전송하지 않습니다.")
            .setView(layout)
            .setNeutralButton("저장정보 삭제") { _, _ ->
                credentialVault.clear(which.wireName)
                sessionState.text = "○ ${which.displayName} 자동로그인 정보 삭제됨"
            }
            .setNegativeButton("취소", null)
            .setPositiveButton("저장") { _, _ ->
                val u = username.text.toString().trim()
                val p = password.text.toString().ifBlank { existing?.password.orEmpty() }
                if (u.isBlank() || p.isBlank()) {
                    Toast.makeText(this, "아이디와 비밀번호를 모두 입력해야 합니다.", Toast.LENGTH_LONG).show()
                    return@setPositiveButton
                }
                runCatching { credentialVault.save(which.wireName, u, p) }
                    .onSuccess {
                        sessionState.text = "● ${which.displayName} 자동로그인 정보 저장됨"
                        recordRuntimeEvent("credential-vault-updated", JSONObject()
                            .put("provider", which.wireName)
                            .put("credentialStored", true)
                            .put("credentialExported", false))
                        if (continueAfterSave) {
                            credentialAutoLoginInFlight = false
                            credentialAutoLoginLastAttemptAtMs = 0L
                            webView.loadUrl(providerLoginUrl(which))
                        }
                    }
                    .onFailure { Toast.makeText(this, "암호화 저장 실패: ${it.javaClass.simpleName}", Toast.LENGTH_LONG).show() }
            }
            .create()
        dialog.show()
    }

    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (provider != which) return
        val now = System.currentTimeMillis()
        if (credentialAutoLoginInFlight && now - credentialAutoLoginLastAttemptAtMs < 6_000L) return
        if (now - credentialAutoLoginLastAttemptAtMs < 1_500L) return
        val credentials = runCatching { credentialVault.load(which.wireName) }.getOrNull() ?: return
        val current = webView.url.orEmpty()
        if (!isProviderLoginUrl(which, current)) return

        credentialAutoLoginInFlight = true
        credentialAutoLoginLastAttemptAtMs = now
        credentialAutoLoginAttempts += 1
        val userJs = JSONObject.quote(credentials.username)
        val passJs = JSONObject.quote(credentials.password)
        val script = """
            (function(){
              try {
                function visible(el){ if(!el) return false; var s=getComputedStyle(el); if(s.display==='none'||s.visibility==='hidden') return false; var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
                function setValue(el,value){
                  var d=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value');
                  if(d&&d.set) d.set.call(el,value); else el.value=value;
                  ['input','change','blur'].forEach(function(t){el.dispatchEvent(new Event(t,{bubbles:true}));});
                }
                var pass=Array.from(document.querySelectorAll('input[type=password]')).find(visible);
                var users=Array.from(document.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio])')).filter(visible);
                function score(el){
                  var meta=((el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.autocomplete||'')).toLowerCase();
                  var n=0;
                  if(/아이디|user|login|member|email|account/.test(meta)) n+=20;
                  if((el.type||'').toLowerCase()==='email') n+=5;
                  return n;
                }
                users.sort(function(a,b){return score(b)-score(a);});
                var user=users[0];
                if(!user||!pass) return 'fields-not-found';
                setValue(user,$userJs); setValue(pass,$passJs);
                var form=pass.form||user.form||pass.closest('form')||user.closest('form');
                var controls=Array.from(document.querySelectorAll('button,input[type=submit],a[role=button]')).filter(visible);
                var submit=controls.find(function(el){var t=((el.innerText||el.value||el.textContent||'')+'').replace(/\\s+/g,'').trim(); return /^(로그인|로그인하기|login|signin)$/i.test(t);});
                if(form&&typeof form.requestSubmit==='function'){ if(submit&&submit.form===form) form.requestSubmit(submit); else form.requestSubmit(); return 'submitted-form'; }
                if(submit){ submit.click(); return 'submitted-click'; }
                if(form){ form.submit(); return 'submitted-native'; }
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
                .put("credentialStored", true)
                .put("credentialExported", false))
            sessionState.text = if (result.startsWith("submitted")) "● ${which.displayName} 자동 로그인 제출됨" else "△ ${which.displayName} 자동 로그인: $result"
            handler.postDelayed({
                checkSessionState { needsLogin, authenticated ->
                    if (authenticated) {
                        val url = webView.url.orEmpty()
                        if (url.isNotBlank()) runCatching { sessionVault.captureAuthenticated(which.wireName, url, VERSION) }
                        if (batchRunning && batchPausedForLogin) resumeAfterLogin()
                    } else if (needsLogin && startupLoginPreflightActive) {
                        val generation = startupLoginPollGeneration
                        scheduleStartupLoginPoll(which, generation)
                    }
                }
            }, 900L)
        }
    }

'''
main = main.replace(marker, helpers + marker, 1)

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

print('v0.9.3 credential auto-login patch applied')
