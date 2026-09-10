package com.admissionhub.collector.jinhak

/**
 * v0.18.4 runtime contract.
 *
 * Jinhak authentication and the protected Susi saved-application repository must use the
 * same foreground WebView.  A second WebView may have the same CookieManager but does not
 * guarantee the same sessionStorage / in-memory SPA state, which made the dedicated-auth
 * handoff fragile on real Galaxy devices.
 *
 * The installed Jinhak application is deliberately not treated as an authentication bridge.
 * Android app-private cookies and WebView state are not transferable unless the provider
 * explicitly exposes an SSO/deep-link contract.  No such contract is assumed here.
 */
object JinhakSingleSurfaceStoragePolicy {
    const val ENABLED = true
    const val AUTH_AND_COLLECTION_SURFACE = "collector-main-webview"
    const val EXTERNAL_APP_SESSION_BRIDGE = false
    const val AUTOFILL_MAX_ATTEMPTS_PER_PAGE = 4
    const val AUTOFILL_RETRY_MS = 700L

    fun isAllowedForegroundState(url: String?): Boolean {
        if (url.isNullOrBlank()) return false
        return JinhakStorageCompetitionPolicy.isStorageUrl(url) ||
            JinhakDedicatedAuthPolicy.isLoginSurface(url)
    }

    fun completedDelta(baseline: Int, current: Int): Int = (current - baseline).coerceAtLeast(0)
}
