package com.admissionhub.collector.jinhak

/**
 * v0.18.6 runtime gate for Jinhak.
 *
 * Before the user reaches the protected Susi storage page, Admission Hub is a passive browser:
 * it must not redirect, stop loading, probe authentication, restore auth state, or autofill.
 * Automation begins only from the exact storage route. Once traversal is active, only storage
 * and same-application report routes are in autonomous scope. Leaving that scope means STOP only.
 */
object JinhakManualBrowserStateMachine {
    enum class Phase {
        MANUAL_BROWSER,
        STORAGE_ARMED,
        REPORT_TRAVERSAL,
        STOP_ONLY
    }

    fun phase(rawUrl: String?, traversalRunning: Boolean): Phase = when {
        JinhakManualStorageReportPolicy.isStorageEntry(rawUrl) -> Phase.STORAGE_ARMED
        traversalRunning && JinhakManualStorageReportPolicy.isReportUrl(rawUrl) -> Phase.REPORT_TRAVERSAL
        traversalRunning -> Phase.STOP_ONLY
        else -> Phase.MANUAL_BROWSER
    }

    fun isPassiveManualBrowser(rawUrl: String?, traversalRunning: Boolean): Boolean =
        phase(rawUrl, traversalRunning) == Phase.MANUAL_BROWSER

    fun shouldStopOnly(rawUrl: String?, traversalRunning: Boolean): Boolean =
        phase(rawUrl, traversalRunning) == Phase.STOP_ONLY

    const val AUTH_OWNERSHIP = "user-browser-only"
    const val INTERCEPT_MANUAL_BROWSER_NAVIGATION = false
    const val STOP_LOADING_IN_MANUAL_BROWSER = false
    const val AUTO_LOGIN = false
    const val AUTH_PROBE = false
    const val SESSION_RESTORE = false
    const val CREDENTIAL_AUTOFILL = false
}
