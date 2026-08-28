package com.admissionhub.collector

import android.app.Activity
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
import java.time.Instant
import java.util.ArrayDeque

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var status: TextView
    private lateinit var sessionState: TextView
    private lateinit var preview: TextView
    private lateinit var batchButton: Button

    private val handler = Handler(Looper.getMainLooper())
    private val sessionKeepAlive = object : Runnable {
        override fun run() {
            attemptSessionExtension()
            handler.postDelayed(this, 45_000L)
        }
    }
    private data class BatchPageAction(val baseUrl: String, val page: Int)

    private val batchQueue = ArrayDeque<String>()
    private val batchVisited = linkedSetOf<String>()
    private val batchQueued = linkedSetOf<String>()
    private val batchPageActions = ArrayDeque<BatchPageAction>()
    private val batchPageActionQueued = linkedSetOf<String>()
    private val batchPageActionVisited = linkedSetOf<String>()
    private var batchSnapshots = JSONArray()
    private var batchRecords = JSONArray()
    private var batchResources = JSONArray()
    private var batchErrors = JSONArray()
    private var batchRunning = false
    private var batchPausedForLogin = false
    private var batchCollecting = false
    private var currentBatchTarget: String? = null
    private var pendingBatchPageAction: BatchPageAction? = null
    private var batchPageCount = 0

    private var lastJson: String = ""
    private var provider: String = "adiga"

    companion object {
        private const val SAVE_JSON_REQUEST = 7001
        private const val ADIGA_URL = "https://www.adiga.kr/"
        private const val JINHAK_URL = "https://www.jinhak.com/"
        private const val MAX_BATCH_PAGES = 900
        private const val PREVIEW_LIMIT = 16000
        private const val VERSION = "0.2.3"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        configureWebView()
        openProvider("adiga")
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
            setOnClickListener { openProvider("adiga") }
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        tabs.addView(Button(this).apply {
            text = "진학사"
            setOnClickListener { openProvider("jinhak") }
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
                if (batchRunning) stopBatch("사용자 중지") else startBatch()
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
        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

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

    private fun openProvider(which: String) {
        if (batchRunning) stopBatch("서비스 전환")
        provider = which
        CookieManager.getInstance().flush()
        val url = if (which == "adiga") ADIGA_URL else JINHAK_URL
        sessionState.text = "세션 상태 확인 중"
        status.text = if (which == "adiga") "어디가 열기" else "진학사 열기"
        webView.loadUrl(url)
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
                        else -> webView.loadUrl(if (provider == "adiga") ADIGA_URL else JINHAK_URL)
                    }
                } catch (_: Exception) {
                    webView.loadUrl(if (provider == "adiga") ADIGA_URL else JINHAK_URL)
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

        batchQueue.clear()
        batchVisited.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        batchPageActionVisited.clear()
        pendingBatchPageAction = null
        batchSnapshots = JSONArray()
        batchRecords = JSONArray()
        batchResources = JSONArray()
        batchErrors = JSONArray()
        batchRunning = true
        batchPausedForLogin = false
        batchCollecting = false
        batchPageCount = 0
        currentBatchTarget = url
        batchButton.text = "일괄 수집 중지"
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

    private fun stopBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchQueue.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        pendingBatchPageAction = null
        batchButton.text = "접근 가능 정보 일괄 수집"
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
        handler.postDelayed({ collectSnapshotForBatch() }, 500)
    }

    private fun collectCurrentPage() {
        status.text = "현재 페이지의 표·헤더·카드·입시정보를 구조적으로 수집 중…"
        collectSnapshot { snapshot ->
            if (snapshot == null) return@collectSnapshot
            val records = normalizeSnapshot(snapshot)
            val out = JSONObject()
                .put("collectorVersion", VERSION)
                .put("provider", provider)
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

            val navigationKey = snapshot.optString("navigationKey")
            if (navigationKey.isNotBlank()) batchVisited.add(navigationKey)
            batchPageCount += 1

            val pageState = snapshot.optJSONObject("pageState") ?: JSONObject()
            if (pageState.optBoolean("isError", false)) {
                batchErrors.put(JSONObject()
                    .put("url", snapshot.optString("url"))
                    .put("type", pageState.optString("errorType", "page-error"))
                    .put("title", snapshot.optString("title")))
                status.text = "오류 페이지 건너뜀: ${pageState.optString("errorType", "error")} / 계속 탐색 중"
                handler.postDelayed({ loadNextBatchPage() }, 250)
                return@collectSnapshot
            }

            val session = snapshot.optJSONObject("session") ?: JSONObject()
            if (session.optBoolean("needsLogin", false)) {
                pauseBatchForLogin()
                return@collectSnapshot
            }

            batchSnapshots.put(stripNavigationLinksForExport(snapshot))
            appendUniqueRecords(batchRecords, normalizeSnapshot(snapshot))
            appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())
            enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())
            enqueuePageActions(snapshot.optJSONArray("pageActions") ?: JSONArray())

            status.text = "일괄 수집: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 오류 ${batchErrors.length()} / URL대기 ${batchQueue.size} / 페이지대기 ${batchPageActions.size} / 레코드 ${batchRecords.length()}"

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
            if (batchPageActionVisited.contains(key)) continue

            val current = canonicalizeBatchUrl(webView.url ?: "")
            pendingBatchPageAction = action
            currentBatchTarget = action.baseUrl
            status.text = "목록 페이지 ${action.page}쪽 탐색 준비"

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
        if (!batchPageActionVisited.add(key)) {
            handler.postDelayed({ loadNextBatchPage() }, 100)
            return
        }

        val js = """
            (function(){
              try{
                if(typeof window.fnSearch !== 'function') return false;
                window.fnSearch(${action.page});
                return true;
              }catch(e){
                return false;
              }
            })();
        """.trimIndent()

        status.text = "목록 페이지 ${action.page}쪽 이동 중"
        webView.evaluateJavascript(js) { result ->
            if (result != "true") {
                batchErrors.put(JSONObject()
                    .put("url", action.baseUrl)
                    .put("type", "pagination-action-unavailable")
                    .put("page", action.page))
                handler.postDelayed({ loadNextBatchPage() }, 150)
            } else {
                // fnSearch가 전체 페이지 이동이 아닌 DOM/AJAX 갱신을 사용하는 경우를 위한 보조 수집.
                handler.postDelayed({
                    if (batchRunning && !batchPausedForLogin && !batchCollecting && pendingBatchPageAction == null) {
                        scheduleBatchSnapshot()
                    }
                }, 1100)
            }
        }
    }

    private fun pageActionKey(action: BatchPageAction): String =
        "${action.baseUrl}|fnSearch|${action.page}"

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
        batchButton.text = "접근 가능 정보 일괄 수집"
        finalizeBatchJson(reason)
        status.text = "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 오류 ${batchErrors.length()} / 레코드 ${batchRecords.length()}"
    }

    private fun finalizeBatchJson(reason: String) {
        val out = JSONObject()
            .put("collectorVersion", VERSION)
            .put("provider", provider)
            .put("collectedAt", Instant.now().toString())
            .put("mode", "batch")
            .put("completion", reason)
            .put("summary", JSONObject()
                .put("attemptedPages", batchPageCount)
                .put("successfulPages", batchSnapshots.length())
                .put("errorPages", batchErrors.length())
                .put("records", batchRecords.length())
                .put("resourceLinks", batchResources.length())
                .put("paginationActionsCompleted", batchPageActionVisited.size))
            .put("errors", batchErrors)
            .put("records", batchRecords)
            .put("snapshots", batchSnapshots)
            .put("resourceLinks", batchResources)
        lastJson = out.toString(2)
        showPreview(lastJson)
    }

    private fun collectSnapshot(callback: (JSONObject?) -> Unit) {
        val js = snapshotJavascript()
        webView.evaluateJavascript(js) { encoded ->
            try {
                val raw = decodeJsString(encoded)
                val obj = JSONObject(raw)
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

    private fun snapshotJavascript(): String = """
        (function(){
          function visible(el){
            if(!el) return false;
            var s=getComputedStyle(el);
            if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
            var r=el.getBoundingClientRect();
            return r.width>0 && r.height>0;
          }
          function cleanText(v){
            return String(v||'').replace(/\s+/g,' ').trim();
          }
          function safeCloneText(el,maxLen){
            if(!el) return '';
            var clone=el.cloneNode(true);
            var rm=clone.querySelectorAll('script,style,noscript,template,input,textarea,select,option,form,[type=hidden],[hidden],[aria-hidden=true]');
            for(var i=0;i<rm.length;i++) rm[i].remove();
            var t=cleanText(clone.innerText||clone.textContent||'');
            t=t.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'[redacted-email]');
            return t.slice(0,maxLen||3000);
          }
          function unsafePseudoUrl(raw){
            raw=String(raw||'').trim();
            if(!raw || raw.length>4096) return true;
            if(/^(?:javascript:|data:|mailto:|tel:)/i.test(raw)) return true;
            if(/^[A-Za-z_$][A-Za-z0-9_$]*\s*\(/.test(raw)) return true;
            if(/^(?:return\s+false|void\s*\()/i.test(raw)) return true;
            return false;
          }
          function safeUrl(raw){
            if(unsafePseudoUrl(raw)) return '';
            try{
              var u=new URL(raw,location.href);
              if(u.protocol!=='https:' && u.protocol!=='http:') return '';
              return u.origin+u.pathname;
            }catch(e){ return ''; }
          }
          function fullNavigationUrl(raw){
            if(unsafePseudoUrl(raw)) return '';
            try{
              var u=new URL(raw,location.href);
              if(u.origin!==location.origin) return '';
              var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|sysReg|sysChg|userId|ipMac/i;
              var filtered=new URLSearchParams();
              u.searchParams.forEach(function(v,k){ if(!badKey.test(k)) filtered.append(k,v); });
              var q=filtered.toString();
              return u.origin+u.pathname+(q?'?'+q:'');
            }catch(e){ return ''; }
          }
          function safeExportUrl(raw){
            if(unsafePseudoUrl(raw)) return '';
            try{
              var u=new URL(raw,location.href);
              if(u.protocol!=='https:' && u.protocol!=='http:') return '';
              var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|preurl|returnurl|redirect|callback|sysReg|sysChg|userId|ipMac/i;
              var filtered=new URLSearchParams();
              u.searchParams.forEach(function(v,k){ if(!badKey.test(k)) filtered.append(k,v); });
              var q=filtered.toString();
              return u.origin+u.pathname+(q?'?'+q:'');
            }catch(e){ return ''; }
          }
          function routeFromScript(raw){
            raw=String(raw||'').replace(/&amp;/g,'&').trim();
            if(!raw || raw.length>4096) return '';

            // 함수 호출 전체를 URL로 해석하지 않는다. 실제 문자열 URL만 추출한다.
            var explicit=[
              /location(?:\.href)?\s*=\s*['"]([^'"]+)['"]/i,
              /location\.(?:assign|replace)\s*\(\s*['"]([^'"]+)['"]/i,
              /window\.open\s*\(\s*['"]([^'"]+)['"]/i
            ];
            for(var i=0;i<explicit.length;i++){
              var em=raw.match(explicit[i]);
              if(em && em[1]){
                var er=fullNavigationUrl(em[1]);
                if(er) return er;
              }
            }

            var quoted=/['"]((?:https?:\/\/[^'"]+|\/[^'"]+\.do(?:\?[^'"]*)?))['"]/ig;
            var m;
            while((m=quoted.exec(raw))!==null){
              var q=fullNavigationUrl(m[1]);
              if(q) return q;
            }
            return '';
          }

          var forbidden=/password|passwd|cookie|session|token|csrf|transkey|captcha|credential|secret/i;
          var loginSensitive=/(아이디|비밀번호|로그인|로그아웃|회원정보|마이페이지|account|sign[ -]?in|sign[ -]?out)/i;
          var admissionTerms=/(대학|대학교|학과|학부|전공|모집|전형|입시|입결|성적|환산|등급|경쟁률|합격|예측|지원|교과|종합|면접|수능|최저|50%|70%|칸수|모집요강|전년도|202[0-9])/i;

          var pass=false;
          var pw=document.querySelectorAll('input[type=password]');
          for(var p=0;p<pw.length;p++){ if(visible(pw[p])) { pass=true; break; } }
          var bodyText=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,16000);
          var logoutControl=false;
          var sessionControls=document.querySelectorAll('a,button,[role=button]');
          for(var sc=0;sc<sessionControls.length;sc++){
            var sn=sessionControls[sc];
            if(!visible(sn)) continue;
            var sl=cleanText(sn.innerText||sn.textContent||sn.getAttribute('aria-label')||'');
            if(/^(로그아웃|log\s*out|sign\s*out)$/i.test(sl)){ logoutControl=true; break; }
          }
          var loginUrl=/(\/mbs\/log\/|login|signin|sign-in|member\/login|loginForm)/i.test(location.href);
          var loginRequired=/(로그인이\s*필요|로그인\s*후\s*(?:이용|사용)|로그인해\s*주세요|로그인해주세요|회원만\s*이용|서비스\s*이용을\s*위해\s*로그인)/i.test(bodyText);
          var authenticated=logoutControl;
          var titleText=cleanText(document.title||'');
          var error404=/(404\s*Not\s*Found|요청하신\s*페이지를\s*찾을\s*수\s*없|페이지를\s*찾을\s*수\s*없)/i.test(titleText+' '+bodyText);
          var serverError=/(500\s*(?:Internal\s*Server\s*Error)?|서비스\s*처리\s*중\s*오류|일시적인\s*오류가\s*발생)/i.test(titleText+' '+bodyText);
          var pageError=error404||serverError;
          var errorType=error404?'404':(serverError?'server-error':'');

          var context=[];
          var contextNodes=document.querySelectorAll('h1,h2,h3,h4,h5,h6,.title,.tit,.sub-title,.breadcrumb,.location,[class*=title],[class*=breadcrumb]');
          for(var c=0;c<contextNodes.length && context.length<80;c++){
            var ce=contextNodes[c];
            if(!visible(ce)) continue;
            var ct=safeCloneText(ce,800);
            if(ct.length>=2 && !forbidden.test(ct) && !loginSensitive.test(ct)) context.push(ct);
          }

          var tables=[];
          var tableNodes=document.querySelectorAll('table,[role=table]');
          for(var ti=0;ti<tableNodes.length && tables.length<50;ti++){
            var table=tableNodes[ti];
            if(!visible(table)) continue;
            var rows=[];
            var trNodes=table.querySelectorAll('tr,[role=row]');
            for(var ri=0;ri<trNodes.length && rows.length<250;ri++){
              var tr=trNodes[ri];
              if(!visible(tr)) continue;
              var cells=[];
              var cellNodes=tr.querySelectorAll('th,td,[role=columnheader],[role=cell]');
              for(var ci=0;ci<cellNodes.length && cells.length<40;ci++){
                var cell=cellNodes[ci];
                if(!visible(cell)) continue;
                var cellText=safeCloneText(cell,1200);
                if(cellText && !forbidden.test(cellText.substring(0,160))) cells.push(cellText);
              }
              if(cells.length>0) rows.push(cells);
            }
            if(rows.length>0){
              tables.push({caption:safeCloneText(table.querySelector('caption'),500),rows:rows});
            }
          }

          var blocks=[];
          var blockNodes=document.querySelectorAll('article,.card,.item,.result,.list-item,.tbl_row,[class*=result],[class*=admission],[class*=score],[class*=grade],[class*=competition],[class*=apply],dl,section');
          for(var bi=0;bi<blockNodes.length && blocks.length<300;bi++){
            var be=blockNodes[bi];
            if(!visible(be)) continue;
            var meta=(be.id||'')+' '+(be.className||'')+' '+(be.getAttribute('name')||'');
            if(forbidden.test(meta)) continue;
            var bt=safeCloneText(be,3000);
            if(bt.length<4 || loginSensitive.test(bt.substring(0,200))) continue;
            if(admissionTerms.test(bt)) blocks.push(bt);
          }

          var nav=[];
          var resources=[];
          var pageActions=[];
          var linkNodes=document.querySelectorAll('a,button,[role=button],[onclick],[data-href],[data-url],[data-link],[data-path]');
          var seenNav={};
          var seenRes={};
          var seenPageAction={};
          var currentParts=location.pathname.split('/').filter(Boolean);
          var prefix=currentParts.slice(0,2).join('/');
          var scriptCandidates=0;
          var paginationAllowed=/\/(?:ucp\/uvt\/uni\/univView|ucp\/cls\/uni\/classUnivView|ucp\/prc\/uni\/admssUnivView|sco\/agu\/univScoScaAnlsView|uct\/acd\/adc\/characteristicsView|uct\/acd\/ueg\/univEtenGuideView|uct\/acd\/ade\/criteriaAndResultView|uct\/acd\/dia\/disabledAdmssView)\.do$/i.test(location.pathname);
          for(var li=0;li<linkNodes.length;li++){
            var a=linkNodes[li];
            if(!visible(a)) continue;
            var href=a.getAttribute('href')||'';
            var onclick=a.getAttribute('onclick')||'';
            var dataRaw=a.getAttribute('data-href')||a.getAttribute('data-url')||a.getAttribute('data-link')||a.getAttribute('data-path')||'';
            var raw=dataRaw||href||'';
            var label=cleanText(a.innerText||a.textContent||a.getAttribute('aria-label')||a.getAttribute('title')||'').slice(0,500);
            var meta2=(a.id||'')+' '+(a.className||'')+' '+label+' '+raw+' '+onclick;
            if(/logout|signout|로그아웃|delete|withdraw|탈퇴|회원탈퇴|원서접수|결제|삭제|저장/i.test(meta2)) continue;
            if(/^mailto:/i.test(raw) || /^tel:/i.test(raw)) continue;

            var scriptText=(onclick||'')+' '+(/^javascript:/i.test(raw)?raw:'');
            if(paginationAllowed){
              var pm=scriptText.match(/\bfnSearch\s*\(\s*([0-9]{1,4})\s*\)/i);
              if(pm){
                var pageNum=parseInt(pm[1],10);
                if(pageNum>1 && pageNum<=500){
                  var actionKey=fullNavigationUrl(location.href)+'|fnSearch|'+pageNum;
                  if(!seenPageAction[actionKey]){
                    pageActions.push({type:'fnSearch',page:pageNum,baseUrl:fullNavigationUrl(location.href)});
                    seenPageAction[actionKey]=1;
                  }
                }
              }
            }

            var route='';
            var directUrlish=/^(?:https?:\/\/|\/|\.\.?\/)/i.test(raw) && !/[{}();]/.test(raw);
            if(raw && directUrlish && raw!=='#') route=fullNavigationUrl(raw);
            if(!route && onclick){ route=routeFromScript(onclick); if(route) scriptCandidates++; }
            if(!route && /^javascript:/i.test(raw)){ route=routeFromScript(raw); if(route) scriptCandidates++; }

            var resourceRaw=(raw && directUrlish) ? raw : (route||'');
            var exportUrl=safeExportUrl(resourceRaw);
            var u=null;
            try{ if(resourceRaw) u=new URL(resourceRaw,location.href); }catch(e){ u=null; }
            var ext=/\.(pdf|hwp|hwpx|xls|xlsx|csv|doc|docx|ppt|pptx|zip)(?:$|[?#])/i;
            if(u && ext.test(u.pathname)){
              if(exportUrl && !seenRes[exportUrl]){ resources.push({label:label,url:exportUrl}); seenRes[exportUrl]=1; }
              continue;
            }

            if(!route) continue;
            var ru;
            try{ ru=new URL(route,location.href); }catch(e2){ continue; }
            if(ru.origin!==location.origin) continue;
            var sameArea=prefix && ru.pathname.split('/').filter(Boolean).slice(0,2).join('/')===prefix;
            if(!(admissionTerms.test(label+' '+ru.pathname+' '+onclick) || sameArea)) continue;
            if(seenNav[route]) continue;
            nav.push({label:label,url:route,exportUrl:safeExportUrl(route)});
            seenNav[route]=1;
            if(nav.length>=240) break;
          }

          return JSON.stringify({
            title:document.title||'',
            url:safeExportUrl(location.href),
            navigationKey:fullNavigationUrl(location.href),
            collectedAt:new Date().toISOString(),
            session:{needsLogin:(pass||loginUrl||loginRequired)&&!authenticated,authenticated:authenticated},
            pageState:{isError:pageError,errorType:errorType},
            discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length},
            context:context,
            tables:tables,
            blocks:blocks,
            navigationLinks:nav,
            pageActions:pageActions,
            resourceLinks:resources
          });
        })();
    """.trimIndent()

    private fun normalizeSnapshot(snapshot: JSONObject): JSONArray {
        if (provider == "adiga") {
            val specialized = normalizeAdigaSnapshot(snapshot)
            if (specialized != null) return dedupeRecords(specialized)
        }
        return normalizeGenericSnapshot(snapshot)
    }

    private fun normalizeAdigaSnapshot(snapshot: JSONObject): JSONArray? {
        val url = snapshot.optString("url")
        return when {
            url.contains("/ucp/uvt/uni/univView.do") -> parseAdigaUniversityList(snapshot)
            url.contains("/ucp/cls/uni/classUnivView.do") -> parseAdigaDepartmentList(snapshot)
            url.contains("/uct/acd/adc/characteristicsView.do") -> parseAdigaCharacteristicsIndex(snapshot)
            url.contains("/uct/acd/ueg/univEtenGuideView.do") -> parseAdigaGuideIndex(snapshot)
            url.contains("/uct/acd/ade/criteriaAndResultView.do") -> parseAdigaCriteriaIndex(snapshot)
            url.contains("/uct/acd/dia/disabledAdmssView.do") -> parseAdigaDisabledAdmissionsIndex(snapshot)
            // 학생부 성적은 Admission Hub의 검증된 학생부 데이터와 충돌하지 않도록
            // raw snapshot만 보존하고 일반 입시 레코드로 변환하지 않는다.
            url.contains("/sco/sca/schScoAnlsView.do") -> JSONArray()
            // 아직 구조가 확인되지 않은 어디가 페이지는 raw snapshot으로 보존하되
            // 잘못된 정규화 레코드는 만들지 않는다.
            url.contains("adiga.kr") -> JSONArray()
            else -> null
        }
    }

    private fun normalizeGenericSnapshot(snapshot: JSONObject): JSONArray {
        val result = JSONArray()
        val contextParts = mutableListOf<String>()
        val context = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until context.length()) {
            val t = context.optString(i).trim()
            if (t.isNotBlank()) contextParts.add(t)
        }
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 20)) {
            val t = blocks.optString(i).trim()
            if (t.isNotBlank()) contextParts.add(t)
        }
        val inherited = inferContext(contextParts.joinToString(" | ").take(8000))

        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until tables.length()) {
            val rows = tables.optJSONObject(ti)?.optJSONArray("rows") ?: continue
            for (ri in 0 until rows.length()) {
                val row = rows.optJSONArray(ri) ?: continue
                val cells = mutableListOf<String>()
                for (ci in 0 until row.length()) cells.add(row.optString(ci))
                buildRecord(cells.joinToString(" | "), inherited)?.let { result.put(it) }
            }
        }
        return dedupeRecords(result)
    }

    private fun firstAdigaTableRows(snapshot: JSONObject): JSONArray? {
        val tables = snapshot.optJSONArray("tables") ?: return null
        if (tables.length() == 0) return null
        return tables.optJSONObject(0)?.optJSONArray("rows")
    }

    private fun parseAdigaUniversityList(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstAdigaTableRows(snapshot) ?: return out
        if (rows.length() < 2) return out
        val header = rows.optJSONArray(0) ?: return out
        val pageYear = queryYear(snapshot.optString("url"))
        val competitionYear = Regex("(20\\d{2})\\s*경쟁률")
            .find(header.optString(2))?.groupValues?.getOrNull(1)?.toIntOrNull()

        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 6) continue
            val university = normalizeUniversityCell(row.optString(0))
            if (!looksLikeUniversity(university)) continue
            val (early, regular) = parseCompetition(row.optString(2))
            val metrics = JSONObject()
                .put("region", valueOrNull(row.optString(1)))
                .put("earlyCompetition", numberOrNull(early))
                .put("regularCompetition", numberOrNull(regular))
                .put("competitionYear", competitionYear ?: JSONObject.NULL)
                .put("enrollmentCapacity", intOrNull(row.optString(3)))
                .put("departmentCount", intOrNull(row.optString(4)))
                .put("admissionCount", intOrNull(row.optString(5)))
            out.put(JSONObject()
                .put("recordType", "university-summary")
                .put("year", pageYear ?: JSONObject.NULL)
                .put("university", university)
                .put("department", JSONObject.NULL)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun parseAdigaDepartmentList(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstAdigaTableRows(snapshot) ?: return out
        if (rows.length() < 2) return out
        val header = rows.optJSONArray(0) ?: return out
        val pageYear = queryYear(snapshot.optString("url"))
        val competitionYear = Regex("(20\\d{2})\\s*경쟁률")
            .find(header.optString(3))?.groupValues?.getOrNull(1)?.toIntOrNull()

        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 5) continue
            val department = row.optString(0).trim()
            val university = normalizeUniversityCell(row.optString(1))
            if (department.isBlank() || department.contains("검색결과가 없습니다") || !looksLikeUniversity(university)) continue
            val (early, regular) = parseCompetition(row.optString(3))
            val metrics = JSONObject()
                .put("region", valueOrNull(row.optString(2)))
                .put("earlyCompetition", numberOrNull(early))
                .put("regularCompetition", numberOrNull(regular))
                .put("competitionYear", competitionYear ?: JSONObject.NULL)
                .put("enrollmentCapacity", intOrNull(row.optString(4)))
                .put("hasAdmissionResult", row.optString(5).contains("입시결과"))
            out.put(JSONObject()
                .put("recordType", "department-summary")
                .put("year", pageYear ?: JSONObject.NULL)
                .put("university", university)
                .put("department", department)
                .put("admission", JSONObject.NULL)
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun parseAdigaCharacteristicsIndex(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstAdigaTableRows(snapshot) ?: return out
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 3) continue
            val university = normalizeUniversityCell(row.optString(0))
            if (!looksLikeUniversity(university)) continue
            val metrics = JSONObject()
                .put("recruitmentTotal", intOrNull(row.optString(1)))
                .put("registeredAt", valueOrNull(row.optString(2)))
            out.put(indexRecord("university-characteristics-index", university, metrics, snapshot, row))
        }
        return out
    }

    private fun parseAdigaGuideIndex(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstAdigaTableRows(snapshot) ?: return out
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 2) continue
            val university = normalizeUniversityCell(row.optString(0))
            if (!looksLikeUniversity(university)) continue
            val metrics = JSONObject().put("registeredAt", valueOrNull(row.optString(1)))
            out.put(indexRecord("university-guide-index", university, metrics, snapshot, row))
        }
        return out
    }

    private fun parseAdigaCriteriaIndex(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstAdigaTableRows(snapshot) ?: return out
        if (rows.length() < 2) return out

        var labels = listOf("학생부위주(종합)", "학생부위주(교과)", "수능위주")
        val maybeLabels = rows.optJSONArray(1)
        if (maybeLabels != null && maybeLabels.length() >= 3 &&
            (0 until minOf(3, maybeLabels.length())).all { maybeLabels.optString(it).contains("위주") }) {
            labels = (0 until 3).map { maybeLabels.optString(it) }
        }

        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 5) continue
            val university = normalizeUniversityCell(row.optString(0))
            if (!looksLikeUniversity(university)) continue
            val metrics = JSONObject()
                .put("holisticRecruitment", intOrNull(row.optString(1)))
                .put("curriculumRecruitment", intOrNull(row.optString(2)))
                .put("csatRecruitment", intOrNull(row.optString(3)))
                .put("registeredAt", valueOrNull(row.optString(4)))
                .put("columnLabels", JSONArray(labels))
            out.put(indexRecord("criteria-result-index", university, metrics, snapshot, row))
        }
        return out
    }

    private fun parseAdigaDisabledAdmissionsIndex(snapshot: JSONObject): JSONArray {
        val out = JSONArray()
        val rows = firstAdigaTableRows(snapshot) ?: return out
        val header = if (rows.length() > 0) rows.optJSONArray(0) else null
        val year = header?.let {
            Regex("(20\\d{2})").find(it.optString(1))?.groupValues?.getOrNull(1)?.toIntOrNull()
        }
        for (ri in 1 until rows.length()) {
            val row = rows.optJSONArray(ri) ?: continue
            if (row.length() < 2) continue
            val university = normalizeUniversityCell(row.optString(0).replace("상세정보", "").trim())
            if (!looksLikeUniversity(university)) continue
            val metrics = JSONObject().put("admittedStudents", intOrNull(row.optString(1)))
            out.put(JSONObject()
                .put("recordType", "disabled-admissions-index")
                .put("year", year ?: JSONObject.NULL)
                .put("university", university)
                .put("department", JSONObject.NULL)
                .put("admission", "대학별 장애인 전형")
                .put("metrics", metrics)
                .put("confidence", "high")
                .put("sourcePage", snapshot.optString("url"))
                .put("rawEvidence", rowToEvidence(row)))
        }
        return out
    }

    private fun indexRecord(
        type: String,
        university: String,
        metrics: JSONObject,
        snapshot: JSONObject,
        row: JSONArray
    ): JSONObject = JSONObject()
        .put("recordType", type)
        .put("year", JSONObject.NULL)
        .put("university", university)
        .put("department", JSONObject.NULL)
        .put("admission", JSONObject.NULL)
        .put("metrics", metrics)
        .put("confidence", "high")
        .put("sourcePage", snapshot.optString("url"))
        .put("rawEvidence", rowToEvidence(row))

    private fun queryYear(url: String): Int? = try {
        Uri.parse(url).getQueryParameter("searchSyr")?.toIntOrNull()
    } catch (_: Exception) {
        null
    }

    private fun normalizeUniversityCell(value: String): String =
        value.replace(Regex("\\s+\\["), "[")
            .replace(Regex("\\s+"), " ")
            .trim()

    private fun looksLikeUniversity(value: String): Boolean {
        if (value.isBlank()) return false
        if (value.contains("대학명을 클릭") || value == "일반대학" || value == "전문대학") return false
        return Regex("(대학교|대학)(?:\\[(?:본교|분교|제\\d+캠퍼스)\\])?$").containsMatchIn(value)
    }

    private fun parseCompetition(value: String): Pair<Double?, Double?> {
        val early = Regex("수시\\s*([0-9]+(?:\\.[0-9]+)?)").find(value)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
        val regular = Regex("정시\\s*([0-9]+(?:\\.[0-9]+)?)").find(value)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
        return early to regular
    }

    private fun intOrNull(value: String): Any =
        value.replace(",", "").trim().toIntOrNull() ?: JSONObject.NULL

    private fun numberOrNull(value: Double?): Any = value ?: JSONObject.NULL

    private fun valueOrNull(value: String): Any =
        value.trim().takeIf { it.isNotBlank() } ?: JSONObject.NULL

    private fun rowToEvidence(row: JSONArray): String {
        val values = mutableListOf<String>()
        for (i in 0 until row.length()) values.add(row.optString(i))
        return values.joinToString(" | ").take(3000)
    }

    private data class InferredContext(
        val university: String?,
        val department: String?,
        val admission: String?,
        val year: Int?
    )

    private fun inferContext(text: String): InferredContext {
        val universityRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,45}(대학교|대학)(?:\\[본교\\])?)")
        val deptRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,55}(학과|학부|전공|모집단위))")
        val admissionRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,70}(전형|학생부교과|학생부종합|교과|종합|추천|면접))")
        val yearRegex = Regex("(?:^|[^0-9])(20[0-9]{2})(?:학년도|년도|년)?")
        return InferredContext(
            universityRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            deptRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            admissionRegex.find(text)?.groupValues?.getOrNull(1)?.trim(),
            yearRegex.find(text)?.groupValues?.getOrNull(1)?.toIntOrNull()
        )
    }

    private fun buildRecord(evidenceRaw: String, inherited: InferredContext): JSONObject? {
        val evidence = evidenceRaw.replace(Regex("\\s+"), " ").trim().take(5000)
        if (evidence.length < 2) return null

        val local = inferContext(evidence)
        val year = local.year ?: inherited.year
        val university = local.university ?: inherited.university
        val department = local.department ?: inherited.department
        val admission = local.admission ?: inherited.admission

        val competitionRegex = Regex("(?:경쟁률)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?(?:\\s*[:대]\\s*1)?)")
        val capacityRegex = Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9]+)")
        val cut50Regex = Regex("(?:50%\\s*(?:컷|cut|등급|점수)|산출점수\\s*50%)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)", RegexOption.IGNORE_CASE)
        val cut70Regex = Regex("(?:70%\\s*(?:컷|cut|등급|점수)|산출점수\\s*70%)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)", RegexOption.IGNORE_CASE)
        val myScoreRegex = Regex("(?:내\\s*(?:환산)?점수|나의\\s*(?:환산)?점수|산출점수|환산점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)")
        val gradeRegex = Regex("(?:등급|반영\\s*평균등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)")
        val barsRegex = Regex("(?:칸수|칸\\s*수)\\s*[:：]?\\s*([0-9]+)")
        val judgmentRegex = Regex("(?:판정|합격예측|지원판정)\\s*[:：]?\\s*(안정|적정|소신|위험|상향|하향|가능|불안|유리|불리)")
        val applicantRegex = Regex("(?:지원자수|지원자 수)\\s*[:：]?\\s*([0-9,]+)")

        val metrics = JSONObject()
            .put("myScore", myScoreRegex.find(evidence)?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: JSONObject.NULL)
            .put("grade", gradeRegex.find(evidence)?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: JSONObject.NULL)
            .put("cut50", cut50Regex.find(evidence)?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: JSONObject.NULL)
            .put("cut70", cut70Regex.find(evidence)?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: JSONObject.NULL)
            .put("competition", competitionRegex.find(evidence)?.groupValues?.getOrNull(1) ?: JSONObject.NULL)
            .put("capacity", capacityRegex.find(evidence)?.groupValues?.getOrNull(1)?.replace(",", "")?.toIntOrNull() ?: JSONObject.NULL)
            .put("applicants", applicantRegex.find(evidence)?.groupValues?.getOrNull(1)?.replace(",", "")?.toIntOrNull() ?: JSONObject.NULL)
            .put("jinhakBars", barsRegex.find(evidence)?.groupValues?.getOrNull(1)?.toIntOrNull() ?: JSONObject.NULL)
            .put("jinhakJudgment", judgmentRegex.find(evidence)?.groupValues?.getOrNull(1) ?: JSONObject.NULL)

        val hasMetric = metrics.keys().asSequence().any { !metrics.isNull(it) }
        if (!hasMetric) return null

        val confidence = when {
            university != null && department != null && admission != null && hasMetric -> "high"
            university != null && department != null && admission != null -> "medium"
            hasMetric && (university != null || department != null || admission != null) -> "medium"
            else -> "raw"
        }

        return JSONObject()
            .put("year", year ?: JSONObject.NULL)
            .put("university", university ?: JSONObject.NULL)
            .put("department", department ?: JSONObject.NULL)
            .put("admission", admission ?: JSONObject.NULL)
            .put("metrics", metrics)
            .put("confidence", confidence)
            .put("rawEvidence", evidence)
    }

    private fun dedupeRecords(input: JSONArray): JSONArray {
        val out = JSONArray()
        val seen = linkedSetOf<String>()
        for (i in 0 until input.length()) {
            val obj = input.optJSONObject(i) ?: continue
            val key = listOf(
                obj.optString("recordType"),
                obj.opt("year")?.toString() ?: "",
                obj.opt("university")?.toString() ?: "",
                obj.opt("department")?.toString() ?: "",
                obj.opt("admission")?.toString() ?: "",
                obj.optJSONObject("metrics")?.toString() ?: "",
                obj.optString("rawEvidence").take(400)
            ).joinToString("|")
            if (seen.add(key)) out.put(obj)
        }
        return out
    }

    private fun appendUniqueRecords(target: JSONArray, incoming: JSONArray) {
        val existing = linkedSetOf<String>()
        for (i in 0 until target.length()) {
            val o = target.optJSONObject(i) ?: continue
            existing.add(recordKey(o))
        }
        for (i in 0 until incoming.length()) {
            val o = incoming.optJSONObject(i) ?: continue
            if (existing.add(recordKey(o))) target.put(o)
        }
    }

    private fun recordKey(o: JSONObject): String = listOf(
        o.optString("recordType"),
        o.opt("year")?.toString() ?: "",
        o.opt("university")?.toString() ?: "",
        o.opt("department")?.toString() ?: "",
        o.opt("admission")?.toString() ?: "",
        o.optJSONObject("metrics")?.toString() ?: "",
        o.optString("rawEvidence").take(300)
    ).joinToString("|")

    private fun appendUniqueResources(target: JSONArray, incoming: JSONArray) {
        val seen = linkedSetOf<String>()
        for (i in 0 until target.length()) seen.add(target.optJSONObject(i)?.optString("url") ?: "")
        for (i in 0 until incoming.length()) {
            val obj = incoming.optJSONObject(i) ?: continue
            val url = obj.optString("url")
            if (url.isNotBlank() && seen.add(url)) target.put(obj)
        }
    }

    private fun enqueueProviderSeeds() {
        val seeds = if (provider == "adiga") {
            listOf(
                "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2027",
                "https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&searchSyr=2026",
                "https://www.adiga.kr/ucp/cls/uni/classUnivView.do?menuId=PCCLSINF2000&searchSyr=2027",
                "https://www.adiga.kr/ucp/cls/uni/classUnivView.do?menuId=PCCLSINF2000&searchSyr=2026",
                "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2027",
                "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRCINF2000&searchSyr=2026",
                "https://www.adiga.kr/sco/agu/univScoScaAnlsView.do?menuId=PCSCOAGU2000",
                "https://www.adiga.kr/uct/ces/archiveView.do?menuId=PCUCTCES1000",
                "https://www.adiga.kr/uct/acd/adc/characteristicsView.do?menuId=PCUCTACD1100",
                "https://www.adiga.kr/uct/acd/ueg/univEtenGuideView.do?menuId=PCUCTACD3100",
                "https://www.adiga.kr/uct/acd/ade/criteriaAndResultView.do?menuId=PCUCTACD2000"
            )
        } else {
            emptyList()
        }

        for (rawUrl in seeds) {
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
            if (url.isBlank() || !isProviderUrl(url)) continue
            if (batchVisited.contains(url)) continue
            if (batchQueued.add(url)) batchQueue.addLast(url)
            if (batchQueue.size + batchVisited.size >= MAX_BATCH_PAGES * 2) break
        }
    }

    private fun enqueuePageActions(actions: JSONArray) {
        for (i in 0 until actions.length()) {
            val obj = actions.optJSONObject(i) ?: continue
            if (obj.optString("type") != "fnSearch") continue
            val page = obj.optInt("page", -1)
            val baseUrl = canonicalizeBatchUrl(obj.optString("baseUrl"))
            if (page <= 1 || page > 500 || baseUrl.isBlank() || !isProviderUrl(baseUrl)) continue
            val action = BatchPageAction(baseUrl, page)
            val key = pageActionKey(action)
            if (batchPageActionVisited.contains(key)) continue
            if (batchPageActionQueued.add(key)) batchPageActions.addLast(action)
            if (batchPageActions.size + batchPageActionVisited.size >= MAX_BATCH_PAGES * 2) break
        }
    }

    private fun stripNavigationLinksForExport(snapshot: JSONObject): JSONObject {
        val copy = JSONObject(snapshot.toString())
        copy.remove("navigationLinks")
        copy.remove("pageActions")
        copy.remove("navigationKey")
        return copy
    }

    private fun isProviderUrl(url: String): Boolean {
        return try {
            val host = Uri.parse(url).host?.lowercase() ?: return false
            if (provider == "adiga") host == "adiga.kr" || host.endsWith(".adiga.kr")
            else host == "jinhak.com" || host.endsWith(".jinhak.com")
        } catch (_: Exception) {
            false
        }
    }

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
            putExtra(Intent.EXTRA_TITLE, "admission-${provider}-v021-${System.currentTimeMillis()}.json")
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
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }
}
