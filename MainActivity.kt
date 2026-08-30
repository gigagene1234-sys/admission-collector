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
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import com.admissionhub.collector.capture.SnapshotScript
import com.admissionhub.collector.cloud.CloudOffloadCoordinator
import com.admissionhub.collector.local.LocalCollectorStore
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
    private lateinit var batchCover: TextView
    private lateinit var diagnosticButton: Button
    private lateinit var cloudOffload: CloudOffloadCoordinator
    private lateinit var localStore: LocalCollectorStore

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
    private var batchCloudPlansPending = 0
    private var batchCloudResumePlans = 0
    private var batchCloudPagesScheduled = 0
    private var batchCloudPagesSkipped = 0
    private var batchCloudPagesDeferred = 0
    private var batchContextRecoveries = 0
    private var batchSessionSyncRetries = 0
    private var batchNavigationWatchdogGeneration = 0
    private var batchNavigationWatchdogRecovery = false
    private var batchCloudFinalCheckInProgress = false
    private var batchLocalResumePlans = 0
    private var batchLocalPagesScheduled = 0
    private var batchLocalPagesSkipped = 0
    private var batchLocalRecordsPersisted = 0
    private var localRunId: String? = null
    private val batchPersistedPageSignatureOwners = linkedMapOf<String, MutableMap<String, Int>>()
    private var batchAuditPagesScheduled = 0
    private var batchUniversityDiscoveryPagesScheduled = 0

    private var lastJson: String = ""
    private var provider: ProviderId = ProviderId.ADIGA
    private var lastJinhakDigest = JSONObject()

    companion object {
        private const val SAVE_JSON_REQUEST = 7001
        private const val MAX_BATCH_PAGES = 3200
        private const val MAX_PAGE_RETRIES = 3
        private const val PREVIEW_LIMIT = 16000
        private const val MAX_SESSION_SYNC_RETRIES = 3
        private const val BATCH_NAVIGATION_TIMEOUT_MS = 15_000L
        private const val VERSION = "0.5.6"
        private const val BUILD_CODE = 10560
        private const val LOCAL_FIRST_BETA = true
        private const val ADIGA_RETRY_SUSPENDED = true
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        cloudOffload = CloudOffloadCoordinator(this)
        localStore = LocalCollectorStore(this)
        buildUi()
        configureWebView()
        openProvider(ProviderId.JINHAK)
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(10, 10, 10, 10)
        }

        root.addView(TextView(this).apply {
            text = "Admission Collector v$VERSION · build $BUILD_CODE · LOCAL-FIRST"
            gravity = Gravity.CENTER
            textSize = 13f
            setPadding(8, 6, 8, 6)
        }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ))

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
        val localState = Button(this).apply {
            text = "로컬 진행상태"
            setOnClickListener {
                val runId = localRunId ?: localStore.latestResumableRun(provider.wireName)
                val message = if (runId == null) {
                    "현재 이어받을 로컬 수집이 없습니다."
                } else {
                    localStore.stats(runId).toString(2)
                }
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Local-First 저장 상태")
                    .setMessage(message)
                    .setPositiveButton("확인", null)
                    .show()
            }
        }
        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(localState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val actions3 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        diagnosticButton = Button(this).apply {
            text = "진학사 분석 전송"
            setOnClickListener {
                if (provider == ProviderId.JINHAK) sendLatestJinhakAnalysisDigest() else sendLatestLocalDiagnostic(manual = true)
            }
        }
        actions3.addView(diagnosticButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        status = TextView(this).apply {
            text = "Admission Collector v$VERSION 준비 중"
            setPadding(8, 8, 8, 8)
        }

        webView = WebView(this)
        batchCover = TextView(this).apply {
            text = "수집 대기 중"
            gravity = Gravity.CENTER
            textSize = 18f
            setTextColor(android.graphics.Color.DKGRAY)
            setBackgroundColor(android.graphics.Color.WHITE)
            setPadding(32, 32, 32, 32)
            visibility = View.GONE
            isClickable = true
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        }
        val browserStack = FrameLayout(this).apply {
            addView(webView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(batchCover, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
        }
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
        root.addView(actions3)
        root.addView(status)
        root.addView(browserStack, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 3f))
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
                if (batchRunning && !batchPausedForLogin) {
                    armBatchNavigationWatchdog(url)
                    status.text = "수집 엔진 로딩: ${safeDisplayUrl(url)}"
                    if (::batchCover.isInitialized) {
                        batchCover.text = "입시정보 수집 중\n\n페이지 렌더링은 이 화면 뒤에서 처리됩니다.\n${safeDisplayUrl(url)}"
                    }
                } else if (!batchRunning) {
                    status.text = "불러오는 중: ${safeDisplayUrl(url)}"
                }
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                if (batchRunning && !batchPausedForLogin) {
                    disarmBatchNavigationWatchdog()
                    if (batchNavigationWatchdogRecovery) {
                        batchNavigationWatchdogRecovery = false
                        return
                    }
                    val pending = pendingBatchPageAction
                    if (pending != null && sameBatchDocument(url, pending.baseUrl)) {
                        executePendingBatchPageAction()
                    } else {
                        scheduleBatchSnapshot()
                    }
                    return
                }
                if (batchPausedForLogin) {
                    checkSessionState { needsLogin, authenticated ->
                        if (!needsLogin && authenticated) {
                            sessionState.text = "● 로그인 상태 복구 감지"
                            resumeAfterLogin()
                        }
                    }
                } else {
                    status.text = "현재 페이지: ${safeDisplayUrl(url)}"
                    checkSessionState()
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
        listOf(webView).forEach { target ->
            target.evaluateJavascript(js) { result ->
                if (result == "true") {
                    CookieManager.getInstance().flush()
                    sessionState.text = "● 로그인 세션 자동 연장"
                }
            }
        }
    }

    private fun currentAdapter(): ProviderAdapter = ProviderRegistry.adapter(provider)

    private fun openProvider(which: ProviderId) {
        if (batchRunning) stopBatch("서비스 전환")
        provider = which
        localRunId = localStore.latestResumableRun(which.wireName)
        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        status.text = if (which == ProviderId.JINHAK) "진학사 분석 모드: 로그인 후 원하는 리포트/대학 화면을 여세요." else "어디가 복구 보류: 진학사 분석 이후 한밭대 381쪽부터 재시도 예정"
        batchButton.text = when (which) {
            ProviderId.JINHAK -> "현재 진학사 화면 분석·누적"
            ProviderId.ADIGA -> "어디가 복구 보류"
        }
        diagnosticButton.text = if (which == ProviderId.JINHAK) "진학사 분석 전송" else "어디가 진단 로그 전송"
        webView.loadUrl(which.homeUrl)
    }

    private fun refreshSessionOrOpenLogin() {
        checkSessionState { needsLogin, hasAuthenticatedUi ->
            if (!needsLogin && hasAuthenticatedUi) {
                sessionState.text = "● 로그인 유지됨"
                if (batchRunning && batchPausedForLogin) {
                    resumeAfterLogin()
                } else {
                    Toast.makeText(this, "로그인 세션이 유지되고 있습니다.", Toast.LENGTH_SHORT).show()
                }
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

        if (provider == ProviderId.ADIGA && ADIGA_RETRY_SUSPENDED) {
            status.text = "어디가 복구는 현재 보류 중입니다. 진학사 분석 버전 검증 후 한밭대 381쪽을 우선 재시도합니다."
            Toast.makeText(this, "어디가 재시도는 진학사 분석 이후 진행합니다.", Toast.LENGTH_LONG).show()
            return
        }

        if (!currentAdapter().supportsBatchCrawl) {
            status.text = "진학사 현재 화면을 분석하고 로컬 이력에 누적합니다."
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
        showBatchCover()
        startCollectionKeepAlive()
        batchPausedForLogin = false
        batchCollecting = false
        batchPageCount = 0
        batchPaginationRetries = 0
        batchCloudPlansPending = 0
        batchCloudResumePlans = 0
        batchCloudPagesScheduled = 0
        batchCloudPagesSkipped = 0
        batchCloudPagesDeferred = 0
        batchContextRecoveries = 0
        batchSessionSyncRetries = 0
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        batchLocalResumePlans = 0
        batchLocalPagesScheduled = 0
        batchLocalPagesSkipped = 0
        batchLocalRecordsPersisted = 0
        batchAuditPagesScheduled = 0
        batchUniversityDiscoveryPagesScheduled = 0
        batchPersistedPageSignatureOwners.clear()
        disarmBatchNavigationWatchdog()
        currentBatchTarget = canonicalizeBatchUrl(url)
        batchButton.text = "일괄 수집 중지"
        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            localRunId = localStore.beginOrResume(provider.wireName, VERSION)
            status.text = "Local-First 수집 시작: Cloudflare 호출 없음 / run ${localRunId?.take(8)}…"
            beginBatchNavigation(null)
        } else {
            status.text = "현재 공급자는 로컬 단일 페이지 모드"
            beginBatchNavigation(null)
        }
    }

    private fun prepareCloudRecoveryAndStart(runId: String?) {
        if (runId.isNullOrBlank() || !cloudOffload.isConfigured()) {
            beginBatchNavigation(runId)
            return
        }
        status.text = "Cloud 전체 미완료 체크포인트 확인 중…"
        cloudOffload.pendingPages { result ->
            runOnUiThread {
                if (!batchRunning) return@runOnUiThread
                val response = result.getOrNull()
                if (response != null) {
                    val scheduled = enqueueGlobalPendingRecovery(response)
                    batchCloudPagesDeferred = response.optJSONArray("deferred")?.length() ?: 0
                    status.text = "Cloud 전역 복구: ${scheduled}쪽 우선 재시도 / ${batchCloudPagesDeferred}쪽 cooldown 보류"
                } else {
                    status.text = "Cloud 전역 복구 조회 실패: 기존 목록 resume-plan으로 계속"
                }
                beginBatchNavigation(runId)
            }
        }
    }

    private fun beginBatchNavigation(runId: String?) {
        enqueueProviderSeeds()
        if (runId != null && batchPageActions.isEmpty()) {
            status.text = "Cloud 체크포인트 연결: ${runId.take(8)}… / 기본 정보영역 ${batchQueue.size}개 탐색"
        } else if (runId == null) {
            status.text = "로컬 안전모드: 기본 정보영역 ${batchQueue.size}개 탐색"
        }
        checkSessionState { needsLogin, _ ->
            if (needsLogin) {
                pauseBatchForLogin()
            } else if (batchPageActions.isNotEmpty()) {
                loadNextBatchPage()
            } else {
                val startUrl = currentBatchTarget
                if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)
                else loadNextBatchPage()
            }
        }
    }

    private fun enqueueGlobalPendingRecovery(response: JSONObject): Int {
        val retry = response.optJSONArray("retry") ?: JSONArray()
        var scheduled = 0
        for (i in 0 until retry.length()) {
            val item = retry.optJSONObject(i) ?: continue
            val familyKey = item.optString("familyKey")
            val page = item.optInt("page", -1)
            if (familyKey.isBlank() || page < 1) continue
            val requestedYear = if (item.isNull("requestedYear")) null else item.optInt("requestedYear").takeIf { it > 0 }
            val totalPages = item.optInt("totalPages", page).coerceAtLeast(page)
            val baseUrl = recoveryUrlForPending(familyKey, requestedYear) ?: continue
            val action = BatchPageAction(
                baseUrl = baseUrl,
                page = page,
                familyKey = familyKey,
                requestedYear = requestedYear,
                totalPages = totalPages,
                pageSize = 0,
                totalItems = 0,
                retry = 0
            )
            val key = pageActionKey(action)
            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue
            if (batchPageActionQueued.add(key)) {
                batchPageActions.addFirst(action)
                scheduled += 1
            }
        }
        batchCloudPagesScheduled += scheduled
        return scheduled
    }

    private fun recoveryUrlForPending(familyKey: String, requestedYear: Int?): String? {
        if (provider != ProviderId.ADIGA) return null
        val raw = if (familyKey.startsWith("http://") || familyKey.startsWith("https://")) {
            familyKey
        } else {
            "https://www.adiga.kr" + if (familyKey.startsWith("/")) familyKey else "/$familyKey"
        }
        return if (requestedYear != null) withQueryParameter(raw, "searchSyr", requestedYear.toString()) else raw
    }

    private fun armBatchNavigationWatchdog(expectedUrl: String) {
        val generation = ++batchNavigationWatchdogGeneration
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || generation != batchNavigationWatchdogGeneration) return@postDelayed
            val current = webView.url ?: expectedUrl
            val sameDocument = canonicalizeBatchUrl(current) == canonicalizeBatchUrl(expectedUrl) || sameBatchDocument(current, expectedUrl)
            if (!sameDocument) return@postDelayed
            batchNavigationWatchdogRecovery = true
            batchNavigationWatchdogGeneration += 1
            status.text = "페이지 로딩 지연 감지: 현재 DOM으로 안전하게 계속합니다."
            if (::batchCover.isInitialized) {
                batchCover.text = "입시정보 수집 계속 중\n\n페이지 로딩이 오래 걸려 현재 상태를 평가한 뒤 다음 항목으로 진행합니다.\n${safeDisplayUrl(current)}"
            }
            runCatching { webView.stopLoading() }
            handler.postDelayed({
                if (!batchRunning || batchPausedForLogin || batchCollecting) return@postDelayed
                scheduleBatchSnapshot()
            }, 250L)
        }, BATCH_NAVIGATION_TIMEOUT_MS)
    }

    private fun disarmBatchNavigationWatchdog() {
        batchNavigationWatchdogGeneration += 1
    }

    private fun showBatchCover() {
        if (!::batchCover.isInitialized) return
        batchCover.text = "입시정보 수집 중\n\n로그인된 브라우저 자체가 수집 엔진으로 동작합니다.\n페이지 이동은 이 화면 뒤에서 처리됩니다."
        batchCover.visibility = View.VISIBLE
        batchCover.bringToFront()
    }

    private fun hideBatchCover() {
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
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
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        webView.stopLoading()
        hideBatchCover()
        stopCollectionKeepAlive()
        batchQueue.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        batchReadinessPolling = false
        pendingBatchPageAction = null
        activeBatchPageAction = null
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        status.text = "일괄 수집 중지: $reason"
        localRunId?.let { localStore.markRun(it, "stopped", reason) }
        if (batchSnapshots.length() > 0 || localRunId != null) finalizeBatchJson("stopped")
    }

    private fun pauseBatchForLogin(autoOpenLogin: Boolean = true) {
        batchPausedForLogin = true
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        hideBatchCover()
        if (autoOpenLogin) {
            sessionState.text = "○ 로그인 갱신 필요"
            status.text = "백그라운드 수집 일시정지: 메인 로그인 갱신 후 자동으로 계속합니다."
        } else {
            sessionState.text = "△ 수집 세션 재동기화 필요"
            status.text = "수집 세션 자동 동기화 실패: 로그인 세션 확인/갱신 후 계속을 눌러주세요."
        }
        batchButton.text = "일괄 수집 중지"
        if (autoOpenLogin) handler.postDelayed({ refreshSessionOrOpenLogin() }, 150)
    }

    private fun recoverCollectorSessionOrPause() {
        if (!batchRunning) return
        CookieManager.getInstance().flush()
        checkSessionState { needsLogin, authenticated ->
            if (!batchRunning) return@checkSessionState
            batchSessionSyncRetries = 0
            if (needsLogin) {
                pauseBatchForLogin(autoOpenLogin = true)
                return@checkSessionState
            }
            batchPausedForLogin = false
            showBatchCover()
            sessionState.text = if (authenticated) "● 로그인 유지 / 동일 수집 브라우저" else "△ 로그인 판정 미확정 / 동일 브라우저 재시도"
            val retry = currentBatchTarget
            handler.postDelayed({
                if (!batchRunning || batchPausedForLogin) return@postDelayed
                if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)
                else loadNextBatchPage()
            }, 250)
        }
    }

    private fun resumeAfterLogin() {
        if (!batchRunning || !batchPausedForLogin) {
            checkSessionState()
            return
        }
        checkSessionState { needsLogin, authenticated ->
            if (needsLogin || !authenticated) {
                Toast.makeText(this, "로그인 상태가 아직 확인되지 않습니다.", Toast.LENGTH_SHORT).show()
                return@checkSessionState
            }
            batchPausedForLogin = false
            showBatchCover()
            sessionState.text = "● 로그인 복구 / 동일 수집 브라우저"
            val retry = currentBatchTarget
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                status.text = "로그인 복구 완료: 중단 지점 재시도"
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
        if (current != baseUrl && !sameBatchDocument(current, baseUrl)) {
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
        status.text = if (provider == ProviderId.JINHAK) "진학사 화면의 과거입결·예측·성적지표를 분석 중…" else "현재 페이지의 표·헤더·카드·입시정보를 구조적으로 수집 중…"
        collectSnapshot { snapshot ->
            if (snapshot == null) return@collectSnapshot
            val records = normalizeSnapshot(snapshot)
            val collectedAt = Instant.now().toString()
            var localStats = JSONObject()
            var stored = 0
            if (provider == ProviderId.JINHAK) {
                val runId = localStore.beginOrResume(provider.wireName, VERSION)
                localRunId = runId
                stored = localStore.storeRecords(runId, provider.wireName, records)
                localStore.markDocument(runId, canonicalizeBatchUrl(snapshot.optString("url")), "completed")
                localStats = localStore.stats(runId)
                lastJinhakDigest = buildJinhakDigest(snapshot, records, runId, collectedAt)
            }
            val out = JSONObject()
                .put("collectorVersion", VERSION)
                .put("provider", provider.wireName)
                .put("collectedAt", collectedAt)
                .put("mode", if (provider == ProviderId.JINHAK) "jinhak-analysis" else "single-page")
                .put("session", snapshot.optJSONObject("session") ?: JSONObject())
                .put("localStoredThisCapture", stored)
                .put("localStats", localStats)
                .put("records", records)
                .put("snapshots", JSONArray().put(stripNavigationLinksForExport(snapshot)))
                .put("resourceLinks", snapshot.optJSONArray("resourceLinks") ?: JSONArray())
            lastJson = out.toString(2)
            showPreview(lastJson)
            status.text = if (provider == ProviderId.JINHAK) {
                "진학사 분석·누적 완료: 이번 ${records.length()}개 / 로컬 누적 ${localStats.optInt("records", records.length())}개 / 필요 시 '진학사 분석 전송'"
            } else {
                "현재 페이지 수집 완료: 구조화 레코드 ${records.length()}개"
            }
        }
    }

    private fun buildJinhakDigest(snapshot: JSONObject, records: JSONArray, runId: String, collectedAt: String): JSONObject {
        val sanitized = JSONArray()
        var universityBound = 0
        var departmentBound = 0
        var admissionBound = 0
        var fullyBound = 0
        for (i in 0 until records.length()) {
            val r = records.optJSONObject(i) ?: continue
            val hasUniversity = !r.isNull("university") && r.optString("university").isNotBlank()
            val hasDepartment = !r.isNull("department") && r.optString("department").isNotBlank()
            val hasAdmission = !r.isNull("admission") && r.optString("admission").isNotBlank()
            if (hasUniversity) universityBound += 1
            if (hasDepartment) departmentBound += 1
            if (hasAdmission) admissionBound += 1
            if (hasUniversity && hasDepartment && hasAdmission) fullyBound += 1
        }
        val limit = minOf(records.length(), 120)
        for (i in 0 until limit) {
            val r = records.optJSONObject(i) ?: continue
            sanitized.put(JSONObject()
                .put("recordType", r.optString("recordType"))
                .put("providerPageType", r.optString("providerPageType"))
                .put("dataScope", r.optString("dataScope"))
                .put("year", if (r.isNull("year")) JSONObject.NULL else r.optInt("year"))
                .put("university", if (r.isNull("university")) JSONObject.NULL else r.optString("university"))
                .put("department", if (r.isNull("department")) JSONObject.NULL else r.optString("department"))
                .put("admission", if (r.isNull("admission")) JSONObject.NULL else r.optString("admission"))
                .put("metrics", r.optJSONObject("metrics") ?: JSONObject())
                .put("confidence", r.optString("confidence"))
                .put("observedAt", r.optString("observedAt", collectedAt))
                .put("cardIndex", if (r.has("cardIndex")) r.optInt("cardIndex") else JSONObject.NULL)
                .put("contextSource", r.optString("contextSource"))
                .put("universityContextSource", if (r.isNull("universityContextSource")) JSONObject.NULL else r.optString("universityContextSource"))
                .put("universityContextDepth", r.optInt("universityContextDepth", -1))
                .put("departmentContextSource", if (r.isNull("departmentContextSource")) JSONObject.NULL else r.optString("departmentContextSource"))
                .put("departmentContextDepth", r.optInt("departmentContextDepth", -1)))
        }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("type", "jinhak-analysis-digest")
            .put("pageType", snapshot.optString("providerPageType"))
            .put("collectedAt", collectedAt)
            .put("recordCount", records.length())
            .put("detectedStorageCards", snapshot.optJSONArray("jinhakCards")?.length() ?: 0)
            .put("cardCaptureStats", snapshot.optJSONObject("jinhakCardStats") ?: JSONObject())
            .put("bindingStats", JSONObject()
                .put("universityBound", universityBound)
                .put("departmentBound", departmentBound)
                .put("admissionBound", admissionBound)
                .put("fullyBound", fullyBound)
                .put("totalRecords", records.length()))
            .put("includedRecords", sanitized.length())
            .put("truncated", records.length() > sanitized.length())
            .put("localStats", localStore.stats(runId))
            .put("records", sanitized)
            .put("privacy", "structured-admission-metrics-only-no-dom-no-raw-evidence-no-url-no-cookie-no-credential")
    }

    private fun sendLatestJinhakAnalysisDigest() {
        if (lastJinhakDigest.length() == 0) {
            Toast.makeText(this, "먼저 진학사에서 분석할 화면을 열고 '현재 진학사 화면 분석·누적'을 눌러주세요.", Toast.LENGTH_LONG).show()
            return
        }
        status.text = "진학사 구조화 분석 결과 전송 중… DOM·쿠키·로그인 정보는 보내지 않습니다."
        cloudOffload.sendDiagnostic("jinhak", VERSION, JSONObject(lastJinhakDigest.toString()).put("trigger", "manual-analysis")) { result ->
            runOnUiThread {
                if (result.isSuccess) {
                    status.text = "진학사 분석 전송 완료: ${result.getOrNull()?.take(8) ?: "unknown"}…"
                    Toast.makeText(this, "진학사 분석 전송 완료", Toast.LENGTH_SHORT).show()
                } else {
                    status.text = "진학사 분석 전송 실패: ${result.exceptionOrNull()?.message ?: "unknown"}"
                    Toast.makeText(this, "진학사 분석 전송 실패", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun collectSnapshotForBatch() {
        if (!batchRunning || batchPausedForLogin || batchCollecting) return
        batchCollecting = true
        collectSnapshot(webView) { snapshot ->
            batchCollecting = false
            if (!batchRunning || snapshot == null) return@collectSnapshot
            stabilizeBatchSnapshotContext(snapshot)

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
                localRunId?.let { runId ->
                    val key = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                    localStore.markDocument(runId, key, "error", activeAction?.retry ?: 0, errorType)
                    if (activeAction != null) {
                        localStore.markPage(
                            runId, activeAction.familyKey, activeAction.requestedYear,
                            activeAction.page, activeAction.totalPages, "error", activeAction.retry, errorType
                        )
                    }
                }
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
                recoverCollectorSessionOrPause()
                return@collectSnapshot
            }
            batchSessionSyncRetries = 0

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

            val pageRecords = normalizeSnapshot(snapshot)
            if (activeAction != null && LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
                val duplicateOwner = persistedDuplicatePageOwner(activeAction, pageRecords)
                if (duplicateOwner != null && duplicateOwner != activeAction.page) {
                    activeBatchPageAction = null
                    status.text = "페이지 ${activeAction.page} 내용이 기존 ${duplicateOwner}쪽과 동일함: stale 판정 / 최대 ${MAX_PAGE_RETRIES}회만 재시도"
                    schedulePageActionRetry(activeAction, "stale-pagination-content")
                    return@collectSnapshot
                }
            }

            batchSnapshots.put(snapshotForLocalExport(snapshot))
            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }
            // University detail records can be large. SQLite is the authoritative local store;
            // avoid keeping a second in-memory copy during the long detail crawl.
            if (!(LOCAL_FIRST_BETA && snapshot.optString("providerPageType") == "adiga-university-detail")) {
                RecordUtils.appendUniqueRecords(batchRecords, pageRecords)
            }
            localRunId?.let { runId ->
                batchLocalRecordsPersisted += localStore.storeRecords(runId, provider.wireName, pageRecords)
                val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                localStore.markDocument(runId, navKey, "completed")
                when {
                    activeAction != null -> localStore.markPage(
                        runId, activeAction.familyKey, activeAction.requestedYear,
                        activeAction.page, activeAction.totalPages, "completed", activeAction.retry
                    )
                    plan != null -> localStore.markPage(
                        runId, plan.familyKey, plan.requestedYear,
                        1, plan.totalPages, "completed", 0
                    )
                }
            }
            if (activeAction != null) rememberAcceptedPageSignature(activeAction, pageRecords)
            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())

            // v0.4.0 only followed links from page 1 because pagination actions skipped
            // discovery. University-list pagination is safe and bounded (220 universities),
            // so collect detail URLs from every university-list page as well.
            val pageType = snapshot.optString("providerPageType")
            if (activeAction == null || pageType == "adiga-university-list") {
                enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())
            }
            if (activeAction == null) {
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

    private fun snapshotForLocalExport(snapshot: JSONObject): JSONObject {
        if (!(LOCAL_FIRST_BETA && provider == ProviderId.ADIGA &&
                snapshot.optString("providerPageType") == "adiga-university-detail")) {
            return stripNavigationLinksForExport(snapshot)
        }
        // Detailed tables are already normalized into durable SQLite records. Keep only
        // lightweight diagnostics here to prevent hundreds of university details from
        // being duplicated in RAM and again in the exported JSON.
        return JSONObject()
            .put("title", snapshot.optString("title"))
            .put("url", snapshot.optString("url"))
            .put("collectedAt", snapshot.optString("collectedAt"))
            .put("providerPageType", snapshot.optString("providerPageType"))
            .put("collectionPage", snapshot.optInt("collectionPage", 1))
            .put("pageState", snapshot.optJSONObject("pageState") ?: JSONObject())
            .put("listMeta", snapshot.optJSONObject("listMeta") ?: JSONObject())
            .put("discovery", snapshot.optJSONObject("discovery") ?: JSONObject())
    }

    private fun pageAuditCacheKey(familyKey: String, requestedYear: Int?): String =
        "$familyKey|year=${requestedYear ?: "unknown"}"

    private fun stableRecordMaterial(obj: JSONObject): String = listOf(
        obj.optString("recordType"),
        obj.optString("university"),
        obj.optString("department"),
        obj.optString("admission"),
        obj.optString("rawEvidence")
    ).joinToString("|")

    private fun normalizedPageSignature(records: JSONArray): String? {
        if (records.length() == 0) return null
        val parts = mutableListOf<String>()
        for (i in 0 until records.length()) {
            records.optJSONObject(i)?.let { parts += stableRecordMaterial(it) }
        }
        if (parts.isEmpty()) return null
        return RecordUtils.sha256(parts.sorted().joinToString("\n"))
    }

    private fun persistedPageSignatureOwners(action: BatchPageAction): MutableMap<String, Int> {
        val runId = localRunId ?: return linkedMapOf()
        val cacheKey = pageAuditCacheKey(action.familyKey, action.requestedYear)
        batchPersistedPageSignatureOwners[cacheKey]?.let { return it }

        val familyPath = action.familyKey.substringBefore('?')
        val grouped = linkedMapOf<Int, MutableList<String>>()
        val stored = localStore.loadRecords(runId)
        for (i in 0 until stored.length()) {
            val obj = stored.optJSONObject(i) ?: continue
            val source = obj.optString("sourcePage")
            if (!source.contains(familyPath)) continue
            if (action.requestedYear != null) {
                if (obj.isNull("year") || obj.optInt("year", -1) != action.requestedYear) continue
            }
            val page = obj.optInt("sourcePageNumber", -1)
            if (page < 1) continue
            grouped.getOrPut(page) { mutableListOf() }.add(stableRecordMaterial(obj))
        }
        val owners = linkedMapOf<String, Int>()
        for ((page, parts) in grouped) {
            if (parts.isNotEmpty()) owners[RecordUtils.sha256(parts.sorted().joinToString("\n"))] = page
        }
        batchPersistedPageSignatureOwners[cacheKey] = owners
        return owners
    }

    private fun persistedPagesWithRecords(runId: String, familyKey: String, requestedYear: Int?): Set<Int> {
        val familyPath = familyKey.substringBefore('?')
        val pages = linkedSetOf<Int>()
        val stored = localStore.loadRecords(runId)
        for (i in 0 until stored.length()) {
            val obj = stored.optJSONObject(i) ?: continue
            if (!obj.optString("sourcePage").contains(familyPath)) continue
            if (requestedYear != null) {
                if (obj.isNull("year") || obj.optInt("year", -1) != requestedYear) continue
            }
            val page = obj.optInt("sourcePageNumber", -1)
            if (page >= 1) pages.add(page)
        }
        return pages
    }

    private fun persistedDuplicatePageOwner(action: BatchPageAction, records: JSONArray): Int? {
        val signature = normalizedPageSignature(records) ?: return null
        return persistedPageSignatureOwners(action)[signature]
    }

    private fun rememberAcceptedPageSignature(action: BatchPageAction, records: JSONArray) {
        val signature = normalizedPageSignature(records) ?: return
        persistedPageSignatureOwners(action)[signature] = action.page
    }

    private fun loadNextBatchPage() {
        if (!batchRunning || batchPausedForLogin) return
        if (batchCloudPlansPending > 0) {
            status.text = "Cloud resume 계획 확인 중: ${batchCloudPlansPending}개 목록"
            handler.postDelayed({ loadNextBatchPage() }, 180)
            return
        }

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
        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) verifyLocalCompletionOrFinish()
        else verifyCloudCompletionOrFinish()
    }

    private fun verifyLocalCompletionOrFinish() {
        if (!batchRunning || batchPausedForLogin) return
        val runId = localRunId
        if (runId == null) {
            finishBatch("completed")
            return
        }
        val unresolved = localStore.unresolvedCount(runId)
        if (unresolved > 0) finishBatch("completed-with-local-errors")
        else finishBatch("completed")
    }

    private fun verifyCloudCompletionOrFinish(drainAttempt: Int = 0) {
        if (!batchRunning || batchPausedForLogin) return
        if (!cloudOffload.isConfigured()) {
            finishBatch("completed")
            return
        }
        if (batchCloudFinalCheckInProgress) return
        batchCloudFinalCheckInProgress = true
        status.text = "Cloud Queue 및 전체 체크포인트 최종 검증 중…"
        cloudOffload.status { statusResult ->
            runOnUiThread {
                if (!batchRunning) {
                    batchCloudFinalCheckInProgress = false
                    return@runOnUiThread
                }
                val run = statusResult.getOrNull()?.optJSONObject("run")
                val uploaded = run?.optInt("uploaded_chunks", 0) ?: 0
                val processed = run?.optInt("processed_chunks", 0) ?: 0
                if (run != null && processed < uploaded && drainAttempt < 20) {
                    batchCloudFinalCheckInProgress = false
                    status.text = "Cloud Queue 반영 대기: $processed/$uploaded"
                    handler.postDelayed({ verifyCloudCompletionOrFinish(drainAttempt + 1) }, 500L)
                    return@runOnUiThread
                }
                cloudOffload.pendingPages { pendingResult ->
                    runOnUiThread {
                        batchCloudFinalCheckInProgress = false
                        if (!batchRunning) return@runOnUiThread
                        val response = pendingResult.getOrNull()
                        if (response == null) {
                            finishBatch("cloud-verification-failed")
                            return@runOnUiThread
                        }
                        val deferred = response.optJSONArray("deferred") ?: JSONArray()
                        batchCloudPagesDeferred = deferred.length()
                        val scheduled = enqueueGlobalPendingRecovery(response)
                        if (scheduled > 0) {
                            status.text = "Cloud 미완료 ${scheduled}쪽을 완료 판정 전에 우선 복구합니다."
                            handler.postDelayed({ loadNextBatchPage() }, 120L)
                            return@runOnUiThread
                        }
                        if (batchCloudPagesDeferred > 0) {
                            finishBatch("completed-with-deferred-errors")
                        } else {
                            finishBatch("completed")
                        }
                    }
                }
            }
        }
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
        status.text = pageActionStatus(action, if (action.retry > 0) "재시도 ${action.retry}/$MAX_PAGE_RETRIES" else "백그라운드 이동 중")
        val yearPrelude = action.requestedYear?.let { expectedYear ->
            """(function(){var n=document.querySelectorAll('[name=searchSyr],#searchSyr');for(var i=0;i<n.length;i++){try{n[i].value='$expectedYear';}catch(e){}}})();"""
        } ?: ""
        webView.evaluateJavascript(yearPrelude + js) { result ->
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
                }, 2200)
            }
        }
    }

    private fun schedulePageActionRetry(action: BatchPageAction, reason: String) {
        // Central retry circuit-breaker. Every caller, including stale-content recovery,
        // must pass through this guard so one bad page can never pin the whole batch.
        if (action.retry >= MAX_PAGE_RETRIES) {
            recordPaginationFailure(action, reason)
            activeBatchPageAction = null
            pendingBatchPageAction = null
            status.text = pageActionStatus(action, "재시도 상한 도달: 오류로 보존 후 다음 페이지 진행")
            handler.postDelayed({ loadNextBatchPage() }, 250L)
            return
        }

        val retry = action.copy(retry = action.retry + 1)
        batchPaginationRetries += 1
        batchRetryEvents.put(JSONObject()
            .put("familyKey", action.familyKey)
            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
            .put("page", action.page)
            .put("attempt", retry.retry)
            .put("maxAttempts", MAX_PAGE_RETRIES)
            .put("reason", reason))
        pendingBatchPageAction = retry
        activeBatchPageAction = null
        currentBatchTarget = retry.baseUrl
        status.text = pageActionStatus(retry, "재시도 대기 ($reason)")
        val delay = 1200L + (retry.retry * 1000L)
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
        localRunId?.let { runId ->
            localStore.markPage(
                runId, action.familyKey, action.requestedYear,
                action.page, action.totalPages, "error", action.retry, type
            )
            localStore.markDocument(runId, canonicalizeBatchUrl(action.baseUrl), "error", action.retry, type)
        }
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
        "${action.familyKey}|year=${action.requestedYear ?: "unknown"}|page=${action.page}"

    private fun sameBatchDocument(a: String, b: String): Boolean {
        return try {
            val ua = Uri.parse(a)
            val ub = Uri.parse(b)
            ua.host.equals(ub.host, ignoreCase = true) && ua.path == ub.path
        } catch (_: Exception) { false }
    }

    private fun queryYearFromUrl(url: String?): Int? {
        if (url.isNullOrBlank()) return null
        return try { Uri.parse(url).getQueryParameter("searchSyr")?.toIntOrNull() } catch (_: Exception) { null }
    }

    private fun withQueryParameter(url: String, key: String, value: String): String {
        return try {
            val uri = Uri.parse(url)
            val builder = uri.buildUpon().clearQuery()
            for (name in uri.queryParameterNames) {
                if (name == key) continue
                for (v in uri.getQueryParameters(name)) builder.appendQueryParameter(name, v)
            }
            builder.appendQueryParameter(key, value).build().toString()
        } catch (_: Exception) { url }
    }

    private fun stabilizeBatchSnapshotContext(snapshot: JSONObject) {
        if (provider != ProviderId.ADIGA) return
        val rawUrl = snapshot.optString("url")
        if (!currentAdapter().isDynamicListPage(rawUrl)) return
        if (queryYearFromUrl(rawUrl) != null) return

        val expectedYear = activeBatchPageAction?.requestedYear
            ?: pendingBatchPageAction?.requestedYear
            ?: queryYearFromUrl(currentBatchTarget)
        if (expectedYear == null) {
            snapshot.put("collectionContextError", "missing-searchSyr")
            return
        }

        val restoredUrl = withQueryParameter(rawUrl, "searchSyr", expectedYear.toString())
        snapshot.put("url", restoredUrl)
        snapshot.put("navigationKey", restoredUrl)
        snapshot.put("collectionContextRecovered", true)
        snapshot.put("collectionExpectedYear", expectedYear)
        currentBatchTarget = restoredUrl
        batchContextRecoveries += 1
    }

    private fun startCollectionKeepAlive() {
        runCatching { startForegroundService(Intent(this, CollectionKeepAliveService::class.java)) }
    }

    private fun stopCollectionKeepAlive() {
        runCatching { stopService(Intent(this, CollectionKeepAliveService::class.java)) }
    }

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

    private fun sendLatestLocalDiagnostic(manual: Boolean) {
        val runId = localRunId ?: localStore.latestRun(provider.wireName)
        if (runId.isNullOrBlank()) {
            if (manual) Toast.makeText(this, "전송할 로컬 수집 로그가 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        val diagnostic = localStore.diagnosticSnapshot(runId)
            .put("trigger", if (manual) "manual" else "batch-finish")
            .put("segment", JSONObject()
                .put("attemptedPages", batchPageCount)
                .put("successfulSnapshots", batchSnapshots.length())
                .put("errorEvents", batchErrors.length())
                .put("paginationActionsCompleted", batchPageActionVisited.size)
                .put("paginationActionsFailed", batchPageActionFailed.size)
                .put("paginationRetries", batchPaginationRetries)
                .put("localPagesScheduled", batchLocalPagesScheduled)
                .put("localPagesSkipped", batchLocalPagesSkipped)
                .put("localRecordsPersisted", batchLocalRecordsPersisted))
        if (manual) status.text = "진단 로그 전송 중… 원본 입시자료는 전송하지 않습니다."
        cloudOffload.sendDiagnostic(provider.wireName, VERSION, diagnostic) { result ->
            runOnUiThread {
                if (result.isSuccess) {
                    val id = result.getOrNull()?.take(8) ?: "unknown"
                    status.text = "진단 로그 전송 완료: $id… / 원본 레코드·로그인 정보 미전송"
                    if (manual) Toast.makeText(this, "진단 로그 전송 완료", Toast.LENGTH_SHORT).show()
                } else if (manual) {
                    status.text = "진단 로그 전송 실패: ${result.exceptionOrNull()?.message ?: "unknown"}"
                    Toast.makeText(this, "진단 로그 전송 실패", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun finishBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        webView.stopLoading()
        hideBatchCover()
        stopCollectionKeepAlive()
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        val effectiveReason = if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            reason
        } else if (reason == "completed" && batchCloudPagesDeferred > 0) {
            "completed-with-deferred-errors"
        } else reason
        localRunId?.let { runId ->
            val runState = if (effectiveReason == "completed" && localStore.unresolvedCount(runId) == 0) "completed" else "incomplete"
            localStore.markRun(runId, runState, effectiveReason)
        }
        finalizeBatchJson(effectiveReason)
        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            // Telemetry is sent only after the crawl has stopped, never per page.
            sendLatestLocalDiagnostic(manual = false)
        }
        if (!LOCAL_FIRST_BETA && effectiveReason == "completed" && batchCloudPagesDeferred == 0) {
            cloudOffload.finish(
                reason = effectiveReason,
                summary = JSONObject()
                    .put("attemptedPages", batchPageCount)
                    .put("successfulPages", batchSnapshots.length())
                    .put("errorPages", batchErrors.length())
                    .put("records", batchRecords.length())
                    .put("paginationRetries", batchPaginationRetries)
                    .put("cloudResumePlans", batchCloudResumePlans)
                    .put("cloudPagesScheduled", batchCloudPagesScheduled)
                    .put("cloudPagesSkipped", batchCloudPagesSkipped)
                    .put("cloudPagesDeferred", batchCloudPagesDeferred)
            )
        }
        status.text = when {
            LOCAL_FIRST_BETA && effectiveReason == "completed-with-local-errors" ->
                "Local-First 1차 순회 종료: 미해결 오류는 로컬에 저장됨 / 다음 실행에서 해당 지점만 재개합니다."
            LOCAL_FIRST_BETA && effectiveReason == "completed" ->
                "어디가 로컬 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 재시도 $batchPaginationRetries / 로컬 레코드 ${localRunId?.let { localStore.stats(it).optInt("records") } ?: batchRecords.length()}"
            effectiveReason == "cloud-verification-failed" ->
                "로컬 수집 종료: Cloud 최종 완결성 확인 실패 / 서버 run은 닫지 않고 유지합니다."
            batchCloudPagesDeferred > 0 ->
                "수집 종료: 서버 오류 ${batchCloudPagesDeferred}쪽은 Cloud에 보류 / 전체 완료로 확정하지 않습니다."
            else ->
                "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"
        }
    }

    private fun finalizeBatchJson(reason: String) {
        val persistedRecords = localRunId?.let { localStore.loadRecords(it) } ?: batchRecords
        val localStats = localRunId?.let { localStore.stats(it) } ?: JSONObject()
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
                .put("records", persistedRecords.length())
                .put("resourceLinks", batchResources.length())
                .put("paginationActionsCompleted", batchPageActionVisited.size)
                .put("paginationActionsFailed", batchPageActionFailed.size)
                .put("paginationRetries", batchPaginationRetries)
                .put("paginationPlans", batchPaginationPlanned.size)
                .put("cloudResumePlans", batchCloudResumePlans)
                .put("cloudPagesScheduled", batchCloudPagesScheduled)
                .put("cloudPagesSkipped", batchCloudPagesSkipped)
                .put("cloudPagesDeferred", batchCloudPagesDeferred)
                .put("contextRecoveries", batchContextRecoveries)
                .put("collectionTransport", "authenticated-webview-covered")
                .put("duplicateYearViewsSkipped", batchDuplicateYearViews.length())
                .put("dynamicSearchBootstraps", batchBootstrapSearchAttempted.size)
                .put("localResumePlans", batchLocalResumePlans)
                .put("localPagesScheduled", batchLocalPagesScheduled)
                .put("localPagesSkipped", batchLocalPagesSkipped)
                .put("localRecordsPersistedThisSegment", batchLocalRecordsPersisted)
                .put("localAuditPagesScheduled", batchAuditPagesScheduled)
                .put("universityDiscoveryPagesScheduled", batchUniversityDiscoveryPagesScheduled))
            .put("localFirst", JSONObject()
                .put("enabled", LOCAL_FIRST_BETA)
                .put("cloudRequestsDuringBatch", 0)
                .put("snapshotScope", "current-process-segment")
                .put("stats", localStats))
            .put("errors", batchErrors)
            .put("retryEvents", batchRetryEvents)
            .put("duplicateYearViews", batchDuplicateYearViews)
            .put("cloudOffload", JSONObject().put("mode", "disabled-during-v0.4.0-local-first"))
            .put("records", persistedRecords)
            .put("snapshots", batchSnapshots)
            .put("resourceLinks", batchResources)
        lastJson = out.toString(2)
        showPreview(lastJson)
    }

    private fun collectSnapshot(callback: (JSONObject?) -> Unit) = collectSnapshot(webView, callback)

    private fun collectSnapshot(target: WebView, callback: (JSONObject?) -> Unit) {
        val js = SnapshotScript.build()
        target.evaluateJavascript(js) { encoded ->
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
            val runId = localRunId
            if (runId != null && !currentAdapter().isDynamicListPage(url) && localStore.isDocumentCompleted(runId, url)) continue
            batchQueued.add(url)
            batchQueue.addLast(url)
        }
    }

    private fun enqueueDiscoveredLinks(links: JSONArray) {
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = canonicalizeBatchUrl(obj.optString("url"))
            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            enqueueDiscoveredUrl(url)
            // One 2027 university-list pass is enough to discover university codes.
            // Mirror each 2027 university detail to 2026 so the same university's
            // 2025 actual-result section is collected without crawling the huge
            // duplicate 2026 department list.
            historicalMirrorUrl(url)?.let { mirror -> enqueueDiscoveredUrl(mirror) }
            if (batchQueue.size + batchVisited.size >= MAX_BATCH_PAGES * 2) break
        }
    }

    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (batchVisited.contains(url)) return
        val runId = localRunId
        if (runId != null && localStore.isDocumentCompleted(runId, url)) return
        if (batchQueued.add(url)) batchQueue.addLast(url)
    }

    private fun historicalMirrorUrl(url: String): String? {
        if (provider != ProviderId.ADIGA) return null
        return try {
            val uri = Uri.parse(url)
            if (uri.path != "/ucp/uvt/uni/univDetailSelection.do") return null
            if (uri.getQueryParameter("searchSyr") != "2027") return null
            val code = uri.getQueryParameter("unvCd")?.trim().orEmpty()
            if (!Regex("^0[0-9]{6}$").matches(code)) return null
            canonicalizeBatchUrl(withQueryParameter(url, "searchSyr", "2026"))
        } catch (_: Exception) { null }
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
        val planKey = "${plan.familyKey}|year=${plan.requestedYear ?: "unknown"}|${plan.totalItems}|${plan.pageSize}|${plan.totalPages}"
        if (!batchPaginationPlanned.add(planKey)) return

        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            val runId = localRunId
            if (runId == null) {
                enqueuePageActions(baseUrl, plan, (2..plan.totalPages).toList())
                return
            }
            val localPlan = localStore.resumePlan(runId, plan.familyKey, plan.requestedYear, plan.totalPages)
            val pages = linkedSetOf<Int>()
            pages.addAll(localPlan.retry)
            pages.addAll(localPlan.missing)

            // Checkpoint state alone is insufficient: v0.4.0 proved that a stale AJAX
            // response could be marked completed while another page's rows were stored.
            // Re-open any checkpoint that has no persisted row evidence, plus neighbors
            // so stale-content detection has a reference page on either side.
            val evidencePages = persistedPagesWithRecords(runId, plan.familyKey, plan.requestedYear)
            val evidenceMissing = (2..plan.totalPages).filter { it !in evidencePages }
            for (page in evidenceMissing) {
                for (candidate in (page - 1)..(page + 1)) {
                    if (candidate in 2..plan.totalPages) pages.add(candidate)
                }
            }
            batchAuditPagesScheduled += evidenceMissing.size

            // v0.4.0 already has all 220 university summary rows, but only page 1 links
            // were followed. Revisit the 21 remaining 2027 university-list pages solely
            // to discover detail URLs; completed detail documents are still skipped.
            if (plan.familyKey.contains("/ucp/uvt/uni/univView.do") && plan.requestedYear == 2027) {
                val discoveryPages = (2..plan.totalPages).toList()
                pages.addAll(discoveryPages)
                batchUniversityDiscoveryPagesScheduled += discoveryPages.size
            }

            val sortedPages = pages.distinct().sorted()
            batchLocalResumePlans += 1
            batchLocalPagesScheduled += sortedPages.size
            batchLocalPagesSkipped += (plan.totalPages - 1 - sortedPages.size).coerceAtLeast(0)
            status.text = "Local audit/resume: ${sortedPages.size}쪽 수집 / 증거누락 ${evidenceMissing.size}쪽 / 대학상세 발견 ${batchUniversityDiscoveryPagesScheduled}쪽"
            enqueuePageActions(baseUrl, plan, sortedPages)
            return
        }
        if (!cloudOffload.isConfigured()) {
            enqueuePageActions(baseUrl, plan, (2..plan.totalPages).toList())
            return
        }

        batchCloudPlansPending += 1
        cloudOffload.resumePlan(plan.familyKey, plan.requestedYear, plan.totalPages) { result ->
            runOnUiThread {
                batchCloudPlansPending = (batchCloudPlansPending - 1).coerceAtLeast(0)
                if (!batchRunning) return@runOnUiThread

                val response = result.getOrNull()
                val pages = linkedSetOf<Int>()
                if (response != null && !(response.optBoolean("truncated", false) && plan.totalPages > 500)) {
                    val missing = response.optJSONArray("missing") ?: JSONArray()
                    for (i in 0 until missing.length()) {
                        val page = missing.optInt(i, -1)
                        if (page in 2..plan.totalPages) pages.add(page)
                    }
                    val retry = response.optJSONArray("retry") ?: JSONArray()
                    for (i in 0 until retry.length()) {
                        val page = retry.optJSONObject(i)?.optInt("page", -1) ?: -1
                        if (page in 2..plan.totalPages) pages.add(page)
                    }
                    val deferred = response.optJSONArray("deferred") ?: JSONArray()
                    batchCloudResumePlans += 1
                    batchCloudPagesScheduled += pages.size
                    batchCloudPagesDeferred += deferred.length()
                    val skipped = (plan.totalPages - 1 - pages.size).coerceAtLeast(0)
                    batchCloudPagesSkipped += skipped
                    status.text = if (deferred.length() > 0) {
                        "Cloud resume: ${pages.size}쪽 재수집 / ${skipped}쪽 건너뜀 / 서버오류 ${deferred.length()}쪽 보류"
                    } else {
                        "Cloud resume: ${pages.size}쪽 재수집 / ${skipped}쪽 완료로 건너뜀"
                    }
                    enqueuePageActions(baseUrl, plan, pages.sorted())
                } else {
                    val fallback = (2..plan.totalPages).toList()
                    enqueuePageActions(baseUrl, plan, fallback)
                    status.text = "Cloud resume 확인 실패: 전체 페이지 안전 수집으로 전환"
                }

                handler.postDelayed({ loadNextBatchPage() }, 120)
            }
        }
    }

    private fun enqueuePageActions(baseUrl: String, plan: PaginationPlan, pages: Collection<Int>) {
        for (page in pages) {
            if (page !in 2..plan.totalPages) continue
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
        stopCollectionKeepAlive()
        cloudOffload.shutdown()
        localStore.close()
        if (::webView.isInitialized) {
            webView.stopLoading()
            webView.destroy()
        }
        super.onDestroy()
    }
}
