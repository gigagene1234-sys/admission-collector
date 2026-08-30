from pathlib import Path

ROOT = Path('.')
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

for p in MAIN_FILES:
    m = p.read_text()
    m = m.replace('private const val VERSION = "0.6.5"', 'private const val VERSION = "0.6.6"', 1)
    m = m.replace('private const val BUILD_CODE = 10650', 'private const val BUILD_CODE = 10660', 1)

    state_anchor = '    private var jinhakRecoveredStalls = 0\n'
    state_new = '''    private var jinhakRecoveredStalls = 0\n    private var jinhakAbsoluteTargetKey = ""\n    private var jinhakAbsoluteTargetGeneration = 0\n    private var unifiedFinishInProgress = false\n    private var pendingUnifiedExportSessionId: String? = null\n'''
    if state_anchor not in m:
        raise SystemExit(f'v066 state anchor missing: {p}')
    m = m.replace(state_anchor, state_new, 1)

    const_anchor = '        private const val JINHAK_HARD_STALL_MS = 24_000L\n'
    const_new = '''        private const val JINHAK_HARD_STALL_MS = 24_000L\n        private const val JINHAK_ABSOLUTE_TARGET_MS = 35_000L\n'''
    if const_anchor not in m:
        raise SystemExit(f'v066 const anchor missing: {p}')
    m = m.replace(const_anchor, const_new, 1)

    page_start_anchor = '''                if (batchRunning && !batchPausedForLogin) {\n                    armBatchNavigationWatchdog(url)\n'''
    page_start_new = '''                if (batchRunning && !batchPausedForLogin) {\n                    if (provider == ProviderId.JINHAK) armJinhakAbsoluteTargetWatchdog(url)\n                    armBatchNavigationWatchdog(url)\n'''
    if page_start_anchor not in m:
        raise SystemExit(f'v066 onPageStarted anchor missing: {p}')
    m = m.replace(page_start_anchor, page_start_new, 1)

    start_reset_anchor = '''        batchSkipSnapshotUntilMs = 0L\n        disarmBatchNavigationWatchdog()\n'''
    start_reset_new = '''        batchSkipSnapshotUntilMs = 0L\n        jinhakAbsoluteTargetKey = ""\n        ++jinhakAbsoluteTargetGeneration\n        disarmBatchNavigationWatchdog()\n'''
    if start_reset_anchor not in m:
        raise SystemExit(f'v066 start reset anchor missing: {p}')
    m = m.replace(start_reset_anchor, start_reset_new, 1)

    # Insert an absolute per-target watchdog. Unlike the soft/hard page-start watchdog,
    # this is keyed to currentBatchTarget and therefore is NOT reset by redirect/reload loops.
    watchdog_marker = '    private fun showBatchCover() {\n'
    watchdog_func = r'''    private fun armJinhakAbsoluteTargetWatchdog(expectedUrl: String) {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return
        val target = canonicalizeBatchUrl(currentBatchTarget ?: expectedUrl)
        if (target.isBlank()) return
        val key = RecordUtils.sha256(target)
        if (key == jinhakAbsoluteTargetKey) return
        jinhakAbsoluteTargetKey = key
        val generation = ++jinhakAbsoluteTargetGeneration
        val startedAt = System.currentTimeMillis()
        recordRuntimeEvent("jinhak-target-start", JSONObject()
            .put("targetSafePath", runtimeSafePath(target))
            .put("currentSafePath", runtimeSafePath(expectedUrl)))

        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
            if (generation != jinhakAbsoluteTargetGeneration || key != jinhakAbsoluteTargetKey) return@postDelayed
            val activeTarget = canonicalizeBatchUrl(currentBatchTarget ?: target)
            if (RecordUtils.sha256(activeTarget) != key) return@postDelayed

            val current = canonicalizeBatchUrl(webView.url ?: expectedUrl)
            recordRuntimeEvent("jinhak-absolute-target-timeout", JSONObject()
                .put("targetSafePath", runtimeSafePath(target))
                .put("currentSafePath", runtimeSafePath(current))
                .put("elapsedMs", System.currentTimeMillis() - startedAt))
            localRunId?.let { runId ->
                localStore.markDocument(runId, target, "error", 0, "jinhak-absolute-target-timeout")
            }
            batchVisited.add(target)
            batchQueued.remove(target)
            batchErrors.put(JSONObject()
                .put("type", "jinhak-absolute-target-timeout")
                .put("targetSafePath", runtimeSafePath(target))
                .put("currentSafePath", runtimeSafePath(current)))
            batchCollecting = false
            batchNavigationWatchdogRecovery = false
            batchReadinessPolling = false
            pendingBatchPageAction = null
            activeBatchPageAction = null
            currentBatchTarget = null
            ++jinhakStallWatchdogGeneration
            jinhakAbsoluteTargetKey = ""
            ++jinhakAbsoluteTargetGeneration
            runCatching { webView.stopLoading() }
            status.text = "진학사 절대 대기시간 초과: redirect/로딩 루프 페이지를 격리하고 다음 대상으로 진행합니다."
            handler.postDelayed({
                if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK) loadNextBatchPage()
            }, 320L)
        }, JINHAK_ABSOLUTE_TARGET_MS)
    }

'''
    if watchdog_marker not in m:
        raise SystemExit(f'v066 watchdog insertion marker missing: {p}')
    m = m.replace(watchdog_marker, watchdog_func + watchdog_marker, 1)

    # Replace unified finish with a non-reentrant, low-memory shutdown. It must never
    # materialize the full unified dataset on the UI thread.
    finish_start = m.index('    private fun finishUnifiedCollection(reason: String) {')
    finish_end = m.index('    private fun isAdigaBlockingErrorMessage', finish_start)
    old_finish = m[finish_start:finish_end]
    new_finish = r'''    private fun finishUnifiedCollection(reason: String) {
        if (unifiedFinishInProgress) return
        unifiedFinishInProgress = true
        try {
            val sessionId = unifiedSessionId ?: localStore.latestUnifiedSession()
            if (batchRunning) stopBatchForUnifiedFinish("unified-$reason")

            unifiedRunning = false
            unifiedJinhakAutoCapture = false
            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = false
            unifiedAutoCaptureScheduled = false
            unifiedPhase = "completed"
            jinhakAbsoluteTargetKey = ""
            ++jinhakAbsoluteTargetGeneration

            if (sessionId == null) {
                unifiedButton.text = "두 사이트 통합 수집 시작"
                status.text = "종료할 통합 수집 세션이 없습니다."
                return
            }
            localStore.updateUnifiedSession(sessionId, "completed", "completed", reason)
            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit().putBoolean("resumeUnified", false).apply()

            val summary = localStore.unifiedStatus(sessionId)
            lastJson = JSONObject()
                .put("schemaVersion", 2)
                .put("type", "admission-unified-session-summary")
                .put("session", summary)
                .put("fullExportMaterializedInMemory", false)
                .put("fullExport", "Use JSON 저장; records are streamed from SQLite to the destination file.")
                .toString(2)
            showPreview(lastJson)
            unifiedButton.text = "두 사이트 통합 수집 시작"
            pendingUnifiedExportSessionId = sessionId
            cloudOffload.sendDiagnostic(
                "unified", VERSION,
                JSONObject(summary.toString())
                    .put("trigger", "unified-finish")
                    .put("containsRawAdmissionRecords", false)
                    .put("memorySafeFinish", true)
            ) { }
            recordRuntimeEvent("unified-finish-memory-safe", JSONObject()
                .put("reason", reason.take(120))
                .put("sessionIdPresent", true))
            status.text = "통합 수집 종료 완료 · 전체 데이터는 SQLite에 보존됨 · JSON 저장 시 메모리에 올리지 않고 스트리밍합니다."
        } catch (t: Throwable) {
            recordRuntimeEvent("unified-finish-failure", JSONObject()
                .put("exceptionClass", t.javaClass.name.take(160)), synchronous = true)
            status.text = "통합 수집 종료 처리 중 오류가 기록되었습니다. 앱을 다시 열면 체크포인트에서 복구합니다."
        } finally {
            unifiedFinishInProgress = false
        }
    }

    private fun stopBatchForUnifiedFinish(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        batchReadinessPolling = false
        disarmBatchNavigationWatchdog()
        jinhakAbsoluteTargetKey = ""
        ++jinhakAbsoluteTargetGeneration
        runCatching { webView.stopLoading() }
        hideBatchCover()
        stopCollectionKeepAlive()
        batchQueue.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        pendingBatchPageAction = null
        activeBatchPageAction = null
        currentBatchTarget = null
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else "현재 진학사 화면 정리"
        localRunId?.let { localStore.markRun(it, "stopped", reason) }
        recordRuntimeEvent("batch-lightweight-stop", JSONObject().put("reason", reason.take(120)))
    }

'''
    m = m[:finish_start] + new_finish + m[finish_end:]

    # Ordinary stop must also not build an enormous Local-First record JSON in RAM.
    old_stop_tail = '''        localRunId?.let { localStore.markRun(it, "stopped", reason) }\n        if (batchSnapshots.length() > 0 || localRunId != null) finalizeBatchJson("stopped")\n    }\n'''
    new_stop_tail = '''        localRunId?.let { localStore.markRun(it, "stopped", reason) }\n        if (batchSnapshots.length() > 0 || localRunId != null) finalizeBatchJson("stopped")\n        jinhakAbsoluteTargetKey = ""\n        ++jinhakAbsoluteTargetGeneration\n    }\n'''
    if old_stop_tail not in m:
        raise SystemExit(f'v066 stop tail anchor missing: {p}')
    m = m.replace(old_stop_tail, new_stop_tail, 1)

    # finalizeBatchJson is now summary-only in Local-First mode. SQLite remains authoritative.
    old_finalize_head = '''    private fun finalizeBatchJson(reason: String) {\n        val persistedRecords = localRunId?.let { localStore.loadRecords(it) } ?: batchRecords\n        val localStats = localRunId?.let { localStore.stats(it) } ?: JSONObject()\n'''
    new_finalize_head = '''    private fun finalizeBatchJson(reason: String) {\n        val localStats = localRunId?.let { localStore.stats(it) } ?: JSONObject()\n        val persistedRecordCount = localStats.optInt("records", batchRecords.length())\n        val persistedRecords = if (LOCAL_FIRST_BETA) JSONArray() else (localRunId?.let { localStore.loadRecords(it) } ?: batchRecords)\n'''
    if old_finalize_head not in m:
        raise SystemExit(f'v066 finalize head anchor missing: {p}')
    m = m.replace(old_finalize_head, new_finalize_head, 1)
    m = m.replace('.put("records", persistedRecords.length())', '.put("records", persistedRecordCount)', 1)
    finalize_records_anchor = '''            .put("cloudOffload", JSONObject().put("mode", "disabled-during-v0.4.0-local-first"))\n            .put("records", persistedRecords)\n'''
    finalize_records_new = '''            .put("cloudOffload", JSONObject().put("mode", "disabled-during-v0.4.0-local-first"))\n            .put("recordsMaterializedInMemory", !LOCAL_FIRST_BETA)\n            .put("records", persistedRecords)\n'''
    if finalize_records_anchor not in m:
        raise SystemExit(f'v066 finalize records anchor missing: {p}')
    m = m.replace(finalize_records_anchor, finalize_records_new, 1)

    # Save completed/running unified sessions via SQLite streaming instead of lastJson.
    save_start = m.index('    private fun saveJson() {')
    save_end = m.index('    override fun onResume()', save_start)
    old_save = m[save_start:save_end]
    new_save = r'''    private fun saveJson() {
        val candidateSession = unifiedSessionId ?: localStore.latestUnifiedSession()
        val useUnifiedStream = candidateSession?.let {
            val s = localStore.unifiedStatus(it)
            s.optString("status") in setOf("running", "completed")
        } ?: false
        pendingUnifiedExportSessionId = if (useUnifiedStream) candidateSession else null

        if (!useUnifiedStream && lastJson.isBlank()) {
            Toast.makeText(this, "먼저 페이지 또는 일괄 수집을 실행하세요.", Toast.LENGTH_SHORT).show()
            return
        }
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/json"
            val prefix = if (useUnifiedStream) "admission-unified" else "admission-${provider.wireName}"
            putExtra(Intent.EXTRA_TITLE, "$prefix-v${VERSION}-${System.currentTimeMillis()}.json")
        }
        startActivityForResult(intent, SAVE_JSON_REQUEST)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == SAVE_JSON_REQUEST && resultCode == RESULT_OK) {
            val uri: Uri = data?.data ?: return
            val streamSession = pendingUnifiedExportSessionId
            pendingUnifiedExportSessionId = null
            status.text = if (streamSession != null) "통합 JSON 스트리밍 저장 중…" else "JSON 저장 중…"
            Thread {
                val result = runCatching {
                    contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { writer ->
                        if (streamSession != null) localStore.writeUnifiedExport(streamSession, writer)
                        else writer.write(lastJson)
                    } ?: error("output-stream-unavailable")
                }
                runOnUiThread {
                    status.text = if (result.isSuccess) {
                        if (streamSession != null) "통합 JSON 스트리밍 저장 완료" else "JSON 저장 완료"
                    } else {
                        "JSON 저장 실패: ${result.exceptionOrNull()?.javaClass?.simpleName ?: "unknown"}"
                    }
                }
            }.start()
        }
    }

'''
    m = m[:save_start] + new_save + m[save_end:]

    p.write_text(m)

# Local store: add memory-safe streaming unified export.
s = STORE.read_text()
if 'import java.io.Writer\n' not in s:
    s = s.replace('import java.time.Instant\n', 'import java.time.Instant\nimport java.io.Writer\n', 1)

store_marker = '    fun beginOrResume(provider: String, collectorVersion: String): String {\n'
stream_func = r'''    fun writeUnifiedExport(sessionId: String, writer: Writer) {
        val status = unifiedStatus(sessionId)
        val adigaRun = status.optJSONObject("adiga")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
        val jinhakRun = status.optJSONObject("jinhak")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }

        fun writeNullableString(value: String?) {
            if (value == null) writer.write("null") else writer.write(JSONObject.quote(value))
        }
        fun writeRecords(runId: String?) {
            writer.write("[")
            var first = true
            if (runId != null) {
                readableDatabase.rawQuery(
                    "SELECT json FROM records WHERE run_id=? ORDER BY updated_at,fingerprint",
                    arrayOf(runId)
                ).use { c ->
                    while (c.moveToNext()) {
                        if (!first) writer.write(",")
                        first = false
                        writer.write(c.getString(0))
                    }
                }
            }
            writer.write("]")
        }
        fun writeAnalyses() {
            writer.write("[")
            var first = true
            readableDatabase.rawQuery(
                "SELECT page_type,payload_json,captured_at FROM unified_analysis_captures WHERE session_id=? ORDER BY captured_at",
                arrayOf(sessionId)
            ).use { c ->
                while (c.moveToNext()) {
                    if (!first) writer.write(",")
                    first = false
                    writer.write("{\"pageType\":")
                    writeNullableString(if (c.isNull(0)) null else c.getString(0))
                    writer.write(",\"capturedAt\":")
                    writeNullableString(c.getString(2))
                    writer.write(",\"analysis\":")
                    writer.write(c.getString(1))
                    writer.write("}")
                }
            }
            writer.write("]")
        }

        writer.write("{\"schemaVersion\":2,\"type\":\"admission-unified-two-provider-export\",\"session\":")
        writer.write(status.toString())
        writer.write(",\"combinationPolicy\":{\"officialBaseline\":\"adiga\",\"predictionAnalysis\":\"jinhak\",\"keepProviderSemanticsSeparate\":true,\"doNotOverwriteHistoricalWithPrediction\":true},\"sources\":{\"adiga\":{\"runId\":")
        writeNullableString(adigaRun)
        writer.write(",\"records\":")
        writeRecords(adigaRun)
        writer.write("},\"jinhak\":{\"runId\":")
        writeNullableString(jinhakRun)
        writer.write(",\"records\":")
        writeRecords(jinhakRun)
        writer.write(",\"pageAnalyses\":")
        writeAnalyses()
        writer.write("}}}")
        writer.flush()
    }

'''
if store_marker not in s:
    raise SystemExit('v066 store insertion marker missing')
s = s.replace(store_marker, stream_func + store_marker, 1)
STORE.write_text(s)

# Metadata.
g = GRADLE.read_text().replace('versionCode = 10650', 'versionCode = 10660', 1).replace('versionName = "0.6.5"', 'versionName = "0.6.6"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text().replace('Admission Collector v0.6.5 Safe Jinhak Explorer', 'Admission Collector v0.6.6 Memory-Safe Autonomous Explorer', 1)
MANIFEST.write_text(mf)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirror mismatch after v0.6.6 patch')

print('v0.6.6 absolute Jinhak dwell guard + memory-safe finish/streaming export applied')
