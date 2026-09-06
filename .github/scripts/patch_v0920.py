from pathlib import Path
import re

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
CLOUD = ROOT / 'app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadCoordinator.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'
READ_DIAG = ROOT / '.github/workflows/read-jinhak-diagnostic.yml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


def regex_replace_once(text: str, pattern: str, repl: str, label: str) -> str:
    new, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one regex match, found {count}')
    return new

main = MAIN.read_text()
cloud = CLOUD.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

# Refuse to patch an unexpected source tree.
required_old = [
    'private const val VERSION = "0.9.19"',
    'private const val BUILD_CODE = 109190',
    'private var runtimeRendererRecovering = false',
    'jinhakMissionCells.onRendererGone(',
    'legacyAgentActionInFlight',
    'legacyBatchCollecting',
]
missing = [x for x in required_old if x not in main]
if missing:
    raise SystemExit('v0.9.19 source precondition failed: ' + ', '.join(missing))
if 'fun sendRecordCheckpoint(' in cloud:
    raise SystemExit('Cloud checkpoint method already exists; refusing double patch')

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.9.19"', 'private const val VERSION = "0.9.20"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 109190', 'private const val BUILD_CODE = 109200', 'main build code')
gradle = replace_once(gradle, 'versionCode = 109190', 'versionCode = 109200', 'gradle versionCode')
gradle = replace_once(gradle, 'versionName = "0.9.19"', 'versionName = "0.9.20"', 'gradle versionName')
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.19 Mission Cell Ownership',
    'Admission Collector v0.9.20 Crash-Safe Checkpoint',
    'manifest label'
)

# MainActivity state for bounded renderer crash recovery + cloud checkpoint observability.
main = replace_once(
    main,
    '    private var runtimeRendererRecovering = false\n',
    '''    private var runtimeRendererRecovering = false
    private var runtimeRendererCrashWindowStartedAtMs = 0L
    private var runtimeRendererCrashCount = 0
    private var runtimeRendererLastCrashAtMs = 0L
    private var runtimeRendererCircuitBreaks = 0
    private var runtimeRendererCircuitGeneration = 0
    private var jinhakCloudRecordCheckpointsQueued = 0
    private var jinhakCloudRecordCheckpointsSucceeded = 0
    private var jinhakCloudRecordCheckpointsFailed = 0
''',
    'renderer/checkpoint fields'
)

main = replace_once(
    main,
    '        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L\n',
    '''        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L
        private const val JINHAK_RENDERER_CRASH_WINDOW_MS = 90_000L
        private const val JINHAK_RENDERER_CIRCUIT_COOLDOWN_MS = 30_000L
        private const val MAX_JINHAK_RENDERER_CRASHES_PER_WINDOW = 2
        private const val MAX_JINHAK_RENDERER_CIRCUIT_BREAKS_PER_SESSION = 2
''',
    'renderer constants'
)

# Replace the foreground renderer handler. First crash remains an in-place retry; repeated
# crashes are checkpointed, cooled down, and resumed from mission origin. Two circuit breaks
# in one Activity session stop automatic browser execution instead of thrashing forever.
renderer_pattern = r'''            override fun onRenderProcessGone\(view: WebView\?, detail: RenderProcessGoneDetail\?\): Boolean \{.*?\n                return true\n            \}\n        \}\n\n        webView\.webChromeClient'''
renderer_replacement = r'''            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                if (runtimeRendererRecovering) return true
                runtimeRendererRecovering = true
                val cellInvalidation = jinhakMissionCells.onRendererGone(
                    reason = if (detail?.didCrash() == true) "foreground-crash" else "foreground-renderer-gone"
                )
                if (cellInvalidation.actionInvalidated) jinhakAgentActionInFlight = false
                if (cellInvalidation.snapshotInvalidated) batchCollecting = false

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
                val now = System.currentTimeMillis()
                if (runtimeRendererCrashWindowStartedAtMs <= 0L ||
                    now - runtimeRendererCrashWindowStartedAtMs > JINHAK_RENDERER_CRASH_WINDOW_MS) {
                    runtimeRendererCrashWindowStartedAtMs = now
                    runtimeRendererCrashCount = 0
                }
                runtimeRendererCrashCount += 1
                runtimeRendererLastCrashAtMs = now
                val repeatedJinhakCrash = provider == ProviderId.JINHAK && wasUnifiedRunning &&
                    runtimeRendererCrashCount >= MAX_JINHAK_RENDERER_CRASHES_PER_WINDOW
                if (repeatedJinhakCrash) runtimeRendererCircuitBreaks += 1
                val circuitGeneration = if (repeatedJinhakCrash) ++runtimeRendererCircuitGeneration else runtimeRendererCircuitGeneration

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
                        .put("rendererCrashCountInWindow", runtimeRendererCrashCount)
                        .put("rendererCrashWindowMs", JINHAK_RENDERER_CRASH_WINDOW_MS)
                        .put("rendererCircuitOpen", repeatedJinhakCrash)
                        .put("rendererCircuitBreaks", runtimeRendererCircuitBreaks)
                        .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
                        .put("missionCells", jinhakMissionCells.diagnostics(now))
                        .put("recoveryMode", if (repeatedJinhakCrash) "checkpoint-cooldown-mission-origin" else "replace-main-webview-in-place")
                )

                // Renderer death is an interrupted render, not a terminal document failure.
                // Pause browser execution only; keep SQLite queue/mission/auth checkpoints intact.
                batchRunning = false
                batchCollecting = false
                disarmBatchNavigationWatchdog()
                persistRuntimeCheckpoint(forceResume = wasUnifiedRunning)
                if (provider == ProviderId.JINHAK && wasUnifiedRunning) {
                    persistJinhakMissionRuntimeState(
                        if (repeatedJinhakCrash) "renderer-circuit-checkpoint" else "renderer-gone-checkpoint"
                    )
                    persistLiveJinhakDiagnostics(
                        if (repeatedJinhakCrash) "renderer-circuit-open" else "renderer-gone",
                        force = true
                    )
                }

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
                        batchCollecting = false
                        currentBatchTarget = currentBatchTarget?.takeIf { it.isNotBlank() } ?: resumeUrl
                        runtimeRendererRecovering = false

                        if (!repeatedJinhakCrash) {
                            batchRunning = wasBatchRunning
                            batchPausedForLogin = wasBatchPausedForLogin
                            recordRuntimeEvent(
                                "webview-renderer-recovered-in-place",
                                JSONObject()
                                    .put("didCrash", didCrash)
                                    .put("batchRunning", batchRunning)
                                    .put("unifiedRunning", unifiedRunning)
                                    .put("resumeSafePath", runtimeSafePath(resumeUrl))
                                    .put("rendererCrashCountInWindow", runtimeRendererCrashCount)
                                    .put("activityRecreated", false)
                            )
                            status.text = "WebView renderer 복구 완료 · 현재 수집 지점에서 재개합니다."
                            replacement.loadUrl(resumeUrl)
                            return@runCatching
                        }

                        // Repeated renderer death is treated as a circuit-open event. Keep the
                        // replacement WebView idle during cooldown so a bad report route cannot
                        // immediately kill the renderer again. Mission/ledger remain resumable.
                        batchRunning = false
                        batchPausedForLogin = wasBatchPausedForLogin
                        replacement.loadUrl("about:blank")
                        recordRuntimeEvent(
                            "jinhak-renderer-circuit-paused",
                            JSONObject()
                                .put("circuitBreaks", runtimeRendererCircuitBreaks)
                                .put("cooldownMs", JINHAK_RENDERER_CIRCUIT_COOLDOWN_MS)
                                .put("resumeSafePath", runtimeSafePath(resumeUrl))
                                .put("missionOriginSafePath", runtimeSafePath(jinhakMissionOriginRoute))
                                .put("automaticResumeEligible", runtimeRendererCircuitBreaks <= MAX_JINHAK_RENDERER_CIRCUIT_BREAKS_PER_SESSION),
                            synchronous = true
                        )
                        persistRuntimeCheckpoint(forceResume = wasUnifiedRunning)

                        if (runtimeRendererCircuitBreaks > MAX_JINHAK_RENDERER_CIRCUIT_BREAKS_PER_SESSION) {
                            status.text = "WebView renderer 반복 충돌 · 체크포인트 저장 후 안전 정지했습니다. 앱을 다시 열면 이어서 복구합니다."
                            return@runCatching
                        }

                        status.text = "WebView renderer 반복 충돌 · 체크포인트 저장 완료 · 30초 안전 대기 후 재개합니다."
                        handler.postDelayed({
                            if (runtimeRendererCircuitGeneration != circuitGeneration ||
                                !unifiedRunning || provider != ProviderId.JINHAK) return@postDelayed
                            runtimeRendererCrashWindowStartedAtMs = System.currentTimeMillis()
                            runtimeRendererCrashCount = 0
                            batchRunning = wasBatchRunning
                            batchPausedForLogin = wasBatchPausedForLogin
                            batchCollecting = false
                            val missionOrigin = jinhakMissionOriginRoute.takeIf { it.isNotBlank() }
                            val safeResume = missionOrigin
                                ?: JinhakSiteTopology.missionSeeds().firstOrNull()?.takeIf { it.isNotBlank() }
                                ?: resumeUrl
                            currentBatchTarget = currentBatchTarget?.takeIf { it.isNotBlank() } ?: safeResume
                            recordRuntimeEvent(
                                "jinhak-renderer-circuit-resume",
                                JSONObject()
                                    .put("circuitBreaks", runtimeRendererCircuitBreaks)
                                    .put("resumeSafePath", runtimeSafePath(safeResume))
                                    .put("resumeFromMissionOrigin", missionOrigin != null)
                                    .put("batchRunning", batchRunning),
                                synchronous = true
                            )
                            status.text = "WebView renderer 안전 대기 종료 · 보존된 mission 지점에서 재개합니다."
                            replacement.loadUrl(safeResume)
                        }, JINHAK_RENDERER_CIRCUIT_COOLDOWN_MS)
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
                                .put("rendererCircuitBreaks", runtimeRendererCircuitBreaks)
                                .put("activityRecreated", false),
                            synchronous = true
                        )
                        status.text = "WebView renderer 복구 실패 · 앱 재실행 시 체크포인트에서 복구합니다."
                    }
                }, 250L)
                return true
            }
        }

        webView.webChromeClient'''
main = regex_replace_once(main, renderer_pattern, renderer_replacement, 'renderer handler')

# Cloud checkpoint helper. It sends only buildJinhakDigest output, which is already bounded and
# privacy-sanitized; no DOM/HTML/query/cookie/session token/form value/credential is added.
checkpoint_helper = '''    private fun checkpointJinhakCaptureToCloud(
        trigger: String,
        digest: JSONObject,
        safeRoute: String,
        pageType: String
    ) {
        if (!cloudOffload.isConfigured() || safeRoute.isBlank()) return
        val explicitContext = ObservationEvidence.explicitContextFromDigest(digest)
        val identity = ObservationEvidence.identity(
            ProviderId.JINHAK.wireName,
            safeRoute,
            explicitContext,
            digest
        )
        val checkpointRecord = JSONObject()
            .put("provider", ProviderId.JINHAK.wireName)
            .put("recordType", "jinhak-capture-checkpoint")
            .put("sourceRowFingerprint", "jinhak-capture:${identity.observationId}")
            .put("year", JSONObject.NULL)
            .put("university", JSONObject.NULL)
            .put("department", JSONObject.NULL)
            .put("admission", JSONObject.NULL)
            .put("metrics", JSONObject()
                .put("pageType", pageType.take(80))
                .put("trigger", trigger.take(80))
                .put("recordCount", digest.optInt("recordCount", 0))
                .put("schemaVersion", digest.optInt("schemaVersion", 0))
                .put("privacy", "sanitized-visible-admission-text-only"))
            .put("sourcePage", safeRoute.take(500))
            .put("sourceRowOrdinal", 0)
            .put("confidence", "crash-safe-checkpoint")
            .put("rawEvidence", digest.toString())

        jinhakCloudRecordCheckpointsQueued += 1
        cloudOffload.sendRecordCheckpoint(
            ProviderId.JINHAK.wireName,
            VERSION,
            JSONArray().put(checkpointRecord)
        ) { result ->
            runOnUiThread {
                if (result.isSuccess) {
                    jinhakCloudRecordCheckpointsSucceeded += 1
                } else {
                    jinhakCloudRecordCheckpointsFailed += 1
                    recordRuntimeEvent(
                        "jinhak-cloud-record-checkpoint-failed",
                        JSONObject()
                            .put("safePath", safeRoute.take(300))
                            .put("pageType", pageType.take(80))
                            .put("trigger", trigger.take(80))
                            .put("failureCount", jinhakCloudRecordCheckpointsFailed)
                            .put("errorClass", result.exceptionOrNull()?.javaClass?.simpleName?.take(80) ?: JSONObject.NULL)
                    )
                }
            }
        }
    }

'''
main = replace_once(
    main,
    '    private fun persistLiveJinhakDiagnostics(trigger: String, force: Boolean = false) {\n',
    checkpoint_helper + '    private fun persistLiveJinhakDiagnostics(trigger: String, force: Boolean = false) {\n',
    'checkpoint helper insertion'
)

# Insert cloud record checkpoints at all three local Jinhak persistence paths.
main = replace_once(
    main,
    '                localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)\n            }\n            batchSnapshots.put(snapshotForLocalExport(snapshot))',
    '                localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)\n                checkpointJinhakCaptureToCloud("slow-lane-completed", digest, safeRoute, pageType)\n            }\n            batchSnapshots.put(snapshotForLocalExport(snapshot))',
    'slow-lane cloud checkpoint'
)

main = replace_once(
    main,
    '''                        localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)
                    persistLiveJinhakDiagnostics("capture")
                        unifiedJinhakCapturedPages.add(localPageKey)''',
    '''                        localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)
                        checkpointJinhakCaptureToCloud("unified-user-viewed-page", lastJinhakDigest, safeRouteKey, pageType)
                        persistLiveJinhakDiagnostics("capture")
                        unifiedJinhakCapturedPages.add(localPageKey)''',
    'single-page cloud checkpoint'
)

main = replace_once(
    main,
    '                    localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)\n                }\n            }\n            if (activeAction != null && LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {',
    '                    localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)\n                    checkpointJinhakCaptureToCloud("batch-capture", digest, safeRoute, batchPageType)\n                }\n            }\n            if (activeAction != null && LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {',
    'batch cloud checkpoint'
)

# Add v0.9.20 counters to live diagnostics so the next exported/cloud log proves what happened.
main = replace_once(
    main,
    '                .put("legacyBatchCollecting", batchCollecting)\n                .put("activeMissionTarget", jinhakActiveMissionTargetId != null)',
    '''                .put("legacyBatchCollecting", batchCollecting)
                .put("cloudRecordCheckpointsQueued", jinhakCloudRecordCheckpointsQueued)
                .put("cloudRecordCheckpointsSucceeded", jinhakCloudRecordCheckpointsSucceeded)
                .put("cloudRecordCheckpointsFailed", jinhakCloudRecordCheckpointsFailed)
                .put("rendererCrashCountInWindow", runtimeRendererCrashCount)
                .put("rendererCrashWindowAgeMs", if (runtimeRendererCrashWindowStartedAtMs > 0L) (now - runtimeRendererCrashWindowStartedAtMs).coerceAtLeast(0L) else JSONObject.NULL)
                .put("rendererLastCrashAgeMs", if (runtimeRendererLastCrashAtMs > 0L) (now - runtimeRendererLastCrashAtMs).coerceAtLeast(0L) else JSONObject.NULL)
                .put("rendererCircuitBreaks", runtimeRendererCircuitBreaks)
                .put("activeMissionTarget", jinhakActiveMissionTargetId != null)''',
    'live checkpoint diagnostics'
)

# Dedicated provider-scoped record checkpoint path in CloudOffloadCoordinator. It deliberately
# does not touch activeRunId/activeProvider, preventing an ADIGA active run from receiving Jinhak.
cloud = replace_once(
    cloud,
    '    private var pendingFinish: PendingFinish? = null\n',
    '''    private var pendingFinish: PendingFinish? = null
    private val recordCheckpointRunIds = linkedMapOf<String, String>()
    private val recordCheckpointRunResolving = linkedSetOf<String>()
    private val pendingRecordCheckpoints = linkedMapOf<String, ArrayDeque<RecordCheckpointRequest>>()
''',
    'cloud checkpoint fields'
)
cloud = replace_once(
    cloud,
    '''    data class PendingFinish(
        val reason: String,
        val summaryJson: String
    )

''',
    '''    data class PendingFinish(
        val reason: String,
        val summaryJson: String
    )

    data class RecordCheckpointRequest(
        val provider: String,
        val collectorVersion: String,
        val recordsJson: String,
        val callback: (Result<String>) -> Unit
    )

''',
    'cloud checkpoint request data class'
)

cloud_methods = '''    /**
     * Persist privacy-sanitized admission records to a provider-specific cloud run without
     * mutating the coordinator's active batch run. This is used by Jinhak user-session mission
     * traversal as a crash-safe incremental checkpoint, not as an unattended crawler.
     */
    fun sendRecordCheckpoint(
        sourceProvider: String,
        collectorVersion: String,
        records: JSONArray,
        callback: (Result<String>) -> Unit = {}
    ) {
        if (!isConfigured()) {
            callback(Result.failure(IllegalStateException("cloud-offload-not-configured")))
            return
        }
        if (records.length() <= 0) {
            callback(Result.failure(IllegalArgumentException("empty-record-checkpoint")))
            return
        }
        val provider = sourceProvider.trim().take(40)
        if (provider.isBlank()) {
            callback(Result.failure(IllegalArgumentException("blank-record-checkpoint-provider")))
            return
        }
        val request = RecordCheckpointRequest(provider, collectorVersion.take(40), records.toString(), callback)
        var readyRun: String? = null
        var shouldResolve = false
        var queueRejected = false
        synchronized(lock) {
            ensureClientLocked()
            readyRun = recordCheckpointRunIds[provider]
            if (readyRun == null) {
                val queue = pendingRecordCheckpoints.getOrPut(provider) { ArrayDeque() }
                if (queue.size >= MAX_RECORD_CHECKPOINT_QUEUE) {
                    queueRejected = true
                } else {
                    queue.addLast(request)
                    shouldResolve = recordCheckpointRunResolving.add(provider)
                }
            }
        }
        if (queueRejected) {
            callback(Result.failure(IllegalStateException("record-checkpoint-queue-full")))
            return
        }
        readyRun?.let {
            uploadRecordCheckpoint(it, request)
            return
        }
        if (shouldResolve) resolveRecordCheckpointRun(provider, collectorVersion)
    }

    private fun resolveRecordCheckpointRun(provider: String, collectorVersion: String) {
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (currentClient == null) {
            completeRecordCheckpointRunResolution(provider, null, IllegalStateException("cloud-client-unavailable"))
            return
        }
        currentClient.getLatestActiveRun(provider) { lookup ->
            lookup.fold(
                onSuccess = { existing ->
                    if (!existing.isNullOrBlank()) {
                        completeRecordCheckpointRunResolution(provider, existing, null)
                    } else {
                        currentClient.createRun(
                            provider,
                            collectorVersion,
                            JSONObject()
                                .put("mode", "crash-safe-record-checkpoint")
                                .put("source", "android-user-session-mission")
                                .put("browserSessionMaterialAccepted", false)
                                .put("credentialExported", false)
                                .put("sessionSecretExported", false)
                        ) { created ->
                            created.fold(
                                onSuccess = { completeRecordCheckpointRunResolution(provider, it, null) },
                                onFailure = { completeRecordCheckpointRunResolution(provider, null, it) }
                            )
                        }
                    }
                },
                onFailure = { completeRecordCheckpointRunResolution(provider, null, it) }
            )
        }
    }

    private fun completeRecordCheckpointRunResolution(provider: String, runId: String?, error: Throwable?) {
        val queued = mutableListOf<RecordCheckpointRequest>()
        synchronized(lock) {
            recordCheckpointRunResolving.remove(provider)
            if (!runId.isNullOrBlank()) recordCheckpointRunIds[provider] = runId
            pendingRecordCheckpoints.remove(provider)?.let { q ->
                while (q.isNotEmpty()) queued += q.removeFirst()
            }
        }
        if (runId.isNullOrBlank()) {
            val failure = error ?: IllegalStateException("record-checkpoint-run-unavailable")
            lastError = failure.message
            queued.forEach { it.callback(Result.failure(failure)) }
            return
        }
        queued.forEach { uploadRecordCheckpoint(runId, it) }
    }

    private fun uploadRecordCheckpoint(runId: String, request: RecordCheckpointRequest) {
        val parsed = runCatching { JSONArray(request.recordsJson) }
        if (parsed.isFailure) {
            request.callback(Result.failure(parsed.exceptionOrNull() ?: IllegalArgumentException("record-checkpoint-json-invalid")))
            return
        }
        val currentClient = synchronized(lock) { ensureClientLocked(); client }
        if (currentClient == null) {
            request.callback(Result.failure(IllegalStateException("cloud-client-unavailable")))
            return
        }
        currentClient.uploadChunk(
            runId = runId,
            provider = request.provider,
            records = parsed.getOrThrow(),
            page = null,
            error = null
        ) { result ->
            result.onFailure { lastError = it.message }
            request.callback(result.map { runId })
        }
    }

'''
cloud = replace_once(
    cloud,
    '    fun sendDiagnostic(\n',
    cloud_methods + '    fun sendDiagnostic(\n',
    'cloud checkpoint methods insertion'
)
cloud = replace_once(
    cloud,
    '        private const val MAX_PENDING_CHUNKS = 200\n',
    '        private const val MAX_PENDING_CHUNKS = 200\n        private const val MAX_RECORD_CHECKPOINT_QUEUE = 64\n',
    'cloud checkpoint queue limit'
)

# Fix the diagnostic reader's argv-size failure by streaming JSON through files instead of a
# shell argument. Output remains sanitized and the token stays in the Authorization header only.
read_diag = '''name: Read Jinhak Diagnostic

on:
  push:
    branches: [ main ]
    paths:
      - ".github/workflows/read-jinhak-diagnostic.yml"
      - ".diagnostics/jinhak-read-request.txt"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  read-jinhak-diagnostic:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    env:
      WORKER_URL: https://admission-collector-offload.gigagene1234.workers.dev
      INGEST_TOKEN: ${{ secrets.ADMISSION_INGEST_TOKEN }}
    steps:
      - name: Read latest Jinhak diagnostic only
        shell: bash
        run: |
          set -euo pipefail
          test -n "$INGEST_TOKEN"
          mkdir -p out
          curl -fsS -H "Authorization: Bearer $INGEST_TOKEN" \
            "$WORKER_URL/v1/runs/latest?provider=jinhak-diagnostic" \
            -o out/latest.json
          echo -n "LATEST_JINHAK_DIAGNOSTIC_RUN="
          cat out/latest.json
          echo
          run_id="$(jq -r '.runId // empty' out/latest.json)"
          if [ -z "$run_id" ]; then
            echo "NO_JINHAK_DIAGNOSTIC_RUN"
            exit 0
          fi
          curl -fsS -H "Authorization: Bearer $INGEST_TOKEN" \
            "$WORKER_URL/v1/runs/$run_id/status" \
            -o out/status.json
          python3 - out/status.json <<'PY'
          import json, sys
          with open(sys.argv[1], 'r', encoding='utf-8') as f:
              payload=json.load(f)
          run=payload.get('run') or {}
          errors=payload.get('recentErrors') or []
          print('JINHAK_DIAGNOSTIC_RUN_SUMMARY=' + json.dumps({
              'run_id': run.get('run_id'),
              'provider': run.get('provider'),
              'collector_version': run.get('collector_version'),
              'uploaded_chunks': run.get('uploaded_chunks'),
              'processed_chunks': run.get('processed_chunks'),
              'error_count': run.get('error_count'),
              'updated_at': run.get('updated_at'),
          }, ensure_ascii=False, separators=(',',':')))
          for i,e in enumerate(errors):
              detail=e.get('detail_json')
              try: detail=json.loads(detail) if isinstance(detail,str) else detail
              except Exception: pass
              print(f'JINHAK_DIAGNOSTIC_EVENT_{i}=' + json.dumps({
                  'error_type': e.get('error_type'),
                  'created_at': e.get('created_at'),
                  'detail': detail,
              }, ensure_ascii=False, separators=(',',':')))
          PY
'''

# Compile-time/source safety checks before writing.
assert 'private const val VERSION = "0.9.20"' in main
assert 'private const val BUILD_CODE = 109200' in main
assert 'checkpointJinhakCaptureToCloud(' in main
assert main.count('checkpointJinhakCaptureToCloud("') == 3
assert 'jinhak-renderer-circuit-paused' in main
assert 'jinhak-renderer-circuit-resume' in main
assert 'MAX_JINHAK_RENDERER_CIRCUIT_BREAKS_PER_SESSION = 2' in main
assert 'fun sendRecordCheckpoint(' in cloud
assert 'browserSessionMaterialAccepted", false' in cloud
assert 'credentialExported", false' in cloud
assert 'sessionSecretExported", false' in cloud

MAIN.write_text(main)
CLOUD.write_text(cloud)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
READ_DIAG.write_text(read_diag)
print('v0.9.20 Crash-Safe Checkpoint patch applied')
