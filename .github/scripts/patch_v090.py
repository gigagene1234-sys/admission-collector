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

# ---------------------------------------------------------------------------
# v0.9.0: startup login preflight state.
# Both provider sessions are verified before a new unified collection starts.
# Passwords/form values are never read, stored, or auto-filled by this patch.
# ---------------------------------------------------------------------------
main = replace_once(
    main,
    '    private var pendingUnifiedExportSessionId: String? = null\n',
    '    private var pendingUnifiedExportSessionId: String? = null\n'
    '    private var startupLoginPreflightActive = false\n'
    '    private var startupLoginPreflightVerified = false\n'
    '    private var startupLoginStage = "idle"\n'
    '    private var startupLoginOpenAttempted = false\n'
    '    private var startupLoginPollGeneration = 0\n'
    '    private var startupLoginTrigger = ""\n',
    'startup login preflight fields'
)

main = replace_once(
    main,
    '        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L\n',
    '        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L\n'
    '        private const val AUTO_LOGIN_AND_COLLECT_ON_LAUNCH = true\n'
    '        private const val LOGIN_PREFLIGHT_DOM_SETTLE_MS = 300L\n'
    '        private const val LOGIN_PREFLIGHT_POLL_MS = 1_500L\n',
    'login preflight constants'
)
main = replace_once(
    main,
    '        private const val VERSION = "0.8.9"\n        private const val BUILD_CODE = 10890\n',
    '        private const val VERSION = "0.9.0"\n        private const val BUILD_CODE = 10900\n',
    'main version'
)

# Automatic sequence on a clean app launch; interrupted unified sessions keep
# their existing crash-safe resume path.
main = replace_once(
    main,
    '        val resumed = resumeInterruptedUnifiedSessionIfNeeded()\n        if (!resumed) openProvider(ProviderId.JINHAK)\n        handler.postDelayed({ sendPendingRuntimeEvents() }, 1200L)\n',
    '        val resumed = resumeInterruptedUnifiedSessionIfNeeded()\n'
    '        if (!resumed) {\n'
    '            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {\n'
    '                handler.postDelayed({ startAutomaticLoginAndCollectionSequence("app-launch") }, 350L)\n'
    '            } else {\n'
    '                openProvider(ProviderId.JINHAK)\n'
    '            }\n'
    '        }\n'
    '        handler.postDelayed({ sendPendingRuntimeEvents() }, 1200L)\n',
    'automatic app launch sequence'
)

# User can cancel login preflight from the same primary button.
main = replace_once(
    main,
    '        unifiedButton = Button(this).apply {\n            text = "두 사이트 통합 수집 시작"\n            setOnClickListener {\n                if (unifiedRunning) finishUnifiedCollection("user-finish") else startUnifiedCollection()\n            }\n        }\n',
    '        unifiedButton = Button(this).apply {\n'
    '            text = "자동 로그인 + 통합 수집"\n'
    '            setOnClickListener {\n'
    '                when {\n'
    '                    startupLoginPreflightActive -> cancelStartupLoginPreflight("user-cancel")\n'
    '                    unifiedRunning -> finishUnifiedCollection("user-finish")\n'
    '                    else -> startUnifiedCollection()\n'
    '                }\n'
    '            }\n'
    '        }\n',
    'primary unified button'
)

# Prevent manual provider switching while the login orchestrator owns the WebView.
main = replace_once(
    main,
    '    private fun openProvider(which: ProviderId) {\n        if (unifiedRunning) {\n',
    '    private fun openProvider(which: ProviderId) {\n'
    '        if (startupLoginPreflightActive) {\n'
    '            Toast.makeText(this, "자동 로그인 준비 중에는 사이트 전환을 로그인 오케스트레이터가 관리합니다.", Toast.LENGTH_SHORT).show()\n'
    '            return\n'
    '        }\n'
    '        if (unifiedRunning) {\n',
    'provider switch preflight guard'
)

# Login preflight owns page-finished handling until both providers are verified.
main = replace_once(
    main,
    '            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n',
    '            override fun onPageFinished(view: WebView, url: String) {\n'
    '                CookieManager.getInstance().flush()\n'
    '                if (startupLoginPreflightActive) {\n'
    '                    handleStartupLoginPreflightPageFinished(url)\n'
    '                    return\n'
    '                }\n',
    'page finished preflight interception'
)

# New startup login orchestrator is inserted immediately before unified start.
marker = '    private fun startUnifiedCollection() {\n'
if marker not in main:
    raise SystemExit('startUnifiedCollection marker not found')

preflight_methods = r'''    private fun startAutomaticLoginAndCollectionSequence(trigger: String) {
        if (startupLoginPreflightActive) return
        if (unifiedRunning || batchRunning) {
            Toast.makeText(this, "진행 중인 수집이 있어 자동 로그인 준비를 시작할 수 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        startupLoginPreflightActive = true
        startupLoginPreflightVerified = false
        startupLoginStage = "adiga-check"
        startupLoginOpenAttempted = false
        startupLoginTrigger = trigger.take(40)
        startupLoginPollGeneration += 1
        unifiedButton.text = "자동 로그인 취소"
        recordRuntimeEvent("startup-login-sequence-start", JSONObject()
            .put("trigger", startupLoginTrigger)
            .put("credentialStorage", false)
            .put("providerOrder", JSONArray().put("adiga").put("jinhak")))
        beginStartupLoginProvider(ProviderId.ADIGA)
    }

    private fun cancelStartupLoginPreflight(reason: String) {
        if (!startupLoginPreflightActive) return
        startupLoginPreflightActive = false
        startupLoginPreflightVerified = false
        startupLoginStage = "cancelled"
        startupLoginOpenAttempted = false
        startupLoginPollGeneration += 1
        unifiedButton.text = "자동 로그인 + 통합 수집"
        status.text = "자동 로그인 준비가 취소되었습니다. 다시 시작하면 어디가→진학사 로그인 확인 후 수집합니다."
        recordRuntimeEvent("startup-login-sequence-cancel", JSONObject().put("reason", reason.take(80)))
    }

    private fun beginStartupLoginProvider(which: ProviderId) {
        if (!startupLoginPreflightActive) return
        provider = which
        startupLoginStage = if (which == ProviderId.ADIGA) "adiga-check" else "jinhak-check"
        startupLoginOpenAttempted = false
        startupLoginPollGeneration += 1
        val generation = startupLoginPollGeneration
        localRunId = localStore.latestResumableRun(which.wireName)
        CookieManager.getInstance().flush()
        val lease = runCatching { sessionVault.restore(which.wireName) }.getOrNull()
        sessionState.text = if (lease?.restored == true) {
            "● ${which.displayName} 암호화 세션 복원 · 유효성 확인 중"
        } else {
            "○ ${which.displayName} 로그인 확인 중"
        }
        status.text = if (which == ProviderId.ADIGA) {
            "자동 준비 1/3 · 어디가 로그인 세션을 확인합니다. 만료 시 로그인 화면을 자동으로 엽니다."
        } else {
            "자동 준비 2/3 · 진학사 로그인 세션을 확인합니다. 만료 시 로그인 화면을 자동으로 엽니다."
        }
        recordRuntimeEvent("startup-login-provider-begin", JSONObject()
            .put("provider", which.wireName)
            .put("restoredLease", lease?.restored == true)
            .put("generation", generation))
        webView.loadUrl(which.homeUrl)
    }

    private fun handleStartupLoginPreflightPageFinished(url: String) {
        if (!startupLoginPreflightActive) return
        val expectedProvider = provider
        val generation = startupLoginPollGeneration
        runtimeLastSafePath = runtimeSafePath(url)
        handler.postDelayed({
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@postDelayed
            evaluateStartupLoginState(expectedProvider, generation)
        }, LOGIN_PREFLIGHT_DOM_SETTLE_MS)
    }

    private fun evaluateStartupLoginState(expectedProvider: ProviderId, generation: Int) {
        if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return
        checkSessionState { needsLogin, authenticated ->
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@checkSessionState
            if (authenticated) {
                onStartupProviderAuthenticated(expectedProvider, generation)
                return@checkSessionState
            }
            if (!startupLoginOpenAttempted) {
                startupLoginOpenAttempted = true
                startupLoginStage = if (expectedProvider == ProviderId.ADIGA) "adiga-wait-login" else "jinhak-wait-login"
                status.text = "${expectedProvider.displayName} 로그인 화면을 자동으로 엽니다. 인증이 필요하면 완료만 해주세요. 완료 감지 후 다음 단계로 자동 진행합니다."
                openStartupLoginPage(expectedProvider, generation)
            } else {
                sessionState.text = if (needsLogin) "○ ${expectedProvider.displayName} 로그인 완료 대기" else "△ ${expectedProvider.displayName} 로그인 상태 확정 대기"
                scheduleStartupLoginPoll(expectedProvider, generation)
            }
        }
    }

    private fun openStartupLoginPage(expectedProvider: ProviderId, generation: Int) {
        if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return
        val js = """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0 && r.height>0;
              }
              var nodes=document.querySelectorAll('a,button,[role=button]');
              for(var i=0;i<nodes.length;i++){
                var el=nodes[i];
                if(!visible(el)) continue;
                var t=(el.innerText||el.textContent||el.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim();
                if(!/(로그인|log\\s*in|sign\\s*in)/i.test(t) || t.length>80) continue;
                if(el.tagName==='A' && el.href){
                  try{
                    var u=new URL(el.href,location.href);
                    if(/^https:$/.test(u.protocol)) return JSON.stringify({action:'url',url:u.href});
                  }catch(e){}
                }
                try{ el.click(); return JSON.stringify({action:'clicked'}); }catch(e2){}
              }
              return JSON.stringify({action:'not-found'});
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { encoded ->
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@evaluateJavascript
            val action = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull()
            when (action?.optString("action")) {
                "url" -> {
                    val target = action.optString("url")
                    if (target.startsWith("https://")) webView.loadUrl(target)
                    else webView.loadUrl(expectedProvider.homeUrl)
                }
                "clicked" -> sessionState.text = "○ ${expectedProvider.displayName} 로그인 화면 열림"
                else -> {
                    sessionState.text = "○ ${expectedProvider.displayName} 로그인 메뉴를 직접 선택할 수 있습니다. 완료되면 자동 감지합니다."
                }
            }
            scheduleStartupLoginPoll(expectedProvider, generation)
        }
    }

    private fun scheduleStartupLoginPoll(expectedProvider: ProviderId, generation: Int) {
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

    private fun onStartupProviderAuthenticated(expectedProvider: ProviderId, generation: Int) {
        if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return
        startupLoginPollGeneration += 1
        startupLoginOpenAttempted = false
        val currentUrl = webView.url.orEmpty()
        if (currentUrl.isNotBlank()) runCatching { sessionVault.captureAuthenticated(expectedProvider.wireName, currentUrl, VERSION) }
        recordRuntimeEvent("startup-login-provider-authenticated", JSONObject()
            .put("provider", expectedProvider.wireName)
            .put("credentialStored", false))
        if (expectedProvider == ProviderId.ADIGA) {
            sessionState.text = "● 어디가 로그인 확인 완료"
            status.text = "자동 준비 1/3 완료 · 진학사 로그인 확인으로 이동합니다."
            handler.postDelayed({
                if (startupLoginPreflightActive) beginStartupLoginProvider(ProviderId.JINHAK)
            }, 250L)
        } else {
            sessionState.text = "● 진학사 로그인 확인 완료"
            startupLoginPreflightActive = false
            startupLoginPreflightVerified = true
            startupLoginStage = "verified"
            startupLoginPollGeneration += 1
            unifiedButton.text = "통합 수집 시작 중"
            status.text = "자동 준비 3/3 · 어디가·진학사 로그인 확인 완료. 통합 수집을 자동 시작합니다."
            recordRuntimeEvent("startup-login-sequence-verified", JSONObject()
                .put("trigger", startupLoginTrigger)
                .put("bothProvidersAuthenticated", true)
                .put("credentialStored", false))
            handler.postDelayed({
                if (!unifiedRunning && !batchRunning && startupLoginPreflightVerified) {
                    startUnifiedCollectionAuthenticated()
                }
            }, 300L)
        }
    }

'''
main = main.replace(marker, preflight_methods + marker, 1)

# Wrapper: every new manual unified run also goes through the same login sequence.
main = replace_once(
    main,
    '    private fun startUnifiedCollection() {\n        if (batchRunning) {\n',
    '    private fun startUnifiedCollection() {\n'
    '        if (!startupLoginPreflightVerified) {\n'
    '            startAutomaticLoginAndCollectionSequence("manual-start")\n'
    '            return\n'
    '        }\n'
    '        startUnifiedCollectionAuthenticated()\n'
    '    }\n\n'
    '    private fun startUnifiedCollectionAuthenticated() {\n'
    '        if (batchRunning) {\n',
    'unified start wrapper'
)

# Reset the preflight verification after each finished unified run so the next
# run must verify both providers again.
main = replace_once(
    main,
    '            unifiedPhase = "completed"\n            jinhakAbsoluteTargetKey = ""\n',
    '            unifiedPhase = "completed"\n'
    '            startupLoginPreflightVerified = false\n'
    '            startupLoginPreflightActive = false\n'
    '            startupLoginStage = "idle"\n'
    '            startupLoginPollGeneration += 1\n'
    '            jinhakAbsoluteTargetKey = ""\n',
    'reset preflight after unified finish'
)
main = main.replace('unifiedButton.text = "두 사이트 통합 수집 시작"', 'unifiedButton.text = "자동 로그인 + 통합 수집"')

# A batch must not be started manually while login preflight owns the WebView.
main = replace_once(
    main,
    '    private fun startBatch() {\n        val url = webView.url\n',
    '    private fun startBatch() {\n'
    '        if (startupLoginPreflightActive) {\n'
    '            Toast.makeText(this, "로그인 준비가 끝난 뒤 수집이 자동 시작됩니다.", Toast.LENGTH_SHORT).show()\n'
    '            return\n'
    '        }\n'
    '        val url = webView.url\n',
    'batch preflight guard'
)

MAIN.write_text(main)

# Version package metadata.
gradle = GRADLE.read_text()
gradle = replace_once(
    gradle,
    '        versionCode = 10890\n        versionName = "0.8.9"\n',
    '        versionCode = 10900\n        versionName = "0.9.0"\n',
    'gradle version'
)
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Collector v0.8.9 Mission Stall Fence"',
    'android:label="Admission Collector v0.9.0 Auto Login Orchestrator"',
    'manifest label'
)
MANIFEST.write_text(manifest)

print('v0.9.0 automatic login orchestration patch applied')
