from pathlib import Path
import re


def read(path):
    return Path(path).read_text()

def write(path, text):
    Path(path).write_text(text)

def replace_once(path, old, new):
    text = read(path)
    if old not in text:
        # Idempotent rerun: if replacement already exists, do nothing.
        if new in text:
            return
        raise SystemExit(f"{path}: missing expected text: {old[:160]!r}")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one match, got {text.count(old)}: {old[:160]!r}")
    write(path, text.replace(old, new, 1))

def regex_once(path, pattern, replacement, flags=re.S):
    text = read(path)
    out, n = re.subn(pattern, replacement, text, count=1, flags=flags)
    if n == 0:
        # Permit idempotent rerun when v0.18.4 marker is already present.
        if "v0.18.4" in text and "JinhakSingleSurfaceStoragePolicy" in text:
            return
        raise SystemExit(f"{path}: regex did not match: {pattern[:180]!r}")
    write(path, out)

# Version.
replace_once("app/build.gradle.kts", '        versionCode = 118300\n        versionName = "0.18.3"', '        versionCode = 118400\n        versionName = "0.18.4"')
replace_once("app/src/main/AndroidManifest.xml", 'android:label="Admission Hub v0.18.3 Storage Competition Watch"', 'android:label="Admission Hub v0.18.4 Single Surface Storage"')
replace_once("app/src/main/java/com/admissionhub/collector/MainActivity.kt", '        private const val VERSION = "0.18.3"\n        private const val BUILD_CODE = 118300', '        private const val VERSION = "0.18.4"\n        private const val BUILD_CODE = 118400')

# Import policy.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    'import com.admissionhub.collector.jinhak.JinhakStorageCompetitionPolicy\n',
    'import com.admissionhub.collector.jinhak.JinhakStorageCompetitionPolicy\nimport com.admissionhub.collector.jinhak.JinhakSingleSurfaceStoragePolicy\n'
)

# Runtime diagnostics and Adiga baseline counters.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '    private var jinhakV0183NextRefreshAtMs = 0L\n',
    '''    private var jinhakV0183NextRefreshAtMs = 0L
    private var jinhakV0184SingleSurfaceLoginPages = 0
    private var jinhakV0184SingleSurfaceAutofillAttempts = 0
    private var jinhakV0184SingleSurfaceSubmits = 0
    private var jinhakV0184AutofillGeneration = 0
    private var jinhakV0184AutofillRunning = false
    private var adigaV0184BaselineCompletedPages = 0
    private var adigaV0184BaselineCompletedDocuments = 0
    private var adigaV0184BaselineRecords = 0
'''
)

# Reset v0.18.4 counters on a new unified run.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        jinhakV0183StorageWatchGeneration += 1
        jinhakV0183NextRefreshAtMs = 0L
''',
    '''        jinhakV0183StorageWatchGeneration += 1
        jinhakV0183NextRefreshAtMs = 0L
        jinhakV0184SingleSurfaceLoginPages = 0
        jinhakV0184SingleSurfaceAutofillAttempts = 0
        jinhakV0184SingleSurfaceSubmits = 0
        jinhakV0184AutofillGeneration += 1
        jinhakV0184AutofillRunning = false
        adigaV0184BaselineCompletedPages = 0
        adigaV0184BaselineCompletedDocuments = 0
        adigaV0184BaselineRecords = 0
'''
)

# Dedicated-auth entry point is kept for compatibility, but v0.18.4 implements it on the SAME
# foreground WebView used for storage collection. No cross-WebView cookie/sessionStorage handoff.
main = "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = read(main)
pattern = r'''    private fun startV0180DedicatedJinhakAuth\(reason: String, forceManual: Boolean = false\) \{.*?(?=\n    private fun completeV0180DedicatedJinhakAuth\()'''
new_block = r'''    private fun beginV0184SingleSurfaceAutofill() {
        if (provider != ProviderId.JINHAK || !JinhakSingleSurfaceStoragePolicy.ENABLED) return
        if (!JinhakDedicatedAuthPolicy.isLoginSurface(webView.url.orEmpty())) return
        if (jinhakV0184AutofillRunning) return
        val credential = credentialVault.load(ProviderId.JINHAK.wireName)
        if (credential == null) {
            status.text = "진학사 로그인 화면입니다. 같은 탐색 화면에서 직접 로그인하세요. 로그인 후 수시저장소로 복귀하면 자동 검증합니다."
            return
        }
        val generation = ++jinhakV0184AutofillGeneration
        jinhakV0184AutofillRunning = true
        attemptV0184SingleSurfaceAutofill(generation, 0, credential.username, credential.password)
    }

    private fun attemptV0184SingleSurfaceAutofill(generation: Int, attempt: Int, username: String, password: String) {
        if (generation != jinhakV0184AutofillGeneration || provider != ProviderId.JINHAK) return
        if (!JinhakDedicatedAuthPolicy.isLoginSurface(webView.url.orEmpty())) {
            jinhakV0184AutofillRunning = false
            return
        }
        if (attempt >= JinhakSingleSurfaceStoragePolicy.AUTOFILL_MAX_ATTEMPTS_PER_PAGE) {
            jinhakV0184AutofillRunning = false
            status.text = "자동 입력 폼을 확인하지 못했습니다. 현재 진학사 화면에서 직접 로그인하면 같은 WebView 세션으로 계속합니다."
            persistJinhakAuthDiagnostics("v0184-single-surface-autofill-exhausted")
            return
        }
        jinhakV0184SingleSurfaceAutofillAttempts += 1
        val u = JSONObject.quote(username)
        val p = JSONObject.quote(password)
        val js = """
            (function(){
              try {
                function visible(e){ if(!e) return false; var s=getComputedStyle(e),r=e.getBoundingClientRect(); return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0; }
                function setv(e,v){ var proto=Object.getPrototypeOf(e), d=Object.getOwnPropertyDescriptor(proto,'value'); if(d&&d.set)d.set.call(e,v); else e.value=v; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); }
                var docs=[document]; try{document.querySelectorAll('iframe,frame').forEach(function(f){try{if(f.contentDocument)docs.push(f.contentDocument);}catch(e){}});}catch(e){}
                for(var di=0;di<docs.length;di++){
                  var d=docs[di];
                  var pass=Array.from(d.querySelectorAll('input[type=password]')).find(visible); if(!pass) continue;
                  var form=pass.form||pass.closest('form')||d;
                  var users=Array.from(form.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);
                  users.sort(function(a,b){function sc(x){var m=((x.name||'')+' '+(x.id||'')+' '+(x.placeholder||'')+' '+(x.autocomplete||'')).toLowerCase(); return (/아이디|user|login|member|email|account/.test(m)?100:0)+((x.autocomplete||'').toLowerCase()==='username'?100:0)-(/search|검색/.test(m)?200:0);} return sc(b)-sc(a);});
                  var user=users[0]; if(!user) continue;
                  setv(user,$u); setv(pass,$p);
                  var controls=Array.from(form.querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);
                  var submit=controls.find(function(e){var t=((e.innerText||e.value||e.textContent||'')+'').replace(/\\s+/g,' ').trim().toLowerCase(); return /로그인|login|sign in/.test(t);}) || controls.find(function(e){return (e.type||'').toLowerCase()==='submit';});
                  if(submit){ submit.click(); return JSON.stringify({filled:true,submitted:true}); }
                  if(form && form.submit){ if(form.requestSubmit) form.requestSubmit(); else form.submit(); return JSON.stringify({filled:true,submitted:true}); }
                  return JSON.stringify({filled:true,submitted:false});
                }
                return JSON.stringify({filled:false,submitted:false});
              } catch(e) { return JSON.stringify({filled:false,submitted:false,error:String(e)}); }
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { raw ->
            if (generation != jinhakV0184AutofillGeneration) return@evaluateJavascript
            val result = runCatching {
                val decoded = if (raw.startsWith("\"") && raw.endsWith("\"")) JSONTokener(raw).nextValue() as? String ?: "{}" else raw
                JSONObject(decoded)
            }.getOrElse { JSONObject() }
            if (result.optBoolean("submitted", false)) {
                jinhakV0184SingleSurfaceSubmits += 1
                jinhakV0184AutofillRunning = false
                credentialAutoLoginLastResult = "v0184-single-surface-submitted-awaiting-storage"
                status.text = "진학사 로그인 제출 완료 · 같은 WebView에서 수시저장소 복귀를 기다립니다."
                persistJinhakAuthDiagnostics("v0184-single-surface-submitted")
            } else {
                handler.postDelayed({ attemptV0184SingleSurfaceAutofill(generation, attempt + 1, username, password) }, JinhakSingleSurfaceStoragePolicy.AUTOFILL_RETRY_MS)
            }
        }
    }

    private fun startV0180DedicatedJinhakAuth(reason: String, forceManual: Boolean = false) {
        provider = ProviderId.JINHAK
        jinhakV0180AuthLastReason = reason.take(100)
        jinhakV0180AuthState = "V0184_SINGLE_SURFACE_STORAGE_AUTH"
        jinhakAuthVerifiedForBatch = false
        jinhakUserSessionConfirmed = false
        batchPausedForLogin = true
        if (::authHost.isInitialized) authHost.visibility = View.GONE
        webView.visibility = View.VISIBLE
        val current = webView.url.orEmpty()
        val storage = JinhakSiteTopology.protectedCoreProbeUrl()
        sessionState.text = "○ 진학사 단일 WebView · 수시저장소 인증 대기"
        when {
            JinhakDedicatedAuthPolicy.isLoginSurface(current) -> beginV0184SingleSurfaceAutofill()
            JinhakStorageCompetitionPolicy.isStorageUrl(current) -> webView.reload()
            else -> loadJinhakV0174High3Only(storage, "v0184-single-surface-auth:$reason")
        }
        persistJinhakAuthDiagnostics("v0184-single-surface-auth-start")
    }
'''
out, n = re.subn(pattern, new_block, text, count=1, flags=re.S)
if n != 1:
    if "V0184_SINGLE_SURFACE_STORAGE_AUTH" not in text:
        raise SystemExit("MainActivity: could not replace dedicated auth function")
else:
    write(main, out)

# Main collector WebView must allow the provider-owned login page to render. It no longer blocks
# and reroutes that main-frame navigation to authWebView.
text = read(main)
text, n1 = re.subn(
    r'''if \(JinhakDedicatedAuthPolicy\.isLoginSurface\(target\)\) \{\s*handler\.post \{\s*jinhakV0180CollectorLoginRouteLoads \+= 1\s*startV0180DedicatedJinhakAuth\("collector-network-login"\)\s*\}\s*return jinhakV0174BlockedResponse\("dedicated-auth-route"\)\s*\}''',
    '''if (JinhakDedicatedAuthPolicy.isLoginSurface(target)) {
                            handler.post {
                                jinhakV0180CollectorLoginRouteLoads += 1
                                jinhakV0184SingleSurfaceLoginPages += 1
                                status.text = "진학사 로그인 페이지 · 수시저장소와 동일한 WebView 세션"
                            }
                            return null
                        }''',
    text, count=1, flags=re.S)
if n1 != 1 and "수시저장소와 동일한 WebView 세션" not in text:
    raise SystemExit("MainActivity: network login interception patch failed")

text, n2 = re.subn(
    r'''if \(JinhakDedicatedAuthPolicy\.isLoginSurface\(target\)\) \{\s*jinhakV0180CollectorLoginRouteLoads \+= 1\s*startV0180DedicatedJinhakAuth\("collector-navigation-login"\)\s*return true\s*\}''',
    '''if (JinhakDedicatedAuthPolicy.isLoginSurface(target)) {
                    jinhakV0180CollectorLoginRouteLoads += 1
                    jinhakV0184SingleSurfaceLoginPages += 1
                    return false
                }''', text, count=1, flags=re.S)
if n2 != 1 and "jinhakV0184SingleSurfaceLoginPages += 1\n                    return false" not in text:
    raise SystemExit("MainActivity: navigation login patch failed")

text, n3 = re.subn(
    r'''if \(JinhakDedicatedAuthPolicy\.isLoginSurface\(url\) == true\) \{\s*jinhakV0180CollectorLoginRouteLoads \+= 1\s*runCatching \{ view\.stopLoading\(\) \}\s*startV0180DedicatedJinhakAuth\("collector-page-started-login"\)\s*return\s*\}''',
    '''if (JinhakDedicatedAuthPolicy.isLoginSurface(url) == true) {
                        jinhakV0180CollectorLoginRouteLoads += 1
                        jinhakV0184SingleSurfaceLoginPages += 1
                        jinhakV0180AuthState = "V0184_SINGLE_SURFACE_LOGIN_VISIBLE"
                        sessionState.text = "○ 진학사 로그인 · 동일 WebView"
                        return
                    }''', text, count=1, flags=re.S)
if n3 != 1 and "V0184_SINGLE_SURFACE_LOGIN_VISIBLE" not in text:
    raise SystemExit("MainActivity: page-started login patch failed")

text, n4 = re.subn(
    r'''if \(JinhakDedicatedAuthPolicy\.isLoginSurface\(url\)\) \{\s*jinhakV0180CollectorLoginRouteLoads \+= 1\s*startV0180DedicatedJinhakAuth\("collector-page-finished-login"\)\s*return\s*\}''',
    '''if (JinhakDedicatedAuthPolicy.isLoginSurface(url)) {
                        jinhakV0180CollectorLoginRouteLoads += 1
                        jinhakV0184SingleSurfaceLoginPages += 1
                        jinhakV0180AuthState = "V0184_SINGLE_SURFACE_LOGIN_READY"
                        beginV0184SingleSurfaceAutofill()
                        return
                    }''', text, count=1, flags=re.S)
if n4 != 1 and "V0184_SINGLE_SURFACE_LOGIN_READY" not in text:
    raise SystemExit("MainActivity: page-finished login patch failed")
write(main, text)

# Periodic storage refresh stays on the same WebView/document session when already in storage.
replace_once(
    main,
    '            loadJinhakV0174High3Only(storage, "v0183-periodic-storage-refresh")',
    '            if (JinhakStorageCompetitionPolicy.isStorageUrl(webView.url.orEmpty())) webView.reload()\n            else loadJinhakV0174High3Only(storage, "v0184-periodic-storage-refresh")'
)

# Capture persisted Adiga baseline before this batch so the UI can distinguish current attempts
# from hundreds of already-completed pages restored from an earlier stopped/incomplete run.
replace_once(
    main,
    '''        batchPageCount = 0
        batchPaginationRetries = 0
''',
    '''        batchPageCount = 0
        if (provider == ProviderId.ADIGA) {
            val baseline = localRunId?.let { localStore.diagnosticSnapshot(it) } ?: JSONObject()
            adigaV0184BaselineCompletedPages = baseline.optInt("completedPages", 0)
            adigaV0184BaselineCompletedDocuments = baseline.optInt("completedDocuments", 0)
            adigaV0184BaselineRecords = baseline.optInt("records", 0)
        }
        batchPaginationRetries = 0
'''
)

# Make the on-screen Adiga counter semantics explicit instead of calling only current snapshots
# "attempts" next to a persisted page count from resumed runs.
old_status = '''            status.text = if (activeAction != null) {
                "목록 ${activeAction.page}/${activeAction.totalPages}쪽 완료 / 시도 $batchPageCount / 오류 ${batchErrors.length()} / 레코드 ${batchRecords.length()}"
            } else {
                "일괄 수집: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 오류 ${batchErrors.length()} / URL대기 ${batchQueue.size} / 페이지대기 ${batchPageActions.size} / 레코드 ${batchRecords.length()}"
            }
'''
new_status = '''            status.text = if (provider == ProviderId.ADIGA) {
                val persisted = localRunId?.let { localStore.diagnosticSnapshot(it) } ?: JSONObject()
                val completedNow = persisted.optInt("completedPages", adigaV0184BaselineCompletedPages)
                val newCompleted = JinhakSingleSurfaceStoragePolicy.completedDelta(adigaV0184BaselineCompletedPages, completedNow)
                "어디가: 이번 실행 화면시도 $batchPageCount / 이번 신규완료 $newCompleted / 시작 전 누적 ${adigaV0184BaselineCompletedPages} / 현재 누적 $completedNow / 오류 ${batchErrors.length()}"
            } else if (activeAction != null) {
                "목록 ${activeAction.page}/${activeAction.totalPages}쪽 완료 / 화면시도 $batchPageCount / 오류 ${batchErrors.length()} / 레코드 ${batchRecords.length()}"
            } else {
                "일괄 수집: 화면시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 오류 ${batchErrors.length()} / URL대기 ${batchQueue.size} / 페이지대기 ${batchPageActions.size} / 레코드 ${batchRecords.length()}"
            }
'''
replace_once(main, old_status, new_status)

# Add v0.18.4 diagnostics to both auth/live payloads.
text = read(main)
needle = '                    .put("v0183NextRefreshAtMs", jinhakV0183NextRefreshAtMs)\n'
replacement = needle + '''                    .put("v0184SingleSurfaceAuth", JinhakSingleSurfaceStoragePolicy.ENABLED)
                    .put("v0184AuthAndCollectionSurface", JinhakSingleSurfaceStoragePolicy.AUTH_AND_COLLECTION_SURFACE)
                    .put("v0184ExternalAppSessionBridge", JinhakSingleSurfaceStoragePolicy.EXTERNAL_APP_SESSION_BRIDGE)
                    .put("v0184SingleSurfaceLoginPages", jinhakV0184SingleSurfaceLoginPages)
                    .put("v0184SingleSurfaceAutofillAttempts", jinhakV0184SingleSurfaceAutofillAttempts)
                    .put("v0184SingleSurfaceSubmits", jinhakV0184SingleSurfaceSubmits)
'''
count = text.count(needle)
if count == 2:
    text = text.replace(needle, replacement)
elif "v0184SingleSurfaceAuth" not in text:
    raise SystemExit(f"MainActivity: expected two v0183 diagnostic anchors, got {count}")
write(main, text)

# Add explicit Adiga persisted/current semantics to batch-finish diagnostic segment.
replace_once(
    main,
    '''                .put("paginationRetries", batchPaginationRetries)
                .put("localPagesScheduled", batchLocalPagesScheduled)
''',
    '''                .put("paginationRetries", batchPaginationRetries)
                .put("adigaCurrentBatchSnapshotAttempts", if (provider == ProviderId.ADIGA) batchPageCount else 0)
                .put("adigaPersistedCompletedPagesAtStart", if (provider == ProviderId.ADIGA) adigaV0184BaselineCompletedPages else 0)
                .put("adigaPersistedCompletedDocumentsAtStart", if (provider == ProviderId.ADIGA) adigaV0184BaselineCompletedDocuments else 0)
                .put("adigaPersistedRecordsAtStart", if (provider == ProviderId.ADIGA) adigaV0184BaselineRecords else 0)
                .put("adigaCounterSemantics", if (provider == ProviderId.ADIGA) "attempts=current-batch-snapshots; completedPages=persisted-run-page-rows; resumed runs may start with hundreds already completed" else JSONObject.NULL)
                .put("localPagesScheduled", batchLocalPagesScheduled)
'''
)

print("v0.18.4 single-surface storage + transparent Adiga counters patch applied")
