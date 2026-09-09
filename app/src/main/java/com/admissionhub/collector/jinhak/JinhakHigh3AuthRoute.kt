package com.admissionhub.collector.jinhak

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
