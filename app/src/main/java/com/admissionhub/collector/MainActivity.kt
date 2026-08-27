package com.admissionhub.collector

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.webkit.*
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.time.Instant

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var status: TextView
    private lateinit var preview: TextView
    private var lastJson: String = ""
    private var provider: String = "adiga"

    companion object {
        private const val SAVE_JSON_REQUEST = 7001
        private const val ADIGA_URL = "https://www.adiga.kr/"
        private const val JINHAK_URL = "https://www.jinhak.com/"
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
            setPadding(12, 12, 12, 12)
        }

        val tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }

        val adigaButton = Button(this).apply {
            text = "어디가"
            setOnClickListener { openProvider("adiga") }
        }
        val jinhakButton = Button(this).apply {
            text = "진학사"
            setOnClickListener { openProvider("jinhak") }
        }
        tabs.addView(adigaButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        tabs.addView(jinhakButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val back = Button(this).apply {
            text = "←"
            setOnClickListener { if (webView.canGoBack()) webView.goBack() }
        }
        val collect = Button(this).apply {
            text = "현재 페이지 수집"
            setOnClickListener { collectCurrentPage() }
        }
        val save = Button(this).apply {
            text = "JSON 저장"
            setOnClickListener { saveJson() }
        }
        actions.addView(back)
        actions.addView(collect, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions.addView(save)

        status = TextView(this).apply {
            text = "준비 중"
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
        root.addView(actions)
        root.addView(status)
        root.addView(webView, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 3f))
        root.addView(scroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 2f))
        setContentView(root)
    }

    @Suppress("SetJavaScriptEnabled")
    private fun configureWebView() {
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            javaScriptCanOpenWindowsAutomatically = true
            setSupportMultipleWindows(true)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = userAgentString + " AdmissionCollector/0.1"
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false
            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                status.text = "불러오는 중: $url"
            }
            override fun onPageFinished(view: WebView, url: String) {
                status.text = "현재 페이지: $url"
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onCreateWindow(view: WebView?, isDialog: Boolean, isUserGesture: Boolean, resultMsg: android.os.Message?): Boolean {
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
        provider = which
        val url = if (which == "adiga") ADIGA_URL else JINHAK_URL
        status.text = if (which == "adiga") "어디가 열기" else "진학사 열기"
        webView.loadUrl(url)
    }

    private fun collectCurrentPage() {
        status.text = "표시된 결과 정보만 수집 중…"
        val js = """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0 && r.height>0;
              }
              var forbidden=/password|passwd|cookie|session|token|csrf|transkey|captcha|auth|credential|secret/i;
              var badTags={SCRIPT:1,STYLE:1,NOSCRIPT:1,TEMPLATE:1,INPUT:1,TEXTAREA:1,SELECT:1,OPTION:1,FORM:1};
              var rows=[];
              var candidates=document.querySelectorAll('table tr, [role=row], article, .card, .item, .result, .list-item, .tbl_row, [class*=result], [class*=admission]');
              for(var i=0;i<candidates.length;i++){
                var el=candidates[i];
                if(!visible(el) || badTags[el.tagName]) continue;
                var meta=(el.id||'')+' '+(el.className||'')+' '+(el.getAttribute('name')||'');
                if(forbidden.test(meta)) continue;
                var clone=el.cloneNode(true);
                var rm=clone.querySelectorAll('script,style,noscript,template,input,textarea,select,option,form,[type=hidden],[hidden],[aria-hidden=true]');
                for(var j=0;j<rm.length;j++) rm[j].remove();
                var text=(clone.innerText||clone.textContent||'').replace(/\\s+/g,' ').trim();
                var sensitiveUi=/(?:아이디|로그인|로그아웃|회원정보|마이페이지|account|sign[ -]?in|sign[ -]?out)/i;
                var admissionTerms=/(?:대학교|대학|학과|학부|전공|모집단위|전형|경쟁률|모집인원|환산점수|50%|70%|칸수|합격예측|안정|적정|소신)/;
                if(text.length<4 || text.length>3000 || forbidden.test(text.substring(0,160)) || sensitiveUi.test(text) || !admissionTerms.test(text)) continue;
                text=text.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/ig,'[redacted-email]');
                rows.push(text);
                if(rows.length>=250) break;
              }
              var safeUrl=location.origin+location.pathname;
              return JSON.stringify({title:document.title||'',url:safeUrl,rows:rows});
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            try {
                val raw = when {
                    encoded == null || encoded == "null" -> "{}"
                    else -> (JSONTokener(encoded).nextValue() as? String) ?: "{}"
                }
                consumeDomJson(raw)
            } catch (e: Exception) {
                status.text = "수집 실패: ${e.message}"
            }
        }
    }

    private fun consumeDomJson(raw: String) {
        val dom = JSONObject(raw)
        val rows = dom.optJSONArray("rows") ?: JSONArray()
        val evidence = mutableListOf<String>()
        for (i in 0 until rows.length()) {
            val t = rows.optString(i).trim()
            if (t.isNotBlank()) evidence.add(t)
        }

        val records = parseRecords(evidence)
        val out = JSONObject()
            .put("provider", provider)
            .put("pageUrl", dom.optString("url", webView.url ?: ""))
            .put("pageTitle", dom.optString("title", webView.title ?: ""))
            .put("collectedAt", Instant.now().toString())
            .put("records", records)
            .put("evidenceCount", evidence.size)

        lastJson = out.toString(2)
        preview.text = lastJson
        status.text = "수집 완료: 구조화 레코드 ${records.length()}개 / 증거 블록 ${evidence.size}개"
    }

    private fun parseRecords(rows: List<String>): JSONArray {
        val result = JSONArray()
        val universityRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,40}(대학교|대학))")
        val deptRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,50}(학과|학부|전공|모집단위))")
        val admissionRegex = Regex("([가-힣A-Za-z0-9·.()\\- ]{2,50}(전형|교과|종합|추천|면접))")
        val competitionRegex = Regex("(?:경쟁률)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?\\s*[:대]\\s*1|[0-9]+(?:\\.[0-9]+)?)")
        val capacityRegex = Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9]+)")
        val cut50Regex = Regex("(?:50%\\s*컷|50%\\s*cut|50\\s*%\\s*cut)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)", RegexOption.IGNORE_CASE)
        val cut70Regex = Regex("(?:70%\\s*컷|70%\\s*cut|70\\s*%\\s*cut)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)", RegexOption.IGNORE_CASE)
        val myScoreRegex = Regex("(?:내\\s*(?:환산)?점수|나의\\s*(?:환산)?점수|환산점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)")
        val barsRegex = Regex("(?:칸수|칸\\s*수)\\s*[:：]?\\s*([0-9]+)")
        val judgmentRegex = Regex("(?:판정|합격예측)\\s*[:：]?\\s*(안정|적정|소신|위험|상향|하향|가능|불안)")

        val candidates = rows.filter { row ->
            universityRegex.containsMatchIn(row) ||
                deptRegex.containsMatchIn(row) ||
                competitionRegex.containsMatchIn(row) ||
                capacityRegex.containsMatchIn(row) ||
                (provider == "jinhak" && (barsRegex.containsMatchIn(row) || judgmentRegex.containsMatchIn(row)))
        }.take(100)

        for (row in candidates) {
            val university = universityRegex.find(row)?.groupValues?.getOrNull(1)?.trim()
            val department = deptRegex.find(row)?.groupValues?.getOrNull(1)?.trim()
            val admission = admissionRegex.find(row)?.groupValues?.getOrNull(1)?.trim()
            val metrics = JSONObject()
                .put("myScore", myScoreRegex.find(row)?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: JSONObject.NULL)
                .put("cut50", cut50Regex.find(row)?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: JSONObject.NULL)
                .put("cut70", cut70Regex.find(row)?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: JSONObject.NULL)
                .put("competition", competitionRegex.find(row)?.groupValues?.getOrNull(1) ?: JSONObject.NULL)
                .put("capacity", capacityRegex.find(row)?.groupValues?.getOrNull(1)?.toIntOrNull() ?: JSONObject.NULL)
                .put("jinhakBars", barsRegex.find(row)?.groupValues?.getOrNull(1)?.toIntOrNull() ?: JSONObject.NULL)
                .put("jinhakJudgment", judgmentRegex.find(row)?.groupValues?.getOrNull(1) ?: JSONObject.NULL)

            if (university != null || department != null || admission != null || metrics.keys().asSequence().any { !metrics.isNull(it) }) {
                val confidence = when {
                    university != null && department != null && admission != null -> "medium"
                    university != null && department != null -> "low"
                    else -> "raw"
                }
                result.put(JSONObject()
                    .put("university", university ?: JSONObject.NULL)
                    .put("department", department ?: JSONObject.NULL)
                    .put("admission", admission ?: JSONObject.NULL)
                    .put("metrics", metrics)
                    .put("confidence", confidence)
                    .put("rawEvidence", row.take(3000)))
            }
        }

        return result
    }

    private fun saveJson() {
        if (lastJson.isBlank()) {
            Toast.makeText(this, "먼저 현재 페이지를 수집하세요.", Toast.LENGTH_SHORT).show()
            return
        }
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/json"
            putExtra(Intent.EXTRA_TITLE, "admission-${provider}-${System.currentTimeMillis()}.json")
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

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }
}
