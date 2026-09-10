package com.admissionhub.collector.competition

import android.app.Activity
import android.app.AlertDialog
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import com.admissionhub.collector.cloud.CloudOffloadCoordinator
import org.json.JSONObject
import org.json.JSONTokener

/**
 * Reads only the public competition table rendered in the user's Android WebView.
 *
 * This class intentionally does not export cookies, credentials, CSRF values, Cloudflare
 * challenge material, or browser storage. If JINHAKAPPLY presents a managed security check,
 * the collector waits for the normal browser flow and skips the target if it does not resolve.
 */
class CompetitionBrowserCollector(
    private val activity: Activity,
    private val host: FrameLayout,
    private val cloud: CloudOffloadCoordinator,
    private val isBusy: () -> Boolean,
    private val onStatus: (String) -> Unit = {},
) {
    private val handler = Handler(Looper.getMainLooper())
    private var webView: WebView? = null
    private var started = false
    private var running = false
    private var destroyed = false
    private var firstCyclePending = true
    private var activeTargetIndex = -1
    private var challengeChecks = 0
    private var challengeDialog: AlertDialog? = null
    private var challengeVisibleSinceMs = 0L
    private var pageGeneration = 0
    private var lastScheduledBucket = Long.MIN_VALUE

    private val ticker = object : Runnable {
        override fun run() {
            if (destroyed || !started) return
            maybeStartCycle()
            handler.postDelayed(this, CompetitionBrowserPolicy.CHECK_INTERVAL_MS)
        }
    }

    fun start() {
        if (started || destroyed) return
        started = true
        ensureWebView()
        handler.postDelayed(ticker, 3_000L)
    }

    fun destroy() {
        if (destroyed) return
        destroyed = true
        started = false
        running = false
        pageGeneration += 1
        handler.removeCallbacksAndMessages(null)
        challengeDialog?.setOnCancelListener(null)
        challengeDialog?.dismiss()
        challengeDialog = null
        challengeVisibleSinceMs = 0L
        webView?.let { view ->
            runCatching { view.stopLoading() }
            runCatching { host.removeView(view) }
            runCatching { view.destroy() }
        }
        webView = null
    }

    private fun maybeStartCycle() {
        if (destroyed || running || isBusy() || !cloud.isConfigured()) return
        val now = System.currentTimeMillis()
        val due = CompetitionBrowserPolicy.isDue(now)
        if (!firstCyclePending && !due) return

        val bucket = Math.floorDiv(now, 10L * 60_000L)
        if (!firstCyclePending && bucket == lastScheduledBucket) return
        firstCyclePending = false
        lastScheduledBucket = bucket
        running = true
        activeTargetIndex = 0
        onStatus("경쟁률 수집 · 진학어플라이 공개 페이지 확인 시작")
        loadActiveTarget()
    }

    private fun loadActiveTarget() {
        if (destroyed || !running) return
        if (isBusy()) {
            finishCycle("경쟁률 수집 · 본 수집 작업과 충돌 방지를 위해 다음 주기로 연기")
            return
        }
        if (activeTargetIndex !in CompetitionBrowserPolicy.targets.indices) {
            finishCycle("경쟁률 수집 · 진학어플라이 4개 대학 확인 완료")
            return
        }

        val target = CompetitionBrowserPolicy.targets[activeTargetIndex]
        challengeChecks = 0
        challengeVisibleSinceMs = 0L
        val generation = ++pageGeneration
        onStatus("경쟁률 수집 · ${target.university} 공개 페이지 확인 중")
        ensureWebView().loadUrl(target.sourceUrl)
        handler.postDelayed({
            if (!destroyed && running && generation == pageGeneration && challengeDialog == null) {
                onStatus("경쟁률 수집 · ${target.university} 페이지 시간 초과")
                moveNextTarget()
            }
        }, CompetitionBrowserPolicy.PAGE_TIMEOUT_MS)
    }

    private fun handlePageFinished(url: String) {
        if (destroyed || !running || activeTargetIndex !in CompetitionBrowserPolicy.targets.indices) return
        val target = CompetitionBrowserPolicy.targets[activeTargetIndex]
        if (!sameHost(url, target.sourceUrl)) {
            onStatus("경쟁률 수집 · ${target.university} 허용되지 않은 외부 이동 감지")
            moveNextTarget()
            return
        }
        val generation = pageGeneration
        handler.postDelayed({ probeRenderedPage(target, generation) }, CompetitionBrowserPolicy.RENDER_SETTLE_MS)
    }

    private fun probeRenderedPage(target: CompetitionBrowserTarget, generation: Int) {
        if (destroyed || !running || generation != pageGeneration) return
        val view = webView ?: return
        view.evaluateJavascript(EXTRACT_PUBLIC_COMPETITION_JS) { encoded ->
            if (destroyed || !running || generation != pageGeneration) return@evaluateJavascript
            val payload = decodeJavascriptObject(encoded)
            if (payload == null) {
                onStatus("경쟁률 수집 · ${target.university} DOM 판독 실패")
                moveNextTarget()
                return@evaluateJavascript
            }

            if (payload.optBoolean("challenge", false)) {
                challengeChecks += 1
                if (challengeVisibleSinceMs == 0L) challengeVisibleSinceMs = System.currentTimeMillis()
                if (challengeDialog == null) showChallengeDialog(target, generation)
                val elapsed = System.currentTimeMillis() - challengeVisibleSinceMs
                if (elapsed < CompetitionBrowserPolicy.USER_CHALLENGE_TIMEOUT_MS) {
                    onStatus("경쟁률 수집 · ${target.university} 사용자 안전 접속 확인 필요")
                    handler.postDelayed(
                        { probeRenderedPage(target, generation) },
                        CompetitionBrowserPolicy.CHALLENGE_VISIBLE_RECHECK_MS,
                    )
                } else {
                    onStatus("경쟁률 수집 · ${target.university} 안전 접속 확인 시간 초과 · 이번 주기 건너뜀")
                    restoreHiddenWebView()
                    moveNextTarget()
                }
                return@evaluateJavascript
            }

            if (challengeDialog != null) {
                restoreHiddenWebView()
                onStatus("경쟁률 수집 · ${target.university} 안전 접속 확인 완료 · 공개 표 분석 중")
            }

            val rows = payload.optJSONArray("rows")
            if (rows == null || rows.length() == 0) {
                onStatus("경쟁률 수집 · ${target.university} 경쟁률 표 미검출")
                moveNextTarget()
                return@evaluateJavascript
            }

            // Only public table observations are forwarded. Query strings and fragments are
            // stripped in JavaScript so managed-challenge/session material cannot be exported.
            val observation = JSONObject()
                .put("targetId", target.id)
                .put("university", target.university)
                .put("sourceUrl", payload.optString("sourceUrl", target.sourceUrl))
                .put("sourceUpdatedAt", payload.opt("sourceUpdatedAt") ?: JSONObject.NULL)
                .put("pageTitle", payload.optString("pageTitle", "${target.university} 경쟁률"))
                .put("rows", rows)
                .put("origin", "USER_BROWSER_PUBLIC_DOM")
                .put("credentialExported", false)
                .put("sessionSecretExported", false)

            cloud.observeCompetition(observation) { result ->
                activity.runOnUiThread {
                    if (destroyed || generation != pageGeneration) return@runOnUiThread
                    if (result.isSuccess) {
                        val state = result.getOrNull()?.optString("status", "saved") ?: "saved"
                        onStatus("경쟁률 수집 · ${target.university} $state · ${rows.length()}행")
                    } else {
                        onStatus("경쟁률 수집 · ${target.university} 서버 저장 실패")
                    }
                    moveNextTarget()
                }
            }
        }
    }

    private fun showChallengeDialog(target: CompetitionBrowserTarget, generation: Int) {
        if (destroyed || !running || generation != pageGeneration || challengeDialog != null) return
        val view = webView ?: return
        (view.parent as? ViewGroup)?.removeView(view)
        val container = FrameLayout(activity).apply {
            minimumHeight = (resources.displayMetrics.heightPixels * 0.68f).toInt()
            setPadding(12, 12, 12, 12)
        }
        container.addView(
            view,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
        val dialog = AlertDialog.Builder(activity)
            .setTitle("${target.university} · 안전 접속 확인")
            .setMessage(
                "진학어플라이가 사용자 브라우저 확인을 요구합니다. 아래 페이지에서 정상 보안 확인을 완료하면 경쟁률 표를 자동으로 읽고 이 창을 닫습니다. 로그인 정보·쿠키·세션 값은 서버로 전송하지 않습니다."
            )
            .setView(container)
            .setNegativeButton("이번 대학 건너뛰기", null)
            .create()
        challengeDialog = dialog
        dialog.setOnCancelListener {
            if (challengeDialog === dialog && !destroyed && running && generation == pageGeneration) {
                challengeDialog = null
                reattachToHiddenHost()
                onStatus("경쟁률 수집 · ${target.university} 사용자 확인 취소 · 이번 주기 건너뜀")
                moveNextTarget()
            }
        }
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE)?.setOnClickListener {
                if (!destroyed && running && generation == pageGeneration) {
                    restoreHiddenWebView()
                    onStatus("경쟁률 수집 · ${target.university} 사용자 선택으로 이번 주기 건너뜀")
                    moveNextTarget()
                }
            }
        }
        dialog.show()
        dialog.window?.setLayout(
            ViewGroup.LayoutParams.MATCH_PARENT,
            (activity.resources.displayMetrics.heightPixels * 0.90f).toInt(),
        )
        onStatus("경쟁률 수집 · ${target.university} 안전 접속 확인 창 표시")
    }

    private fun restoreHiddenWebView() {
        val dialog = challengeDialog
        challengeDialog = null
        challengeVisibleSinceMs = 0L
        dialog?.setOnCancelListener(null)
        reattachToHiddenHost()
        dialog?.dismiss()
    }

    private fun reattachToHiddenHost() {
        val view = webView ?: return
        (view.parent as? ViewGroup)?.removeView(view)
        if (!destroyed) {
            host.addView(
                view,
                FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT,
                ),
            )
        }
    }

    private fun moveNextTarget() {
        if (destroyed || !running) return
        restoreHiddenWebView()
        pageGeneration += 1
        webView?.stopLoading()
        activeTargetIndex += 1
        handler.postDelayed({ loadActiveTarget() }, 500L)
    }

    private fun finishCycle(message: String) {
        pageGeneration += 1
        running = false
        activeTargetIndex = -1
        webView?.stopLoading()
        onStatus(message)
    }

    @Suppress("SetJavaScriptEnabled")
    private fun ensureWebView(): WebView {
        webView?.let { return it }
        val view = WebView(activity)
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(view, true)
        }
        view.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = false
            cacheMode = WebSettings.LOAD_DEFAULT
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        }
        view.webChromeClient = WebChromeClient()
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = CompetitionBrowserPolicy.targets.getOrNull(activeTargetIndex) ?: return true
                return !sameHost(request.url?.toString().orEmpty(), target.sourceUrl)
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                handlePageFinished(url)
            }
        }
        host.addView(
            view,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
        webView = view
        return view
    }

    private fun sameHost(left: String, right: String): Boolean = runCatching {
        java.net.URI(left).host.equals(java.net.URI(right).host, ignoreCase = true)
    }.getOrDefault(false)

    private fun decodeJavascriptObject(encoded: String?): JSONObject? = runCatching {
        val outer = JSONTokener(encoded ?: "null").nextValue()
        when (outer) {
            is JSONObject -> outer
            is String -> JSONObject(outer)
            else -> null
        }
    }.getOrNull()

    companion object {
        private val EXTRACT_PUBLIC_COMPETITION_JS = """
            (function(){
              try {
                var body=(document.body&&document.body.innerText?document.body.innerText:'').replace(/\s+/g,' ').trim();
                var title=document.title||'';
                var challenge=/안전한\s*접속\s*확인|Security\s*Check\s*\|\s*JINHAKAPPLY/i.test(title+' '+body.slice(0,5000));
                if(challenge){return JSON.stringify({challenge:true,rows:[]});}

                function clean(v){return String(v==null?'':v).replace(/\s+/g,' ').trim();}
                function integer(v){var s=clean(v).replace(/,/g,'');return /^\d+$/.test(s)?Number(s):null;}
                function ratio(v){var m=clean(v).replace(/,/g,'').match(/(\d+(?:\.\d+)?)\s*(?::|대)\s*1/);return m?Number(m[1]):null;}
                function numeric(v){return integer(v)!==null||ratio(v)!==null||/^[-–—]$/.test(clean(v));}
                function label(v){var s=clean(v);return !s||numeric(s)?null:s.slice(0,300);}
                function header(cells){
                  var h={admission:-1,department:-1,quota:-1,applicants:-1,ratio:-1};
                  cells.forEach(function(c,i){var n=clean(c).replace(/[\s·._()\-]/g,'').toLowerCase();
                    if(h.admission<0&&/전형명|전형/.test(n))h.admission=i;
                    if(h.department<0&&/모집단위|학과|전공/.test(n))h.department=i;
                    if(h.quota<0&&/모집인원|모집정원|정원/.test(n))h.quota=i;
                    if(h.applicants<0&&/지원인원|지원자수|지원자/.test(n))h.applicants=i;
                    if(h.ratio<0&&/경쟁률/.test(n))h.ratio=i;
                  });
                  return h;
                }
                function at(a,i){return i>=0&&i<a.length?a[i]:null;}
                function countsMatch(q,a,r){
                  if(q===null||a===null||r===null)return true;
                  if(q===0)return a===0&&Math.abs(r)<=0.005;
                  return Math.abs((a/q)-r)<=0.015;
                }

                var out=[];var currentHeader=null;var section=null;
                Array.from(document.querySelectorAll('table tr')).forEach(function(tr){
                  var cells=Array.from(tr.querySelectorAll('th,td')).map(function(td){return clean(td.innerText||td.textContent||'');}).filter(Boolean).slice(0,30);
                  if(!cells.length)return;
                  var h=header(cells);
                  if(h.ratio>=0&&(h.department>=0||h.quota>=0)){currentHeader=h;return;}
                  if(cells.length<=3&&!cells.some(function(c){return ratio(c)!==null;})){
                    var candidate=clean(cells.join(' '));
                    if(candidate&&candidate.length<180&&!/합계|총계|모집인원|지원인원|경쟁률/.test(candidate))section=candidate;
                  }
                  var ri=currentHeader&&currentHeader.ratio>=0?currentHeader.ratio:-1;
                  if(ri<0||ri>=cells.length||ratio(cells[ri])===null){
                    ri=-1;for(var i=cells.length-1;i>=0;i--){if(ratio(cells[i])!==null){ri=i;break;}}
                  }
                  if(ri<0)return;
                  var r=ratio(cells[ri]);if(r===null)return;
                  var before=cells.slice(0,ri);
                  var ints=[];
                  before.forEach(function(c,i){var v=integer(c);if(v!==null)ints.push({i:i,v:v});});
                  var quota=null,applicants=null,tail=ri;
                  if(ints.length>=2){
                    quota=ints[ints.length-2].v;
                    applicants=ints[ints.length-1].v;
                    tail=ints[ints.length-2].i;
                  }else{
                    quota=integer(at(cells,currentHeader?currentHeader.quota:-1));
                    applicants=integer(at(cells,currentHeader?currentHeader.applicants:-1));
                  }
                  var texts=before.slice(0,tail).filter(function(c){return !numeric(c);});
                  var department=texts.length?label(texts[texts.length-1]):label(at(cells,currentHeader?currentHeader.department:-1));
                  var admission=label(section);
                  var indexedAdmission=label(at(cells,currentHeader?currentHeader.admission:-1));
                  if(indexedAdmission&&indexedAdmission!==department)admission=indexedAdmission;
                  else if(!admission&&texts.length>1)admission=label(texts[texts.length-2]);
                  if(!countsMatch(quota,applicants,r))return;
                  if(!department&&quota===null&&applicants===null)return;
                  out.push({admission:admission,department:department,quota:quota,applicants:applicants,ratio:r,cells:cells});
                });

                var seen={};out=out.filter(function(r){var k=JSON.stringify([r.admission,r.department,r.quota,r.applicants,r.ratio]);if(seen[k])return false;seen[k]=true;return true;});
                var sourceUpdatedAt=null;
                var datePattern='(20\\d{2})\\s*[.\\/-]\\s*(\\d{1,2})\\s*[.\\/-]\\s*(\\d{1,2})[^\\d]{0,20}(\\d{1,2})\\s*:\\s*(\\d{2})';
                var dm=body.match(new RegExp('(?:업데이트|갱신|기준|현재)[^0-9]{0,30}'+datePattern,'i'))||body.match(new RegExp(datePattern+'[^가-힣A-Za-z0-9]{0,20}(?:업데이트|갱신|기준|현재)','i'));
                if(dm){
                  var offset=dm.length>6?dm.length-5:1;
                  sourceUpdatedAt=dm[offset]+'-'+String(dm[offset+1]).padStart(2,'0')+'-'+String(dm[offset+2]).padStart(2,'0')+'T'+String(dm[offset+3]).padStart(2,'0')+':'+dm[offset+4]+':00+09:00';
                }
                return JSON.stringify({
                  challenge:false,
                  sourceUrl:location.origin+location.pathname,
                  sourceUpdatedAt:sourceUpdatedAt,
                  pageTitle:title.slice(0,300),
                  rows:out.slice(0,600)
                });
              }catch(e){return JSON.stringify({challenge:false,error:'dom-extract-failed',rows:[]});}
            })();
        """.trimIndent()
    }
}
