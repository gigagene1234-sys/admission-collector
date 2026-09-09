from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"

main = MAIN.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

# -----------------------------------------------------------------------------
# Version metadata
# -----------------------------------------------------------------------------
gradle = gradle.replace('versionCode = 117500', 'versionCode = 118000')
gradle = gradle.replace('versionName = "0.17.5"', 'versionName = "0.18.0"')
manifest = manifest.replace(
    'android:label="Admission Hub v0.17.5 Runtime-Stable High3 Sandbox"',
    'android:label="Admission Hub v0.18.0 Dedicated Auto Login"'
)
main = main.replace('private const val VERSION = "0.17.4"', 'private const val VERSION = "0.18.0"')
main = main.replace('private const val BUILD_CODE = 117400', 'private const val BUILD_CODE = 118000')

# Dedicated auth policy import.
import_anchor = 'import com.admissionhub.collector.jinhak.JinhakStrictHigh3Sandbox\n'
if import_anchor not in main:
    raise SystemExit('JinhakStrictHigh3Sandbox import anchor not found')
main = main.replace(
    import_anchor,
    import_anchor + 'import com.admissionhub.collector.jinhak.JinhakDedicatedAuthPolicy\n',
    1,
)

# Dedicated auth WebView lives independently from the collector WebView.
field_anchor = '    private lateinit var webView: WebView\n'
if field_anchor not in main:
    raise SystemExit('webView field anchor not found')
main = main.replace(
    field_anchor,
    field_anchor +
    '    private lateinit var authWebView: WebView\n'
    '    private lateinit var authHost: FrameLayout\n',
    1,
)

# v0.18.0 deterministic auth diagnostics/state. No secret values are stored here.
diag_field_anchor = '    private var jinhakV0174ExplicitHigh3Confirmations = 0\n'
if diag_field_anchor not in main:
    raise SystemExit('v0174 diagnostic field anchor not found')
main = main.replace(
    diag_field_anchor,
    diag_field_anchor + '''    private var jinhakV0180AuthState = "IDLE"
    private var jinhakV0180AuthGeneration = 0
    private var jinhakV0180AuthSubmitGeneration = -1
    private var jinhakV0180AuthFillAttempt = 0
    private var jinhakV0180AuthHigh3ProbeGeneration = -1
    private var jinhakV0180AuthRendererRestarts = 0
    private var jinhakV0180AuthSubmitAttempts = 0
    private var jinhakV0180AuthSubmissions = 0
    private var jinhakV0180AuthSuccesses = 0
    private var jinhakV0180AuthFailures = 0
    private var jinhakV0180CollectorLoginRouteLoads = 0
    private var jinhakV0180LowerGradeBlocks = 0
    private var jinhakV0180AuthLastReason = ""
    private var jinhakV0180AuthLastSafePath = ""
''',
    1,
)

# Bounded auth retry constants. There is deliberately no recursive auth poll loop.
const_anchor = '        private const val MAX_JINHAK_REAUTH_CYCLES = 3\n'
if const_anchor not in main:
    raise SystemExit('auth constants anchor not found')
main = main.replace(
    const_anchor,
    const_anchor +
    '        private const val V0180_AUTH_MAX_FILL_ATTEMPTS = 3\n'
    '        private const val V0180_AUTH_RENDERER_RESTART_LIMIT = 2\n',
    1,
)

# Configure both WebViews after the UI creates them.
oncreate_anchor = '        configureWebView()\n        initializeProcessResumeJournal()\n'
if oncreate_anchor not in main:
    raise SystemExit('onCreate configure anchor not found')
main = main.replace(
    oncreate_anchor,
    '        configureWebView()\n        configureDedicatedJinhakAuthWebView()\n        initializeProcessResumeJournal()\n',
    1,
)

# Build a dedicated auth surface in the same browser stack. It shares WebView/CookieManager's
# native cookie jar, but its navigation policy is separate from the high3-only collector.
ui_anchor = '''        webView = WebView(this)
        webView.settings.useWideViewPort = true
        webView.settings.loadWithOverviewMode = false
        batchCover = TextView(this).apply {'''
if ui_anchor not in main:
    raise SystemExit('buildUi webView anchor not found')
ui_replacement = '''        webView = WebView(this)
        webView.settings.useWideViewPort = true
        webView.settings.loadWithOverviewMode = false
        authWebView = WebView(this)
        authHost = FrameLayout(this).apply {
            visibility = View.GONE
            setBackgroundColor(android.graphics.Color.WHITE)
            addView(authWebView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
        }
        batchCover = TextView(this).apply {'''
main = main.replace(ui_anchor, ui_replacement, 1)

stack_anchor = '''            addView(webView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(slowLaneHost, FrameLayout.LayoutParams('''
if stack_anchor not in main:
    raise SystemExit('browserStack anchor not found')
stack_replacement = '''            addView(webView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(authHost, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(slowLaneHost, FrameLayout.LayoutParams('''
main = main.replace(stack_anchor, stack_replacement, 1)

# -----------------------------------------------------------------------------
# Re-enable encrypted on-device Jinhak credentials.
# v0.17.x deliberately cleared/disabled Jinhak credentials; v0.18.0 uses the existing
# Android-Keystore CredentialVault and a dedicated auth WebView instead.
# -----------------------------------------------------------------------------
show_pattern = re.compile(
    r'    private fun showCredentialDialog\(which: ProviderId, continueAfterSave: Boolean\) \{\n'
    r'        if \(which == ProviderId\.JINHAK\) \{.*?\n'
    r'        \}\n'
    r'        if \(credentialAutoLoginInFlight\) return',
    re.S,
)
main, count = show_pattern.subn(
    '    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {\n'
    '        if (credentialAutoLoginInFlight) return',
    main,
    count=1,
)
if count != 1:
    raise SystemExit(f'failed to re-enable Jinhak credential dialog: {count}')

main = main.replace(
    'if (which == ProviderId.JINHAK) openJinhakV0174StrictEntry("credential-dialog-direct-login")\n                    else loadMainUrl(providerLoginUrl(which))',
    'if (which == ProviderId.JINHAK) startV0180DedicatedJinhakAuth("credential-dialog-direct-login", forceManual = true)\n                    else loadMainUrl(providerLoginUrl(which))',
    1,
)

baseline_pattern = re.compile(
    r'    private fun attemptSavedCredentialLoginV0912Baseline\(reason: String\) \{.*?\n    \}\n'
    r'    private fun attemptSavedCredentialLogin\(which: ProviderId, reason: String\) \{\n'
    r'        if \(which == ProviderId\.JINHAK\) \{.*?\n'
    r'        \}\n'
    r'        if \(provider != which\) return\n'
    r'        if \(which == ProviderId\.JINHAK\) \{.*?\n'
    r'        \}\n',
    re.S,
)
baseline_replacement = '''    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {
        if (provider != ProviderId.JINHAK) return
        startV0180DedicatedJinhakAuth("legacy-entry:$reason")
    }
    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (which == ProviderId.JINHAK) {
            provider = ProviderId.JINHAK
            startV0180DedicatedJinhakAuth("saved-credential:$reason")
            return
        }
        if (provider != which) return
'''
main, count = baseline_pattern.subn(baseline_replacement, main, count=1)
if count != 1:
    raise SystemExit(f'failed to replace saved credential entry: {count}')

# -----------------------------------------------------------------------------
# Collector routes never own login again. Login is redirected into the dedicated auth WebView.
# -----------------------------------------------------------------------------
member_loader_pattern = re.compile(
    r'    private fun loadJinhakV0174SiteMemberLogin\(target: String, source: String\): Boolean \{.*?\n    \}\n\n    private fun loadJinhakV0174High3Only',
    re.S,
)
member_loader_replacement = '''    private fun loadJinhakV0174SiteMemberLogin(target: String, source: String): Boolean {
        if (provider != ProviderId.JINHAK) return false
        jinhakV0180CollectorLoginRouteLoads += 1
        recordRuntimeEvent(
            "jinhak-v0180-login-rerouted-to-auth-webview",
            JSONObject().put("source", source.take(80)).put("safePath", runtimeSafePath(target))
        )
        startV0180DedicatedJinhakAuth("site-member:$source")
        return false
    }

    private fun loadJinhakV0174High3Only'''
main, count = member_loader_pattern.subn(member_loader_replacement, main, count=1)
if count != 1:
    raise SystemExit(f'failed to replace member login loader: {count}')

# Strict entry automatically authenticates if the app does not already have an explicitly
# confirmed high3 session. After success, the collector receives only a high3 URL.
strict_entry_pattern = re.compile(
    r'    private fun openJinhakV0174StrictEntry\(reason: String\) \{.*?\n    \}\n\n    private fun safeJinhakV0174Back',
    re.S,
)
strict_entry_replacement = '''    private fun openJinhakV0174StrictEntry(reason: String) {
        if (provider != ProviderId.JINHAK) provider = ProviderId.JINHAK
        jinhakV0174StrictEntryRequests += 1
        if (!jinhakUserSessionConfirmed || !jinhakAuthVerifiedForBatch) {
            startV0180DedicatedJinhakAuth("strict-entry:$reason")
            return
        }
        batchPausedForLogin = false
        loadJinhakV0174High3Only(JinhakStrictHigh3Sandbox.strictEntryUrl(), "strict-entry:$reason")
        sessionState.text = "● 진학사 고3 전용 세션"
        status.text = "고3 전용 수집 화면을 열었습니다."
    }

    private fun safeJinhakV0174Back'''
main, count = strict_entry_pattern.subn(strict_entry_replacement, main, count=1)
if count != 1:
    raise SystemExit(f'failed to replace strict entry: {count}')

# If a blocked collector navigation is actually a login route, dispatch auth exactly once into
# the auth WebView. The collector page remains untouched.
block_marker = '        noteJinhakV0174Decision(source, target, decision)\n\n        // v0.17.5:'
if block_marker not in main:
    raise SystemExit('v0175 block marker not found')
main = main.replace(
    block_marker,
    '''        noteJinhakV0174Decision(source, target, decision)
        if (JinhakDedicatedAuthPolicy.isLoginSurface(target)) {
            jinhakV0180CollectorLoginRouteLoads += 1
            handler.post { startV0180DedicatedJinhakAuth("collector-route:$source") }
        }

        // v0.17.5:''',
    1,
)

# Network main-frame login redirect: block it in collector and hand auth to authWebView.
intercept_anchor = '''                    if (request.isForMainFrame) {
                        val decision = JinhakStrictHigh3Sandbox.decision(target)'''
if intercept_anchor not in main:
    raise SystemExit('collector intercept main-frame anchor not found')
main = main.replace(
    intercept_anchor,
    '''                    if (request.isForMainFrame) {
                        if (JinhakDedicatedAuthPolicy.isLoginSurface(target)) {
                            handler.post {
                                jinhakV0180CollectorLoginRouteLoads += 1
                                startV0180DedicatedJinhakAuth("collector-network-login")
                            }
                            return jinhakV0174BlockedResponse("dedicated-auth-route")
                        }
                        val decision = JinhakStrictHigh3Sandbox.decision(target)''',
    1,
)

# Navigation callback login redirect.
override_anchor = '''                if (!request.isForMainFrame) return false
                val decision = JinhakStrictHigh3Sandbox.decision(target)'''
if override_anchor not in main:
    raise SystemExit('collector override anchor not found')
main = main.replace(
    override_anchor,
    '''                if (!request.isForMainFrame) return false
                if (JinhakDedicatedAuthPolicy.isLoginSurface(target)) {
                    jinhakV0180CollectorLoginRouteLoads += 1
                    startV0180DedicatedJinhakAuth("collector-navigation-login")
                    return true
                }
                val decision = JinhakStrictHigh3Sandbox.decision(target)''',
    1,
)

# Page callbacks must never allow a login document to become the collector document.
started_anchor = '''                if (provider == ProviderId.JINHAK) {
                    val decision = JinhakStrictHigh3Sandbox.decision(url)
                    when (decision) {'''
if started_anchor not in main:
    raise SystemExit('collector page-started anchor not found')
main = main.replace(
    started_anchor,
    '''                if (provider == ProviderId.JINHAK) {
                    if (JinhakDedicatedAuthPolicy.isLoginSurface(url)) {
                        jinhakV0180CollectorLoginRouteLoads += 1
                        runCatching { view.stopLoading() }
                        startV0180DedicatedJinhakAuth("collector-page-started-login")
                        return
                    }
                    val decision = JinhakStrictHigh3Sandbox.decision(url)
                    when (decision) {''',
    1,
)

finished_anchor = '''                if (provider == ProviderId.JINHAK) {
                    val visible = webView.url.orEmpty()'''
if finished_anchor not in main:
    raise SystemExit('collector page-finished anchor not found')
main = main.replace(
    finished_anchor,
    '''                if (provider == ProviderId.JINHAK) {
                    if (JinhakDedicatedAuthPolicy.isLoginSurface(url)) {
                        jinhakV0180CollectorLoginRouteLoads += 1
                        startV0180DedicatedJinhakAuth("collector-page-finished-login")
                        return
                    }
                    val visible = webView.url.orEmpty()''',
    1,
)

# -----------------------------------------------------------------------------
# Dedicated v0.18.0 auth state machine.
# -----------------------------------------------------------------------------
auth_insert_anchor = '    private fun isFreshJinhakRealAuthProbe(): Boolean = false\n'
if auth_insert_anchor not in main:
    raise SystemExit('auth insertion anchor not found')

auth_block = r'''    @Suppress("SetJavaScriptEnabled")
    private fun configureDedicatedJinhakAuthWebView() {
        if (!::authWebView.isInitialized) return
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(authWebView, true)
        }
        authWebView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = userAgentString + " AdmissionHubAuth/$VERSION"
        }
        authWebView.webChromeClient = WebChromeClient()
        authWebView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val target = request.url?.toString().orEmpty()
                if (JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                    handler.post {
                        jinhakV0180LowerGradeBlocks += 1
                        persistJinhakAuthDiagnostics("v0180-auth-lower-grade-request-block")
                    }
                    return jinhakV0174BlockedResponse("v0180-lower-grade-auth")
                }
                if (request.isForMainFrame && !JinhakDedicatedAuthPolicy.allowsAuthMainFrame(target)) {
                    return jinhakV0174BlockedResponse("v0180-auth-mainframe-policy")
                }
                return super.shouldInterceptRequest(view, request)
            }

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (!request.isForMainFrame) return false
                val route = JinhakDedicatedAuthPolicy.classify(target)
                if (route == JinhakDedicatedAuthPolicy.Route.BLOCK_LOWER_GRADE) {
                    jinhakV0180LowerGradeBlocks += 1
                    persistJinhakAuthDiagnostics("v0180-auth-lower-grade-mainframe-block")
                    return true
                }
                return !JinhakDedicatedAuthPolicy.allowsAuthMainFrame(target)
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                jinhakV0180AuthLastSafePath = runtimeSafePath(url)
                when (JinhakDedicatedAuthPolicy.classify(url)) {
                    JinhakDedicatedAuthPolicy.Route.LOGIN_FORM,
                    JinhakDedicatedAuthPolicy.Route.MEMBER_LOGIN -> jinhakV0180AuthState = "FORM_LOADING"
                    JinhakDedicatedAuthPolicy.Route.HIGH3_SUCCESS -> jinhakV0180AuthState = "HIGH3_RETURN_LOADING"
                    JinhakDedicatedAuthPolicy.Route.BLOCK_LOWER_GRADE -> {
                        jinhakV0180LowerGradeBlocks += 1
                        runCatching { view.stopLoading() }
                    }
                    else -> Unit
                }
                persistJinhakAuthDiagnostics("v0180-auth-page-started")
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                jinhakV0180AuthLastSafePath = runtimeSafePath(url)
                when (JinhakDedicatedAuthPolicy.classify(url)) {
                    JinhakDedicatedAuthPolicy.Route.HIGH3_SUCCESS -> {
                        completeV0180DedicatedJinhakAuth(url)
                        return
                    }
                    JinhakDedicatedAuthPolicy.Route.LOGIN_FORM,
                    JinhakDedicatedAuthPolicy.Route.MEMBER_LOGIN -> {
                        jinhakV0180AuthState = "FORM_READY"
                        attemptV0180JinhakAuthAutofill(jinhakV0180AuthGeneration, 0)
                    }
                    JinhakDedicatedAuthPolicy.Route.JINHAK_SUPPORT -> {
                        // Some login implementations hand off through a same-site support/root page.
                        // After a submitted form, probe high3 exactly once; no recurring auth poll exists.
                        if (jinhakV0180AuthSubmitGeneration == jinhakV0180AuthGeneration &&
                            jinhakV0180AuthHigh3ProbeGeneration != jinhakV0180AuthGeneration) {
                            jinhakV0180AuthHigh3ProbeGeneration = jinhakV0180AuthGeneration
                            handler.postDelayed({
                                if (jinhakV0180AuthGeneration == jinhakV0180AuthHigh3ProbeGeneration &&
                                    ::authHost.isInitialized && authHost.visibility == View.VISIBLE) {
                                    authWebView.loadUrl(JinhakStrictHigh3Sandbox.strictEntryUrl())
                                }
                            }, 350L)
                        }
                    }
                    JinhakDedicatedAuthPolicy.Route.BLOCK_LOWER_GRADE -> {
                        jinhakV0180LowerGradeBlocks += 1
                        runCatching { view.stopLoading() }
                    }
                    else -> Unit
                }
                persistJinhakAuthDiagnostics("v0180-auth-page-finished")
            }

            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                jinhakV0180AuthRendererRestarts += 1
                jinhakV0180AuthFailures += 1
                val activeGeneration = jinhakV0180AuthGeneration
                recordRuntimeEvent(
                    "jinhak-v0180-auth-renderer-gone",
                    JSONObject()
                        .put("didCrash", detail?.didCrash() ?: false)
                        .put("generation", activeGeneration)
                        .put("restart", jinhakV0180AuthRendererRestarts),
                    synchronous = true
                )
                if (jinhakV0180AuthRendererRestarts > V0180_AUTH_RENDERER_RESTART_LIMIT) {
                    jinhakV0180AuthState = "AUTH_RENDERER_FAILED"
                    status.text = "진학사 로그인 렌더러가 반복 종료되었습니다. 로그인 화면을 그대로 열어 수동 완료할 수 있습니다."
                    return true
                }
                handler.postDelayed({ recreateV0180AuthWebView(activeGeneration) }, 1_200L)
                return true
            }
        }
    }

    private fun startV0180DedicatedJinhakAuth(reason: String, forceManual: Boolean = false) {
        provider = ProviderId.JINHAK
        jinhakV0180AuthLastReason = reason.take(100)
        if (::authHost.isInitialized && authHost.visibility == View.VISIBLE &&
            jinhakV0180AuthState !in setOf("IDLE", "SUCCESS", "AUTH_RENDERER_FAILED")) {
            persistJinhakAuthDiagnostics("v0180-auth-duplicate-start-suppressed")
            return
        }

        val credential = credentialVault.load(ProviderId.JINHAK.wireName)
        if (credential == null && !forceManual) {
            jinhakV0180AuthState = "CREDENTIALS_REQUIRED"
            batchPausedForLogin = batchRunning
            sessionState.text = "○ 진학사 자동 로그인 계정 1회 설정 필요"
            status.text = "기기에 저장된 진학사 계정이 없습니다. 한 번 저장하면 이후 수집부터 자동 로그인합니다."
            if (startupCredentialPromptedProvider != ProviderId.JINHAK) {
                startupCredentialPromptedProvider = ProviderId.JINHAK
                handler.post { showCredentialDialog(ProviderId.JINHAK, continueAfterSave = true) }
            }
            persistJinhakAuthDiagnostics("v0180-credentials-required")
            return
        }

        jinhakV0180AuthGeneration += 1
        jinhakV0180AuthSubmitGeneration = -1
        jinhakV0180AuthFillAttempt = 0
        jinhakV0180AuthHigh3ProbeGeneration = -1
        jinhakV0180AuthRendererRestarts = 0
        jinhakV0180AuthState = if (credential == null) "MANUAL_LOGIN" else "AUTH_WEBVIEW_LOADING"
        batchPausedForLogin = batchRunning
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
        if (::authHost.isInitialized) authHost.visibility = View.VISIBLE
        if (::authWebView.isInitialized) {
            authWebView.visibility = View.VISIBLE
            runCatching { authWebView.stopLoading() }
            runCatching { authWebView.clearHistory() }
            authWebView.loadUrl(JinhakDedicatedAuthPolicy.LOGIN_URL)
        }
        sessionState.text = if (credential == null) "○ 진학사 로그인 화면" else "● 진학사 자동 로그인 실행 중"
        status.text = if (credential == null) {
            "진학사 로그인 화면을 열었습니다. 로그인 완료 후 고3 화면으로 이동하면 자동으로 수집을 재개합니다."
        } else {
            "진학사 전용 로그인 WebView에서 저장 계정을 자동 입력합니다. 수집 WebView는 로그인 페이지를 열지 않습니다."
        }
        persistJinhakAuthDiagnostics("v0180-auth-start")
    }

    private fun attemptV0180JinhakAuthAutofill(generation: Int, attempt: Int) {
        if (provider != ProviderId.JINHAK || generation != jinhakV0180AuthGeneration) return
        if (!::authHost.isInitialized || authHost.visibility != View.VISIBLE) return
        if (jinhakV0180AuthSubmitGeneration == generation) return
        val credential = credentialVault.load(ProviderId.JINHAK.wireName) ?: run {
            jinhakV0180AuthState = "WAITING_USER_LOGIN"
            return
        }
        if (attempt >= V0180_AUTH_MAX_FILL_ATTEMPTS) {
            jinhakV0180AuthFailures += 1
            jinhakV0180AuthState = "FORM_NOT_AUTOMATABLE"
            status.text = "자동 입력 폼을 찾지 못했습니다. 현재 로그인 화면에서 직접 로그인하면 고3 복귀 후 자동 재개합니다."
            persistJinhakAuthDiagnostics("v0180-auth-form-not-found")
            return
        }

        jinhakV0180AuthFillAttempt = attempt + 1
        jinhakV0180AuthSubmitAttempts += 1
        credentialAutoLoginAttempts += 1
        credentialAutoLoginLastProvider = ProviderId.JINHAK.wireName
        credentialAutoLoginLastAtMs = System.currentTimeMillis()
        val userJson = JSONObject.quote(credential.username)
        val passJson = JSONObject.quote(credential.password)
        val js = """
            (function(){
              try{
                function visible(el){if(!el)return false;var s=getComputedStyle(el);if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0')return false;var r=el.getBoundingClientRect();return r.width>0&&r.height>0;}
                function setValue(el,v){
                  try{var proto=Object.getPrototypeOf(el);var d=Object.getOwnPropertyDescriptor(proto,'value')||Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');if(d&&d.set)d.set.call(el,v);else el.value=v;}catch(e){el.value=v;}
                  try{el.focus();el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:v}));}catch(e){try{el.dispatchEvent(new Event('input',{bubbles:true}));}catch(x){}}
                  try{el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();}catch(e){}
                }
                var roots=[document];
                try{Array.from(document.querySelectorAll('*')).forEach(function(el){if(el.shadowRoot)roots.push(el.shadowRoot);});}catch(e){}
                for(var r=0;r<roots.length;r++){
                  var root=roots[r];
                  var passList=[];try{passList=Array.from(root.querySelectorAll('input[type=password]')).filter(visible);}catch(e){}
                  for(var p=0;p<passList.length;p++){
                    var pass=passList[p],form=pass.form||pass.closest('form'),base=form||root;
                    var users=[];try{users=Array.from(base.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                    if(!users.length)continue;
                    function score(el){var m=((el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.autocomplete||'')).toLowerCase();var n=0;if(/아이디|user|login|member|email|account/.test(m))n+=80;if((el.autocomplete||'').toLowerCase()==='username')n+=120;if(/search|검색/.test(m))n-=300;if(form&&el.form===form)n+=100;return n;}
                    users.sort(function(a,b){return score(b)-score(a);});
                    var user=users[0];if(!user)continue;
                    setValue(user,$userJson);setValue(pass,$passJson);
                    var controls=[];try{controls=Array.from(base.querySelectorAll('button,input[type=submit],input[type=button],[role=button]')).filter(visible);}catch(e){}
                    function label(el){return ((el.innerText||el.value||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\s+/g,' ').trim();}
                    var submit=controls.find(function(el){return /^(로그인|로그인하기|log\s*in|sign\s*in)$/i.test(label(el));})||controls.find(function(el){return (el.type||'').toLowerCase()==='submit';})||null;
                    if(submit){submit.click();return JSON.stringify({submitted:true,method:'button'});}
                    if(form){if(form.requestSubmit)form.requestSubmit();else form.submit();return JSON.stringify({submitted:true,method:'form'});}
                    return JSON.stringify({submitted:false,reason:'submit-control-missing'});
                  }
                }
                return JSON.stringify({submitted:false,reason:'visible-login-fields-missing'});
              }catch(e){return JSON.stringify({submitted:false,reason:'script-error'});}
            })();
        """.trimIndent()

        authWebView.evaluateJavascript(js) { raw ->
            if (generation != jinhakV0180AuthGeneration) return@evaluateJavascript
            val decoded = runCatching { JSONTokener(raw).nextValue() as? String }.getOrNull().orEmpty()
            val result = runCatching { JSONObject(decoded) }.getOrDefault(JSONObject())
            if (result.optBoolean("submitted", false)) {
                jinhakV0180AuthSubmitGeneration = generation
                jinhakV0180AuthSubmissions += 1
                credentialAutoLoginSubmissions += 1
                credentialAutoLoginLastResult = "v0180-submitted-${result.optString("method", "unknown")}"
                jinhakV0180AuthState = "SUBMITTED"
                status.text = "진학사 자동 로그인 제출 완료 · 서버의 고3 복귀를 기다립니다."
                handler.postDelayed({ inspectV0180SubmittedLogin(generation) }, 5_000L)
            } else {
                credentialAutoLoginLastResult = "v0180-not-submitted-${result.optString("reason", "unknown")}"
                val next = attempt + 1
                if (next < V0180_AUTH_MAX_FILL_ATTEMPTS) {
                    val delay = when (next) { 1 -> 350L; else -> 900L }
                    handler.postDelayed({ attemptV0180JinhakAuthAutofill(generation, next) }, delay)
                } else {
                    jinhakV0180AuthFailures += 1
                    credentialAutoLoginFailures += 1
                    jinhakV0180AuthState = "FORM_NOT_AUTOMATABLE"
                    status.text = "진학사 로그인 폼 자동 입력에 실패했습니다. 현재 화면에서 직접 로그인하면 수집은 자동 재개됩니다."
                }
            }
            persistJinhakAuthDiagnostics("v0180-auth-autofill-result")
        }
    }

    private fun inspectV0180SubmittedLogin(generation: Int) {
        if (generation != jinhakV0180AuthGeneration || !::authHost.isInitialized || authHost.visibility != View.VISIBLE) return
        val current = authWebView.url.orEmpty()
        if (JinhakDedicatedAuthPolicy.isHigh3Success(current)) {
            completeV0180DedicatedJinhakAuth(current)
            return
        }
        if (!JinhakDedicatedAuthPolicy.isLoginSurface(current)) return
        val js = """
            (function(){
              try{
                var t=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,30000);
                var bad=/(아이디|비밀번호).*(확인|일치하지|잘못|오류|실패)|로그인.*실패/i.test(t);
                return JSON.stringify({credentialError:bad});
              }catch(e){return JSON.stringify({credentialError:false});}
            })();
        """.trimIndent()
        authWebView.evaluateJavascript(js) { raw ->
            if (generation != jinhakV0180AuthGeneration) return@evaluateJavascript
            val decoded = runCatching { JSONTokener(raw).nextValue() as? String }.getOrNull().orEmpty()
            val result = runCatching { JSONObject(decoded) }.getOrDefault(JSONObject())
            if (result.optBoolean("credentialError", false)) {
                jinhakV0180AuthFailures += 1
                credentialAutoLoginFailures += 1
                credentialAutoLoginLastResult = "v0180-credential-rejected"
                jinhakV0180AuthState = "CREDENTIAL_REJECTED"
                status.text = "진학사에서 로그인 정보 확인 오류를 반환했습니다. 저장 계정을 다시 입력하면 즉시 재시도합니다."
                startupCredentialPromptedProvider = null
                showCredentialDialog(ProviderId.JINHAK, continueAfterSave = true)
            }
            persistJinhakAuthDiagnostics("v0180-auth-submit-inspection")
        }
    }

    private fun completeV0180DedicatedJinhakAuth(successUrl: String) {
        if (provider != ProviderId.JINHAK) return
        jinhakV0180AuthState = "SUCCESS"
        jinhakV0180AuthSuccesses += 1
        if (jinhakV0180AuthSubmitGeneration == jinhakV0180AuthGeneration) {
            credentialAutoLoginSuccesses += 1
            credentialAutoLoginLastResult = "v0180-success-high3-return"
        }
        jinhakUserSessionConfirmed = true
        jinhakAuthVerifiedForBatch = true
        batchPausedForLogin = false
        jinhakTransitionAuthGateActive = false
        jinhakRealAuthResumeGatePending = false
        jinhakCoreBootstrapState = "v0180-dedicated-auth-high3"
        jinhakLastAuthEvidence = "v0180-server-high3-return"
        jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
        CookieManager.getInstance().flush()
        if (::authWebView.isInitialized) {
            runCatching { authWebView.stopLoading() }
            runCatching { authWebView.clearHistory() }
        }
        if (::authHost.isInitialized) authHost.visibility = View.GONE
        if (::webView.isInitialized) webView.visibility = View.VISIBLE
        sessionState.text = "● 진학사 자동 로그인 완료 · 고3 세션"
        status.text = "진학사 로그인 완료 · 고3 전용 수집 WebView에서 자동 재개합니다."
        recordRuntimeEvent(
            "jinhak-v0180-auth-success",
            JSONObject()
                .put("generation", jinhakV0180AuthGeneration)
                .put("successSafePath", runtimeSafePath(successUrl))
                .put("batchRunning", batchRunning)
                .put("unifiedRunning", unifiedRunning),
            synchronous = true
        )
        persistJinhakAuthDiagnostics("v0180-auth-success")

        val target = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget)
            ?: JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(successUrl)
            ?: JinhakStrictHigh3Sandbox.strictEntryUrl()
        currentBatchTarget = target
        loadJinhakV0174High3Only(target, "v0180-auth-success-handoff")
    }

    private fun recreateV0180AuthWebView(generation: Int) {
        if (generation != jinhakV0180AuthGeneration || !::authHost.isInitialized) return
        val old = if (::authWebView.isInitialized) authWebView else null
        runCatching { old?.stopLoading() }
        runCatching { authHost.removeAllViews() }
        runCatching { old?.destroy() }
        authWebView = WebView(this)
        authHost.addView(authWebView, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ))
        configureDedicatedJinhakAuthWebView()
        authHost.visibility = View.VISIBLE
        jinhakV0180AuthState = "AUTH_WEBVIEW_RECREATED"
        authWebView.loadUrl(JinhakDedicatedAuthPolicy.LOGIN_URL)
        persistJinhakAuthDiagnostics("v0180-auth-renderer-recreated")
    }

'''
main = main.replace(auth_insert_anchor, auth_block + auth_insert_anchor, 1)

# Legacy "real auth probe" button and resume gates now enter the same deterministic auth path.
probe_pattern = re.compile(
    r'    private fun startJinhakRealAuthProbe\(autoContinue: Boolean, trigger: String\) \{.*?\n    \}\n'
    r'    private fun scheduleJinhakRealAuthProbePoll',
    re.S,
)
probe_replacement = '''    private fun startJinhakRealAuthProbe(autoContinue: Boolean, trigger: String) {
        provider = ProviderId.JINHAK
        jinhakRealAuthProbeActive = false
        jinhakRealAuthProbeAutoContinue = autoContinue
        jinhakRealAuthProbeResult = "delegated-v0180-dedicated-auth"
        startV0180DedicatedJinhakAuth("real-auth-entry:$trigger")
    }
    private fun scheduleJinhakRealAuthProbePoll'''
main, count = probe_pattern.subn(probe_replacement, main, count=1)
if count != 1:
    raise SystemExit(f'failed to replace real auth probe entry: {count}')

# Export explicit v0.18.0 contract diagnostics. Never export username/password/form/cookie values.
main = main.replace(
    'user-owned-session-explicit-high3-runtime-stable-v0175',
    'dedicated-auth-webview-autologin-v0180'
)
diag_anchor = '.put("v0175RendererCrashCooldownMs", JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS)'
if diag_anchor not in main:
    raise SystemExit('v0175 diagnostics anchor not found')
main = main.replace(
    diag_anchor,
    diag_anchor + '''
                    .put("v0180DedicatedAuthWebView", true)
                    .put("v0180CredentialVaultAutoLogin", true)
                    .put("v0180AuthState", jinhakV0180AuthState)
                    .put("v0180AuthGeneration", jinhakV0180AuthGeneration)
                    .put("v0180AuthSubmitAttempts", jinhakV0180AuthSubmitAttempts)
                    .put("v0180AuthSubmissions", jinhakV0180AuthSubmissions)
                    .put("v0180AuthSuccesses", jinhakV0180AuthSuccesses)
                    .put("v0180AuthFailures", jinhakV0180AuthFailures)
                    .put("v0180AuthRendererRestarts", jinhakV0180AuthRendererRestarts)
                    .put("v0180CollectorLoginRouteLoads", jinhakV0180CollectorLoginRouteLoads)
                    .put("v0180LowerGradeBlocks", jinhakV0180LowerGradeBlocks)
                    .put("v0180RecursiveAuthPolling", false)
                    .put("v0180CollectorOwnsLogin", false)
                    .put("v0180AuthLastReason", jinhakV0180AuthLastReason)
                    .put("v0180AuthLastSafePath", jinhakV0180AuthLastSafePath)'''
)

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('Applied v0.18.0 dedicated auth WebView + encrypted device auto-login overhaul')
