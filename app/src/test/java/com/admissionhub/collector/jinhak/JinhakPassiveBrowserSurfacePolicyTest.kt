package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakPassiveBrowserSurfacePolicyTest {
    @Test
    fun manualBrowserHasNoCollectorPopupHandoff() {
        assertFalse(JinhakPassiveBrowserSurfacePolicy.allowCollectorPopupHandoff(false))
        assertFalse(JinhakPassiveBrowserSurfacePolicy.multipleWindowsEnabled(false))
        assertFalse(JinhakPassiveBrowserSurfacePolicy.automaticWindowsEnabled(false))
    }

    @Test
    fun reportTraversalMayUseCollectorPopupBridge() {
        assertTrue(JinhakPassiveBrowserSurfacePolicy.allowCollectorPopupHandoff(true))
        assertTrue(JinhakPassiveBrowserSurfacePolicy.multipleWindowsEnabled(true))
        assertTrue(JinhakPassiveBrowserSurfacePolicy.automaticWindowsEnabled(true))
    }

    @Test
    fun providerBrowserIdentityAndCookiesArePreserved() {
        assertTrue(JinhakPassiveBrowserSurfacePolicy.USE_DEFAULT_WEBVIEW_USER_AGENT)
        assertTrue(JinhakPassiveBrowserSurfacePolicy.FLUSH_PROVIDER_COOKIES)
        assertFalse(JinhakPassiveBrowserSurfacePolicy.MANUAL_BROWSER_MULTIPLE_WINDOWS)
        assertFalse(JinhakPassiveBrowserSurfacePolicy.MANUAL_BROWSER_AUTOMATIC_WINDOWS)
        assertFalse(JinhakPassiveBrowserSurfacePolicy.MANUAL_BROWSER_POPUP_HANDOFF)
    }
}
