package com.admissionhub.collector.jinhak

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * Jinhak high3 route policy for the v0.17.0 server-owned authentication model.
 *
 * Authentication is not initiated or proven by the Collector. The Collector opens only real
 * protected high3 mission routes. If Jinhak decides that authentication is required, the site's
 * own redirect to a login surface is allowed to render unchanged. A natural return to high3 is
 * treated as a browser/navigation event, not as a DOM authentication verdict.
 *
 * Lower-grade routes remain transport-level blocked. No method in this object creates a member
 * login URL or rewrites a generic login URL into another login route.
 */
object JinhakHigh3AuthRoute {
    const val SCHEMA_VERSION = 3
    private const val WWW_HOST = "www.jinhak.com"
    private const val MEMBER_HOST = "member.jinhak.com"

    /**
     * Legacy enum names are retained so older call sites compile while the v0.17.0 migration is
     * completed. REWRITE_GENERIC_LOGIN is intentionally unreachable from [decision].
     */
    enum class MainFrameDecision {
        ALLOW_HIGH3,
        ALLOW_CANONICAL_AUTH,
        REWRITE_GENERIC_LOGIN,
        BLOCK_LOWER_GRADE,
        ALLOW_OTHER_JINHAK
    }

    /**
     * Compatibility shim only. v0.17.0 never constructs a member-login URL. If an old call site
     * accidentally invokes this method it is fail-safe: it returns the protected high3 target,
     * letting Jinhak's server decide whether a login redirect is necessary.
     */
    @Deprecated("v0.17.0 uses server-owned authentication and never constructs login URLs")
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
        val path = uri.path.orEmpty().lowercase()
        return path == "/jh/high3" || path.startsWith("/jh/high3/")
    }

    fun isGenericProductLogin(url: String): Boolean {
        if (url.isBlank()) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        val host = uri.host?.lowercase().orEmpty()
        val path = uri.path.orEmpty().lowercase()
        return (host == WWW_HOST || host == "jinhak.com") && path == "/jh/member/login"
    }

    fun isMemberLoginSurface(url: String): Boolean {
        if (url.isBlank()) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        return uri.scheme?.lowercase() == "https" &&
            uri.host?.lowercase() == MEMBER_HOST &&
            uri.path.orEmpty().lowercase().endsWith("/memberlogin.aspx")
    }

    fun isCanonicalMemberLogin(url: String): Boolean {
        if (url.isBlank() || JinhakGradeRouteFence.isBlockedLowerGrade(url)) return false
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
            val key = decode(keyRaw)
            if (!key.equals("ReturnURL", ignoreCase = true)) continue
            var value = decode(valueRaw)
            for (i in 0 until 2) {
                val next = decode(value)
                if (next == value) break
                value = next
            }
            return value
        }
        return null
    }

    fun decision(url: String): MainFrameDecision {
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) return MainFrameDecision.BLOCK_LOWER_GRADE
        if (isAllowedHigh3Target(url)) return MainFrameDecision.ALLOW_HIGH3
        if (isMemberLoginSurface(url) || isGenericProductLogin(url)) return MainFrameDecision.ALLOW_CANONICAL_AUTH
        return MainFrameDecision.ALLOW_OTHER_JINHAK
    }

    private fun decode(value: String): String = runCatching {
        URLDecoder.decode(value, StandardCharsets.UTF_8.name())
    }.getOrDefault(value)
}
