package com.admissionhub.collector.jinhak

/**
 * v0.17.1 Jinhak authentication/session ownership contract.
 *
 * The Collector never authenticates Jinhak. The user owns the Jinhak browser session completely.
 * Collection is allowed only after the user explicitly confirms that login is complete. If the
 * site later renders a login surface, collection pauses and returns control to the user.
 */
object JinhakUserSessionPolicy {
    const val SCHEMA_VERSION = 2

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
        JinhakHigh3AuthRoute.isMemberLoginSurface(url) || JinhakHigh3AuthRoute.isGenericProductLogin(url)

    fun confirmationDecision(url: String): ConfirmationDecision = when {
        JinhakGradeRouteFence.isBlockedLowerGrade(url) -> ConfirmationDecision.WAIT_FOR_HIGH3
        isLoginSurface(url) -> ConfirmationDecision.ARM_AFTER_SITE_LOGIN
        JinhakGradeRouteFence.isHigh3(url) -> ConfirmationDecision.ACTIVATE_CURRENT_HIGH3
        else -> ConfirmationDecision.WAIT_FOR_HIGH3
    }

    fun shouldIgnoreStaleLoginCallback(callbackUrl: String, currentVisibleUrl: String): Boolean {
        if (!isLoginSurface(callbackUrl)) return false
        if (isLoginSurface(currentVisibleUrl)) return false
        return JinhakGradeRouteFence.isHigh3(currentVisibleUrl)
    }

    fun decision(url: String): NavigationDecision = when {
        JinhakGradeRouteFence.isBlockedLowerGrade(url) -> NavigationDecision.DROP_LOWER_GRADE
        JinhakHigh3AuthRoute.isMemberLoginSurface(url) || JinhakHigh3AuthRoute.isGenericProductLogin(url) ->
            NavigationDecision.PAUSE_FOR_USER_SESSION
        else -> NavigationDecision.ALLOW_ASSUMING_USER_LOGIN
    }

    fun collectorMayVerifyLogin(): Boolean = false
    fun collectorMayReadCredentials(): Boolean = false
    fun collectorMaySubmitCredentials(): Boolean = false
    fun collectorMayRestoreJinhakAuthLease(): Boolean = false
    fun collectorMayCaptureJinhakAuthLease(): Boolean = false
    fun collectorMayExtendJinhakSession(): Boolean = false
    fun collectorMayConstructLoginNavigation(): Boolean = false
}
