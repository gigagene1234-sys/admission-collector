from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


main = MAIN.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

required = [
    'private const val VERSION = "0.9.20"',
    'private const val BUILD_CODE = 109200',
    'installRuntimeCrashGuard()',
    'sendPendingRuntimeEvents()',
    'persistRuntimeCheckpoint(forceResume = unifiedRunning)',
    'jinhakCloudRecordCheckpointsSucceeded',
    'jinhakMissionCells.onRendererGone(',
    'restoreJinhakAuthProofCheckpoint("activity-create")',
    'private fun resumeInterruptedUnifiedSessionIfNeeded(): Boolean',
    'private fun finishUnifiedCollection(reason: String)',
]
missing = [x for x in required if x not in main]
if missing:
    raise SystemExit('v0.9.20 source precondition failed: ' + ', '.join(missing))

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.9.20"', 'private const val VERSION = "0.9.21"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 109200', 'private const val BUILD_CODE = 109210', 'main build code')
gradle = replace_once(gradle, 'versionCode = 109200', 'versionCode = 109210', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.9.20"', 'versionName = "0.9.21"', 'gradle version name')
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.20 Crash-Safe Checkpoint',
    'Admission Collector v0.9.21 Process Resume Journal',
    'manifest label'
)

# Runtime process journal state. This is operational telemetry only: no browser session material.
main = replace_once(
    main,
    '    private var jinhakCloudRecordCheckpointsFailed = 0\n',
    '''    private var jinhakCloudRecordCheckpointsFailed = 0
    private var processRuntimeId = ""
    private var processJournalPreviousUncleanTermination = false
    private var processResumeGatePending = false
    private var processResumeGateRuns = 0
    private var processHeartbeatGeneration = 0
    private var processHeartbeatAtMs = 0L
    private var processLastLifecycle = "created"
''',
    'process journal fields'
)

main = replace_once(
    main,
    '        private const val RUNTIME_PREFS = "collector_runtime_v064"\n',
    '''        private const val RUNTIME_PREFS = "collector_runtime_v064"
        private const val PROCESS_HEARTBEAT_MS = 15_000L
        private const val PROCESS_JOURNAL_SCHEMA = 1
''',
    'process journal constants'
)

# Initialize the journal only after local/cloud components exist, but before any automatic resume.
main = replace_once(
    main,
    '        configureWebView()\n        restoreJinhakAuthProofCheckpoint("activity-create")\n',
    '''        configureWebView()
        initializeProcessResumeJournal()
        restoreJinhakAuthProofCheckpoint("activity-create")
''',
    'journal initialization'
)

# A same-version unclean process restart must not blindly treat a deep report route as trusted.
# Keep the persisted mission ledger, but require the existing protected-core auth/bootstrap path.
main = replace_once(
    main,
    '        unifiedButton.text = "통합 수집 종료"\n        jinhakConsecutiveStalls = 0\n        batchRunning = false\n        batchCollecting = false\n',
    '''        unifiedButton.text = "통합 수집 종료"
        jinhakConsecutiveStalls = 0
        batchRunning = false
        batchCollecting = false
        if (processResumeGatePending && unifiedPhase == "jinhak") {
            processResumeGateRuns += 1
            jinhakAuthVerifiedForBatch = false
            jinhakCoreBootstrapState = "process-resume-auth-gate"
            jinhakTransitionAuthGateActive = false
            currentBatchTarget = null
            runtimeLastSafePath = ""
            recordRuntimeEvent(
                "process-resume-gate-armed",
                JSONObject()
                    .put("preservedMissionLedger", true)
                    .put("deepRouteDiscarded", true)
                    .put("authRevalidationRequired", true),
                synchronous = true
            )
        }
        activateProcessResumeJournal("resume-unified")
''',
    'same-version process resume gate'
)

# Activate process journaling on a fresh unified collection.
main = replace_once(
    main,
    '        unifiedSessionId = sessionId\n        unifiedRunning = true\n        unifiedPhase = "adiga"\n',
    '''        unifiedSessionId = sessionId
        unifiedRunning = true
        unifiedPhase = "adiga"
        activateProcessResumeJournal("start-unified")
''',
    'fresh unified journal activation'
)

# Explicit unified completion is a clean terminal point for the active collection journal.
main = replace_once(
    main,
    '            unifiedPhase = "completed"\n',
    '''            unifiedPhase = "completed"
            markProcessResumeJournalClean("unified-finish:${reason.take(80)}")
''',
    'clean unified finish journal'
)

# Lifecycle edges synchronously checkpoint the tiny journal while work is active.
main = replace_once(
    main,
    '    override fun onPause() {\n        handler.removeCallbacks(sessionKeepAlive)\n',
    '''    override fun onPause() {
        persistProcessResumeJournal("onPause", synchronous = true)
        handler.removeCallbacks(sessionKeepAlive)
''',
    'onPause journal'
)
main = replace_once(
    main,
    '    override fun onStop() {\n        CookieManager.getInstance().flush()\n',
    '''    override fun onStop() {
        persistProcessResumeJournal("onStop", synchronous = true)
        CookieManager.getInstance().flush()
''',
    'onStop journal'
)
main = replace_once(
    main,
    '    override fun onDestroy() {\n        if (::slowLanePool.isInitialized) slowLanePool.destroy()\n',
    '''    override fun onDestroy() {
        if (isFinishing && !unifiedRunning && !batchRunning) {
            markProcessResumeJournalClean("activity-finished-idle")
        } else {
            persistProcessResumeJournal("onDestroy-active-or-system", synchronous = true)
        }
        if (::slowLanePool.isInitialized) slowLanePool.destroy()
''',
    'onDestroy journal'
)
main = replace_once(
    main,
    '        if (level >= TRIM_MEMORY_RUNNING_LOW) {\n            recordRuntimeEvent("memory-trim", JSONObject().put("level", level))\n',
    '''        if (level >= TRIM_MEMORY_RUNNING_LOW) {
            recordRuntimeEvent("memory-trim", JSONObject().put("level", level))
            persistProcessResumeJournal("memory-trim-$level", synchronous = true)
''',
    'trim memory journal'
)

# Uncaught exceptions must synchronously persist the journal before the previous handler kills the process.
main = replace_once(
    main,
    '                persistRuntimeCheckpoint(forceResume = unifiedRunning)\n            }\n            previous?.uncaughtException(thread, throwable)\n',
    '''                persistProcessResumeJournal("uncaught-exception", synchronous = true)
                persistRuntimeCheckpoint(forceResume = unifiedRunning)
            }
            previous?.uncaughtException(thread, throwable)
''',
    'uncaught journal persistence'
)

# Remember the most recent sanitized runtime event type for next-start correlation.
main = replace_once(
    main,
    '            val editor = prefs.edit().putString("events", arr.toString())\n                .putBoolean("hasPendingEvents", true)\n',
    '''            val editor = prefs.edit().putString("events", arr.toString())
                .putString("lastRuntimeEventType", type.take(80))
                .putBoolean("hasPendingEvents", true)
''',
    'last runtime event type'
)

# Insert process journal helpers immediately before the existing runtime checkpoint helper.
journal_helpers = r'''    private fun initializeProcessResumeJournal() {
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        val previousActive = prefs.getBoolean("processJournalActive", false)
        val previousClean = prefs.getBoolean("processJournalClean", true)
        val previousVersion = prefs.getString("processJournalVersion", "").orEmpty()
        val previousRuntimeId = prefs.getString("processRuntimeId", "").orEmpty().take(80)
        val previousHeartbeat = prefs.getLong("processHeartbeatAtMs", 0L)
        val previousLifecycle = prefs.getString("processLastLifecycle", "unknown").orEmpty().take(80)
        val previousSafePath = prefs.getString("processLastSafePath", "").orEmpty().take(300)
        val previousProvider = prefs.getString("processLastProvider", "").orEmpty().take(30)
        val previousPhase = prefs.getString("processLastPhase", "").orEmpty().take(80)
        val previousTarget = prefs.getString("processLastMissionTarget", "").orEmpty().take(96)
        val previousAgentBusy = prefs.getBoolean("processAgentActionInFlight", false)
        val previousSnapshotBusy = prefs.getBoolean("processBatchCollecting", false)
        val previousLastEvent = prefs.getString("lastRuntimeEventType", "").orEmpty().take(80)
        val now = System.currentTimeMillis()

        processJournalPreviousUncleanTermination = previousActive && !previousClean && previousVersion == VERSION
        processResumeGatePending = processJournalPreviousUncleanTermination
        if (processJournalPreviousUncleanTermination) {
            recordRuntimeEvent(
                "unclean-process-termination-detected",
                JSONObject()
                    .put("previousRuntimeId", previousRuntimeId.ifBlank { JSONObject.NULL })
                    .put("previousHeartbeatAgeMs", if (previousHeartbeat > 0L) (now - previousHeartbeat).coerceAtLeast(0L) else JSONObject.NULL)
                    .put("previousLifecycle", previousLifecycle)
                    .put("previousSafePath", previousSafePath)
                    .put("previousProvider", previousProvider)
                    .put("previousPhase", previousPhase)
                    .put("previousMissionTarget", previousTarget.ifBlank { JSONObject.NULL })
                    .put("previousAgentActionInFlight", previousAgentBusy)
                    .put("previousBatchCollecting", previousSnapshotBusy)
                    .put("previousLastRuntimeEventType", previousLastEvent.ifBlank { JSONObject.NULL })
                    .put("credentialsPersisted", false)
                    .put("sessionSecretsPersisted", false),
                synchronous = true
            )
        }

        processRuntimeId = java.util.UUID.randomUUID().toString()
        processHeartbeatAtMs = now
        processLastLifecycle = "activity-create"
        prefs.edit()
            .putInt("processJournalSchema", PROCESS_JOURNAL_SCHEMA)
            .putString("processJournalVersion", VERSION)
            .putString("processRuntimeId", processRuntimeId)
            .putBoolean("processJournalActive", false)
            .putBoolean("processJournalClean", true)
            .putLong("processHeartbeatAtMs", now)
            .putString("processLastLifecycle", processLastLifecycle)
            .putBoolean("processCredentialStored", false)
            .putBoolean("processSessionSecretStored", false)
            .commit()
    }

    private fun activateProcessResumeJournal(trigger: String) {
        processResumeGatePending = processResumeGatePending && unifiedPhase == "jinhak"
        getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit()
            .putBoolean("processJournalActive", true)
            .putBoolean("processJournalClean", false)
            .putString("processJournalVersion", VERSION)
            .putString("processRuntimeId", processRuntimeId)
            .putString("processJournalActivation", trigger.take(80))
            .commit()
        persistProcessResumeJournal("active:$trigger", synchronous = true)
        armProcessResumeHeartbeat()
    }

    private fun markProcessResumeJournalClean(reason: String) {
        processHeartbeatGeneration += 1
        processLastLifecycle = "clean:$reason"
        getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit()
            .putBoolean("processJournalActive", false)
            .putBoolean("processJournalClean", true)
            .putString("processLastLifecycle", processLastLifecycle.take(120))
            .putLong("processHeartbeatAtMs", System.currentTimeMillis())
            .putString("processCleanReason", reason.take(120))
            .commit()
        processResumeGatePending = false
    }

    private fun armProcessResumeHeartbeat() {
        val generation = ++processHeartbeatGeneration
        handler.postDelayed(object : Runnable {
            override fun run() {
                if (generation != processHeartbeatGeneration) return
                val active = unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive
                if (!active) return
                persistProcessResumeJournal("heartbeat", synchronous = false)
                handler.postDelayed(this, PROCESS_HEARTBEAT_MS)
            }
        }, PROCESS_HEARTBEAT_MS)
    }

    private fun persistProcessResumeJournal(lifecycle: String, synchronous: Boolean = false) {
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        if (!prefs.getBoolean("processJournalActive", false)) return
        val now = System.currentTimeMillis()
        processHeartbeatAtMs = now
        processLastLifecycle = lifecycle.take(120)
        val currentUrl = if (::webView.isInitialized) runCatching { webView.url.orEmpty() }.getOrDefault("") else ""
        val safePath = runtimeSafePath(currentUrl).take(300)
        val targetId = jinhakActiveMissionTargetId.orEmpty().take(96)
        val summary = jinhakMissionTargetLedger.summary()
        val editor = prefs.edit()
            .putInt("processJournalSchema", PROCESS_JOURNAL_SCHEMA)
            .putString("processJournalVersion", VERSION)
            .putString("processRuntimeId", processRuntimeId)
            .putBoolean("processJournalActive", true)
            .putBoolean("processJournalClean", false)
            .putLong("processHeartbeatAtMs", now)
            .putString("processLastLifecycle", processLastLifecycle)
            .putString("processLastSafePath", safePath)
            .putString("processLastProvider", provider.wireName.take(30))
            .putString("processLastPhase", unifiedPhase.take(80))
            .putString("processLastMissionTarget", targetId)
            .putBoolean("processAgentActionInFlight", jinhakAgentActionInFlight)
            .putBoolean("processBatchCollecting", batchCollecting)
            .putInt("processMissionTargets", summary.optInt("targets", 0))
            .putInt("processMissionPending", summary.optInt("pending", 0))
            .putInt("processMissionConfirmed", summary.optJSONObject("states")?.optInt("confirmed", 0) ?: 0)
            .putInt("processRendererCrashCount", runtimeRendererCrashCount)
            .putInt("processRendererCircuitBreaks", runtimeRendererCircuitBreaks)
            .putBoolean("processCredentialStored", false)
            .putBoolean("processSessionSecretStored", false)
        if (synchronous) editor.commit() else editor.apply()
    }

'''
main = replace_once(
    main,
    '    private fun persistRuntimeCheckpoint(forceResume: Boolean = unifiedRunning) {\n',
    journal_helpers + '    private fun persistRuntimeCheckpoint(forceResume: Boolean = unifiedRunning) {\n',
    'process journal helpers'
)

# Export enough process state to distinguish renderer events from whole-process death on the next report.
main = replace_once(
    main,
    '                        .put("legacyAgentActionInFlight", jinhakAgentActionInFlight)\n                        .put("legacyBatchCollecting", batchCollecting)\n',
    '''                        .put("legacyAgentActionInFlight", jinhakAgentActionInFlight)
                        .put("legacyBatchCollecting", batchCollecting)
                        .put("processJournalActive", getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).getBoolean("processJournalActive", false))
                        .put("processJournalClean", getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).getBoolean("processJournalClean", true))
                        .put("processRuntimeId", processRuntimeId.take(80))
                        .put("previousUncleanTerminationDetected", processJournalPreviousUncleanTermination)
                        .put("processResumeGateRuns", processResumeGateRuns)
                        .put("processResumeGatePending", processResumeGatePending)
                        .put("processHeartbeatAgeMs", if (processHeartbeatAtMs > 0L) (System.currentTimeMillis() - processHeartbeatAtMs).coerceAtLeast(0L) else JSONObject.NULL)
                        .put("processLastLifecycle", processLastLifecycle.take(120))
                        .put("lastRuntimeEventType", getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).getString("lastRuntimeEventType", "").orEmpty().take(80))
                        .put("processCredentialStored", false)
                        .put("processSessionSecretStored", false)
''',
    'process diagnostics export'
)

# Strong safety checks before writing.
for forbidden in [
    '.putString("processCookie"',
    '.putString("processPassword"',
    '.putString("processToken"',
    'CookieManager.getCookie(',
]:
    if forbidden in journal_helpers:
        raise SystemExit('forbidden process journal material: ' + forbidden)

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('v0.9.21 Process Resume Journal patch applied')
