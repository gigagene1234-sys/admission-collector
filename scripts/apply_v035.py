from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_FILES = [
    ROOT / "MainActivity.kt",
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
]
GRADLE = ROOT / "app/build.gradle.kts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_main(path: Path) -> None:
    text = path.read_text()

    text = replace_once(
        text,
        'private const val VERSION = "0.3.4"',
        'private const val VERSION = "0.3.5"',
        f"{path}: version",
    )

    text = replace_once(
        text,
        'private var batchContextRecoveries = 0\n    private var batchSessionSyncRetries = 0\n\n    private var lastJson',
        'private var batchContextRecoveries = 0\n    private var batchSessionSyncRetries = 0\n    private var collectorStateSyncInProgress = false\n    private var collectorStateSyncPayload: String? = null\n    private var collectorStateSyncTarget: String? = null\n\n    private var lastJson',
        f"{path}: browser state sync fields",
    )

    old_collector_finished = '''            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                if (!batchRunning || batchPausedForLogin) return
                val pending = pendingBatchPageAction
                if (pending != null && sameBatchDocument(url, pending.baseUrl)) {
                    executePendingBatchPageAction()
                } else {
                    scheduleBatchSnapshot()
                }
            }
'''
    new_collector_finished = '''            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                if (!batchRunning || batchPausedForLogin) return
                if (collectorStateSyncInProgress) {
                    applyCollectorBrowserStateAndContinue(url)
                    return
                }
                val pending = pendingBatchPageAction
                if (pending != null && sameBatchDocument(url, pending.baseUrl)) {
                    executePendingBatchPageAction()
                } else {
                    scheduleBatchSnapshot()
                }
            }
'''
    text = replace_once(text, old_collector_finished, new_collector_finished, f"{path}: collector sync on finish")

    text = replace_once(
        text,
        'batchContextRecoveries = 0\n        batchSessionSyncRetries = 0\n        currentBatchTarget = canonicalizeBatchUrl(url)',
        'batchContextRecoveries = 0\n        batchSessionSyncRetries = 0\n        collectorStateSyncInProgress = false\n        collectorStateSyncPayload = null\n        collectorStateSyncTarget = null\n        currentBatchTarget = canonicalizeBatchUrl(url)',
        f"{path}: reset browser state sync",
    )

    old_start_load = '''                    } else {
                        val startUrl = currentBatchTarget
                        if (!startUrl.isNullOrBlank()) collectorWebView.loadUrl(startUrl)
                        else loadNextBatchPage()
                    }
'''
    new_start_load = '''                    } else {
                        val startUrl = currentBatchTarget
                        if (!startUrl.isNullOrBlank()) synchronizeCollectorBrowserState(startUrl)
                        else loadNextBatchPage()
                    }
'''
    text = replace_once(text, old_start_load, new_start_load, f"{path}: initial browser state sync")

    old_stop = '''    private fun stopBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        collectorWebView.stopLoading()
        stopCollectionKeepAlive()
'''
    new_stop = '''    private fun stopBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        collectorStateSyncInProgress = false
        collectorStateSyncPayload = null
        collectorStateSyncTarget = null
        collectorWebView.stopLoading()
        stopCollectionKeepAlive()
'''
    text = replace_once(text, old_stop, new_stop, f"{path}: stop browser state sync")

    old_recover = '''                val retry = currentBatchTarget
                status.text = "백그라운드 수집 세션 재동기화 ${batchSessionSyncRetries}/$MAX_SESSION_SYNC_RETRIES"
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin) return@postDelayed
                    if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                        collectorWebView.loadUrl(retry)
                    } else {
                        loadNextBatchPage()
                    }
                }, 300)
                return@checkSessionState
'''
    new_recover = '''                val retry = currentBatchTarget
                status.text = "브라우저 인증상태 재동기화 ${batchSessionSyncRetries}/$MAX_SESSION_SYNC_RETRIES"
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin) return@postDelayed
                    if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                        synchronizeCollectorBrowserState(retry)
                    } else {
                        loadNextBatchPage()
                    }
                }, 300)
                return@checkSessionState
'''
    text = replace_once(text, old_recover, new_recover, f"{path}: recovery browser state sync")

    old_resume = '''        checkSessionState { needsLogin, _ ->
            if (needsLogin) {
                Toast.makeText(this, "아직 로그인 화면으로 감지됩니다.", Toast.LENGTH_SHORT).show()
                return@checkSessionState
            }
            batchPausedForLogin = false
            sessionState.text = "● 수집 세션 복구"
            val retry = currentBatchTarget
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                status.text = "로그인 갱신 완료: 중단 지점 재시도"
                collectorWebView.loadUrl(retry)
            } else {
                loadNextBatchPage()
            }
        }
'''
    new_resume = '''        checkSessionState { needsLogin, authenticated ->
            if (needsLogin || !authenticated) {
                Toast.makeText(this, "메인 로그인 상태가 아직 확인되지 않습니다.", Toast.LENGTH_SHORT).show()
                return@checkSessionState
            }
            batchPausedForLogin = false
            sessionState.text = "● 메인 로그인 확인 / 수집 브라우저 동기화"
            val retry = currentBatchTarget
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                status.text = "로그인 확인 완료: 브라우저 인증상태 복제 후 중단 지점 재시도"
                synchronizeCollectorBrowserState(retry)
            } else {
                loadNextBatchPage()
            }
        }
'''
    text = replace_once(text, old_resume, new_resume, f"{path}: manual resume browser state sync")

    marker = '''    private fun scheduleBatchSnapshot() {
'''
    sync_functions = r'''    private fun synchronizeCollectorBrowserState(targetUrl: String) {
        if (!batchRunning || batchPausedForLogin) return
        if (!isProviderUrl(targetUrl)) {
            loadNextBatchPage()
            return
        }
        CookieManager.getInstance().flush()
        status.text = "메인 브라우저 인증상태 읽는 중…"
        val js = """
            (function(){
              try{
                var local={};
                var session={};
                try{
                  for(var i=0;i<localStorage.length;i++){
                    var k=localStorage.key(i); if(k!==null) local[k]=localStorage.getItem(k);
                  }
                }catch(e1){}
                try{
                  for(var j=0;j<sessionStorage.length;j++){
                    var s=sessionStorage.key(j); if(s!==null) session[s]=sessionStorage.getItem(s);
                  }
                }catch(e2){}
                return JSON.stringify({
                  origin:String(location.origin||''),
                  url:String(location.href||''),
                  localStorage:local,
                  sessionStorage:session,
                  windowName:String(window.name||'')
                });
              }catch(e){
                return JSON.stringify({origin:String(location.origin||''),localStorage:{},sessionStorage:{},windowName:''});
              }
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
            try {
                val payload = decodeJsString(encoded)
                val state = JSONObject(payload)
                val origin = state.optString("origin")
                if (origin.isBlank()) {
                    pauseBatchForLogin(autoOpenLogin = false)
                    return@evaluateJavascript
                }
                val targetOrigin = try {
                    android.net.Uri.parse(targetUrl).let { "${it.scheme}://${it.host}" }
                } catch (_: Exception) { "" }
                if (targetOrigin.isBlank() || !origin.equals(targetOrigin, ignoreCase = true)) {
                    status.text = "수집 브라우저 동기화 중단: 메인 화면과 대상 origin 불일치"
                    pauseBatchForLogin(autoOpenLogin = false)
                    return@evaluateJavascript
                }
                collectorStateSyncPayload = payload
                collectorStateSyncTarget = targetUrl
                collectorStateSyncInProgress = true
                val localCount = state.optJSONObject("localStorage")?.length() ?: 0
                val sessionCount = state.optJSONObject("sessionStorage")?.length() ?: 0
                status.text = "인증상태 복제 준비: session $sessionCount / local $localCount"
                CookieManager.getInstance().flush()
                collectorWebView.loadUrl(provider.homeUrl)
            } catch (_: Exception) {
                collectorStateSyncInProgress = false
                collectorStateSyncPayload = null
                collectorStateSyncTarget = null
                status.text = "메인 브라우저 인증상태 읽기 실패"
                pauseBatchForLogin(autoOpenLogin = false)
            }
        }
    }

    private fun applyCollectorBrowserStateAndContinue(loadedUrl: String) {
        val payload = collectorStateSyncPayload ?: run {
            collectorStateSyncInProgress = false
            pauseBatchForLogin(autoOpenLogin = false)
            return
        }
        val target = collectorStateSyncTarget ?: currentBatchTarget ?: provider.homeUrl
        val quotedPayload = JSONObject.quote(payload)
        val js = """
            (function(){
              try{
                var p=JSON.parse($quotedPayload);
                if(p.origin && String(location.origin||'')!==String(p.origin)){
                  return JSON.stringify({ok:false,reason:'origin'});
                }
                var sessionCount=0;
                var localCount=0;
                try{
                  sessionStorage.clear();
                  var ss=p.sessionStorage||{};
                  Object.keys(ss).forEach(function(k){ sessionStorage.setItem(k,ss[k]); sessionCount++; });
                }catch(e1){}
                try{
                  var ls=p.localStorage||{};
                  Object.keys(ls).forEach(function(k){ localStorage.setItem(k,ls[k]); localCount++; });
                }catch(e2){}
                try{ window.name=String(p.windowName||''); }catch(e3){}
                return JSON.stringify({ok:true,sessionCount:sessionCount,localCount:localCount});
              }catch(e){
                return JSON.stringify({ok:false,reason:String(e&&e.message?e.message:e)});
              }
            })();
        """.trimIndent()

        collectorWebView.evaluateJavascript(js) { encoded ->
            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
            try {
                val result = JSONObject(decodeJsString(encoded))
                if (!result.optBoolean("ok", false)) {
                    collectorStateSyncInProgress = false
                    collectorStateSyncPayload = null
                    collectorStateSyncTarget = null
                    status.text = "수집 브라우저 저장소 복제 실패: ${result.optString("reason", "unknown")}"
                    pauseBatchForLogin(autoOpenLogin = false)
                    return@evaluateJavascript
                }
                val sessionCount = result.optInt("sessionCount", 0)
                val localCount = result.optInt("localCount", 0)
                collectorStateSyncInProgress = false
                collectorStateSyncPayload = null
                collectorStateSyncTarget = null
                sessionState.text = "● 수집 브라우저 인증상태 동기화"
                status.text = "인증상태 복제 완료: session $sessionCount / local $localCount / 대상 재진입"
                CookieManager.getInstance().flush()
                handler.postDelayed({
                    if (batchRunning && !batchPausedForLogin) collectorWebView.loadUrl(target)
                }, 180)
            } catch (_: Exception) {
                collectorStateSyncInProgress = false
                collectorStateSyncPayload = null
                collectorStateSyncTarget = null
                status.text = "수집 브라우저 저장소 복제 결과 확인 실패"
                pauseBatchForLogin(autoOpenLogin = false)
            }
        }
    }

'''
    if sync_functions not in text:
        if marker not in text:
            raise SystemExit(f"{path}: scheduleBatchSnapshot marker missing")
        text = text.replace(marker, sync_functions + marker, 1)

    path.write_text(text)


for main in MAIN_FILES:
    patch_main(main)

text = GRADLE.read_text()
text = replace_once(text, 'versionCode = 11', 'versionCode = 12', 'gradle versionCode')
text = replace_once(text, 'versionName = "0.3.4"', 'versionName = "0.3.5"', 'gradle versionName')
GRADLE.write_text(text)

print("v0.3.5 browser session-state synchronization patch applied")
