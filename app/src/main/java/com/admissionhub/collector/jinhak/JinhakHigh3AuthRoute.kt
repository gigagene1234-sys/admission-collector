package com.admissionhub.collector.jinhak

import java.net.URI
import java.net.URLDecoder
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/**
 * Canonical authentication entry for the high3/N수 collector.
 *
 * The collector must never use a product-selector/login wrapper as an auth bootstrap. A protected
 * high3 URL currently redirects to member.jinhak.com with an explicit high3 ReturnURL; this helper
 * models that transport contract and rejects every lower-grade destination before navigation.
 *
 * This class is deliberately UI-agnostic: it never hides DOM nodes, changes WebView visibility,
 * clicks grade selectors, or performs navigation by itself.
 */
object JinhakHigh3AuthRoute {
    const val SCHEMA_VERSION = 2
    private const val MEMBER_LOGIN_ROOT = "https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx"
    private const val WWW_HOST = "www.jinhak.com"
    private const val MEMBER_HOST = "member.jinhak.com"

    enum class MainFrameDecision {
        ALLOW_HIGH3,
        ALLOW_CANONICAL_AUTH,
        REWRITE_GENERIC_LOGIN,
        BLOCK_LOWER_GRADE,
        ALLOW_OTHER_JINHAK
    }

    fun canonicalLoginUrl(requestedReturnTarget: String?): String {
        val target = sanitizeReturnTarget(requestedReturnTarget)
        val encoded = URLEncoder.encode(target, StandardCharsets.UTF_8.name())
        return "$MEMBER_LOGIN_ROOT?ReturnURL=$encoded"
    }

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
        if (isCanonicalMemberLogin(url)) return MainFrameDecision.ALLOW_CANONICAL_AUTH
        if (isGenericProductLogin(url)) return MainFrameDecision.REWRITE_GENERIC_LOGIN
        return MainFrameDecision.ALLOW_OTHER_JINHAK
    }

    private fun decode(value: String): String = runCatching {
        URLDecoder.decode(value, StandardCharsets.UTF_8.name())
    }.getOrDefault(value)
}
