package com.admissionhub.collector.jinhak

/**
 * v0.17.1 Jinhak authentication/session ownership contract.
 *
 * The Collector never authenticates Jinhak. The user owns the Jinhak browser session completely.
 * Collection is allowed only after the user explicitly confirms that login is complete. If the
 * site later renders a login surface, collection pauses and returns control to the user.
 */
object JinhakUserSessionPolicy {
    const val SCHEMA_VERSION = 1

    enum class NavigationDecision {
        ALLOW_ASSUMING_USER_LOGIN,
        PAUSE_FOR_USER_SESSION,
        DROP_LOWER_GRADE
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
