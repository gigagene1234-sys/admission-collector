package com.admissionhub.collector.jinhak

/**
 * v0.18.8 browser-surface contract.
 *
 * Before the exact Susi storage page is visible, Admission Hub must behave as a
 * passive browser shell. The provider owns authentication, cookies and its
 * normal navigation. Report-only automation may enable the collector popup
 * bridge only after storage has armed a batch.
 */
object JinhakPassiveBrowserSurfacePolicy {
    const val USE_DEFAULT_WEBVIEW_USER_AGENT = true
    const val FLUSH_PROVIDER_COOKIES = true
    const val MANUAL_BROWSER_MULTIPLE_WINDOWS = false
    const val MANUAL_BROWSER_AUTOMATIC_WINDOWS = false
    const val MANUAL_BROWSER_POPUP_HANDOFF = false


    fun needsSurfaceReconfigure(
        sameWebView: Boolean,
        previousBatchMode: Boolean?,
        requestedBatchMode: Boolean
    ): Boolean = !sameWebView || previousBatchMode != requestedBatchMode

    fun applyPersistentBrowserIdentity(firstConfigurationForWebView: Boolean): Boolean =
        firstConfigurationForWebView

    fun allowCollectorPopupHandoff(batchRunning: Boolean): Boolean = batchRunning

    fun multipleWindowsEnabled(batchRunning: Boolean): Boolean = batchRunning

    fun automaticWindowsEnabled(batchRunning: Boolean): Boolean = batchRunning
}
