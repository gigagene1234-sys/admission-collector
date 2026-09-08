from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    assert count == 1, f"{label}: expected exactly one match, found {count}"
    return text.replace(old, new, 1)

root = Path('app/src/main/java/com/admissionhub/collector')
main_path = root / 'MainActivity.kt'
main = main_path.read_text()

main = replace_once(main, 'import android.widget.Button\n', 'import android.widget.Button\nimport android.widget.CheckBox\n', 'CheckBox import')
main = replace_once(main, 'private const val VERSION = "0.14.1"', 'private const val VERSION = "0.14.2"', 'MainActivity VERSION')
main = replace_once(main, 'private const val BUILD_CODE = 114100', 'private const val BUILD_CODE = 114200', 'MainActivity BUILD_CODE')
main = replace_once(main, 'text = "계정 로그인 화면 열기"', 'text = "로그인 기억 / 자동 로그인 설정"', 'login button label')
main = replace_once(main, '.put("credentialStorage", false)', '.put("credentialStorage", "android-keystore-aes-gcm")', 'startup credential storage diagnostic')

show_pattern = re.compile(
    r'    private fun showCredentialDialog\(which: ProviderId, continueAfterSave: Boolean\) \{.*?\n    \}\n\n    private fun scheduleLoginSurfaceDetection',
    re.S,
)
show_replacement = r'''    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {
        hubAdvancedPanel.visibility = View.VISIBLE
        hubAdvancedToggle.text = "고급 도구 닫기"
        val saved = credentialVault.load(which.wireName)
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 10, 36, 4)
        }
        val explanation = TextView(this).apply {
            text = "한 번 저장하면 이 기기의 AndroidKeyStore로 암호화해 보관하고, 다음 로그인 화면에서 자동 입력·제출합니다. 비밀번호는 입시자료 export나 클라우드 수집에 포함하지 않습니다."
            textSize = 13f
            setPadding(0, 6, 0, 10)
        }
        val username = EditText(this).apply {
            hint = "아이디 / 이메일"
            setSingleLine(true)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            saved?.let { setText(it.username) }
        }
        val password = EditText(this).apply {
            hint = "비밀번호"
            setSingleLine(true)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            saved?.let { setText(it.password) }
        }
        val remember = CheckBox(this).apply {
            text = "이 기기에 암호화 저장하고 다음부터 자동 로그인"
            isChecked = saved?.persisted != false
        }
        form.addView(explanation)
        form.addView(username)
        form.addView(password)
        form.addView(remember)

        val dialog = AlertDialog.Builder(this)
            .setTitle("${which.displayName} 로그인")
            .setView(form)
            .setNegativeButton("공식 사이트에서 직접 로그인") { _, _ ->
                status.text = "${which.displayName} 공식 사이트에서 직접 로그인하세요. 로그인 성공 세션은 WebView 쿠키로 유지됩니다."
                webView.loadUrl(which.homeUrl)
                handler.postDelayed({ scheduleLoginSurfaceDetection(which, "manual-login-open") }, 700L)
            }
            .setNeutralButton("저장 정보 삭제") { _, _ ->
                credentialVault.clear(which.wireName)
                sessionState.text = "○ ${which.displayName} 저장 로그인 정보 삭제됨"
                status.text = "저장된 아이디/비밀번호만 삭제했습니다. 현재 WebView 로그인 세션은 강제로 지우지 않습니다."
            }
            .setPositiveButton("저장하고 자동 로그인", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val user = username.text.toString().trim()
                val pass = password.text.toString()
                if (user.isBlank() || pass.isBlank()) {
                    Toast.makeText(this, "아이디와 비밀번호를 입력하세요.", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                runCatching { credentialVault.save(which.wireName, user, pass, remember.isChecked) }
                    .onFailure {
                        Toast.makeText(this, "로그인 정보 암호화 저장에 실패했습니다.", Toast.LENGTH_LONG).show()
                        return@setOnClickListener
                    }
                dialog.dismiss()
                sessionState.text = "○ ${which.displayName} 로그인 정보 준비됨"
                status.text = if (remember.isChecked) "암호화 저장 완료 · 로그인 화면에서 자동 로그인을 시도합니다." else "현재 실행 중에만 로그인 정보를 사용합니다."
                attemptSavedCredentialLogin(which, if (continueAfterSave) "credential-dialog-resume" else "credential-dialog")
            }
        }
        dialog.show()
    }

    private fun scheduleLoginSurfaceDetection'''
main, count = show_pattern.subn(show_replacement, main, count=1)
assert count == 1, f"showCredentialDialog replacement failed: {count}"

attempt_pattern = re.compile(
    r'    private fun attemptSavedCredentialLogin\(which: ProviderId, reason: String\) \{.*?\n    \}\n\n    private fun isFreshJinhakRealAuthProbe',
    re.S,
)
attempt_replacement = r'''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        val credential = credentialVault.load(which.wireName)
        if (credential == null) {
            credentialAutoLoginSuppressedNoCredential += 1
            if (startupCredentialPromptedProvider != which) startupCredentialPromptedProvider = which
            showCredentialDialog(which, continueAfterSave = true)
            return
        }
        if (credentialAutoLoginInFlight) {
            credentialAutoLoginSuppressedInFlight += 1
            return
        }
        val now = System.currentTimeMillis()
        if (now - credentialAutoLoginLastAttemptAtMs < 700L) {
            credentialAutoLoginSuppressedThrottle += 1
            return
        }
        if (credentialLoginSurfaceAttempts >= 3) {
            credentialAutoLoginSuppressedRetryLimit += 1
            credentialAutoLoginFailures += 1
            credentialAutoLoginLastResult = "retry-limit-manual-review"
            status.text = "자동 로그인 재시도 한도에 도달했습니다. 저장 정보가 바뀌었는지 확인하세요."
            showCredentialDialog(which, continueAfterSave = true)
            return
        }
        val current = webView.url.orEmpty()
        if (!isProviderUrl(current)) {
            webView.loadUrl(which.homeUrl)
            handler.postDelayed({ scheduleLoginSurfaceDetection(which, "auto-login-open-$reason") }, 700L)
            return
        }

        credentialAutoLoginInFlight = true
        credentialAutoLoginLastAttemptAtMs = now
        credentialAutoLoginAttempts += 1
        credentialLoginSurfaceAttempts += 1
        credentialAutoLoginLastProvider = which.wireName
        credentialAutoLoginLastAtMs = now
        credentialAutoLoginLastResult = "probing-login-surface"
        probeLoginSurface(which) { probe ->
            if (provider != which) {
                credentialAutoLoginInFlight = false
                credentialAutoLoginSuppressedProbeLost += 1
                return@probeLoginSurface
            }
            if (!probe.optBoolean("detected", false)) {
                credentialAutoLoginInFlight = false
                credentialAutoLoginSuppressedProbeLost += 1
                credentialAutoLoginLastResult = "login-surface-not-detected"
                scheduleLoginSurfaceDetection(which, "auto-login-probe-lost-$reason")
                return@probeLoginSurface
            }

            val usernameJs = JSONObject.quote(credential.username)
            val passwordJs = JSONObject.quote(credential.password)
            val script = """
                (function(){
                  try {
                    const visible = (el) => !!el && !el.disabled && el.type !== 'hidden' && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
                    const passwords = Array.from(document.querySelectorAll('input[type=password]')).filter(visible);
                    if (!passwords.length) return JSON.stringify({submitted:false,reason:'password-field-missing'});
                    const p = passwords[0];
                    const form = p.form || p.closest('form');
                    const scope = form || document;
                    const selectors = [
                      'input[type=email]',
                      'input[autocomplete=username]',
                      'input[name*=user i]', 'input[name*=login i]', 'input[name*=member i]', 'input[name*=id i]',
                      'input[id*=user i]', 'input[id*=login i]', 'input[id*=member i]', 'input[id*=id i]',
                      'input[type=text]'
                    ];
                    let u = null;
                    for (const s of selectors) {
                      const candidate = Array.from(scope.querySelectorAll(s)).find(el => visible(el) && el !== p);
                      if (candidate) { u = candidate; break; }
                    }
                    if (!u) return JSON.stringify({submitted:false,reason:'username-field-missing'});
                    const setValue = (el, value) => {
                      const proto = Object.getPrototypeOf(el);
                      const descriptor = Object.getOwnPropertyDescriptor(proto, 'value') || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
                      if (descriptor && descriptor.set) descriptor.set.call(el, value); else el.value = value;
                      el.dispatchEvent(new Event('input', {bubbles:true}));
                      el.dispatchEvent(new Event('change', {bubbles:true}));
                      el.dispatchEvent(new Event('blur', {bubbles:true}));
                    };
                    setValue(u, $usernameJs);
                    setValue(p, $passwordJs);
                    const submit = form && (form.querySelector('button[type=submit]') || form.querySelector('input[type=submit]') || Array.from(form.querySelectorAll('button')).find(visible));
                    if (submit && visible(submit)) submit.click();
                    else if (form && typeof form.requestSubmit === 'function') form.requestSubmit();
                    else if (form) form.submit();
                    else return JSON.stringify({submitted:false,reason:'submit-control-missing'});
                    return JSON.stringify({submitted:true});
                  } catch (e) {
                    return JSON.stringify({submitted:false,reason:'dom-exception'});
                  }
                })();
            """.trimIndent()
            webView.evaluateJavascript(script) { raw ->
                credentialAutoLoginInFlight = false
                val submitted = raw.orEmpty().contains("submitted") && raw.orEmpty().contains("true")
                if (submitted) {
                    credentialAutoLoginSubmissions += 1
                    credentialAwaitingLoginExitProvider = which
                    credentialAutoLoginLastResult = "submitted-awaiting-provider-verification"
                    credentialAutoLoginLastProvider = which.wireName
                    credentialAutoLoginLastAtMs = System.currentTimeMillis()
                    sessionState.text = "○ ${which.displayName} 자동 로그인 제출 · 인증 확인 중"
                    status.text = "저장된 암호화 로그인 정보로 로그인 폼을 제출했습니다. 보호 페이지 인증을 확인한 뒤 수집을 자동 재개합니다."
                    handler.postDelayed({
                        if (provider != which) return@postDelayed
                        checkSessionState { needsLogin, authenticated ->
                            if (authenticated) {
                                credentialAutoLoginLastResult = "authenticated-session-detected"
                                scheduleLoginSurfaceDetection(which, "auto-login-authenticated-$reason")
                            } else if (needsLogin) {
                                scheduleLoginSurfaceDetection(which, "auto-login-still-needs-login-$reason")
                            }
                        }
                    }, 1_100L)
                } else {
                    credentialAutoLoginFailures += 1
                    credentialAutoLoginLastResult = "login-form-submit-not-found"
                    credentialAutoLoginLastProvider = which.wireName
                    credentialAutoLoginLastAtMs = System.currentTimeMillis()
                    status.text = "자동 로그인 폼 연결에 실패했습니다. 저장 정보를 확인하거나 공식 사이트에서 직접 로그인하세요."
                    if (credentialLoginSurfaceAttempts >= 3) showCredentialDialog(which, continueAfterSave = true)
                    else handler.postDelayed({ scheduleLoginSurfaceDetection(which, "auto-login-dom-retry-$reason") }, 900L)
                }
            }
        }
    }

    private fun isFreshJinhakRealAuthProbe'''
main, count = attempt_pattern.subn(attempt_replacement, main, count=1)
assert count == 1, f"attemptSavedCredentialLogin replacement failed: {count}"

main_path.write_text(main)

# Make the transcript entry point describe the new single-screen behavior and remove the accidental duplicate XLS wording.
score_path = root / 'score/ScoreReviewUi.kt'
score = score_path.read_text()
score = replace_once(
    score,
    'button(p, "XLS / XLS / XLSX 파일 가져오기 · 시트/열 미리보기") {',
    'button(p, "학생부 Excel 분석 · 입력 · 대학환산 한 번에") {',
    'score import button label'
)
score_path.write_text(score)

print('v0.14.2 MainActivity auto-login and score entry patch applied')
