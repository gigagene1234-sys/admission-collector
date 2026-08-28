package com.admissionhub.collector

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import com.admissionhub.collector.capture.SnapshotScript
import com.admissionhub.collector.cloud.CloudOffloadCoordinator
import com.admissionhub.collector.parser.RecordUtils
import com.admissionhub.collector.provider.PaginationPlan
import com.admissionhub.collector.provider.ProviderAdapter
import com.admissionhub.collector.provider.ProviderId
import com.admissionhub.collector.provider.ProviderRegistry
import java.time.Instant
import java.util.ArrayDeque

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var status: TextView
    private lateinit var sessionState: TextView
    private lateinit var preview: TextView
    private lateinit var batchButton: Button
    private lateinit var cloudOffload: CloudOffloadCoordinator

    private val handler = Handler(Looper.getMainLooper())
    private val sessionKeepAlive = object : Runnable {
        override fun run() {
            attemptSessionExtension()
            handler.postDelayed(this, 45_000L)
        }
    }
    private data class BatchPageAction(
        val baseUrl: String,
        val page: Int,
        val familyKey: String,
        val requestedYear: Int?,
        val totalPages: Int,
        val pageSize: Int,
        val totalItems: Int,
        val retry: Int = 0
    )

    private data class ListFingerprint(
        val requestedYear: Int?,
        val totalItems: Int,
        val pageSize: Int,
        val fingerprint: String
    )

    private val batchQueue = ArrayDeque<String>()
    private val batchVisited = linkedSetOf<String>()
    private val batchQueued = linkedSetOf<String>()
    private val batchPageActions = ArrayDeque<BatchPageAction>()
    private val batchPageActionQueued = linkedSetOf<String>()
    private val batchPageActionVisited = linkedSetOf<String>()
    private val batchPageActionFailed = linkedSetOf<String>()
    private val batchPaginationPlanned = linkedSetOf<String>()
    private val batchListFingerprints = linkedMapOf<String, ListFingerprint>()
    private val batchLastTableSignatures = linkedMapOf<String, String>()
    private val batchBootstrapSearchAttempted = linkedSetOf<String>()
    private var batchReadinessPolling = false
    private var batchSnapshots = JSONArray()
    private var batchRecords = JSONArray()
    private var batchResources = JSONArray()
    private var batchErrors = JSONArray()
    private var batchRetryEvents = JSONArray()
    private var batchDuplicateYearViews = JSONArray()
    private var batchRunning = false
    private var batchPausedForLogin = false
    private var batchCollecting = false
    private var currentBatchTarget: String? = null
    private var pendingBatchPageAction: BatchPageAction? = null
    private var activeBatchPageAction: BatchPageAction? = null
    private var batchPageCount = 0
    private var batchPaginationRetries = 0

    private var lastJson: String = ""
    private var provider: ProviderId = ProviderId.ADIGA

    companion object {
        private const val SAVE_JSON_REQUEST = 7001
        private const val MAX_BATCH_PAGES = 2000
        private const val MAX_PAGE_RETRIES = 2
        private const val PREVIEW_LIMIT = 16000
        private const val VERSION = "0.3.2"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        cloudOffload = CloudOffloadCoordinator(this)
        buildUi()
        configureWebView()
        openProvider(ProviderId.ADIGA)
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(10, 10, 10, 10)
        }

        val tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        tabs.addView(Button(this).apply {
            text = "어디가"
            setOnClickListener { openProvider(ProviderId.ADIGA) }
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        tabs.addView(Button(this).apply {
            text = "진학사"
            setOnClickListener { openProvider(ProviderId.JINHAK) }
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val sessionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        sessionState = TextView(this).apply {
            text = "세션 상태 확인 중"
            setPadding(8, 8, 8, 8)
        }
        val sessionButton = Button(this).apply {
            text = "세션 확인/갱신"
            setOnClickListener { refreshSessionOrOpenLogin() }
        }
        sessionRow.addView(sessionState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        sessionRow.addView(sessionButton)

        val actions1 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val back = Button(this).apply {
            text = "←"
            setOnClickListener { if (webView.canGoBack()) webView.goBack() }
        }
        val currentCollect = Button(this).apply {
            text = "현재 페이지 수집"
            setOnClickListener { collectCurrentPage() }
        }
        batchButton = Button(this).apply {
            text = "접근 가능 정보 일괄 수집"
            setOnClickListener {
                if (batchRunning) confirmStopBatch() else startBatch()
            }
        }
        actions1.addView(back)
        actions1.addView(currentCollect, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions1.addView(batchButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val actions2 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val resume = Button(this).apply {
            text = "로그인 갱신 후 계속"
            setOnClickListener { resumeAfterLogin() }
        }
        val save = Button(this).apply {
            text = "JSON 저장"
            setOnClickListener { saveJson() }
        }
        val cloudSettings = Button(this).apply {
            text = "Cloud 설정"
            setOnClickListener {
                cloudOffload.showSettingsDialog(this@MainActivity) {
                    status.text = if (cloudOffload.isConfigured()) {
                        "Cloudflare Offload 설정됨"
                    } else {
                        "Cloudflare Offload 미설정: 로컬 수집 모드"
                    }
                }
            }
        }
        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(cloudSettings, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        status = TextView(this).apply {
            text = "Admission Collector v$VERSION 준비 중"
            setPadding(8, 8, 8, 8)
        }

        webView = WebView(this)
        preview = TextView(this).apply {
            text = "수집 결과가 여기에 표시됩니다."
            setTextIsSelectable(true)
            setPadding(12, 12, 12, 12)
        }
        val scroll = ScrollView(this).apply { addView(preview) }

        root.addView(tabs)
        root.addView(sessionRow)
        root.addView(actions1)
        root.addView(actions2)
        root.addView(status)
        root.addView(webView, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 3f))
        root.addView(scroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 2f))
        setContentView(root)
    }

    @Suppress("SetJavaScriptEnabled")
    private fun configureWebView() {
        WebView.setWebContentsDebuggingEnabled(false)
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            javaScriptCanOpenWindowsAutomatically = true
            setSupportMultipleWindows(true)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = userAgentString + " AdmissionCollector/$VERSION"
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                status.text = "불러오는 중: ${safeDisplayUrl(url)}"
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                status.text = "현재 페이지: ${safeDisplayUrl(url)}"

                when {
                    batchPausedForLogin -> checkSessionState { needsLogin, _ ->
                        if (!needsLogin) {
                            sessionState.text = "● 로그인 상태 복구 감지"
                            resumeAfterLogin()
                        }
                    }
                    batchRunning -> {
                        val pending = pendingBatchPageAction
                        if (pending != null && canonicalizeBatchUrl(url) == pending.baseUrl) {
                            executePendingBatchPageAction()
                        } else {
                            scheduleBatchSnapshot()
                        }
                    }
                    else -> checkSessionState()
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
                val child = WebView(this@MainActivity)
                child.settings.javaScriptEnabled = true
                child.settings.domStorageEnabled = true
                child.settings.javaScriptCanOpenWindowsAutomatically = true
                child.settings.setSupportMultipleWindows(true)
                child.webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean {
                        webView.loadUrl(request.url.toString())
                        return true
                    }

                    override fun onPageFinished(v: WebView, url: String) {
                        if (url.isNotBlank() && url != "about:blank") webView.loadUrl(url)
                    }
                }
                transport.webView = child
                resultMsg.sendToTarget()
                return true
            }
        }
    }

    private fun attemptSessionExtension() {
        if (!::webView.isInitialized) return
        val js = """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0 && r.height>0;
              }
              var body=(document.body&&document.body.innerText?document.body.innerText:'').replace(/\s+/g,' ');
              if(!/(자동\s*로그아웃|로그인\s*시간.*연장|세션.*연장)/i.test(body)) return false;
              var nodes=document.querySelectorAll('button,a,[role=button]');
              for(var i=0;i<nodes.length;i++){
                var el=nodes[i];
                if(!visible(el)) continue;
                var label=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
                if(/^(연장하기|로그인\s*연장|세션\s*연장|시간\s*연장)$/i.test(label)){
                  try{ el.click(); return true; }catch(e){}
                }
              }
              return false;
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { result ->
            if (result == "true") {
                CookieManager.getInstance().flush()
                sessionState.text = "● 로그인 세션 자동 연장"
            }
        }
    }

    private fun currentAdapter(): ProviderAdapter = ProviderRegistry.adapter(provider)

    private fun openProvider(which: ProviderId) {
        if (batchRunning) stopBatch("서비스 전환")
        provider = which
        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        status.text = "${which.displayName} 열기"
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        webView.loadUrl(which.homeUrl)
    }

    private fun refreshSessionOrOpenLogin() {
        checkSessionState { needsLogin, hasAuthenticatedUi ->
            if (!needsLogin && hasAuthenticatedUi) {
                sessionState.text = "● 로그인 유지됨"
                Toast.makeText(this, "로그인 세션이 유지되고 있습니다.", Toast.LENGTH_SHORT).show()
                return@checkSessionState
            }

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
                    var t=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
                    if(!/^(로그인|log\s*in|sign\s*in)$/i.test(t)) continue;
                    if(el.tagName==='A' && el.href){
                      try{
                        var u=new URL(el.href,location.href);
                        if(u.origin===location.origin) return JSON.stringify({action:'url',url:u.origin+u.pathname+u.hash});
                      }catch(e){}
                    }
                    try{ el.click(); return JSON.stringify({action:'clicked'}); }catch(e2){}
                  }
                  return JSON.stringify({action:'home'});
                })();
            """.trimIndent()

            webView.evaluateJavascript(js) { encoded ->
                try {
                    val raw = decodeJsString(encoded)
                    val obj = JSONObject(raw)
                    when (obj.optString("action")) {
                        "url" -> webView.loadUrl(obj.optString("url"))
                        "clicked" -> sessionState.text = "○ 로그인 갱신 화면 열림"
                        else -> webView.loadUrl(provider.homeUrl)
                    }
                } catch (_: Exception) {
                    webView.loadUrl(provider.homeUrl)
                }
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
              var pass=false;
              var pw=document.querySelectorAll('input[type=password]');
              for(var i=0;i<pw.length;i++){ if(visible(pw[i])) { pass=true; break; } }
              var text=(document.body && document.body.innerText ? document.body.innerText : '').slice(0,12000);
              var logoutControl=false;
              var controls=document.querySelectorAll('a,button,[role=button]');
              for(var j=0;j<controls.length;j++){
                var node=controls[j];
                if(!visible(node)) continue;
                var label=(node.innerText||node.textContent||node.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
                if(/^(로그아웃|log\s*out|sign\s*out)$/i.test(label)){ logoutControl=true; break; }
              }
              var loginUrl=/(\/mbs\/log\/|login|signin|sign-in|member\/login|loginForm)/i.test(location.href);
              var loginRequired=/(로그인이\s*필요|로그인\s*후\s*(?:이용|사용)|로그인해\s*주세요|로그인해주세요|회원만\s*이용|서비스\s*이용을\s*위해\s*로그인)/i.test(text);
              var authenticated=logoutControl;
              return JSON.stringify({needsLogin:(pass||loginUrl||loginRequired)&&!authenticated,authenticated:authenticated});
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            try {
                val obj = JSONObject(decodeJsString(encoded))
                val needsLogin = obj.optBoolean("needsLogin", false)
                val authenticated = obj.optBoolean("authenticated", false)
                sessionState.text = when {
                    authenticated -> "● 로그인 유지됨"
                    needsLogin -> "○ 로그인 갱신 필요"
                    else -> "△ 로그인 상태 미확정"
                }
                callback?.invoke(needsLogin, authenticated)
            } catch (_: Exception) {
                sessionState.text = "△ 로그인 상태 확인 불가"
                callback?.invoke(false, false)
            }
        }
    }

    private fun startBatch() {
        val url = webView.url
        if (url.isNullOrBlank() || !isProviderUrl(url)) {
            Toast.makeText(this, "먼저 어디가 또는 진학사에서 수집 시작 위치를 여세요.", Toast.LENGTH_LONG).show()
            return
        }

        if (!currentAdapter().supportsBatchCrawl) {
            status.text = "진학사는 사이트 전체 순회 대신 현재 화면을 안전하게 구조화합니다."
            collectCurrentPage()
            return
        }

        batchQueue.clear()
        batchVisited.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        batchPageActionVisited.clear()
        batchPageActionFailed.clear()
        batchPaginationPlanned.clear()
        batchListFingerprints.clear()
        batchLastTableSignatures.clear()
        batchBootstrapSearchAttempted.clear()
        batchReadinessPolling = false
        pendingBatchPageAction = null
        activeBatchPageAction = null
        batchSnapshots = JSONArray()
        batchRecords = JSONArray()
        batchResources = JSONArray()
        batchErrors = JSONArray()
        batchRetryEvents = JSONArray()
        batchDuplicateYearViews = JSONArray()
        batchRunning = true
        batchPausedForLogin = false
        batchCollecting = false
        batchPageCount = 0
        batchPaginationRetries = 0
        currentBatchTarget = url
        batchButton.text = "일괄 수집 중지"
        cloudOffload.beginOrResume(provider.wireName, VERSION) { runId ->
            if (runId != null) {
                runOnUiThread {
                    status.text = "Cloud 체크포인트 연결: ${runId.take(8)}… / 수집 시작"
                }
            }
        }
        enqueueProviderSeeds()
        status.text = "일괄 수집 시작: 기본 정보영역 ${batchQueue.size}개를 포함해 탐색합니다."

        checkSessionState { needsLogin, _ ->
            if (needsLogin) {
                pauseBatchForLogin()
            } else {
                scheduleBatchSnapshot()
            }
        }
    }

    private fun confirmStopBatch() {
        AlertDialog.Builder(this)
            .setTitle("일괄 수집을 중지할까요?")
            .setMessage("현재까지 수집한 결과는 보존됩니다. 실수로 누른 경우 '계속 수집'을 선택하세요.")
            .setNegativeButton("계속 수집", null)
            .setPositiveButton("중지") { _, _ -> stopBatch("사용자 중지") }
            .show()
    }

    private fun stopBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchQueue.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        batchReadinessPolling = false
        pendingBatchPageAction = null
        activeBatchPageAction = null
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        status.text = "일괄 수집 중지: $reason"
        if (batchSnapshots.length() > 0) finalizeBatchJson("stopped")
    }

    private fun pauseBatchForLogin() {
        batchPausedForLogin = true
        batchCollecting = false
        sessionState.text = "○ 로그인 갱신 필요"
        status.text = "수집 일시정지: 로그인 갱신 후 자동/수동으로 계속할 수 있습니다."
        batchButton.text = "일괄 수집 중지"
    }

    private fun resumeAfterLogin() {
        if (!batchRunning || !batchPausedForLogin) {
            checkSessionState()
            return
        }

        checkSessionState { needsLogin, _ ->
            if (needsLogin) {
                Toast.makeText(this, "아직 로그인 화면으로 감지됩니다.", Toast.LENGTH_SHORT).show()
                return@checkSessionState
            }
            batchPausedForLogin = false
            sessionState.text = "● 수집 세션 복구"
            val retry = currentBatchTarget
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                status.text = "로그인 갱신 완료: 중단 지점 재시도"
                webView.loadUrl(retry)
            } else {
                loadNextBatchPage()
            }
        }
    }

    private fun scheduleBatchSnapshot() {
        if (!batchRunning || batchPausedForLogin || batchCollecting) return

        // Pagination actions already wait for AJAX after fnSearch(N). Do not run the
        // first-page bootstrap logic here, because the legitimate last page may
        // contain only one row.
        val activeAction = activeBatchPageAction
        if (activeAction != null) {
            pollPaginationActionReadiness(activeAction, attempt = 0)
            return
        }

        val url = canonicalizeBatchUrl(webView.url ?: "")
        if (currentAdapter().isDynamicListPage(url)) {
            if (batchReadinessPolling) return
            batchReadinessPolling = true
            pollAdigaDynamicListReadiness(url, attempt = 0, afterBootstrap = false)
        } else {
            handler.postDelayed({ collectSnapshotForBatch() }, 650)
        }
    }


    private fun pollPaginationActionReadiness(action: BatchPageAction, attempt: Int) {
        if (!batchRunning || batchPausedForLogin || batchCollecting || activeBatchPageAction == null) return
        val js = """
            (function(){
              try{
                var body=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,20000);
                var title=String(document.title||'');
                var error=/(404\s*Not\s*Found|500\s*(?:Internal\s*Server\s*Error)?|서비스\s*처리\s*중\s*오류|일시적인\s*오류가\s*발생|웹페이지를\s*사용할\s*수\s*없|net::ERR_)/i.test(title+' '+body);
                var table=document.querySelector('table,[role=table]');
                var rows=table?table.querySelectorAll('tr,[role=row]').length:0;
                var tableText=table?(table.innerText||table.textContent||'').replace(/\s+/g,' ').trim().slice(0,30000):'';
                return JSON.stringify({error:error,rows:rows,tableText:tableText});
              }catch(e){return JSON.stringify({error:false,rows:0,tableText:''});}
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            if (!batchRunning || batchPausedForLogin || activeBatchPageAction == null) return@evaluateJavascript
            try {
                val obj = JSONObject(decodeJsString(encoded))
                val isError = obj.optBoolean("error", false)
                val rows = obj.optInt("rows", 0)
                val tableText = obj.optString("tableText")
                val signature = if (tableText.isNotBlank()) RecordUtils.sha256(tableText) else ""
                val previous = batchLastTableSignatures[action.baseUrl]
                val changed = signature.isNotBlank() && (previous == null || previous != signature)
                if (isError || (rows > 1 && changed) || attempt >= 12) {
                    collectSnapshotForBatch()
                } else {
                    handler.postDelayed({ pollPaginationActionReadiness(action, attempt + 1) }, 250)
                }
            } catch (_: Exception) {
                if (attempt >= 12) collectSnapshotForBatch()
                else handler.postDelayed({ pollPaginationActionReadiness(action, attempt + 1) }, 250)
            }
        }
    }

    private fun pollAdigaDynamicListReadiness(baseUrl: String, attempt: Int, afterBootstrap: Boolean) {
        if (!batchRunning || batchPausedForLogin || batchCollecting) {
            batchReadinessPolling = false
            return
        }
        val current = canonicalizeBatchUrl(webView.url ?: "")
        if (current != baseUrl) {
            batchReadinessPolling = false
            scheduleBatchSnapshot()
            return
        }

        val js = """
            (function(){
              try{
                var text=(document.body&&document.body.innerText?document.body.innerText:'').replace(/\s+/g,' ');
                var m=text.match(/총\s*([0-9,]+)\s*건/);
                var total=m?parseInt(m[1].replace(/,/g,''),10):-1;
                var table=document.querySelector('table,[role=table]');
                var rows=table?table.querySelectorAll('tr,[role=row]').length:0;
                var noResult=/검색결과가\s*없습니다/.test(text);
                return JSON.stringify({
                  total:isNaN(total)?-1:total,
                  rows:rows,
                  noResult:noResult,
                  canFnSearch:(typeof window.fnSearch==='function')
                });
              }catch(e){
                return JSON.stringify({total:-1,rows:0,noResult:false,canFnSearch:false});
              }
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            if (!batchRunning || batchPausedForLogin) {
                batchReadinessPolling = false
                return@evaluateJavascript
            }
            try {
                val obj = JSONObject(decodeJsString(encoded))
                val total = obj.optInt("total", -1)
                val rows = obj.optInt("rows", 0)
                val visibleDataRows = (rows - 1).coerceAtLeast(0)
                val ready = total > 0 && visibleDataRows > 0 &&
                    (total <= visibleDataRows || visibleDataRows >= 5)

                if (ready) {
                    batchReadinessPolling = false
                    status.text = "동적 목록 준비 완료: 총 ${total}건"
                    handler.postDelayed({ collectSnapshotForBatch() }, 250)
                    return@evaluateJavascript
                }

                val maxAttempts = if (afterBootstrap) 18 else 12
                if (attempt < maxAttempts) {
                    status.text = "동적 목록 로딩 대기: ${attempt + 1}/$maxAttempts"
                    handler.postDelayed({
                        pollAdigaDynamicListReadiness(baseUrl, attempt + 1, afterBootstrap)
                    }, 450)
                    return@evaluateJavascript
                }

                val canFnSearch = obj.optBoolean("canFnSearch", false)
                if (!afterBootstrap && canFnSearch && batchBootstrapSearchAttempted.add(baseUrl)) {
                    status.text = "초기 검색 실행 후 목록 재대기"
                    webView.evaluateJavascript(
                        "(function(){try{window.fnSearch(1);return true;}catch(e){return false;}})();"
                    ) {
                        handler.postDelayed({
                            pollAdigaDynamicListReadiness(baseUrl, attempt = 0, afterBootstrap = true)
                        }, 900)
                    }
                    return@evaluateJavascript
                }

                batchReadinessPolling = false
                status.text = "동적 목록 준비 시간 초과: 현재 상태 그대로 안전 수집"
                collectSnapshotForBatch()
            } catch (_: Exception) {
                batchReadinessPolling = false
                handler.postDelayed({ collectSnapshotForBatch() }, 250)
            }
        }
    }

    private fun collectCurrentPage() {
        status.text = "현재 페이지의 표·헤더·카드·입시정보를 구조적으로 수집 중…"
        collectSnapshot { snapshot ->
            if (snapshot == null) return@collectSnapshot
            val records = normalizeSnapshot(snapshot)
            val out = JSONObject()
                .put("collectorVersion", VERSION)
                .put("provider", provider.wireName)
                .put("collectedAt", Instant.now().toString())
                .put("mode", "single-page")
                .put("session", snapshot.optJSONObject("session") ?: JSONObject())
                .put("records", records)
                .put("snapshots", JSONArray().put(stripNavigationLinksForExport(snapshot)))
                .put("resourceLinks", snapshot.optJSONArray("resourceLinks") ?: JSONArray())
            lastJson = out.toString(2)
            showPreview(lastJson)
            status.text = "현재 페이지 수집 완료: 구조화 레코드 ${records.length()}개"
        }
    }

    private fun collectSnapshotForBatch() {
        if (!batchRunning || batchPausedForLogin || batchCollecting) return
        batchCollecting = true
        collectSnapshot { snapshot ->
            batchCollecting = false
            if (!batchRunning || snapshot == null) return@collectSnapshot

            val activeAction = activeBatchPageAction
            val collectionPage = activeAction?.page ?: 1
            snapshot.put("collectionPage", collectionPage)
            if (activeAction != null) {
                snapshot.put("collectionPagination", JSONObject()
                    .put("page", activeAction.page)
                    .put("totalPages", activeAction.totalPages)
                    .put("pageSize", activeAction.pageSize)
                    .put("totalItems", activeAction.totalItems)
                    .put("familyKey", activeAction.familyKey)
                    .put("requestedYear", activeAction.requestedYear ?: JSONObject.NULL)
                    .put("retry", activeAction.retry))
            }

            val navigationKey = snapshot.optString("navigationKey")
            if (navigationKey.isNotBlank()) batchVisited.add(navigationKey)
            batchPageCount += 1

            val pageState = snapshot.optJSONObject("pageState") ?: JSONObject()
            if (pageState.optBoolean("isError", false)) {
                val errorType = pageState.optString("errorType", "page-error")
                if (activeAction != null && activeAction.retry < MAX_PAGE_RETRIES) {
                    activeBatchPageAction = null
                    schedulePageActionRetry(activeAction, errorType)
                    return@collectSnapshot
                }

                if (activeAction != null) {
                    batchPageActionFailed.add(pageActionKey(activeAction))
                    activeBatchPageAction = null
                }
                val error = JSONObject()
                    .put("url", snapshot.optString("url"))
                    .put("type", errorType)
                    .put("title", snapshot.optString("title"))
                if (activeAction != null) {
                    error.put("page", activeAction.page)
                        .put("totalPages", activeAction.totalPages)
                        .put("familyKey", activeAction.familyKey)
                        .put("requestedYear", activeAction.requestedYear ?: JSONObject.NULL)
                        .put("retryCount", activeAction.retry)
                }
                batchErrors.put(error)
                cloudOffload.uploadError(
                    provider = provider.wireName,
                    familyKey = activeAction?.familyKey,
                    requestedYear = activeAction?.requestedYear,
                    page = activeAction?.page,
                    retryCount = activeAction?.retry ?: 0,
                    error = error
                )
                status.text = if (activeAction != null) {
                    "목록 ${activeAction.page}/${activeAction.totalPages}쪽 최종 실패 / 다음 페이지 계속"
                } else {
                    "오류 페이지 건너뜀: $errorType / 계속 탐색 중"
                }
                handler.postDelayed({ loadNextBatchPage() }, 300)
                return@collectSnapshot
            }

            val session = snapshot.optJSONObject("session") ?: JSONObject()
            if (session.optBoolean("needsLogin", false)) {
                if (activeAction != null) {
                    pendingBatchPageAction = activeAction
                    activeBatchPageAction = null
                }
                pauseBatchForLogin()
                return@collectSnapshot
            }

            val plan = if (activeAction == null) currentAdapter().paginationPlan(snapshot) else null
            val duplicateOfYear = plan?.let { duplicateYearViewOf(it) }
            if (duplicateOfYear != null && plan != null) {
                val copy = stripNavigationLinksForExport(snapshot)
                copy.put("duplicateYearView", JSONObject()
                    .put("skippedYear", plan.requestedYear ?: JSONObject.NULL)
                    .put("duplicateOfYear", duplicateOfYear)
                    .put("familyKey", plan.familyKey)
                    .put("totalItems", plan.totalItems))
                batchSnapshots.put(copy)
                batchDuplicateYearViews.put(JSONObject()
                    .put("familyKey", plan.familyKey)
                    .put("skippedYear", plan.requestedYear ?: JSONObject.NULL)
                    .put("duplicateOfYear", duplicateOfYear)
                    .put("totalItems", plan.totalItems))
                status.text = "중복 연도 목록 생략: ${plan.requestedYear} → $duplicateOfYear (${plan.totalItems}건 동일)"
                handler.postDelayed({ loadNextBatchPage() }, 250)
                return@collectSnapshot
            }

            if (plan != null) registerListFingerprint(plan)

            batchSnapshots.put(stripNavigationLinksForExport(snapshot))
            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }
            val pageRecords = normalizeSnapshot(snapshot)
            RecordUtils.appendUniqueRecords(batchRecords, pageRecords)
            cloudOffload.uploadPage(
                provider = provider.wireName,
                records = pageRecords,
                familyKey = activeAction?.familyKey ?: plan?.familyKey,
                requestedYear = activeAction?.requestedYear ?: plan?.requestedYear,
                page = activeAction?.page ?: if (plan != null) 1 else null,
                retryCount = activeAction?.retry ?: 0
            )
            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())

            if (activeAction == null) {
                enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())
                if (plan != null) enqueueCalculatedPageActions(snapshot, plan)
            } else {
                batchPageActionVisited.add(pageActionKey(activeAction))
                activeBatchPageAction = null
            }

            status.text = if (activeAction != null) {
                "목록 ${activeAction.page}/${activeAction.totalPages}쪽 완료 / 시도 $batchPageCount / 오류 ${batchErrors.length()} / 레코드 ${batchRecords.length()}"
            } else {
                "일괄 수집: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 오류 ${batchErrors.length()} / URL대기 ${batchQueue.size} / 페이지대기 ${batchPageActions.size} / 레코드 ${batchRecords.length()}"
            }

            if (batchPageCount >= MAX_BATCH_PAGES) {
                finishBatch("page-limit")
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 350)
            }
        }
    }

    private fun loadNextBatchPage() {
        if (!batchRunning || batchPausedForLogin) return

        while (batchPageActions.isNotEmpty()) {
            val action = batchPageActions.removeFirst()
            val key = pageActionKey(action)
            batchPageActionQueued.remove(key)
            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue

            val current = canonicalizeBatchUrl(webView.url ?: "")
            pendingBatchPageAction = action
            currentBatchTarget = action.baseUrl
            status.text = pageActionStatus(action, "탐색 준비")

            if (current == action.baseUrl) {
                executePendingBatchPageAction()
            } else {
                webView.loadUrl(action.baseUrl)
            }
            return
        }

        while (batchQueue.isNotEmpty()) {
            val nextRaw = batchQueue.removeFirst()
            val next = canonicalizeBatchUrl(nextRaw)
            batchQueued.remove(next)
            if (next.isBlank() || batchVisited.contains(next) || !isProviderUrl(next)) continue
            currentBatchTarget = next
            status.text = "다음 입시정보 페이지 탐색: ${safeDisplayUrl(next)}"
            webView.loadUrl(next)
            return
        }
        finishBatch("completed")
    }

    private fun executePendingBatchPageAction() {
        if (!batchRunning || batchPausedForLogin) return
        val action = pendingBatchPageAction ?: return
        pendingBatchPageAction = null

        val key = pageActionKey(action)
        if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) {
            handler.postDelayed({ loadNextBatchPage() }, 100)
            return
        }

        val js = currentAdapter().paginationScript(action.page)
        if (js.isNullOrBlank()) {
            recordPaginationFailure(action, "pagination-action-unavailable")
            handler.postDelayed({ loadNextBatchPage() }, 150)
            return
        }

        activeBatchPageAction = action
        status.text = pageActionStatus(action, if (action.retry > 0) "재시도 ${action.retry}/$MAX_PAGE_RETRIES" else "이동 중")
        webView.evaluateJavascript(js) { result ->
            if (result != "true") {
                activeBatchPageAction = null
                if (action.retry < MAX_PAGE_RETRIES) {
                    schedulePageActionRetry(action, "pagination-action-unavailable")
                } else {
                    recordPaginationFailure(action, "pagination-action-unavailable")
                    handler.postDelayed({ loadNextBatchPage() }, 150)
                }
            } else {
                handler.postDelayed({
                    if (batchRunning && !batchPausedForLogin && !batchCollecting && pendingBatchPageAction == null) {
                        scheduleBatchSnapshot()
                    }
                }, 1100)
            }
        }
    }

    private fun schedulePageActionRetry(action: BatchPageAction, reason: String) {
        val retry = action.copy(retry = action.retry + 1)
        batchPaginationRetries += 1
        batchRetryEvents.put(JSONObject()
            .put("familyKey", action.familyKey)
            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
            .put("page", action.page)
            .put("attempt", retry.retry)
            .put("reason", reason))
        pendingBatchPageAction = retry
        activeBatchPageAction = null
        currentBatchTarget = retry.baseUrl
        status.text = pageActionStatus(retry, "서버 오류 후 재시도 대기")
        val delay = 900L + (retry.retry * 900L)
        handler.postDelayed({
            if (batchRunning && !batchPausedForLogin) webView.loadUrl(retry.baseUrl)
        }, delay)
    }

    private fun recordPaginationFailure(action: BatchPageAction, type: String) {
        batchPageActionFailed.add(pageActionKey(action))
        val error = JSONObject()
            .put("url", action.baseUrl)
            .put("type", type)
            .put("page", action.page)
            .put("totalPages", action.totalPages)
            .put("familyKey", action.familyKey)
            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
            .put("retryCount", action.retry)
        batchErrors.put(error)
        cloudOffload.uploadError(
            provider = provider.wireName,
            familyKey = action.familyKey,
            requestedYear = action.requestedYear,
            page = action.page,
            retryCount = action.retry,
            error = error
        )
    }

    private fun pageActionStatus(action: BatchPageAction, suffix: String): String {
        val year = action.requestedYear?.let { " $it" } ?: ""
        val label = when {
            action.familyKey.contains("classUnivView") -> "학과정보"
            action.familyKey.contains("univView") -> "대학정보"
            action.familyKey.contains("admssUnivView") -> "전형정보"
            else -> "목록"
        }
        return "$label$year ${action.page}/${action.totalPages}쪽 $suffix"
    }

    private fun pageActionKey(action: BatchPageAction): String =
        "${action.baseUrl}|page|${action.page}"

    private fun canonicalizeBatchUrl(url: String): String {
        if (url.isBlank()) return ""
        return try {
            val uri = Uri.parse(url)
            val host = uri.host ?: return ""
            val builder = Uri.Builder()
                .scheme(uri.scheme ?: "https")
                .authority(host)
                .path(uri.path ?: "/")

            val forbidden = Regex("token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential", RegexOption.IGNORE_CASE)
            val names = uri.queryParameterNames
            for (name in names) {
                if (forbidden.containsMatchIn(name)) continue
                for (value in uri.getQueryParameters(name)) builder.appendQueryParameter(name, value)
            }
            builder.build().toString()
        } catch (_: Exception) {
            url.substringBefore('#')
        }
    }

    private fun finishBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        finalizeBatchJson(reason)
        cloudOffload.finish(
            reason = reason,
            summary = JSONObject()
                .put("attemptedPages", batchPageCount)
                .put("successfulPages", batchSnapshots.length())
                .put("errorPages", batchErrors.length())
                .put("records", batchRecords.length())
                .put("paginationRetries", batchPaginationRetries)
        )
        status.text = "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"
    }

    private fun finalizeBatchJson(reason: String) {
        val out = JSONObject()
            .put("collectorVersion", VERSION)
            .put("provider", provider.wireName)
            .put("collectedAt", Instant.now().toString())
            .put("mode", "batch")
            .put("completion", reason)
            .put("summary", JSONObject()
                .put("attemptedPages", batchPageCount)
                .put("successfulPages", batchSnapshots.length())
                .put("errorPages", batchErrors.length())
                .put("records", batchRecords.length())
                .put("resourceLinks", batchResources.length())
                .put("paginationActionsCompleted", batchPageActionVisited.size)
                .put("paginationActionsFailed", batchPageActionFailed.size)
                .put("paginationRetries", batchPaginationRetries)
                .put("paginationPlans", batchPaginationPlanned.size)
                .put("duplicateYearViewsSkipped", batchDuplicateYearViews.length())
                .put("dynamicSearchBootstraps", batchBootstrapSearchAttempted.size))
            .put("errors", batchErrors)
            .put("retryEvents", batchRetryEvents)
            .put("duplicateYearViews", batchDuplicateYearViews)
            .put("cloudOffload", cloudOffload.snapshotStatus())
            .put("records", batchRecords)
            .put("snapshots", batchSnapshots)
            .put("resourceLinks", batchResources)
        lastJson = out.toString(2)
        showPreview(lastJson)
    }

    private fun collectSnapshot(callback: (JSONObject?) -> Unit) {
        val js = SnapshotScript.build()
        webView.evaluateJavascript(js) { encoded ->
            try {
                val raw = decodeJsString(encoded)
                val obj = JSONObject(raw)
                obj.put("providerPageType", currentAdapter().classify(obj))
                val session = obj.optJSONObject("session") ?: JSONObject()
                sessionState.text = when {
                    session.optBoolean("authenticated", false) -> "● 로그인 유지됨"
                    session.optBoolean("needsLogin", false) -> "○ 로그인 갱신 필요"
                    else -> "△ 로그인 상태 미확정"
                }
                callback(obj)
            } catch (e: Exception) {
                status.text = "수집 실패: ${e.message}"
                callback(null)
            }
        }
    }


    private fun normalizeSnapshot(snapshot: JSONObject): JSONArray =
        currentAdapter().normalize(snapshot)

    private fun enqueueProviderSeeds() {
        for (rawUrl in currentAdapter().seedUrls()) {
            val url = canonicalizeBatchUrl(rawUrl)
            if (url.isBlank() || !isProviderUrl(url) || batchVisited.contains(url) || batchQueued.contains(url)) continue
            batchQueued.add(url)
            batchQueue.addLast(url)
        }
    }

    private fun enqueueDiscoveredLinks(links: JSONArray) {
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = canonicalizeBatchUrl(obj.optString("url"))
            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            if (batchVisited.contains(url)) continue
            if (batchQueued.add(url)) batchQueue.addLast(url)
            if (batchQueue.size + batchVisited.size >= MAX_BATCH_PAGES * 2) break
        }
    }

    private fun tableFingerprint(snapshot: JSONObject): String? {
        val tables = snapshot.optJSONArray("tables") ?: return null
        if (tables.length() == 0) return null
        val rows = tables.optJSONObject(0)?.optJSONArray("rows") ?: return null
        if (rows.length() == 0) return null
        return RecordUtils.sha256(rows.toString())
    }

    private fun enqueueCalculatedPageActions(snapshot: JSONObject, plan: PaginationPlan) {
        val baseUrl = canonicalizeBatchUrl(snapshot.optString("url"))
        if (baseUrl.isBlank() || !isProviderUrl(baseUrl) || plan.totalPages <= 1) return
        val planKey = "$baseUrl|${plan.totalItems}|${plan.pageSize}|${plan.totalPages}"
        if (!batchPaginationPlanned.add(planKey)) return

        for (page in 2..plan.totalPages) {
            val action = BatchPageAction(
                baseUrl = baseUrl,
                page = page,
                familyKey = plan.familyKey,
                requestedYear = plan.requestedYear,
                totalPages = plan.totalPages,
                pageSize = plan.pageSize,
                totalItems = plan.totalItems
            )
            val key = pageActionKey(action)
            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue
            if (batchPageActionQueued.add(key)) batchPageActions.addLast(action)
        }
    }

    private fun duplicateYearViewOf(plan: PaginationPlan): Int? {
        val previous = batchListFingerprints[plan.familyKey] ?: return null
        val year = plan.requestedYear ?: return null
        val previousYear = previous.requestedYear ?: return null
        if (year >= previousYear) return null
        val identical = previous.totalItems == plan.totalItems &&
            previous.pageSize == plan.pageSize &&
            previous.fingerprint == plan.firstPageFingerprint
        return if (identical) previousYear else null
    }

    private fun registerListFingerprint(plan: PaginationPlan) {
        val current = batchListFingerprints[plan.familyKey]
        val incoming = ListFingerprint(
            requestedYear = plan.requestedYear,
            totalItems = plan.totalItems,
            pageSize = plan.pageSize,
            fingerprint = plan.firstPageFingerprint
        )
        if (current == null) {
            batchListFingerprints[plan.familyKey] = incoming
            return
        }
        val currentYear = current.requestedYear
        val incomingYear = incoming.requestedYear
        if (currentYear == null || (incomingYear != null && incomingYear > currentYear)) {
            batchListFingerprints[plan.familyKey] = incoming
        }
    }

    private fun stripNavigationLinksForExport(snapshot: JSONObject): JSONObject {
        val copy = JSONObject(snapshot.toString())
        copy.remove("navigationLinks")
        copy.remove("pageActions")
        copy.remove("navigationKey")
        return copy
    }

    private fun isBatchNavigableProviderUrl(url: String): Boolean = currentAdapter().isBatchNavigable(url)

    private fun isProviderUrl(url: String): Boolean = currentAdapter().accepts(url)

    private fun safeDisplayUrl(url: String): String {
        return try {
            val u = Uri.parse(url)
            buildString {
                append(u.scheme ?: "https")
                append("://")
                append(u.host ?: "")
                append(u.path ?: "")
            }
        } catch (_: Exception) {
            url.substringBefore('?')
        }
    }

    private fun decodeJsString(encoded: String?): String {
        if (encoded == null || encoded == "null") return "{}"
        return (JSONTokener(encoded).nextValue() as? String) ?: "{}"
    }

    private fun showPreview(json: String) {
        preview.text = if (json.length <= PREVIEW_LIMIT) json else {
            json.take(PREVIEW_LIMIT) + "\n\n… 미리보기 생략 (${json.length - PREVIEW_LIMIT}자). JSON 저장 시 전체 데이터가 저장됩니다."
        }
    }

    private fun saveJson() {
        if (lastJson.isBlank()) {
            Toast.makeText(this, "먼저 페이지 또는 일괄 수집을 실행하세요.", Toast.LENGTH_SHORT).show()
            return
        }
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/json"
            putExtra(Intent.EXTRA_TITLE, "admission-${provider.wireName}-v${VERSION}-${System.currentTimeMillis()}.json")
        }
        startActivityForResult(intent, SAVE_JSON_REQUEST)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == SAVE_JSON_REQUEST && resultCode == RESULT_OK) {
            val uri: Uri = data?.data ?: return
            contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { it.write(lastJson) }
            status.text = "JSON 저장 완료"
        }
    }

    override fun onResume() {
        super.onResume()
        handler.removeCallbacks(sessionKeepAlive)
        handler.postDelayed(sessionKeepAlive, 45_000L)
    }

    override fun onPause() {
        handler.removeCallbacks(sessionKeepAlive)
        CookieManager.getInstance().flush()
        super.onPause()
    }

    override fun onStop() {
        CookieManager.getInstance().flush()
        super.onStop()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        CookieManager.getInstance().flush()
        cloudOffload.shutdown()
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }
}
