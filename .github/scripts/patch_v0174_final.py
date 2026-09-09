from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
ADAPTER = ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt"
GRADE = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt"
AUTH = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakHigh3AuthRoute.kt"

# -----------------------------------------------------------------------------
# 1) Fix the Kotlin adapter regex caught by CI. Keep it a raw Kotlin string so
#    no future escaping edit can turn \. into an illegal Kotlin escape.
# -----------------------------------------------------------------------------
adapter = ADAPTER.read_text()
old_regex = 'Regex("\\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|map|woff2?|ttf|eot|zip|hwp|hwpx|pdf)$", RegexOption.IGNORE_CASE)'
new_regex = 'Regex("""\\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|map|woff2?|ttf|eot|zip|hwp|hwpx|pdf)$""", RegexOption.IGNORE_CASE)'
if old_regex in adapter:
    adapter = adapter.replace(old_regex, new_regex)
elif new_regex not in adapter:
    raise SystemExit("JinhakAdapter asset regex anchor not found")
ADAPTER.write_text(adapter)

# -----------------------------------------------------------------------------
# 2) Deep-encoding lower-grade fence. Check the whole URL repeatedly, normalize
#    backslashes, and decode until stable (bounded to prevent pathological input).
# -----------------------------------------------------------------------------
GRADE.write_text(r'''package com.admissionhub.collector.jinhak

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * v0.17.4 final lower-grade transport fence.
 *
 * high1/high2/high12 are forbidden collector destinations and forbidden request
 * material even when buried inside repeatedly encoded query/fragment/ReturnURL
 * values. The implementation is deliberately fail-closed for those markers and
 * never relies on DOM/UI hiding.
 */
object JinhakGradeRouteFence {
    const val SCHEMA_VERSION = 5
    private const val MAX_DECODE_ROUNDS = 12
    private const val MAX_SCAN_CHARS = 65_536

    private val lowerGradeRouteMarkers = listOf(
        "/jh/high1/",
        "/jh/high2/",
        "/jh/high12/"
    )

    private val lowerGradeTerminalMarkers = listOf(
        "/jh/high1",
        "/jh/high2",
        "/jh/high12"
    )

    fun isBlockedLowerGrade(url: String): Boolean {
        if (url.isBlank()) return false
        var candidate = normalize(url.take(MAX_SCAN_CHARS))
        repeat(MAX_DECODE_ROUNDS + 1) {
            if (containsLowerGradeRoute(candidate)) return true
            val decoded = runCatching {
                URLDecoder.decode(candidate, StandardCharsets.UTF_8.name())
            }.getOrDefault(candidate)
            val normalized = normalize(decoded.take(MAX_SCAN_CHARS))
            if (normalized == candidate) return false
            candidate = normalized
        }
        return containsLowerGradeRoute(candidate)
    }

    fun isHigh3(url: String): Boolean {
        if (url.isBlank() || isBlockedLowerGrade(url)) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        val path = normalize(uri.path.orEmpty())
        return path == "/jh/high3" || path.startsWith("/jh/high3/")
    }

    fun protectedHigh3Core(): String = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()

    private fun normalize(value: String): String = value.lowercase().replace('\\', '/')

    private fun containsLowerGradeRoute(value: String): Boolean {
        if (value.isBlank()) return false
        val normalized = normalize(value)
        return lowerGradeRouteMarkers.any(normalized::contains) ||
            lowerGradeTerminalMarkers.any { marker ->
                normalized == marker ||
                    normalized.endsWith(marker) ||
                    normalized.contains("$marker?") ||
                    normalized.contains("$marker#") ||
                    normalized.contains("$marker&") ||
                    normalized.contains("$marker=") ||
                    normalized.contains("$marker%")
            }
    }
}
''')

# -----------------------------------------------------------------------------
# 3) High3/member-login parser with the same bounded repeated decoding model.
#    The Collector never constructs a login URL; only a site-returned exact member
#    login with a high3 ReturnURL is recognized as canonical by strict sandbox.
# -----------------------------------------------------------------------------
AUTH.write_text(r'''package com.admissionhub.collector.jinhak

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

object JinhakHigh3AuthRoute {
    const val SCHEMA_VERSION = 4
    private const val WWW_HOST = "www.jinhak.com"
    private const val MEMBER_HOST = "member.jinhak.com"
    private const val MAX_DECODE_ROUNDS = 12
    private const val MAX_VALUE_CHARS = 65_536

    enum class MainFrameDecision {
        ALLOW_HIGH3,
        ALLOW_CANONICAL_AUTH,
        REWRITE_GENERIC_LOGIN,
        BLOCK_LOWER_GRADE,
        ALLOW_OTHER_JINHAK
    }

    @Deprecated("v0.17.x uses user/server-owned authentication and never constructs login URLs")
    fun canonicalLoginUrl(requestedReturnTarget: String?): String = sanitizeReturnTarget(requestedReturnTarget)

    fun sanitizeReturnTarget(requested: String?): String {
        val candidate = requested.orEmpty().trim()
        if (isAllowedHigh3Target(candidate)) return candidate
        return JinhakGradeRouteFence.protectedHigh3Core()
    }

    fun isAllowedHigh3Target(url: String): Boolean {
        if (url.isBlank() || JinhakGradeRouteFence.isBlockedLowerGrade(url)) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        val scheme = uri.scheme?.lowercase() ?: return false
        val host = uri.host?.lowercase() ?: return false
        if (scheme != "https") return false
        if (host != WWW_HOST && host != "jinhak.com") return false
        val path = uri.path.orEmpty().lowercase().replace('\\', '/')
        return path == "/jh/high3" || path.startsWith("/jh/high3/")
    }

    fun isGenericProductLogin(url: String): Boolean {
        if (url.isBlank()) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        val host = uri.host?.lowercase().orEmpty()
        val path = uri.path.orEmpty().lowercase().replace('\\', '/')
        return (host == WWW_HOST || host == "jinhak.com") && path == "/jh/member/login"
    }

    fun isMemberLoginSurface(url: String): Boolean {
        if (url.isBlank() || JinhakGradeRouteFence.isBlockedLowerGrade(url)) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        return uri.scheme?.lowercase() == "https" &&
            uri.host?.lowercase() == MEMBER_HOST &&
            uri.path.orEmpty().lowercase().replace('\\', '/').endsWith("/memberlogin.aspx")
    }

    fun isCanonicalMemberLogin(url: String): Boolean {
        if (!isMemberLoginSurface(url)) return false
        val returnTarget = returnUrl(url) ?: return false
        return isAllowedHigh3Target(returnTarget)
    }

    fun returnUrl(url: String): String? {
        val uri = runCatching { URI(url) }.getOrNull() ?: return null
        val raw = uri.rawQuery.orEmpty()
        if (raw.isBlank()) return null
        for (pair in raw.split('&')) {
            if (pair.isBlank()) continue
            val idx = pair.indexOf('=')
            val keyRaw = if (idx >= 0) pair.substring(0, idx) else pair
            val valueRaw = if (idx >= 0) pair.substring(idx + 1) else ""
            val key = decodeUntilStable(keyRaw)
            if (!key.equals("ReturnURL", ignoreCase = true)) continue
            return decodeUntilStable(valueRaw).take(MAX_VALUE_CHARS)
        }
        return null
    }

    fun decision(url: String): MainFrameDecision {
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) return MainFrameDecision.BLOCK_LOWER_GRADE
        if (isAllowedHigh3Target(url)) return MainFrameDecision.ALLOW_HIGH3
        if (isCanonicalMemberLogin(url)) return MainFrameDecision.ALLOW_CANONICAL_AUTH
        return MainFrameDecision.ALLOW_OTHER_JINHAK
    }

    private fun decodeUntilStable(value: String): String {
        var current = value.take(MAX_VALUE_CHARS)
        repeat(MAX_DECODE_ROUNDS) {
            val next = runCatching {
                URLDecoder.decode(current, StandardCharsets.UTF_8.name())
            }.getOrDefault(current).take(MAX_VALUE_CHARS)
            if (next == current) return current
            current = next
        }
        return current
    }
}
''')

# -----------------------------------------------------------------------------
# 4) MainActivity: centralize every foreground app-originated WebView load. This
#    is a structural invariant, not a list of known call sites. Natural WebView
#    redirects still pass through WebViewClient transport/page fences.
# -----------------------------------------------------------------------------
text = MAIN.read_text()

# Centralize all current foreground app loads first. The helper itself is inserted
# afterwards, so its raw WebView loads remain the only ordinary raw primitive.
text = text.replace("webView.loadUrl(", "loadMainUrl(")

helper_marker = "    private fun loadJinhakV0174High3Only(target: String?, reason: String): Boolean {"
if "private fun loadMainUrl(target: String" not in text:
    if helper_marker not in text:
        raise SystemExit("strict high3 loader marker missing")
    helper = r'''    private fun loadMainUrl(target: String, source: String = "app-load"): Boolean {
        if (provider != ProviderId.JINHAK) {
            webView.loadUrl(target)
            return true
        }
        val decision = JinhakStrictHigh3Sandbox.decision(target)
        return when (decision) {
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> {
                noteJinhakV0174Decision("central-$source", target, decision)
                webView.loadUrl(target)
                true
            }
            JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK -> {
                webView.loadUrl("about:blank")
                true
            }
            else -> {
                jinhakV0174AppNavigationBlocks += 1
                blockJinhakV0174MainFrame("central-$source", target, decision)
                false
            }
        }
    }

    private fun loadJinhakV0174SiteMemberLogin(target: String, source: String): Boolean {
        if (provider != ProviderId.JINHAK) return false
        val decision = JinhakStrictHigh3Sandbox.decision(target)
        if (decision != JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN) {
            jinhakV0174AppNavigationBlocks += 1
            blockJinhakV0174MainFrame("site-member-$source", target, decision)
            return false
        }
        noteJinhakV0174Decision("site-member-$source", target, decision)
        // This URL comes from a site popup/navigation event and has already passed the
        // exact member host/path + high3 ReturnURL policy. The app never constructs it.
        webView.loadUrl(target)
        return true
    }

'''
    text = text.replace(helper_marker, helper + helper_marker, 1)

# Popup member-login handoff must use the only dedicated, strict site-event exception.
text = text.replace(
    "JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> loadMainUrl(target)",
    'JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> loadJinhakV0174SiteMemberLogin(target, "popup-handoff")'
)

# Android physical back must obey the same strict history gate as the visible back button.
old_back = '''    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }
'''
new_back = '''    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (provider == ProviderId.JINHAK) {
            if (webView.canGoBack()) safeJinhakV0174Back() else super.onBackPressed()
        } else {
            if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
        }
    }
'''
if old_back in text:
    text = text.replace(old_back, new_back, 1)
elif new_back not in text:
    raise SystemExit("physical back anchor missing")

# Browser-history/SPA URL mutation fence. pushState/replaceState may not create a
# normal network navigation; doUpdateVisitedHistory therefore independently checks it.
page_started_marker = "            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {"
if "override fun doUpdateVisitedHistory(view: WebView, url: String, isReload: Boolean)" not in text:
    if page_started_marker not in text:
        raise SystemExit("onPageStarted marker missing for SPA fence")
    history_override = r'''            override fun doUpdateVisitedHistory(view: WebView, url: String, isReload: Boolean) {
                super.doUpdateVisitedHistory(view, url, isReload)
                if (provider != ProviderId.JINHAK) return
                val decision = JinhakStrictHigh3Sandbox.decision(url)
                val allowed = decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 ||
                    decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN ||
                    decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK
                if (allowed) return
                jinhakV0174HistoryBlocks += 1
                runCatching { view.stopLoading() }
                blockJinhakV0174MainFrame("spa-history", url, decision)
                handler.post {
                    if (::webView.isInitialized && webView === view) loadMainUrl("about:blank", "spa-history-neutralize")
                }
            }

'''
    text = text.replace(page_started_marker, history_override + page_started_marker, 1)

# Renderer state can never preserve an unsafe target even if it was saved before v0.17.4.
text = text.replace(
    "currentBatchTarget = currentBatchTarget?.takeIf { it.isNotBlank() } ?: resumeUrl",
    '''currentBatchTarget = if (provider == ProviderId.JINHAK) {
                            JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget) ?: resumeUrl
                        } else {
                            currentBatchTarget?.takeIf { it.isNotBlank() } ?: resumeUrl
                        }'''
)
text = text.replace(
    "val missionOrigin = jinhakMissionOriginRoute.takeIf { it.isNotBlank() }\n                            val safeResume = missionOrigin\n                                ?: JinhakSiteTopology.protectedCoreProbeUrl().takeIf { it.isNotBlank() }\n                                ?: resumeUrl",
    '''val missionOrigin = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(jinhakMissionOriginRoute)
                            val safeResume = missionOrigin
                                ?: JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(JinhakSiteTopology.protectedCoreProbeUrl())
                                ?: resumeUrl'''
)

MAIN.write_text(text)
print("v0.17.4 final patch applied: central foreground navigation, physical-back + SPA fence, deep lower-grade decoding, compile fix")
