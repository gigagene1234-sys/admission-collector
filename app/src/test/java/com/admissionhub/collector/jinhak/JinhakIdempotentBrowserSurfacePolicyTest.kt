package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakIdempotentBrowserSurfacePolicyTest {
    @Test
    fun `same webview and same manual mode is a no-op`() {
        assertFalse(
            JinhakPassiveBrowserSurfacePolicy.needsSurfaceReconfigure(
                sameWebView = true,
                previousBatchMode = false,
                requestedBatchMode = false
            )
        )
    }

    @Test
    fun `same webview only reconfigures on real mode transition`() {
        assertTrue(
            JinhakPassiveBrowserSurfacePolicy.needsSurfaceReconfigure(
                sameWebView = true,
                previousBatchMode = false,
                requestedBatchMode = true
            )
        )
        assertTrue(
            JinhakPassiveBrowserSurfacePolicy.needsSurfaceReconfigure(
                sameWebView = true,
                previousBatchMode = true,
                requestedBatchMode = false
            )
        )
    }

    @Test
    fun `replacement webview always receives one configuration`() {
        assertTrue(
            JinhakPassiveBrowserSurfacePolicy.needsSurfaceReconfigure(
                sameWebView = false,
                previousBatchMode = false,
                requestedBatchMode = false
            )
        )
    }

    @Test
    fun `persistent browser identity is only applied on first configuration for a webview`() {
        assertTrue(JinhakPassiveBrowserSurfacePolicy.applyPersistentBrowserIdentity(true))
        assertFalse(JinhakPassiveBrowserSurfacePolicy.applyPersistentBrowserIdentity(false))
    }
}
