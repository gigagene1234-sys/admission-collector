package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * v0.17.4 strict high3-only browser sandbox.
 *
 * Main-frame policy is fail-closed. Inside the Admission Hub Jinhak WebView the only Jinhak
 * destinations that may become the visible top-level page are:
 *   1) HTTPS www.jinhak.com/jh/high3[/...]
 *   2) the exact HTTPS member.jinhak.com .../MemberLogIn.aspx surface that Jinhak itself may
 *      redirect to while the user owns the login session
 *   3) about:blank used as a neutral renderer placeholder
 *
 * Shared root/product routers, generic login routers, high1/high2/high12, other Jinhak product
 * routes and external main-frame destinations are blocked. Lower-grade markers are also treated
 * as forbidden when nested in encoded query/fragment/ReturnURL material by JinhakGradeRouteFence.
 */
object JinhakStrictHigh3Sandbox {
    const val SCHEMA_VERSION = 1

    enum class MainFrameDecision {
        ALLOW_HIGH3,
        ALLOW_MEMBER_LOGIN,
        ALLOW_BLANK,
        BLOCK_LOWER_GRADE,
        BLOCK_SHARED_ROOT,
        BLOCK_GENERIC_LOGIN,
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
            return if (JinhakHigh3AuthRoute.isMemberLoginSurface(url)) {
                MainFrameDecision.ALLOW_MEMBER_LOGIN
            } else {
                MainFrameDecision.BLOCK_OTHER_JINHAK
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

    fun sanitizedHigh3OrNull(url: String?): String? {
        val candidate = url.orEmpty().trim()
        return candidate.takeIf { decision(it) == MainFrameDecision.ALLOW_HIGH3 }
    }

    fun reason(decision: MainFrameDecision): String = when (decision) {
        MainFrameDecision.ALLOW_HIGH3 -> "allow-high3"
        MainFrameDecision.ALLOW_MEMBER_LOGIN -> "allow-member-login"
        MainFrameDecision.ALLOW_BLANK -> "allow-blank"
        MainFrameDecision.BLOCK_LOWER_GRADE -> "block-lower-grade"
        MainFrameDecision.BLOCK_SHARED_ROOT -> "block-shared-root"
        MainFrameDecision.BLOCK_GENERIC_LOGIN -> "block-generic-login"
        MainFrameDecision.BLOCK_OTHER_JINHAK -> "block-other-jinhak"
        MainFrameDecision.BLOCK_EXTERNAL -> "block-external"
        MainFrameDecision.BLOCK_INVALID -> "block-invalid"
    }
}
