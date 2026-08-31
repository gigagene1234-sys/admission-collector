from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
SNAPSHOT = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
CLIENT = ROOT / 'app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadClient.kt'
COORD = ROOT / 'app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadCoordinator.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'
WORKER = ROOT / 'cloudflare/src/index.js'
WRANGLER = ROOT / 'cloudflare/wrangler.jsonc'
SESSION = ROOT / 'app/src/main/java/com/admissionhub/collector/session/SecureSessionVault.kt'
AGENT = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt'
MIGRATION = ROOT / 'cloudflare/migrations/0004_crawl_frontier.sql'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 anchor, found {count}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# New secure local session vault. Cookies/session material never leaves Android.
# ---------------------------------------------------------------------------
SESSION.parent.mkdir(parents=True, exist_ok=True)
SESSION.write_text(r'''package com.admissionhub.collector.session

import android.content.Context
import android.util.Base64
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.URI
import java.security.KeyStore
import java.time.Instant
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties

/**
 * Hardware/OS-keystore protected backup for the authenticated WebView session.
 *
 * Security boundary:
 * - never stores a password, form value, CSRF value, CAPTCHA material or raw DOM;
 * - encrypted cookie material remains on this Android device only;
 * - cloud/export/diagnostic code receives only SessionLeaseSummary;
 * - leaseId is an opaque random identifier, never a reversible encryption seed.
 */
class SecureSessionVault(context: Context) {
    data class SessionLeaseSummary(
        val provider: String,
        val leaseId: String,
        val origin: String,
        val capturedAt: String,
        val collectorVersion: String,
        val cookieCount: Int,
        val restored: Boolean = false
    ) {
        fun toJson(): JSONObject = JSONObject()
            .put("provider", provider)
            .put("leaseId", leaseId)
            .put("origin", origin)
            .put("capturedAt", capturedAt)
            .put("collectorVersion", collectorVersion)
            .put("cookieCount", cookieCount)
            .put("restored", restored)
            .put("containsCredential", false)
            .put("cloudExportAllowed", false)
    }

    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun captureAuthenticated(provider: String, pageUrl: String, collectorVersion: String): SessionLeaseSummary? {
        val origin = safeOrigin(pageUrl) ?: return null
        val cookieHeader = CookieManager.getInstance().getCookie(pageUrl).orEmpty().trim()
        if (cookieHeader.isBlank()) return null
        val cookieCount = cookieHeader.split(';').count { it.trim().contains('=') }
        val leaseId = existingMetadata(provider)?.optString("leaseId")?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString()
        val capturedAt = Instant.now().toString()
        val payload = JSONObject()
            .put("provider", provider)
            .put("leaseId", leaseId)
            .put("origin", origin)
            .put("cookieHeader", cookieHeader)
            .put("capturedAt", capturedAt)
            .put("collectorVersion", collectorVersion)
        val encrypted = encrypt(payload.toString().toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString(secretKey(provider), encrypted)
            .putString(metadataKey(provider), JSONObject()
                .put("provider", provider)
                .put("leaseId", leaseId)
                .put("origin", origin)
                .put("capturedAt", capturedAt)
                .put("collectorVersion", collectorVersion)
                .put("cookieCount", cookieCount)
                .toString())
            .apply()
        return SessionLeaseSummary(provider, leaseId, origin, capturedAt, collectorVersion, cookieCount)
    }

    fun restore(provider: String): SessionLeaseSummary? {
        val encoded = prefs.getString(secretKey(provider), null)?.takeIf { it.isNotBlank() } ?: return null
        val raw = runCatching { String(decrypt(encoded), Charsets.UTF_8) }.getOrNull() ?: return null
        val payload = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        if (payload.optString("provider") != provider) return null
        val origin = payload.optString("origin")
        val cookieHeader = payload.optString("cookieHeader")
        if (origin.isBlank() || cookieHeader.isBlank()) return null
        val manager = CookieManager.getInstance()
        var restored = 0
        cookieHeader.split(';').map { it.trim() }.filter { it.contains('=') }.forEach { cookie ->
            runCatching {
                manager.setCookie(origin, "$cookie; Secure; SameSite=Lax")
                restored += 1
            }
        }
        manager.flush()
        return SessionLeaseSummary(
            provider = provider,
            leaseId = payload.optString("leaseId"),
            origin = origin,
            capturedAt = payload.optString("capturedAt"),
            collectorVersion = payload.optString("collectorVersion"),
            cookieCount = restored,
            restored = restored > 0
        )
    }

    fun summary(provider: String): SessionLeaseSummary? {
        val meta = existingMetadata(provider) ?: return null
        return SessionLeaseSummary(
            provider = provider,
            leaseId = meta.optString("leaseId"),
            origin = meta.optString("origin"),
            capturedAt = meta.optString("capturedAt"),
            collectorVersion = meta.optString("collectorVersion"),
            cookieCount = meta.optInt("cookieCount", 0),
            restored = false
        )
    }

    fun clear(provider: String) {
        prefs.edit().remove(secretKey(provider)).remove(metadataKey(provider)).apply()
    }

    private fun existingMetadata(provider: String): JSONObject? =
        prefs.getString(metadataKey(provider), null)?.let { runCatching { JSONObject(it) }.getOrNull() }

    private fun safeOrigin(raw: String): String? = try {
        val uri = URI(raw)
        val scheme = uri.scheme?.lowercase()?.takeIf { it == "https" } ?: return null
        val host = uri.host?.lowercase()?.takeIf { it.isNotBlank() } ?: return null
        "$scheme://$host/"
    } catch (_: Exception) { null }

    private fun secretKey(provider: String) = "secret_${provider.lowercase()}"
    private fun metadataKey(provider: String) = "meta_${provider.lowercase()}"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }

    private fun encrypt(bytes: ByteArray): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val iv = cipher.iv
        val encrypted = cipher.doFinal(bytes)
        val out = ByteArray(1 + iv.size + encrypted.size)
        out[0] = iv.size.toByte()
        System.arraycopy(iv, 0, out, 1, iv.size)
        System.arraycopy(encrypted, 0, out, 1 + iv.size, encrypted.size)
        return Base64.encodeToString(out, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): ByteArray {
        val all = Base64.decode(encoded, Base64.NO_WRAP)
        require(all.isNotEmpty())
        val ivSize = all[0].toInt() and 0xff
        require(ivSize in 12..32 && all.size > 1 + ivSize)
        val iv = all.copyOfRange(1, 1 + ivSize)
        val encrypted = all.copyOfRange(1 + ivSize, all.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        return cipher.doFinal(encrypted)
    }

    companion object {
        private const val PREFS = "admission_secure_session_v1"
        private const val KEY_ALIAS = "admission_collector_session_v1"
    }
}
''')

# ---------------------------------------------------------------------------
# Safe browser-navigation agent. It only clicks allow-listed read/navigation UI.
# ---------------------------------------------------------------------------
AGENT.parent.mkdir(parents=True, exist_ok=True)
AGENT.write_text(r'''package com.admissionhub.collector.jinhak

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject

object JinhakAgentNavigator {
    data class Candidate(val scanIndex: Int, val label: String, val tag: String, val kind: String)

    fun candidates(snapshot: JSONObject): List<Candidate> {
        val array = snapshot.optJSONArray("agentActions") ?: JSONArray()
        val out = mutableListOf<Candidate>()
        for (i in 0 until minOf(array.length(), 80)) {
            val obj = array.optJSONObject(i) ?: continue
            val scanIndex = obj.optInt("scanIndex", -1)
            val label = obj.optString("label").replace(Regex("\\s+"), " ").trim().take(120)
            val tag = obj.optString("tag").take(24)
            val kind = obj.optString("kind", "read-navigation").take(40)
            if (scanIndex < 0 || label.isBlank()) continue
            if (!isSafeReadNavigationLabel(label)) continue
            out += Candidate(scanIndex, label, tag, kind)
        }
        return out
    }

    fun key(safeRoute: String, candidate: Candidate): String = RecordUtils.sha256(
        listOf(safeRoute, candidate.scanIndex.toString(), candidate.label, candidate.tag, candidate.kind).joinToString("|")
    )

    fun executionScript(candidate: Candidate): String {
        val expected = JSONObject.quote(candidate.label)
        return """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0&&r.height>0;
              }
              function clean(v){return String(v||'').replace(/\\s+/g,' ').trim();}
              var nodes=document.querySelectorAll('a,button,[role=button],[role=tab],[onclick],[data-href],[data-url],[data-link],[data-path]');
              var el=nodes[${candidate.scanIndex}];
              if(!el||!visible(el)) return JSON.stringify({ok:false,reason:'missing-or-hidden'});
              var label=clean(el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title')||'').slice(0,120);
              var expected=$expected;
              if(label!==expected) return JSON.stringify({ok:false,reason:'label-changed'});
              var blocked=/(원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰)/i;
              var allowed=/(상세|보기|조회|검색|리포트|대학\\s*정보|전형\\s*정보|학과\\s*정보|합격\\s*예측|모의\\s*지원|수시\\s*저장소|정시\\s*저장소|추천\\s*대학|성적\\s*분석|다음|더보기|결과|탭)/i;
              if(blocked.test(label)||!allowed.test(label)) return JSON.stringify({ok:false,reason:'policy-block'});
              var before=location.href;
              try{el.click();}catch(e){return JSON.stringify({ok:false,reason:'click-failed'});}
              return JSON.stringify({ok:true,label:label,before:before===location.href?'same-document':'navigation-started'});
            })();
        """.trimIndent()
    }

    private fun isSafeReadNavigationLabel(label: String): Boolean {
        if (Regex("(원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰)", RegexOption.IGNORE_CASE).containsMatchIn(label)) return false
        return Regex("(상세|보기|조회|검색|리포트|대학\\s*정보|전형\\s*정보|학과\\s*정보|합격\\s*예측|모의\\s*지원|수시\\s*저장소|정시\\s*저장소|추천\\s*대학|성적\\s*분석|다음|더보기|결과|탭)", RegexOption.IGNORE_CASE).containsMatchIn(label)
    }
}
''')

# ---------------------------------------------------------------------------
# MainActivity v0.8.0 integration.
# ---------------------------------------------------------------------------
main = MAIN.read_text()
main = replace_once(main, 'import com.admissionhub.collector.jinhak.JinhakCapabilityProbe\n', 'import com.admissionhub.collector.jinhak.JinhakCapabilityProbe\nimport com.admissionhub.collector.jinhak.JinhakAgentNavigator\nimport com.admissionhub.collector.session.SecureSessionVault\n', 'imports')
main = replace_once(main, '    private lateinit var localStore: LocalCollectorStore\n', '    private lateinit var localStore: LocalCollectorStore\n    private lateinit var sessionVault: SecureSessionVault\n', 'session field')
main = replace_once(main, '    private var unifiedAutoCaptureScheduled = false\n', '''    private var unifiedAutoCaptureScheduled = false
    private val jinhakAgentActionSeen = linkedSetOf<String>()
    private var jinhakAgentActionInFlight = false
    private var jinhakAgentActionsExecuted = 0
    private val cloudFrontierTaskIds = linkedMapOf<String, String>()
    private var cloudFrontierClaimInProgress = false
    private var cloudFrontierClaimAttempts = 0
    private var cloudFrontierPublished = 0
    private var cloudFrontierClaimed = 0
''', 'agent state fields')
main = replace_once(main, '        private const val MAX_JINHAK_CONSECUTIVE_STALLS = 4\n', '        private const val MAX_JINHAK_CONSECUTIVE_STALLS = 4\n        private const val MAX_JINHAK_AGENT_ACTIONS = 180\n        private const val MAX_CLOUD_FRONTIER_CLAIM_ATTEMPTS = 3\n', 'agent constants')
main = replace_once(main, '        private const val VERSION = "0.7.1"\n        private const val BUILD_CODE = 10710\n', '        private const val VERSION = "0.8.0"\n        private const val BUILD_CODE = 10800\n', 'version')
main = replace_once(main, '        localStore = LocalCollectorStore(this)\n        buildUi()\n', '        localStore = LocalCollectorStore(this)\n        sessionVault = SecureSessionVault(this)\n        buildUi()\n', 'vault init')

# Session state now captures/restores encrypted local cookie material.
old_session_result = '''                sessionState.text = when {
                    authenticated -> "● 로그인 유지됨"
                    needsLogin -> "○ 로그인 갱신 필요"
                    else -> "△ 로그인 상태 미확정"
                }
                callback?.invoke(needsLogin, authenticated)'''
new_session_result = '''                sessionState.text = when {
                    authenticated -> "● 로그인 유지됨 · 보안 세션 lease 갱신"
                    needsLogin -> "○ 로그인 갱신 필요"
                    else -> "△ 로그인 상태 미확정"
                }
                if (authenticated) {
                    val currentUrl = webView.url.orEmpty()
                    if (currentUrl.isNotBlank()) {
                        runCatching { sessionVault.captureAuthenticated(provider.wireName, currentUrl, VERSION) }
                    }
                }
                callback?.invoke(needsLogin, authenticated)'''
main = replace_once(main, old_session_result, new_session_result, 'session capture')

old_open_provider = '''        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        val capabilities = ProviderCapabilities.profile(which)'''
new_open_provider = '''        CookieManager.getInstance().flush()
        val restoredLease = runCatching { sessionVault.restore(which.wireName) }.getOrNull()
        sessionState.text = if (restoredLease?.restored == true) {
            "● 암호화 세션 lease 복구 · ${restoredLease.leaseId.take(8)}…"
        } else "세션 상태 확인 중"
        val capabilities = ProviderCapabilities.profile(which)'''
main = replace_once(main, old_open_provider, new_open_provider, 'open provider restore')
main = replace_once(main, '            ProviderId.JINHAK -> "현재 진학사 화면 전체 분석·누적"\n', '            ProviderId.JINHAK -> "진학사 에이전트 자동 수집"\n', 'jinhak button')

old_resume_jinhak = '''            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = false
            status.text = "이전 중단 감지: 진학사 자동 크롤러를 체크포인트에서 재개합니다."
            webView.loadUrl(ProviderId.JINHAK.homeUrl)
            true'''
new_resume_jinhak = '''            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = false
            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()
            status.text = if (lease?.restored == true) {
                "이전 중단 감지: 암호화 로그인 세션을 복구하고 진학사 에이전트를 체크포인트에서 재개합니다."
            } else {
                "이전 중단 감지: 저장된 브라우저 세션을 검증한 뒤 진학사 에이전트를 재개합니다."
            }
            webView.loadUrl(ProviderId.JINHAK.homeUrl)
            true'''
main = replace_once(main, old_resume_jinhak, new_resume_jinhak, 'resume session lease')

# Agent/cloud counters reset on each batch.
old_reset = '''        batchUniversityDiscoveryPagesScheduled = 0
        batchPersistedPageSignatureOwners.clear()
        batchSkipSnapshotUntilMs = 0L'''
new_reset = '''        batchUniversityDiscoveryPagesScheduled = 0
        batchPersistedPageSignatureOwners.clear()
        jinhakAgentActionSeen.clear()
        jinhakAgentActionInFlight = false
        jinhakAgentActionsExecuted = 0
        cloudFrontierTaskIds.clear()
        cloudFrontierClaimInProgress = false
        cloudFrontierClaimAttempts = 0
        cloudFrontierPublished = 0
        cloudFrontierClaimed = 0
        batchSkipSnapshotUntilMs = 0L'''
main = replace_once(main, old_reset, new_reset, 'batch reset')

# At batch start, probe cloud frontier without blocking collection.
old_begin_nav = '''    private fun beginBatchNavigation(runId: String?) {
        enqueueProviderSeeds()
        if (runId != null && batchPageActions.isEmpty()) {'''
new_begin_nav = '''    private fun beginBatchNavigation(runId: String?) {
        enqueueProviderSeeds()
        cloudOffload.probeFrontier { available ->
            runOnUiThread {
                if (available) {
                    status.text = "Cloud frontier 연결됨: 링크 계획·중복제거·재시도를 클라우드와 동기화합니다."
                }
            }
        }
        if (runId != null && batchPageActions.isEmpty()) {'''
main = replace_once(main, old_begin_nav, new_begin_nav, 'frontier probe')

# Complete claimed cloud task after successful snapshot.
old_mark_doc = '''                localStore.markDocument(runId, navKey, "completed")
                when {'''
new_mark_doc = '''                localStore.markDocument(runId, navKey, "completed")
                cloudFrontierTaskIds.remove(navKey)?.let { taskId ->
                    cloudOffload.completeFrontier(taskId, "completed", null)
                }
                when {'''
main = replace_once(main, old_mark_doc, new_mark_doc, 'frontier completion')

# Execute one safe read-navigation action before moving away from a Jinhak page.
old_after_discovery = '''            if (activeAction == null) {
                if (plan != null) enqueueCalculatedPageActions(snapshot, plan)
            } else {
                batchPageActionVisited.add(pageActionKey(activeAction))
                activeBatchPageAction = null
            }

            status.text = if (activeAction != null) {'''
new_after_discovery = '''            if (activeAction == null) {
                if (plan != null) enqueueCalculatedPageActions(snapshot, plan)
            } else {
                batchPageActionVisited.add(pageActionKey(activeAction))
                activeBatchPageAction = null
            }

            if (provider == ProviderId.JINHAK && activeAction == null && maybeExecuteJinhakAgentAction(snapshot)) {
                return@collectSnapshot
            }

            status.text = if (activeAction != null) {'''
main = replace_once(main, old_after_discovery, new_after_discovery, 'agent execute hook')

# Publish discovered URLs to cloud frontier in a single batched request per page.
old_enqueue_links = '''    private fun enqueueDiscoveredLinks(links: JSONArray) {
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
'''
new_enqueue_links = '''    private fun enqueueDiscoveredLinks(links: JSONArray) {
        val frontierBatch = JSONArray()
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = canonicalizeBatchUrl(obj.optString("url"))
            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            enqueueDiscoveredUrl(url)
            frontierBatch.put(url)
            historicalMirrorUrl(url)?.let { mirror ->
                enqueueDiscoveredUrl(mirror)
                frontierBatch.put(mirror)
            }
            if (batchQueue.size + batchVisited.size >= MAX_BATCH_PAGES * 2) break
        }
        if (frontierBatch.length() > 0) {
            cloudOffload.publishFrontier(
                provider = provider.wireName,
                urls = frontierBatch,
                sourceSafePath = runtimeSafePath(webView.url),
                publicFetchEligible = provider == ProviderId.ADIGA
            ) { accepted ->
                if (accepted > 0) cloudFrontierPublished += accepted
            }
        }
    }
'''
main = replace_once(main, old_enqueue_links, new_enqueue_links, 'frontier publish')

# When local URL queue drains, claim cloud frontier tasks before declaring completion.
old_queue_drain = '''        if (LOCAL_FIRST_BETA && (provider == ProviderId.ADIGA || provider == ProviderId.JINHAK)) verifyLocalCompletionOrFinish()
        else verifyCloudCompletionOrFinish()
    }
'''
new_queue_drain = '''        if (!cloudFrontierClaimInProgress && cloudFrontierClaimAttempts < MAX_CLOUD_FRONTIER_CLAIM_ATTEMPTS) {
            cloudFrontierClaimInProgress = true
            cloudFrontierClaimAttempts += 1
            cloudOffload.claimFrontier(provider.wireName, 40) { result ->
                runOnUiThread {
                    cloudFrontierClaimInProgress = false
                    if (!batchRunning || batchPausedForLogin) return@runOnUiThread
                    val tasks = result.getOrNull() ?: JSONArray()
                    var added = 0
                    for (i in 0 until tasks.length()) {
                        val item = tasks.optJSONObject(i) ?: continue
                        val url = canonicalizeBatchUrl(item.optString("url"))
                        val taskId = item.optString("taskId")
                        if (url.isBlank() || taskId.isBlank() || !isBatchNavigableProviderUrl(url)) continue
                        if (!batchVisited.contains(url) && batchQueued.add(url)) {
                            batchQueue.addLast(url)
                            cloudFrontierTaskIds[url] = taskId
                            added += 1
                        }
                    }
                    cloudFrontierClaimed += added
                    if (added > 0) {
                        cloudFrontierClaimAttempts = 0
                        status.text = "Cloud frontier에서 ${added}개 탐색 작업 인계: 로그인된 브라우저 에이전트가 계속 처리합니다."
                        handler.postDelayed({ loadNextBatchPage() }, 80L)
                    } else {
                        handler.postDelayed({ loadNextBatchPage() }, 80L)
                    }
                }
            }
            return
        }
        if (LOCAL_FIRST_BETA && (provider == ProviderId.ADIGA || provider == ProviderId.JINHAK)) verifyLocalCompletionOrFinish()
        else verifyCloudCompletionOrFinish()
    }
'''
main = replace_once(main, old_queue_drain, new_queue_drain, 'frontier claim')

# Add agent method before loadNextBatchPage.
agent_method = r'''
    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject): Boolean {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return false
        if (jinhakAgentActionInFlight || jinhakAgentActionsExecuted >= MAX_JINHAK_AGENT_ACTIONS) return false
        val route = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        val candidate = JinhakAgentNavigator.candidates(snapshot).firstOrNull { action ->
            !jinhakAgentActionSeen.contains(JinhakAgentNavigator.key(route, action))
        } ?: return false
        val actionKey = JinhakAgentNavigator.key(route, candidate)
        jinhakAgentActionSeen.add(actionKey)
        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
        currentBatchTarget = route.ifBlank { currentBatchTarget }
        status.text = "진학사 에이전트 직접 탐색 ${jinhakAgentActionsExecuted}/$MAX_JINHAK_AGENT_ACTIONS · ${candidate.label.take(48)}"
        recordRuntimeEvent("jinhak-agent-action", JSONObject()
            .put("safePath", runtimeSafePath(route))
            .put("label", candidate.label.take(80))
            .put("kind", candidate.kind))
        webView.evaluateJavascript(JinhakAgentNavigator.executionScript(candidate)) { encoded ->
            val result = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull() ?: JSONObject()
            jinhakAgentActionInFlight = false
            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
            if (result.optBoolean("ok", false)) {
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin || batchCollecting) return@postDelayed
                    val now = canonicalizeBatchUrl(webView.url.orEmpty())
                    if (now == route || sameBatchDocument(now, route)) scheduleBatchSnapshot()
                }, 1100L)
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 120L)
            }
        }
        return true
    }

'''
main = replace_once(main, '    private fun loadNextBatchPage() {\n', agent_method + '    private fun loadNextBatchPage() {\n', 'insert agent method')

# Batch summary exposes new architecture without secret material.
old_summary_tail = '''                .put("localAuditPagesScheduled", batchAuditPagesScheduled)
                .put("universityDiscoveryPagesScheduled", batchUniversityDiscoveryPagesScheduled))'''
new_summary_tail = '''                .put("localAuditPagesScheduled", batchAuditPagesScheduled)
                .put("universityDiscoveryPagesScheduled", batchUniversityDiscoveryPagesScheduled)
                .put("jinhakAgentActionsExecuted", jinhakAgentActionsExecuted)
                .put("cloudFrontierPublished", cloudFrontierPublished)
                .put("cloudFrontierClaimed", cloudFrontierClaimed)
                .put("sessionLease", sessionVault.summary(provider.wireName)?.toJson() ?: JSONObject.NULL))'''
main = replace_once(main, old_summary_tail, new_summary_tail, 'summary')
MAIN.write_text(main)

# ---------------------------------------------------------------------------
# Snapshot agent action discovery. No form values or credentials are captured.
# ---------------------------------------------------------------------------
snap = SNAPSHOT.read_text()
snap = replace_once(snap, '  var pageActions=[];\n', '  var pageActions=[];\n  var agentActions=[];\n', 'agent action array')
snap = replace_once(snap, '  var seenPageAction={};\n', '  var seenPageAction={};\n  var seenAgentAction={};\n', 'agent seen')
anchor = '''    if(!route){
      route=inferredUniversityDetailRoute(scriptText+' '+dataRaw+' '+raw);
      if(route) scriptCandidates++;
    }

    var resourceRaw=(raw && directUrlish) ? raw : (route||'');'''
insert = '''    if(!route){
      route=inferredUniversityDetailRoute(scriptText+' '+dataRaw+' '+raw);
      if(route) scriptCandidates++;
    }

    if(isJinhakHost && agentActions.length<160){
      var agentBlocked=/(원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰)/i;
      var agentAllowed=/(상세|보기|조회|검색|리포트|대학\\s*정보|전형\\s*정보|학과\\s*정보|합격\\s*예측|모의\\s*지원|수시\\s*저장소|정시\\s*저장소|추천\\s*대학|성적\\s*분석|다음|더보기|결과|탭)/i;
      var role=cleanText(a.getAttribute('role')||'');
      var dynamicControl=!route || role==='tab' || a.tagName==='BUTTON';
      if(dynamicControl && label && !agentBlocked.test(label+' '+meta2) && agentAllowed.test(label)){
        var ak=li+'|'+label+'|'+String(a.tagName||'')+'|'+role;
        if(!seenAgentAction[ak]){
          agentActions.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:role==='tab'?'tab-navigation':'read-navigation'});
          seenAgentAction[ak]=1;
        }
      }
    }

    var resourceRaw=(raw && directUrlish) ? raw : (route||'');'''
snap = replace_once(snap, anchor, insert, 'agent discovery insert')
snap = replace_once(snap, '    discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length,jinhakDeepPage:jinhakDeepPage},\n', '    discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length,agentActions:agentActions.length,jinhakDeepPage:jinhakDeepPage},\n', 'discovery count')
snap = replace_once(snap, '    pageActions:pageActions,\n    resourceLinks:resources\n', '    pageActions:pageActions,\n    agentActions:agentActions,\n    resourceLinks:resources\n', 'return agent actions')
SNAPSHOT.write_text(snap)

# ---------------------------------------------------------------------------
# Cloud client frontier API. Health probe is intentionally unauthenticated only for /health.
# ---------------------------------------------------------------------------
client = CLIENT.read_text()
client = replace_once(client, '    fun shutdown() {\n        io.shutdownNow()\n    }\n', r'''    fun getHealth(callback: (Result<JSONObject>) -> Unit) = io.execute {
        callback(runCatching { publicGet("/health") })
    }

    fun publishFrontier(
        provider: String,
        urls: JSONArray,
        sourceSafePath: String,
        publicFetchEligible: Boolean,
        callback: (Result<Int>) -> Unit
    ) = io.execute {
        callback(runCatching {
            val response = post("/v1/frontier/batch", JSONObject()
                .put("provider", provider)
                .put("urls", urls)
                .put("sourceSafePath", sourceSafePath)
                .put("publicFetchEligible", publicFetchEligible))
            response.optInt("accepted", 0)
        })
    }

    fun claimFrontier(provider: String, clientId: String, limit: Int, callback: (Result<JSONArray>) -> Unit) = io.execute {
        callback(runCatching {
            post("/v1/frontier/claim", JSONObject()
                .put("provider", provider)
                .put("clientId", clientId)
                .put("limit", limit.coerceIn(1, 50)))
                .optJSONArray("tasks") ?: JSONArray()
        })
    }

    fun completeFrontier(taskId: String, state: String, errorType: String?, callback: (Result<Unit>) -> Unit = {}) = io.execute {
        callback(runCatching {
            post("/v1/frontier/complete", JSONObject()
                .put("tasks", JSONArray().put(JSONObject()
                    .put("taskId", taskId)
                    .put("state", state)
                    .put("errorType", errorType ?: JSONObject.NULL))))
            Unit
        })
    }

    fun shutdown() {
        io.shutdownNow()
    }
''', 'cloud client methods')
client = replace_once(client, '    private fun get(path: String): JSONObject =\n        request("GET", path, null)\n', '    private fun get(path: String): JSONObject =\n        request("GET", path, null)\n\n    private fun publicGet(path: String): JSONObject = request("GET", path, null, requireAuth = false)\n', 'public health get')
client = replace_once(client, '    private fun request(method: String, path: String, body: String?): JSONObject {\n        val token = tokenProvider()?.takeIf { it.isNotBlank() }\n            ?: error("Cloud offload token is not configured")\n\n        val base = workerUrl.trimEnd(\'/\')\n', '''    private fun request(method: String, path: String, body: String?, requireAuth: Boolean = true): JSONObject {
        val token = if (requireAuth) tokenProvider()?.takeIf { it.isNotBlank() }
            ?: error("Cloud offload token is not configured") else null

        val base = workerUrl.trimEnd('/')
''', 'request auth flag')
client = replace_once(client, '            setRequestProperty("Authorization", "Bearer $token")\n            setRequestProperty("Accept", "application/json")\n', '            if (token != null) setRequestProperty("Authorization", "Bearer $token")\n            setRequestProperty("Accept", "application/json")\n', 'conditional auth header')
CLIENT.write_text(client)

# ---------------------------------------------------------------------------
# Coordinator capability-gated frontier support. Current 0.3.9 worker fails open.
# ---------------------------------------------------------------------------
coord = COORD.read_text()
coord = replace_once(coord, '    @Volatile private var reusedRun: Boolean = false\n', '    @Volatile private var reusedRun: Boolean = false\n    @Volatile private var frontierAvailable: Boolean? = null\n    @Volatile private var frontierProbeInFlight: Boolean = false\n    private val frontierClientId: String by lazy { prefs.getString(KEY_FRONTIER_CLIENT_ID, null) ?: java.util.UUID.randomUUID().toString().also { prefs.edit().putString(KEY_FRONTIER_CLIENT_ID, it).apply() } }\n', 'coordinator frontier fields')
coord = replace_once(coord, '    fun pendingPages(callback: (Result<JSONObject>) -> Unit) {\n', r'''    fun probeFrontier(callback: (Boolean) -> Unit = {}) {
        val cached = frontierAvailable
        if (cached != null) { callback(cached); return }
        synchronized(lock) {
            if (frontierProbeInFlight) { callback(false); return }
            frontierProbeInFlight = true
            ensureClientLocked()
        }
        val currentClient = synchronized(lock) { client }
        if (currentClient == null) {
            frontierProbeInFlight = false
            frontierAvailable = false
            callback(false)
            return
        }
        currentClient.getHealth { result ->
            val available = result.getOrNull()?.optJSONObject("capabilities")?.optBoolean("frontierBatch", false) == true
            frontierAvailable = available
            frontierProbeInFlight = false
            callback(available)
        }
    }

    fun publishFrontier(
        provider: String,
        urls: JSONArray,
        sourceSafePath: String,
        publicFetchEligible: Boolean,
        callback: (Int) -> Unit = {}
    ) {
        if (urls.length() == 0 || !isConfigured()) { callback(0); return }
        probeFrontier { available ->
            if (!available) { callback(0); return@probeFrontier }
            val currentClient = synchronized(lock) { ensureClientLocked(); client }
            if (currentClient == null) { callback(0); return@probeFrontier }
            currentClient.publishFrontier(provider, urls, sourceSafePath, publicFetchEligible) { result ->
                result.onFailure { lastError = it.message }
                callback(result.getOrDefault(0))
            }
        }
    }

    fun claimFrontier(provider: String, limit: Int, callback: (Result<JSONArray>) -> Unit) {
        if (!isConfigured()) { callback(Result.success(JSONArray())); return }
        probeFrontier { available ->
            if (!available) { callback(Result.success(JSONArray())); return@probeFrontier }
            val currentClient = synchronized(lock) { ensureClientLocked(); client }
            if (currentClient == null) { callback(Result.success(JSONArray())); return@probeFrontier }
            currentClient.claimFrontier(provider, frontierClientId, limit, callback)
        }
    }

    fun completeFrontier(taskId: String, state: String, errorType: String?) {
        if (taskId.isBlank() || frontierAvailable != true) return
        val currentClient = synchronized(lock) { ensureClientLocked(); client } ?: return
        currentClient.completeFrontier(taskId, state, errorType) { result ->
            result.onFailure { lastError = it.message }
        }
    }

    fun pendingPages(callback: (Result<JSONObject>) -> Unit) {
''', 'coordinator frontier methods')
coord = replace_once(coord, '        .put("lastError", lastError ?: JSONObject.NULL)\n', '        .put("lastError", lastError ?: JSONObject.NULL)\n        .put("frontierAvailable", frontierAvailable ?: JSONObject.NULL)\n', 'frontier status')
coord = replace_once(coord, '        private const val KEY_ACTIVE_PROVIDER = "active_provider"\n', '        private const val KEY_ACTIVE_PROVIDER = "active_provider"\n        private const val KEY_FRONTIER_CLIENT_ID = "frontier_client_id"\n', 'frontier client id key')
COORD.write_text(coord)

# ---------------------------------------------------------------------------
# Worker 0.4.0: batched frontier + D1 leases + scheduled public Adiga link discovery.
# No Jinhak cookie/session/auth material is accepted by these endpoints.
# ---------------------------------------------------------------------------
worker = WORKER.read_text()
worker = replace_once(worker, '          version: "0.3.9",\n          time: new Date().toISOString(),\n', '''          version: "0.4.0",
          capabilities: {
            frontierBatch: true,
            frontierClaim: true,
            publicAdigaDiscovery: true,
            acceptsBrowserSessionMaterial: false,
          },
          time: new Date().toISOString(),
''', 'worker health')
frontier_routes = r'''
      if (request.method === "POST" && url.pathname === "/v1/frontier/batch") {
        const body = await readJson(request, 512_000);
        return frontierBatch(env, body);
      }

      if (request.method === "POST" && url.pathname === "/v1/frontier/claim") {
        const body = await readJson(request, 64_000);
        return frontierClaim(env, body);
      }

      if (request.method === "POST" && url.pathname === "/v1/frontier/complete") {
        const body = await readJson(request, 128_000);
        return frontierComplete(env, body);
      }

'''
worker = replace_once(worker, '      return json({ error: "not_found" }, 404);\n', frontier_routes + '      return json({ error: "not_found" }, 404);\n', 'worker routes')
worker = replace_once(worker, '''  async queue(batch, env, ctx) {
    for (const message of batch.messages) {
      try {
        await processChunk(env, message.body);
      } catch (error) {
        console.error(JSON.stringify({
          level: "error",
          event: "queue_chunk_failed",
          messageId: message.id,
          message: String(error?.message || error),
          stack: error?.stack || null,
        }));
        throw error;
      }
    }
  },
};''', '''  async queue(batch, env, ctx) {
    for (const message of batch.messages) {
      try {
        await processChunk(env, message.body);
      } catch (error) {
        console.error(JSON.stringify({
          level: "error",
          event: "queue_chunk_failed",
          messageId: message.id,
          message: String(error?.message || error),
          stack: error?.stack || null,
        }));
        throw error;
      }
    }
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(processPublicFrontier(env, 12));
  },
};''', 'worker scheduled handler')

frontier_helpers = r'''

function allowedProviderHost(provider, host) {
  host = String(host || "").toLowerCase();
  if (provider === "adiga") return host === "adiga.kr" || host.endsWith(".adiga.kr");
  if (provider === "jinhak") return host === "jinhak.com" || host.endsWith(".jinhak.com");
  return false;
}

function sanitizeFrontierUrl(provider, raw) {
  try {
    const url = new URL(String(raw || ""));
    if (url.protocol !== "https:" || !allowedProviderHost(provider, url.hostname)) return null;
    const forbidden = /token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|userid|ipmac/i;
    const clean = new URL(url.origin + url.pathname);
    for (const [key, value] of url.searchParams.entries()) {
      if (!forbidden.test(key) && String(value).length <= 400) clean.searchParams.append(key, value);
    }
    clean.hash = "";
    return clean.toString();
  } catch (_) {
    return null;
  }
}

async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(String(text || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function frontierBatch(env, body) {
  const provider = String(body.provider || "").toLowerCase();
  if (!['adiga', 'jinhak'].includes(provider)) return json({ error: "invalid_provider" }, 400);
  const urls = Array.isArray(body.urls) ? body.urls.slice(0, 200) : [];
  const sourceSafePath = String(body.sourceSafePath || "").slice(0, 300);
  const publicFetchEligible = provider === 'adiga' && body.publicFetchEligible === true;
  const now = new Date().toISOString();
  let accepted = 0;
  let rejected = 0;
  for (const raw of urls) {
    const clean = sanitizeFrontierUrl(provider, raw);
    if (!clean) { rejected += 1; continue; }
    const hash = await sha256Hex(clean);
    const taskId = `${provider}-${hash}`;
    const result = await env.DB.prepare(`
      INSERT INTO crawl_frontier (
        task_id, provider, url, url_hash, source_safe_path, state, priority,
        public_fetch_eligible, attempt_count, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, 'pending', 100, ?, 0, ?, ?)
      ON CONFLICT(provider, url_hash) DO UPDATE SET
        source_safe_path = CASE WHEN excluded.source_safe_path != '' THEN excluded.source_safe_path ELSE crawl_frontier.source_safe_path END,
        public_fetch_eligible = MAX(crawl_frontier.public_fetch_eligible, excluded.public_fetch_eligible),
        updated_at = excluded.updated_at
    `).bind(taskId, provider, clean, hash, sourceSafePath, publicFetchEligible ? 1 : 0, now, now).run();
    accepted += 1;
  }
  return json({ accepted, rejected, provider });
}

async function releaseExpiredFrontierLeases(env) {
  const now = new Date().toISOString();
  await env.DB.prepare(`
    UPDATE crawl_frontier
    SET state='pending', lease_owner=NULL, lease_expires_at=NULL, updated_at=?
    WHERE state='claimed' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
  `).bind(now, now).run();
}

async function frontierClaim(env, body) {
  const provider = String(body.provider || "").toLowerCase();
  if (!['adiga', 'jinhak'].includes(provider)) return json({ error: "invalid_provider" }, 400);
  const clientId = String(body.clientId || "").slice(0, 100);
  if (!clientId) return json({ error: "clientId_required" }, 400);
  const limit = boundedInt(body.limit || 20, 1, 50) || 20;
  await releaseExpiredFrontierLeases(env);
  const rows = await env.DB.prepare(`
    SELECT task_id, url, attempt_count
    FROM crawl_frontier
    WHERE provider=? AND state='pending' AND attempt_count < 4
    ORDER BY priority ASC, updated_at ASC
    LIMIT ?
  `).bind(provider, limit).all();
  const now = new Date();
  const expires = new Date(now.getTime() + 5 * 60 * 1000).toISOString();
  const tasks = [];
  for (const row of rows.results || []) {
    const updated = await env.DB.prepare(`
      UPDATE crawl_frontier
      SET state='claimed', lease_owner=?, lease_expires_at=?, attempt_count=attempt_count+1, updated_at=?
      WHERE task_id=? AND state='pending'
    `).bind(clientId, expires, now.toISOString(), row.task_id).run();
    if (Number(updated?.meta?.changes || 0) > 0) {
      tasks.push({ taskId: row.task_id, url: row.url, attempt: Number(row.attempt_count || 0) + 1 });
    }
  }
  return json({ provider, tasks, leaseSeconds: 300 });
}

async function frontierComplete(env, body) {
  const tasks = Array.isArray(body.tasks) ? body.tasks.slice(0, 100) : [];
  const now = new Date().toISOString();
  let updated = 0;
  for (const item of tasks) {
    const taskId = String(item?.taskId || "");
    const requestedState = String(item?.state || "completed");
    const state = ['completed', 'error', 'pending'].includes(requestedState) ? requestedState : 'error';
    if (!taskId) continue;
    const result = await env.DB.prepare(`
      UPDATE crawl_frontier
      SET state=?, error_type=?, lease_owner=NULL, lease_expires_at=NULL, updated_at=?
      WHERE task_id=?
    `).bind(state, nullableString(item?.errorType), now, taskId).run();
    updated += Number(result?.meta?.changes || 0);
  }
  return json({ updated });
}

function extractPublicLinks(provider, baseUrl, html) {
  const out = [];
  const seen = new Set();
  const regex = /<a\b[^>]*\bhref\s*=\s*["']([^"']+)["']/ig;
  let match;
  while ((match = regex.exec(html)) && out.length < 180) {
    let absolute;
    try { absolute = new URL(match[1], baseUrl).toString(); } catch (_) { continue; }
    const clean = sanitizeFrontierUrl(provider, absolute);
    if (!clean || seen.has(clean)) continue;
    seen.add(clean);
    out.push(clean);
  }
  return out;
}

function extractTitle(html) {
  const match = String(html || '').match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return match ? match[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 300) : '';
}

async function processPublicFrontier(env, maxTasks) {
  await releaseExpiredFrontierLeases(env);
  const rows = await env.DB.prepare(`
    SELECT task_id, provider, url, url_hash, attempt_count
    FROM crawl_frontier
    WHERE provider='adiga' AND public_fetch_eligible=1 AND state='pending' AND attempt_count < 4
    ORDER BY priority ASC, updated_at ASC
    LIMIT ?
  `).bind(maxTasks).all();
  for (const row of rows.results || []) {
    const now = new Date().toISOString();
    await env.DB.prepare(`UPDATE crawl_frontier SET state='claimed', lease_owner='cloud-public', lease_expires_at=?, attempt_count=attempt_count+1, updated_at=? WHERE task_id=? AND state='pending'`)
      .bind(new Date(Date.now() + 60000).toISOString(), now, row.task_id).run();
    try {
      const response = await fetch(row.url, {
        method: 'GET',
        redirect: 'follow',
        headers: { 'accept': 'text/html,application/xhtml+xml', 'user-agent': 'AdmissionCollectorCloud/0.4.0' },
      });
      const contentType = String(response.headers.get('content-type') || '').slice(0, 120);
      const contentLength = Number(response.headers.get('content-length') || 0);
      let html = '';
      if (response.ok && /text\/html|application\/xhtml\+xml/i.test(contentType) && (!contentLength || contentLength <= 1200000)) {
        html = (await response.text()).slice(0, 1200000);
      }
      const links = html ? extractPublicLinks('adiga', row.url, html) : [];
      const bodyHash = html ? await sha256Hex(html) : null;
      await env.DB.prepare(`
        INSERT INTO public_page_snapshots(provider,url_hash,url,status_code,content_type,title,body_hash,discovered_links_json,observed_at)
        VALUES('adiga',?,?,?,?,?,?,?,?)
        ON CONFLICT(provider,url_hash) DO UPDATE SET status_code=excluded.status_code,content_type=excluded.content_type,title=excluded.title,body_hash=excluded.body_hash,discovered_links_json=excluded.discovered_links_json,observed_at=excluded.observed_at
      `).bind(row.url_hash, row.url, response.status, contentType, extractTitle(html), bodyHash, JSON.stringify(links), now).run();
      if (links.length) await frontierBatch(env, { provider: 'adiga', urls: links, sourceSafePath: new URL(row.url).hostname + new URL(row.url).pathname, publicFetchEligible: true });
      await env.DB.prepare(`UPDATE crawl_frontier SET state='completed', error_type=NULL, lease_owner=NULL, lease_expires_at=NULL, updated_at=? WHERE task_id=?`)
        .bind(now, row.task_id).run();
    } catch (error) {
      await env.DB.prepare(`UPDATE crawl_frontier SET state='pending', error_type=?, lease_owner=NULL, lease_expires_at=NULL, updated_at=? WHERE task_id=?`)
        .bind(String(error?.name || 'public-fetch-error').slice(0, 80), now, row.task_id).run();
    }
  }
}
'''
worker = replace_once(worker, '\nfunction scopeProviderFingerprint(provider, year, fingerprint) {\n', frontier_helpers + '\nfunction scopeProviderFingerprint(provider, year, fingerprint) {\n', 'worker frontier helpers')
WORKER.write_text(worker)

# D1 migration.
MIGRATION.write_text(r'''CREATE TABLE IF NOT EXISTS crawl_frontier (
  task_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  url TEXT NOT NULL,
  url_hash TEXT NOT NULL,
  source_safe_path TEXT,
  state TEXT NOT NULL DEFAULT 'pending',
  priority INTEGER NOT NULL DEFAULT 100,
  public_fetch_eligible INTEGER NOT NULL DEFAULT 0,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  lease_owner TEXT,
  lease_expires_at TEXT,
  error_type TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(provider, url_hash)
);
CREATE INDEX IF NOT EXISTS idx_crawl_frontier_claim ON crawl_frontier(provider,state,priority,updated_at);
CREATE INDEX IF NOT EXISTS idx_crawl_frontier_public ON crawl_frontier(provider,public_fetch_eligible,state,updated_at);

CREATE TABLE IF NOT EXISTS public_page_snapshots (
  provider TEXT NOT NULL,
  url_hash TEXT NOT NULL,
  url TEXT NOT NULL,
  status_code INTEGER,
  content_type TEXT,
  title TEXT,
  body_hash TEXT,
  discovered_links_json TEXT NOT NULL DEFAULT '[]',
  observed_at TEXT NOT NULL,
  PRIMARY KEY(provider, url_hash)
);
''')

# Scheduled Cloudflare public discovery every five minutes. Exact provider quotas are
# intentionally not encoded as assumptions; each tick has its own conservative cap.
wrangler = WRANGLER.read_text()
wrangler = replace_once(wrangler, '  "queues": {\n', '  "triggers": {\n    "crons": ["*/5 * * * *"]\n  },\n  "queues": {\n', 'wrangler cron')
WRANGLER.write_text(wrangler)

# Version/label.
gradle = GRADLE.read_text().replace('versionCode = 10710', 'versionCode = 10800').replace('versionName = "0.7.1"', 'versionName = "0.8.0"')
GRADLE.write_text(gradle)
manifest = MANIFEST.read_text().replace('Admission Collector v0.7.1 Autonomous Analysis Ready', 'Admission Collector v0.8.0 Session Agent Cloud').replace('Admission Collector v0.7.0 Observation Foundation', 'Admission Collector v0.8.0 Session Agent Cloud')
MANIFEST.write_text(manifest)

print('v0.8.0 patch applied: secure-session-vault, direct-navigation-agent, cloud-frontier, public-cloud-discovery')
