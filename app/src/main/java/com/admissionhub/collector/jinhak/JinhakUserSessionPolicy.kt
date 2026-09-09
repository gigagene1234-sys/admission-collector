package com.admissionhub.collector.jinhak

/**
 * v0.17.4 Jinhak user-owned session contract.
 *
 * The Collector never authenticates Jinhak. The user owns the browser session completely.
 * Collection may become active only while the currently-visible top-level page is strict high3.
 * Shared root/product routers, generic login routers, lower-grade routes and other Jinhak product
 * spaces are not treated as an authenticated state and are never collection destinations.
 */
object JinhakUserSessionPolicy {
    const val SCHEMA_VERSION = 3

    enum class NavigationDecision {
        ALLOW_ASSUMING_USER_LOGIN,
        PAUSE_FOR_USER_SESSION,
        DROP_LOWER_GRADE
    }

    enum class ConfirmationDecision {
        ARM_AFTER_SITE_LOGIN,
        ACTIVATE_CURRENT_HIGH3,
        WAIT_FOR_HIGH3
    }

    fun isLoginSurface(url: String): Boolean =
        JinhakStrictHigh3Sandbox.allowsUserLoginSurface(url)

    fun confirmationDecision(url: String): ConfirmationDecision = when (JinhakStrictHigh3Sandbox.decision(url)) {
        JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> ConfirmationDecision.ACTIVATE_CURRENT_HIGH3
        JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN -> ConfirmationDecision.ARM_AFTER_SITE_LOGIN
        else -> ConfirmationDecision.WAIT_FOR_HIGH3
    }

    fun shouldIgnoreStaleLoginCallback(callbackUrl: String, currentVisibleUrl: String): Boolean {
        if (!isLoginSurface(callbackUrl)) return false
        if (isLoginSurface(currentVisibleUrl)) return false
        return JinhakStrictHigh3Sandbox.decision(currentVisibleUrl) == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3
    }

    fun decision(url: String): NavigationDecision = when (JinhakStrictHigh3Sandbox.decision(url)) {
        JinhakStrictHigh3Sandbox.MainFrameDecision.BLOCK_LOWER_GRADE -> NavigationDecision.DROP_LOWER_GRADE
        JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 -> NavigationDecision.ALLOW_ASSUMING_USER_LOGIN
        else -> NavigationDecision.PAUSE_FOR_USER_SESSION
    }

    fun collectorMayVerifyLogin(): Boolean = false
    fun collectorMayReadCredentials(): Boolean = false
    fun collectorMaySubmitCredentials(): Boolean = false
    fun collectorMayRestoreJinhakAuthLease(): Boolean = false
    fun collectorMayCaptureJinhakAuthLease(): Boolean = false
    fun collectorMayExtendJinhakSession(): Boolean = false
    fun collectorMayConstructLoginNavigation(): Boolean = false
    fun collectorMayUseSharedProductRoot(): Boolean = false
    fun collectorMayUseGenericProductLoginRouter(): Boolean = false
    fun collectorMayAutoResumeAfterLogin(): Boolean = false
}
