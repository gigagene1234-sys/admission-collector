package com.admissionhub.collector.jinhak

import android.app.Activity
import android.graphics.Bitmap
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.view.View
import android.webkit.CookieManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import com.admissionhub.collector.capture.SnapshotScript
import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONObject
import java.util.ArrayDeque

/**
 * Bounded authenticated background browser pool for slow Jinhak read-only pages.
 *
 * Security/privacy invariants:
 * - Uses the process-wide WebView CookieManager but never exports cookie/session material.
 * - Heartbeats inspect only privacy-sanitized visible text shape/markers; no form values,
 *   localStorage, sessionStorage, cookies, raw DOM or credential fields are read.
 * - Replay may click only the already-approved read-navigation label inside the same
 *   application card context. It never clicks write/payment/submission/consent controls.
 *
 * Scheduling semantics:
 * - The foreground WebView escalates a target after 35s rather than failing it.
 * - At most two slow workers render concurrently. Tasks may keep progressing until
 *   120s, while a no-progress window after 90s is considered a true stall.
 */
class JinhakSlowLanePool(
    private val activity: Activity,
    private val host: FrameLayout,
    private val listener: Listener
) {
    data class Task(
        val id: String,
        val targetUrl: String,
        val originUrl: String,
        val actionLabel: String?,
        val missionContext: JSONObject?,
        val laneHint: String,
        val priority: Int,
        val reason: String,
        val enqueuedAtMs: Long = System.currentTimeMillis()
    ) {
        fun dedupeKey(): String = RecordUtils.sha256(
            listOf(
                targetUrl,
                originUrl,
                actionLabel ?: "",
                missionContext?.optString("identityKey") ?: "",
                laneHint
            ).joinToString("|")
        )
    }

    data class ResultStats(
        val workerId: Int,
        val elapsedMs: Long,
        val progressEvents: Int,
        val stablePolls: Int,
        val replayUsed: Boolean,
        val laneSatisfied: Boolean
    )

    data class Stats(
        val queued: Int,
        val running: Int,
        val completed: Int,
        val failed: Int,
        val escalated: Int,
        val progressExtensions: Int,
        val replayAttempts: Int,
        val replaySuccesses: Int,
        val maxActiveWorkers: Int
    )

    interface Listener {
        fun onSlowLaneCompleted(task: Task, snapshot: JSONObject, stats: ResultStats)
        fun onSlowLaneFailed(task: Task, reason: String, stats: ResultStats)
        fun onSlowLaneStatsChanged(stats: Stats)
    }

    private data class WorkerSlot(
        val id: Int,
        val webView: WebView,
        var task: Task? = null,
        var startedAtMs: Long = 0L,
        var lastProgressAtMs: Long = 0L,
        var lastSignature: String = "",
        var stablePolls: Int = 0,
        var progressEvents: Int = 0,
        var heartbeatGeneration: Int = 0,
        var pageFinished: Boolean = false,
        var replayAttempted: Boolean = false,
        var replaySucceeded: Boolean = false,
        var captureInProgress: Boolean = false
    )

    private val handler = Handler(Looper.getMainLooper())
    private val pending = ArrayDeque<Task>()
    private val pendingKeys = linkedSetOf<String>()
    private val slots = mutableListOf<WorkerSlot>()
    private var maxActiveWorkers = 2
    private var completedCount = 0
    private var failedCount = 0
    private var escalatedCount = 0
    private var progressExtensions = 0
    private var replayAttempts = 0
    private var replaySuccesses = 0
    private var destroyed = false

    companion object {
        const val DEFAULT_MAX_WORKERS = 2
        private const val MAX_QUEUE = 24
        private const val HEARTBEAT_MS = 2_000L
        private const val STALL_CHECK_AFTER_MS = 90_000L
        private const val STALL_NO_PROGRESS_MS = 18_000L
        private const val HARD_MAX_MS = 120_000L
        private const val MIN_CAPTURE_MS = 4_000L
        private const val GENERIC_STABLE_CAPTURE_MS = 12_000L
    }

    fun enqueue(task: Task): Boolean {
        if (destroyed || !isAllowedJinhakUrl(task.targetUrl) || !isAllowedJinhakUrl(task.originUrl.ifBlank { task.targetUrl })) return false
        val key = task.dedupeKey()
        if (pendingKeys.contains(key) || slots.any { it.task?.dedupeKey() == key }) return true
        if (pending.size >= MAX_QUEUE) return false
        if (task.priority >= 90) pending.addFirst(task) else pending.addLast(task)
        pendingKeys.add(key)
        escalatedCount += 1
        notifyStats()
        pump()
        return true
    }

    fun hasWork(): Boolean = pending.isNotEmpty() || slots.any { it.task != null }

    fun stats(): Stats = Stats(
        queued = pending.size,
        running = slots.count { it.task != null },
        completed = completedCount,
        failed = failedCount,
        escalated = escalatedCount,
        progressExtensions = progressExtensions,
        replayAttempts = replayAttempts,
        replaySuccesses = replaySuccesses,
        maxActiveWorkers = maxActiveWorkers
    )

    fun setMaxActiveWorkers(value: Int) {
        if (destroyed) return
        val next = value.coerceIn(1, DEFAULT_MAX_WORKERS)
        if (next == maxActiveWorkers) return
        maxActiveWorkers = next
        if (slots.size > next) {
            val overflow = slots.drop(next).toList()
            overflow.forEach { slot ->
                slot.task?.let { task ->
                    val key = task.dedupeKey()
                    if (!pendingKeys.contains(key)) {
                        pending.addFirst(task)
                        pendingKeys.add(key)
                    }
                }
                destroySlot(slot)
            }
            slots.removeAll(overflow.toSet())
        }
        notifyStats()
        pump()
    }

    fun cancelAll(reason: String) {
        if (destroyed) return
        pending.clear()
        pendingKeys.clear()
        slots.forEach { slot ->
            val task = slot.task
            if (task != null) {
                failedCount += 1
                listener.onSlowLaneFailed(task, reason, resultStats(slot, laneSatisfied = false))
            }
            resetSlot(slot)
        }
        notifyStats()
    }

    fun destroy() {
        if (destroyed) return
        destroyed = true
        pending.clear()
        pendingKeys.clear()
        slots.toList().forEach { destroySlot(it) }
        slots.clear()
    }

    private fun pump() {
        if (destroyed) return
        while (slots.size < maxActiveWorkers) slots += createSlot(slots.size + 1)
        for (slot in slots) {
            if (slot.task != null || pending.isEmpty()) continue
            val task = pending.removeFirst()
            pendingKeys.remove(task.dedupeKey())
            start(slot, task)
        }
        notifyStats()
    }

    @Suppress("SetJavaScriptEnabled")
    private fun createSlot(id: Int): WorkerSlot {
        val view = WebView(activity)
        view.visibility = View.INVISIBLE
        view.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = userAgentString + " AdmissionCollector-SlowLane/$id"
        }
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(view, true)
        }
        val slot = WorkerSlot(id, view)
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean =
                !isAllowedJinhakUrl(request.url.toString())

            override fun onPageStarted(v: WebView, url: String, favicon: Bitmap?) {
                if (slot.task == null) return
                slot.lastProgressAtMs = System.currentTimeMillis()
                slot.pageFinished = false
                slot.stablePolls = 0
            }

            override fun onPageFinished(v: WebView, url: String) {
                if (slot.task == null) return
                slot.pageFinished = true
                CookieManager.getInstance().flush()
                maybeReplay(slot)
                scheduleHeartbeat(slot, 500L)
            }

            override fun onRenderProcessGone(v: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                val task = slot.task
                if (task != null) finishFailure(slot, "slow-lane-renderer-gone")
                return true
            }
        }
        host.addView(view, FrameLayout.LayoutParams(1, 1))
        return slot
    }

    private fun start(slot: WorkerSlot, task: Task) {
        val now = System.currentTimeMillis()
        slot.task = task
        slot.startedAtMs = now
        slot.lastProgressAtMs = now
        slot.lastSignature = ""
        slot.stablePolls = 0
        slot.progressEvents = 0
        slot.heartbeatGeneration += 1
        slot.pageFinished = false
        slot.replayAttempted = false
        slot.replaySucceeded = task.actionLabel.isNullOrBlank()
        slot.captureInProgress = false
        val firstUrl = if (!task.actionLabel.isNullOrBlank() && task.originUrl.isNotBlank()) task.originUrl else task.targetUrl
        slot.webView.loadUrl(firstUrl)
    }

    private fun maybeReplay(slot: WorkerSlot) {
        val task = slot.task ?: return
        val label = task.actionLabel?.takeIf { it.isNotBlank() } ?: return
        if (slot.replayAttempted) return
        slot.replayAttempted = true
        replayAttempts += 1
        val script = replayScript(label, task.missionContext)
        slot.webView.evaluateJavascript(script) { encoded ->
            if (slot.task?.id != task.id) return@evaluateJavascript
            val result = decodeJson(encoded)
            if (result?.optBoolean("ok", false) == true) {
                slot.replaySucceeded = true
                replaySuccesses += 1
                slot.lastProgressAtMs = System.currentTimeMillis()
                slot.progressEvents += 1
                slot.stablePolls = 0
                scheduleHeartbeat(slot, 850L)
            } else {
                scheduleHeartbeat(slot, 500L)
            }
            notifyStats()
        }
    }

    private fun scheduleHeartbeat(slot: WorkerSlot, delayMs: Long = HEARTBEAT_MS) {
        val generation = slot.heartbeatGeneration
        handler.postDelayed({
            if (destroyed || slot.task == null || generation != slot.heartbeatGeneration) return@postDelayed
            heartbeat(slot)
        }, delayMs)
    }

    private fun heartbeat(slot: WorkerSlot) {
        val task = slot.task ?: return
        slot.webView.evaluateJavascript(heartbeatScript()) { encoded ->
            if (slot.task?.id != task.id) return@evaluateJavascript
            val now = System.currentTimeMillis()
            val elapsed = now - slot.startedAtMs
            val obj = decodeJson(encoded)
            if (obj == null) {
                if (elapsed >= HARD_MAX_MS) finishFailure(slot, "slow-lane-heartbeat-unreadable")
                else scheduleHeartbeat(slot)
                return@evaluateJavascript
            }
            val signature = obj.optString("signature")
            if (signature.isNotBlank() && signature != slot.lastSignature) {
                if (slot.lastSignature.isNotBlank() && elapsed >= 35_000L) progressExtensions += 1
                slot.lastSignature = signature
                slot.lastProgressAtMs = now
                slot.progressEvents += 1
                slot.stablePolls = 0
            } else {
                slot.stablePolls += 1
            }

            val laneSatisfied = laneSatisfied(task.laneHint, obj.optJSONObject("markers") ?: JSONObject())
            val progressedRecently = now - slot.lastProgressAtMs < STALL_NO_PROGRESS_MS
            val replayReady = task.actionLabel.isNullOrBlank() || slot.replaySucceeded
            val genericStable = elapsed >= GENERIC_STABLE_CAPTURE_MS && slot.stablePolls >= 2 && obj.optInt("visibleTextLength", 0) >= 800
            val markerStable = laneSatisfied && elapsed >= MIN_CAPTURE_MS && slot.stablePolls >= 1
            if (slot.pageFinished && replayReady && (markerStable || genericStable)) {
                capture(slot, laneSatisfied)
                return@evaluateJavascript
            }
            if (elapsed >= HARD_MAX_MS) {
                finishFailure(slot, "slow-lane-hard-max")
                return@evaluateJavascript
            }
            if (elapsed >= STALL_CHECK_AFTER_MS && !progressedRecently) {
                finishFailure(slot, "slow-lane-no-progress")
                return@evaluateJavascript
            }
            scheduleHeartbeat(slot)
            notifyStats()
        }
    }

    private fun capture(slot: WorkerSlot, laneSatisfied: Boolean) {
        val task = slot.task ?: return
        if (slot.captureInProgress) return
        slot.captureInProgress = true
        slot.webView.evaluateJavascript(SnapshotScript.build()) { encoded ->
            if (slot.task?.id != task.id) return@evaluateJavascript
            val snapshot = decodeJson(encoded)
            if (snapshot == null) {
                slot.captureInProgress = false
                scheduleHeartbeat(slot, 1_000L)
                return@evaluateJavascript
            }
            completedCount += 1
            listener.onSlowLaneCompleted(task, snapshot, resultStats(slot, laneSatisfied))
            resetSlot(slot)
            notifyStats()
            pump()
        }
    }

    private fun finishFailure(slot: WorkerSlot, reason: String) {
        val task = slot.task ?: return
        failedCount += 1
        listener.onSlowLaneFailed(task, reason, resultStats(slot, laneSatisfied = false))
        resetSlot(slot)
        notifyStats()
        pump()
    }

    private fun resultStats(slot: WorkerSlot, laneSatisfied: Boolean): ResultStats = ResultStats(
        workerId = slot.id,
        elapsedMs = (System.currentTimeMillis() - slot.startedAtMs).coerceAtLeast(0L),
        progressEvents = slot.progressEvents,
        stablePolls = slot.stablePolls,
        replayUsed = slot.replayAttempted,
        laneSatisfied = laneSatisfied
    )

    private fun resetSlot(slot: WorkerSlot) {
        slot.heartbeatGeneration += 1
        runCatching { slot.webView.stopLoading() }
        runCatching { slot.webView.loadUrl("about:blank") }
        slot.task = null
        slot.startedAtMs = 0L
        slot.lastProgressAtMs = 0L
        slot.lastSignature = ""
        slot.stablePolls = 0
        slot.progressEvents = 0
        slot.pageFinished = false
        slot.replayAttempted = false
        slot.replaySucceeded = false
        slot.captureInProgress = false
    }

    private fun destroySlot(slot: WorkerSlot) {
        slot.heartbeatGeneration += 1
        runCatching { slot.webView.stopLoading() }
        runCatching { host.removeView(slot.webView) }
        runCatching { slot.webView.destroy() }
    }

    private fun notifyStats() = listener.onSlowLaneStatsChanged(stats())

    private fun laneSatisfied(lane: String, markers: JSONObject): Boolean = when (lane) {
        "current-prediction" -> markers.optBoolean("prediction")
        "mock-support" -> markers.optBoolean("mockSupport")
        "actual-admit" -> markers.optBoolean("actualAdmit")
        "university-result" -> markers.optBoolean("universityResult")
        "score-analysis" -> markers.optBoolean("scoreAnalysis")
        "strategy" -> markers.optBoolean("strategy")
        else -> markers.optInt("signalCount", 0) >= 1
    }

    private fun heartbeatScript(): String = """
        (function(){
          try{
            function clean(v){return String(v||'').replace(/\s+/g,' ').trim();}
            function hash(s){var h=2166136261>>>0;for(var i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return (h>>>0).toString(16);}
            var body=document.body?document.body.cloneNode(true):null;
            if(body){
              var rm=body.querySelectorAll('script,style,noscript,template,input,textarea,select,option,form,[type=hidden],[hidden],[aria-hidden=true]');
              for(var i=0;i<rm.length;i++) rm[i].remove();
            }
            var text=clean(body?(body.innerText||body.textContent||''):'').slice(0,60000);
            text=text.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'[redacted-email]');
            var markers={
              prediction:/(합격\s*예측|합격\s*안정성|예상\s*합격선|적정지원컷|칸\s*수|[0-9]{1,2}\s*칸)/i.test(text),
              mockSupport:/(모의\s*지원|지원자\s*분포|모의지원자\s*평균|내\s*순위)/i.test(text),
              actualAdmit:/(실제\s*합격자|과거\s*합격자|합격자\s*점수\s*분포|불합격자)/i.test(text),
              universityResult:/(입시\s*결과|전년도\s*경쟁률|50%\s*컷|70%\s*컷|충원)/i.test(text),
              scoreAnalysis:/(내\s*점수|환산\s*점수|반영\s*등급|수능\s*최저|성적\s*분석)/i.test(text),
              strategy:/(입시\s*전략|지원\s*전략|상향\s*지원|적정\s*지원|안정\s*지원)/i.test(text)
            };
            var count=0;Object.keys(markers).forEach(function(k){if(markers[k])count++;});markers.signalCount=count;
            var material=[String(document.readyState||''),String(location.pathname||''),String(document.title||''),String(text.length),text.slice(0,12000),text.slice(-4000)].join('|');
            return JSON.stringify({readyState:String(document.readyState||''),visibleTextLength:text.length,signature:hash(material),markers:markers});
          }catch(e){return JSON.stringify({readyState:'',visibleTextLength:0,signature:'',markers:{signalCount:0}});}
        })();
    """.trimIndent()

    private fun replayScript(label: String, context: JSONObject?): String {
        val expected = JSONObject.quote(label.take(120))
        val university = JSONObject.quote(context?.optString("university")?.take(80).orEmpty())
        val department = JSONObject.quote(context?.optString("departmentRaw")?.take(100).orEmpty())
        val admission = JSONObject.quote(context?.optString("admission")?.take(80).orEmpty())
        return """
            (function(){
              function visible(el){if(!el)return false;var s=getComputedStyle(el);if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0')return false;var r=el.getBoundingClientRect();return r.width>0&&r.height>0;}
              function clean(v){return String(v||'').replace(/\s+/g,' ').trim();}
              var expected=$expected, uni=$university, dept=$department, adm=$admission;
              var blocked=/(원서\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)/i;
              var nodes=document.querySelectorAll('a,button,[role=button],[role=tab],[onclick],[data-href],[data-url],[data-link],[data-path]');
              for(var i=0;i<nodes.length;i++){
                var el=nodes[i]; if(!visible(el)) continue;
                var lab=clean(el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title')||'').slice(0,120);
                if(lab!==expected || blocked.test(lab)) continue;
                var cur=el, matched=false;
                for(var d=0;cur&&d<9;d++,cur=cur.parentElement){
                  var t=clean(cur.innerText||cur.textContent||'').slice(0,5000);
                  var okUni=!uni||t.indexOf(uni)>=0;
                  var okDept=!dept||t.indexOf(dept)>=0;
                  var okAdm=!adm||t.indexOf(adm)>=0;
                  if(okUni&&okDept&&okAdm){matched=true;break;}
                }
                if(!matched && (uni||dept)) continue;
                try{el.click();return JSON.stringify({ok:true,matchedContext:matched});}catch(e){return JSON.stringify({ok:false,reason:'click-failed'});}
              }
              return JSON.stringify({ok:false,reason:'mission-action-not-found'});
            })();
        """.trimIndent()
    }

    private fun isAllowedJinhakUrl(raw: String): Boolean = try {
        val uri = Uri.parse(raw)
        val host = uri.host.orEmpty().lowercase()
        uri.scheme == "https" && (host == "jinhak.com" || host.endsWith(".jinhak.com"))
    } catch (_: Exception) { false }

    private fun decodeJson(encoded: String?): JSONObject? {
        if (encoded.isNullOrBlank() || encoded == "null") return null
        return runCatching {
            val raw = if (encoded.startsWith("\"") && encoded.endsWith("\"")) {
                org.json.JSONTokener(encoded).nextValue() as? String ?: encoded
            } else encoded
            JSONObject(raw)
        }.getOrNull()
    }
}
