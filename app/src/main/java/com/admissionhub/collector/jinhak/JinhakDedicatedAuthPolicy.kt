package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * v0.18.0 authentication-surface policy.
 *
 * Authentication and collection are deliberately separate contexts:
 * - the collector WebView remains high3-only;
 * - this policy is used only by the dedicated auth WebView;
 * - high1/high2/high12 are rejected in both contexts.
 */
object JinhakDedicatedAuthPolicy {
    const val SCHEMA_VERSION = 1
    const val LOGIN_URL = "https://www.jinhak.com/jh/member/login"

    enum class Route {
        LOGIN_FORM,
        MEMBER_LOGIN,
        HIGH3_SUCCESS,
        JINHAK_SUPPORT,
        BLANK,
        BLOCK_LOWER_GRADE,
        BLOCK_EXTERNAL,
        BLOCK_INVALID
    }

    fun classify(rawUrl: String): Route {
        val url = rawUrl.trim()
        if (url == "about:blank") return Route.BLANK
        if (url.isBlank()) return Route.BLOCK_INVALID
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) return Route.BLOCK_LOWER_GRADE
        if (JinhakHigh3AuthRoute.isAllowedHigh3Target(url)) return Route.HIGH3_SUCCESS
        if (JinhakHigh3AuthRoute.isGenericProductLogin(url)) return Route.LOGIN_FORM
        if (JinhakHigh3AuthRoute.isMemberLoginSurface(url)) return Route.MEMBER_LOGIN

        val uri = runCatching { URI(url) }.getOrNull() ?: return Route.BLOCK_INVALID
        if (uri.scheme?.lowercase() != "https") return Route.BLOCK_EXTERNAL
        val host = uri.host?.lowercase().orEmpty()
        val path = uri.path.orEmpty().lowercase().replace('\\', '/')
        if (host == "www.jinhak.com" || host == "jinhak.com") {
            // Auth-only support pages/callbacks are allowed in the auth WebView. They are never
            // promoted to collector destinations. Lower-grade paths were rejected above.
            return if (path.startsWith("/jh/")) Route.JINHAK_SUPPORT else Route.JINHAK_SUPPORT
        }
        if (host == "member.jinhak.com") return Route.JINHAK_SUPPORT
        return Route.BLOCK_EXTERNAL
    }

    fun allowsAuthMainFrame(rawUrl: String): Boolean = when (classify(rawUrl)) {
        Route.LOGIN_FORM,
        Route.MEMBER_LOGIN,
        Route.HIGH3_SUCCESS,
        Route.JINHAK_SUPPORT,
        Route.BLANK -> true
        Route.BLOCK_LOWER_GRADE,
        Route.BLOCK_EXTERNAL,
        Route.BLOCK_INVALID -> false
    }

    fun isLoginSurface(rawUrl: String): Boolean = when (classify(rawUrl)) {
        Route.LOGIN_FORM, Route.MEMBER_LOGIN -> true
        else -> false
    }

    fun isHigh3Success(rawUrl: String): Boolean = classify(rawUrl) == Route.HIGH3_SUCCESS
}
