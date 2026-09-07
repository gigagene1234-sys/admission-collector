package com.admissionhub.collector.hub

object HubFirstLayoutPolicy {
    fun columnsForWidthDp(widthDp: Int): Int = when {
        widthDp >= 900 -> 3
        widthDp >= 600 -> 2
        else -> 1
    }
    fun rowsForSix(widthDp: Int): Int {
        val columns = columnsForWidthDp(widthDp)
        return (6 + columns - 1) / columns
    }
    fun cardHeightDp(widthDp: Int): Int = when (columnsForWidthDp(widthDp)) {
        3 -> 236
        2 -> 248
        else -> 264
    }
    const val advancedToolsInitiallyVisible = false
}
