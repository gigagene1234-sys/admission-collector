package com.admissionhub.collector.jinhak

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * User-enabled, read-only observer for the official Jinhak app.
 *
 * It never performs clicks, text entry, navigation, or login. Password and editable nodes are
 * discarded before any text reaches private app storage. Only screens that look like the Susi
 * saved-application repository are persisted.
 */
class JinhakNativeBridgeAccessibilityService : AccessibilityService() {
    private var lastFingerprint = ""
    private var lastStoredAtMs = 0L

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val packageName = event?.packageName?.toString().orEmpty()
        if (packageName != JinhakNativeAppBridge.OFFICIAL_APP_PACKAGE) return
        val root = rootInActiveWindow ?: event?.source ?: return
        val lines = ArrayList<String>(192)
        collectVisibleNonEditableText(root, lines, 0)
        if (lines.isEmpty()) return
        val joined = lines.joinToString("\n")
        if (!JinhakNativeAppBridge.looksLikeSusiStorage(joined)) return
        val fingerprint = joined.hashCode().toString(16)
        val now = System.currentTimeMillis()
        if (fingerprint == lastFingerprint && now - lastStoredAtMs < 2_500L) return
        lastFingerprint = fingerprint
        lastStoredAtMs = now
        JinhakNativeAppBridge.storeObservation(applicationContext, lines, now)
    }

    override fun onInterrupt() = Unit

    private fun collectVisibleNonEditableText(node: AccessibilityNodeInfo, out: MutableList<String>, depth: Int) {
        if (depth > 18 || out.size >= 260) return
        val className = node.className?.toString().orEmpty()
        val isInput = node.isPassword || node.isEditable || className.contains("EditText", ignoreCase = true)
        if (!isInput && node.isVisibleToUser) {
            node.text?.toString()?.trim()?.takeIf { it.isNotBlank() }?.let(out::add)
            node.contentDescription?.toString()?.trim()?.takeIf { it.isNotBlank() }?.let(out::add)
        }
        if (isInput) return
        for (i in 0 until node.childCount) {
            val child = runCatching { node.getChild(i) }.getOrNull() ?: continue
            collectVisibleNonEditableText(child, out, depth + 1)
            runCatching { child.recycle() }
        }
    }
}
