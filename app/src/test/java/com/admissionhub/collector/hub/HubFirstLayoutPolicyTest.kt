package com.admissionhub.collector.hub

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class HubFirstLayoutPolicyTest {
    @Test fun wideTabletUsesThreeByTwo() {
        assertEquals(3, HubFirstLayoutPolicy.columnsForWidthDp(1200))
        assertEquals(2, HubFirstLayoutPolicy.rowsForSix(1200))
        assertEquals(236, HubFirstLayoutPolicy.cardHeightDp(1200))
    }
    @Test fun narrowerLayoutsDoNotUseSixWideStrip() {
        assertEquals(2, HubFirstLayoutPolicy.columnsForWidthDp(700))
        assertEquals(3, HubFirstLayoutPolicy.rowsForSix(700))
        assertEquals(1, HubFirstLayoutPolicy.columnsForWidthDp(420))
        assertEquals(6, HubFirstLayoutPolicy.rowsForSix(420))
    }
    @Test fun advancedToolsAreCollapsedInitially() {
        assertFalse(HubFirstLayoutPolicy.advancedToolsInitiallyVisible)
    }
}
