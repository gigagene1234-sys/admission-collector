from pathlib import Path

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

old_block = '''            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                if (runtimeRendererRecovering) return true
                runtimeRendererRecovering = true
                val didCrash = detail?.didCrash() ?: false
                recordRuntimeEvent(
                    "webview-renderer-gone",
                    JSONObject()
                        .put("didCrash", didCrash)
                        .put("priorityAtExit", detail?.rendererPriorityAtExit() ?: -1)
                        .put("batchRunning", batchRunning)
                )
                localRunId?.let { runId ->
                    val key = currentBatchTarget?.let { canonicalizeBatchUrl(it) }.orEmpty()
                    if (key.isNotBlank()) localStore.markDocument(runId, key, "error", 0, "webview-renderer-gone")
                }
                persistRuntimeCheckpoint(forceResume = unifiedRunning)
                batchRunning = false
                batchCollecting = false
                disarmBatchNavigationWatchdog()
                runCatching {
                    (view?.parent as? ViewGroup)?.removeView(view)
                    view?.destroy()
                }
                handler.postDelayed({ recreate() }, 250L)
                return true
            }
'''

new_block = '''            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                if (runtimeRendererRecovering) return true
                runtimeRendererRecovering = true

                val deadView = view ?: webView
                val parent = deadView.parent as? ViewGroup
                val childIndex = parent?.indexOfChild(deadView) ?: -1
                val oldLayoutParams = deadView.layoutParams
                val wasBatchRunning = batchRunning
                val wasBatchPausedForLogin = batchPausedForLogin
                val wasUnifiedRunning = unifiedRunning
                val resumeUrl = currentBatchTarget?.takeIf { it.isNotBlank() }
                    ?: runCatching { deadView.url }.getOrNull()?.takeIf { !it.isNullOrBlank() }
                    ?: when (provider) {
                        ProviderId.JINHAK -> ProviderId.JINHAK.homeUrl
                        ProviderId.ADIGA -> ProviderId.ADIGA.homeUrl
                    }
                val didCrash = detail?.didCrash() ?: false
                val webViewPackage = runCatching { WebView.getCurrentWebViewPackage() }.getOrNull()

                recordRuntimeEvent(
                    "webview-renderer-gone",
                    JSONObject()
                        .put("didCrash", didCrash)
                        .put("priorityAtExit", detail?.rendererPriorityAtExit() ?: -1)
                        .put("webViewPackage", webViewPackage?.packageName ?: JSONObject.NULL)
                        .put("webViewVersion", webViewPackage?.versionName ?: JSONObject.NULL)
                        .put("batchRunning", wasBatchRunning)
                        .put("batchPausedForLogin", wasBatchPausedForLogin)
                        .put("unifiedRunning", wasUnifiedRunning)
                        .put("resumeSafePath", runtimeSafePath(resumeUrl))
                        .put("recoveryMode", "replace-main-webview-in-place")
                )
                // Renderer death is an interrupted render, not a terminal document failure.
                // Keep the current target and all in-memory mission state intact.
                batchCollecting = false
                disarmBatchNavigationWatchdog()
                persistRuntimeCheckpoint(forceResume = wasUnifiedRunning)

                handler.postDelayed({
                    val recovery = runCatching {
                        require(parent != null && childIndex >= 0) { "renderer-parent-unavailable" }
                        runCatching { parent.removeView(deadView) }
                        runCatching { deadView.stopLoading() }
                        runCatching { deadView.destroy() }

                        val replacement = WebView(this@MainActivity)
                        webView = replacement
                        parent.addView(replacement, childIndex, oldLayoutParams)
                        configureWebView()

                        // configureWebView creates only a new browser surface. Restore the
                        // runtime flags that were already authoritative before renderer death.
                        batchRunning = wasBatchRunning
                        batchPausedForLogin = wasBatchPausedForLogin
                        batchCollecting = false
                        currentBatchTarget = currentBatchTarget?.takeIf { it.isNotBlank() } ?: resumeUrl
                        runtimeRendererRecovering = false
                        recordRuntimeEvent(
                            "webview-renderer-recovered-in-place",
                            JSONObject()
                                .put("didCrash", didCrash)
                                .put("batchRunning", batchRunning)
                                .put("unifiedRunning", unifiedRunning)
                                .put("resumeSafePath", runtimeSafePath(resumeUrl))
                                .put("activityRecreated", false)
                        )
                        status.text = "WebView renderer 복구 완료 · 현재 수집 지점에서 재개합니다."
                        replacement.loadUrl(resumeUrl)
                    }
                    recovery.onFailure { error ->
                        runtimeRendererRecovering = false
                        batchRunning = false
                        batchCollecting = false
                        persistRuntimeCheckpoint(forceResume = wasUnifiedRunning)
                        recordRuntimeEvent(
                            "webview-renderer-recovery-failed",
                            JSONObject()
                                .put("errorClass", error.javaClass.simpleName.take(80))
                                .put("resumeSafePath", runtimeSafePath(resumeUrl))
                                .put("activityRecreated", false),
                            synchronous = true
                        )
                        status.text = "WebView renderer 복구 실패 · 앱 재실행 시 체크포인트에서 복구합니다."
                    }
                }, 250L)
                return true
            }
'''

if old_block not in m:
    raise SystemExit('v0.9.9 renderer block anchor not found')
m = m.replace(old_block, new_block, 1)

for old, new in [
    ('private const val VERSION = "0.9.9"', 'private const val VERSION = "0.9.10"'),
    ('private const val BUILD_CODE = 10990', 'private const val BUILD_CODE = 109100'),
]:
    if old not in m:
        raise SystemExit(f'MainActivity version anchor not found: {old}')
    m = m.replace(old, new, 1)

for old, new in [
    ('versionCode = 10990', 'versionCode = 109100'),
    ('versionName = "0.9.9"', 'versionName = "0.9.10"'),
]:
    if old not in g:
        raise SystemExit(f'Gradle version anchor not found: {old}')
    g = g.replace(old, new, 1)

old_label = 'android:label="Admission Collector v0.9.9 Mission Ledger Routing"'
new_label = 'android:label="Admission Collector v0.9.10 Renderer Recovery"'
if old_label not in manifest:
    raise SystemExit('Manifest v0.9.9 label anchor not found')
manifest = manifest.replace(old_label, new_label, 1)

# v0.9.10 is intentionally single-purpose. Reject accidental edits to other runtime features.
required = [
    'webview-renderer-recovered-in-place',
    'replace-main-webview-in-place',
    'activityRecreated", false',
    'parent.addView(replacement, childIndex, oldLayoutParams)',
    'currentBatchTarget = currentBatchTarget?.takeIf { it.isNotBlank() } ?: resumeUrl',
]
missing = [x for x in required if x not in m]
if missing:
    raise SystemExit('renderer recovery patch incomplete: ' + ', '.join(missing))
if 'handler.postDelayed({ recreate() }, 250L)' in m:
    raise SystemExit('Activity recreate path still present')

main_path.write_text(m)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('Applied v0.9.10 Renderer Recovery patch')
