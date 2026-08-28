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
    private val batchQueue = ArrayDeque<String>()
    private val batchVisited = linkedSetOf<String>()
    private val batchQueued = linkedSetOf<String>()
    private var batchSnapshots = JSONArray()
    private var batchRecords = JSONArray()
    private var batchResources = JSONArray()
    private var batchRunning = false
    private var batchPausedForLogin = false
    private var batchCollecting = false
    private var currentBatchTarget: String? = null
    private var batchPageCount = 0

    private var lastJson: String = ""
    private var provider: String = "adiga"

    companion object {
        private const val SAVE_JSON_REQUEST = 7001
        private const val ADIGA_URL = "https://www.adiga.kr/"
        private const val JINHAK_URL = "https://www.jinhak.com/"
        private const val MAX_BATCH_PAGES = 120
        private const val PREVIEW_LIMIT = 16000
        private const val VERSION = "0.2.0"
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
                    batchRunning -> scheduleBatchSnapshot()
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
                    var t=(el.innerText||el.textContent||'').replace(/\\s+/g,' ').trim();
                    if(!/^(로그인|log\\s*in|sign\\s*in)$/i.test(t)) continue;
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
              var authenticated=/(로그아웃|마이페이지|내\\s*정보|회원정보|MY\\s*PAGE|LOG\\s*OUT|SIGN\\s*OUT)/i.test(text);
              var loginUrl=/(login|signin|sign-in|member\\/login|loginForm)/i.test(location.href);
              return JSON.stringify({needsLogin:(pass||loginUrl)&&!authenticated,authenticated:authenticated});
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
        batchSnapshots = JSONArray()
        batchRecords = JSONArray()
        batchResources = JSONArray()
        batchRunning = true
        batchPausedForLogin = false
        batchCollecting = false
        batchPageCount = 0
        currentBatchTarget = url
        batchButton.text = "일괄 수집 중지"
        status.text = "일괄 수집 시작: 현재 영역을 탐색합니다."

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

            val session = snapshot.optJSONObject("session") ?: JSONObject()
            if (session.optBoolean("needsLogin", false)) {
                pauseBatchForLogin()
                return@collectSnapshot
            }

            val navigationKey = snapshot.optString("navigationKey")
            if (navigationKey.isNotBlank()) batchVisited.add(navigationKey)
            batchPageCount += 1

            batchSnapshots.put(stripNavigationLinksForExport(snapshot))
            appendUniqueRecords(batchRecords, normalizeSnapshot(snapshot))
            appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())
            enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())

            status.text = "일괄 수집: 페이지 $batchPageCount / 대기 ${batchQueue.size} / 레코드 ${batchRecords.length()}"

            if (batchPageCount >= MAX_BATCH_PAGES) {
                finishBatch("page-limit")
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 350)
            }
        }
    }

    private fun loadNextBatchPage() {
        if (!batchRunning || batchPausedForLogin) return
        while (batchQueue.isNotEmpty()) {
            val next = batchQueue.removeFirst()
            batchQueued.remove(next)
            if (batchVisited.contains(next) || !isProviderUrl(next)) continue
            currentBatchTarget = next
            status.text = "다음 입시정보 페이지 탐색: ${safeDisplayUrl(next)}"
            webView.loadUrl(next)
            return
        }
        finishBatch("completed")
    }

    private fun finishBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchButton.text = "접근 가능 정보 일괄 수집"
        finalizeBatchJson(reason)
        status.text = "일괄 수집 완료: 페이지 $batchPageCount / 레코드 ${batchRecords.length()} / 자료링크 ${batchResources.length()}"
    }

    private fun finalizeBatchJson(reason: String) {
        val out = JSONObject()
            .put("collectorVersion", VERSION)
            .put("provider", provider)
            .put("collectedAt", Instant.now().toString())
            .put("mode", "batch")
            .put("completion", reason)
            .put("summary", JSONObject()
                .put("pages", batchSnapshots.length())
                .put("records", batchRecords.length())
                .put("resourceLinks", batchResources.length()))
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
            return String(v||'').replace(/\\s+/g,' ').trim();
          }
          function safeCloneText(el,maxLen){
            if(!el) return '';
            var clone=el.cloneNode(true);
            var rm=clone.querySelectorAll('script,style,noscript,template,input,textarea,select,option,form,[type=hidden],[hidden],[aria-hidden=true]');
            for(var i=0;i<rm.length;i++) rm[i].remove();
            var t=cleanText(clone.innerText||clone.textContent||'');
            t=t.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/ig,'[redacted-email]');
            return t.slice(0,maxLen||3000);
          }
          function safeUrl(raw){
            try{
              var u=new URL(raw,location.href);
              if(u.protocol!=='https:' && u.protocol!=='http:') return '';
              return u.origin+u.pathname+u.hash;
            }catch(e){ return ''; }
          }
          function fullNavigationUrl(raw){
            try{
              var u=new URL(raw,location.href);
              if(u.origin!==location.origin) return '';
              var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential/i;
              var filtered=new URLSearchParams();
              u.searchParams.forEach(function(v,k){ if(!badKey.test(k)) filtered.append(k,v); });
              var q=filtered.toString();
              return u.origin+u.pathname+(q?'?'+q:'')+u.hash;
            }catch(e){ return ''; }
          }

          var forbidden=/password|passwd|cookie|session|token|csrf|transkey|captcha|credential|secret/i;
          var loginSensitive=/(아이디|비밀번호|로그인|로그아웃|회원정보|마이페이지|account|sign[ -]?in|sign[ -]?out)/i;
          var admissionTerms=/(대학|대학교|학과|학부|전공|모집|전형|입시|입결|성적|환산|등급|경쟁률|합격|예측|지원|교과|종합|면접|수능|최저|50%|70%|칸수|모집요강|전년도|202[0-9])/i;

          var pass=false;
          var pw=document.querySelectorAll('input[type=password]');
          for(var p=0;p<pw.length;p++){ if(visible(pw[p])) { pass=true; break; } }
          var bodyText=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,12000);
          var authenticated=/(로그아웃|마이페이지|내\\s*정보|회원정보|MY\\s*PAGE|LOG\\s*OUT|SIGN\\s*OUT)/i.test(bodyText);
          var loginUrl=/(login|signin|sign-in|member\\/login|loginForm)/i.test(location.href);

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
          var linkNodes=document.querySelectorAll('a[href],[data-href],[data-url]');
          var seenNav={};
          var seenRes={};
          var currentParts=location.pathname.split('/').filter(Boolean);
          var prefix=currentParts.slice(0,2).join('/');
          for(var li=0;li<linkNodes.length;li++){
            var a=linkNodes[li];
            if(!visible(a)) continue;
            var raw=a.getAttribute('href')||a.getAttribute('data-href')||a.getAttribute('data-url')||'';
            if(!raw || /^javascript:/i.test(raw) || /^mailto:/i.test(raw) || /^tel:/i.test(raw)) continue;
            var label=cleanText(a.innerText||a.textContent||a.getAttribute('aria-label')||'').slice(0,500);
            var meta2=(a.id||'')+' '+(a.className||'')+' '+label+' '+raw;
            if(/logout|signout|로그아웃|delete|withdraw|탈퇴/i.test(meta2)) continue;
            var exportUrl=safeUrl(raw);
            if(!exportUrl) continue;
            var u;
            try{ u=new URL(raw,location.href); }catch(e){ continue; }
            var ext=/\\.(pdf|hwp|hwpx|xls|xlsx|csv|doc|docx|ppt|pptx)(?:$|[?#])/i;
            if(ext.test(u.pathname)){
              if(!seenRes[exportUrl]){ resources.push({label:label,url:exportUrl}); seenRes[exportUrl]=1; }
              continue;
            }
            if(u.origin!==location.origin) continue;
            var sameArea=prefix && u.pathname.split('/').filter(Boolean).slice(0,2).join('/')===prefix;
            if(!(admissionTerms.test(label+' '+u.pathname) || sameArea)) continue;
            var navUrl=fullNavigationUrl(raw);
            if(!navUrl || seenNav[navUrl]) continue;
            nav.push({label:label,url:navUrl,exportUrl:exportUrl});
            seenNav[navUrl]=1;
            if(nav.length>=160) break;
          }

          return JSON.stringify({
            title:document.title||'',
            url:location.origin+location.pathname+location.hash,
            navigationKey:fullNavigationUrl(location.href),
            collectedAt:new Date().toISOString(),
            session:{needsLogin:(pass||loginUrl)&&!authenticated,authenticated:authenticated},
            context:context,
            tables:tables,
            blocks:blocks,
            navigationLinks:nav,
            resourceLinks:resources
          });
        })();
    """.trimIndent()

    private fun normalizeSnapshot(snapshot: JSONObject): JSONArray {
        val result = JSONArray()
        val contextParts = mutableListOf<String>()
        val context = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until context.length()) {
            val t = context.optString(i).trim()
            if (t.isNotBlank()) contextParts.add(t)
        }
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 30)) {
            val t = blocks.optString(i).trim()
            if (t.isNotBlank()) contextParts.add(t)
        }
        val pageContext = contextParts.joinToString(" | ").take(12000)
        val inherited = inferContext(pageContext)

        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until tables.length()) {
            val table = tables.optJSONObject(ti) ?: continue
            val rows = table.optJSONArray("rows") ?: continue
            val header = mutableListOf<String>()
            if (rows.length() > 0) {
                val first = rows.optJSONArray(0)
                if (first != null) for (ci in 0 until first.length()) header.add(first.optString(ci))
            }
            for (ri in 0 until rows.length()) {
                val row = rows.optJSONArray(ri) ?: continue
                val cells = mutableListOf<String>()
                for (ci in 0 until row.length()) cells.add(row.optString(ci))
                val evidence = if (header.isNotEmpty() && ri > 0) {
                    cells.mapIndexed { idx, value ->
                        val h = header.getOrNull(idx)?.takeIf { it.isNotBlank() }
                        if (h != null) "$h: $value" else value
                    }.joinToString(" | ")
                } else {
                    cells.joinToString(" | ")
                }
                buildRecord(evidence, inherited)?.let { result.put(it) }
            }
        }

        for (i in 0 until blocks.length()) {
            val evidence = blocks.optString(i)
            buildRecord(evidence, inherited)?.let { result.put(it) }
        }
        return dedupeRecords(result)
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
        val admissionTerms = Regex("(대학|학과|학부|전공|전형|경쟁률|모집인원|산출점수|환산점수|등급|50%|70%|합격예측|칸수|지원자|입결|수능최저|면접)")
        if (!hasMetric && university == null && department == null && admission == null && !admissionTerms.containsMatchIn(evidence)) return null

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

    private fun enqueueDiscoveredLinks(links: JSONArray) {
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = obj.optString("url")
            if (url.isBlank() || !isProviderUrl(url)) continue
            if (batchVisited.contains(url)) continue
            if (batchQueued.add(url)) batchQueue.addLast(url)
            if (batchQueue.size + batchVisited.size >= MAX_BATCH_PAGES * 3) break
        }
    }

    private fun stripNavigationLinksForExport(snapshot: JSONObject): JSONObject {
        val copy = JSONObject(snapshot.toString())
        copy.remove("navigationLinks")
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
            putExtra(Intent.EXTRA_TITLE, "admission-${provider}-v02-${System.currentTimeMillis()}.json")
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

    override fun onPause() {
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
