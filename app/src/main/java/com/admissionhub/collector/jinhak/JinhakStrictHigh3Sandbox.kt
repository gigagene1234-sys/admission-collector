package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * Strict high3-only browser sandbox.
 *
 * Main-frame policy remains fail-closed. v0.17.5 additionally separates route rejection from
 * authentication state: rejecting a navigation is not evidence that the user was logged out.
 * A narrow same-document SPA alias may be observed without being promoted to an allowed
 * collector/main-frame destination.
 */
object JinhakStrictHigh3Sandbox {
    const val SCHEMA_VERSION = 3

    enum class MainFrameDecision {
        ALLOW_HIGH3,
        ALLOW_MEMBER_LOGIN,
        ALLOW_BLANK,
        BLOCK_LOWER_GRADE,
        BLOCK_SHARED_ROOT,
        BLOCK_GENERIC_LOGIN,
        BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN,
        BLOCK_OTHER_JINHAK,
        BLOCK_EXTERNAL,
        BLOCK_INVALID
    }

    fun strictEntryUrl(): String = JinhakSiteTopology.userSessionBootstrapUrl()

    fun decision(url: String): MainFrameDecision {
        if (url.isBlank()) return MainFrameDecision.BLOCK_INVALID
        if (url == "about:blank") return MainFrameDecision.ALLOW_BLANK
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) return MainFrameDecision.BLOCK_LOWER_GRADE

        val uri = runCatching { URI(url) }.getOrNull() ?: return MainFrameDecision.BLOCK_INVALID
        val scheme = uri.scheme?.lowercase().orEmpty()
        val host = uri.host?.lowercase().orEmpty()
        val path = uri.path.orEmpty().lowercase()

        if (scheme != "https") return MainFrameDecision.BLOCK_EXTERNAL

        if (host == "member.jinhak.com") {
            if (!JinhakHigh3AuthRoute.isMemberLoginSurface(url)) return MainFrameDecision.BLOCK_OTHER_JINHAK
            val returnTarget = JinhakHigh3AuthRoute.returnUrl(url)
            return if (!returnTarget.isNullOrBlank() && JinhakHigh3AuthRoute.isAllowedHigh3Target(returnTarget)) {
                MainFrameDecision.ALLOW_MEMBER_LOGIN
            } else {
                MainFrameDecision.BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN
            }
        }

        if (host != "www.jinhak.com" && host != "jinhak.com") {
            return MainFrameDecision.BLOCK_EXTERNAL
        }

        if (JinhakHigh3AuthRoute.isAllowedHigh3Target(url)) return MainFrameDecision.ALLOW_HIGH3
        if (JinhakHigh3AuthRoute.isGenericProductLogin(url)) return MainFrameDecision.BLOCK_GENERIC_LOGIN
        if (path.isBlank() || path == "/") return MainFrameDecision.BLOCK_SHARED_ROOT
        return MainFrameDecision.BLOCK_OTHER_JINHAK
    }

    fun allowsVisibleMainFrame(url: String): Boolean = when (decision(url)) {
        MainFrameDecision.ALLOW_HIGH3,
        MainFrameDecision.ALLOW_MEMBER_LOGIN,
        MainFrameDecision.ALLOW_BLANK -> true
        else -> false
    }

    fun allowsCollectorNavigation(url: String): Boolean = decision(url) == MainFrameDecision.ALLOW_HIGH3

    fun allowsUserLoginSurface(url: String): Boolean = decision(url) == MainFrameDecision.ALLOW_MEMBER_LOGIN

    fun shouldBlockAnyRequest(url: String): Boolean = JinhakGradeRouteFence.isBlockedLowerGrade(url)

    /**
     * Jinhak can rewrite only the browser history to /jh/search while the already loaded high3
     * document stays on screen. This is not an allowed network/main-frame destination; it is only
     * a benign same-document history alias. The caller must already hold an explicitly confirmed
     * high3 user session before using this exception.
     */
    fun isBenignSameDocumentHistoryAlias(url: String): Boolean {
        if (url.isBlank() || JinhakGradeRouteFence.isBlockedLowerGrade(url)) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        val scheme = uri.scheme?.lowercase().orEmpty()
        val host = uri.host?.lowercase().orEmpty()
        val path = uri.path.orEmpty().lowercase().replace('\\', '/').trimEnd('/')
        return scheme == "https" &&
            (host == "www.jinhak.com" || host == "jinhak.com") &&
            path == "/jh/search"
    }

    fun sanitizedHigh3OrNull(url: String?): String? {
        val candidate = url.orEmpty().trim()
        return candidate.takeIf { decision(it) == MainFrameDecision.ALLOW_HIGH3 }
    }

    fun reason(decision: MainFrameDecision): String = when (decision) {
        MainFrameDecision.ALLOW_HIGH3 -> "allow-high3"
        MainFrameDecision.ALLOW_MEMBER_LOGIN -> "allow-member-login-high3-return"
        MainFrameDecision.ALLOW_BLANK -> "allow-blank"
        MainFrameDecision.BLOCK_LOWER_GRADE -> "block-lower-grade"
        MainFrameDecision.BLOCK_SHARED_ROOT -> "block-shared-root"
        MainFrameDecision.BLOCK_GENERIC_LOGIN -> "block-generic-login"
        MainFrameDecision.BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN -> "block-member-login-without-high3-return"
        MainFrameDecision.BLOCK_OTHER_JINHAK -> "block-other-jinhak"
        MainFrameDecision.BLOCK_EXTERNAL -> "block-external"
        MainFrameDecision.BLOCK_INVALID -> "block-invalid"
    }
}
