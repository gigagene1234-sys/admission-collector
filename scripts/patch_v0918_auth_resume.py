from pathlib import Path

MAIN = Path("app/src/main/java/com/admissionhub/collector/MainActivity.kt")
GRADLE = Path("app/build.gradle.kts")
MANIFEST = Path("app/src/main/AndroidManifest.xml")
WORKFLOW = Path(".github/workflows/build-admission-collector-main.yml")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


main = MAIN.read_text()

# Version bump only. All pre-v0.9.18 mission/auth/safety behavior remains cumulative.
main = replace_once(main, 'private const val VERSION = "0.9.17"', 'private const val VERSION = "0.9.18"', "MainActivity VERSION")
main = replace_once(main, 'private const val BUILD_CODE = 109170', 'private const val BUILD_CODE = 109180', "MainActivity BUILD_CODE")

# Durable, privacy-safe auth continuity telemetry. These fields contain only booleans,
# timestamps, bounded state strings, and the already-sanitized probe result. No URL query,
# cookie, storage, form value, credential, or token is persisted here.
main = replace_once(
    main,
    '    private var jinhakRealAuthProbeBaselineAutoFailures = 0\n',
    '''    private var jinhakRealAuthProbeBaselineAutoFailures = 0\n    private var jinhakActivityResumeAuthRevalidations = 0\n    private var jinhakRuntimeAuthEvidenceRestored = false\n    private var jinhakRuntimeAuthPreviousVerified = false\n''',
    "auth resume fields",
)

old_checkpoint = '''    private fun persistRuntimeCheckpoint(forceResume: Boolean = unifiedRunning) {\n        runCatching {\n            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit()\n                .putBoolean("resumeUnified", forceResume)\n                .putString("provider", provider.wireName)\n                .putString("phase", unifiedPhase)\n                .putString("safePath", runtimeLastSafePath)\n                .putInt("batchPageCount", batchPageCount)\n                .putInt("queueSize", batchQueue.size)\n                .putInt("errorCount", batchErrors.length())\n                .apply()\n        }\n        if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {\n            persistJinhakMissionRuntimeState("runtime-checkpoint")\n        }\n    }\n'''
new_checkpoint = '''    private fun persistRuntimeCheckpoint(forceResume: Boolean = unifiedRunning) {\n        runCatching {\n            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit()\n                .putBoolean("resumeUnified", forceResume)\n                .putString("provider", provider.wireName)\n                .putString("phase", unifiedPhase)\n                .putString("safePath", runtimeLastSafePath)\n                .putInt("batchPageCount", batchPageCount)\n                .putInt("queueSize", batchQueue.size)\n                .putInt("errorCount", batchErrors.length())\n                .apply()\n        }\n        persistJinhakAuthRuntimeEvidence()\n        if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {\n            persistJinhakMissionRuntimeState("runtime-checkpoint")\n        }\n    }\n\n    private fun persistJinhakAuthRuntimeEvidence() {\n        runCatching {\n            // v0.9.18: this checkpoint is deliberately credential-free. It preserves only\n            // sanitized auth evidence so an Activity/process recreation cannot make a\n            // successful Real Auth Probe look like \"never-run\". A restored verified bit is\n            // diagnostic evidence only; collection still has to revalidate protected core.\n            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit()\n                .putString("jinhakAuthEvidenceVersion", VERSION)\n                .putString("jinhakRealAuthProbeResult", jinhakRealAuthProbeResult.take(80))\n                .putLong("jinhakRealAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)\n                .putBoolean("jinhakRealAuthRouteCycleDetected", jinhakRealAuthProbeRouteCycleDetected)\n                .putBoolean("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)\n                .putString("jinhakCoreBootstrapState", jinhakCoreBootstrapState.take(80))\n                .putLong("jinhakLastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)\n                .putString("jinhakLastAuthEvidence", jinhakLastAuthEvidence.take(80))\n                .putInt("jinhakActivityResumeAuthRevalidations", jinhakActivityResumeAuthRevalidations)\n                .commit()\n        }\n    }\n\n    private fun restoreJinhakAuthRuntimeEvidence(): Boolean {\n        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)\n        if (prefs.getString("jinhakAuthEvidenceVersion", "") != VERSION) return false\n        if (!prefs.contains("jinhakRealAuthProbeResult") && !prefs.contains("jinhakLastCoreVerifiedAtMs")) return false\n        jinhakRealAuthProbeResult = prefs.getString("jinhakRealAuthProbeResult", "never-run").orEmpty().take(80)\n        jinhakRealAuthProbeVerifiedAtMs = prefs.getLong("jinhakRealAuthProbeVerifiedAtMs", 0L)\n        jinhakRealAuthProbeRouteCycleDetected = prefs.getBoolean("jinhakRealAuthRouteCycleDetected", false)\n        jinhakRuntimeAuthPreviousVerified = prefs.getBoolean("jinhakAuthVerifiedForBatch", false)\n        jinhakCoreBootstrapState = prefs.getString("jinhakCoreBootstrapState", "idle").orEmpty().take(80)\n        jinhakLastCoreVerifiedAtMs = prefs.getLong("jinhakLastCoreVerifiedAtMs", 0L)\n        jinhakLastAuthEvidence = prefs.getString("jinhakLastAuthEvidence", "none").orEmpty().take(80)\n        jinhakActivityResumeAuthRevalidations = prefs.getInt("jinhakActivityResumeAuthRevalidations", 0)\n        jinhakRuntimeAuthEvidenceRestored = true\n        return true\n    }\n'''
main = replace_once(main, old_checkpoint, new_checkpoint, "runtime checkpoint")

# A completed standalone probe must become durable before auto-continuation starts navigating.
main = replace_once(
    main,
    '        realJinhakAuthProbeButton.text = "진학사 실제 로그인 진단"\n        unifiedButton.isEnabled = true\n        val output = JSONObject()\n',
    '        realJinhakAuthProbeButton.text = "진학사 실제 로그인 진단"\n        unifiedButton.isEnabled = true\n        persistJinhakAuthRuntimeEvidence()\n        val output = JSONObject()\n',
    "persist real auth probe result",
)

# Every protected-core verification refreshes the durable safe evidence too.
main = replace_once(
    main,
    '        runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }\n        persistJinhakAuthDiagnostics("$reason-auth-verified")\n',
    '        runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }\n        persistJinhakAuthRuntimeEvidence()\n        persistJinhakAuthDiagnostics("$reason-auth-verified")\n',
    "persist protected-core verification",
)

# v0.9.17 restored the mission ledger but then reopened Jinhak home and left the pending-start
# flag armed. v0.9.18 restores only safe auth evidence for diagnostics and ALWAYS places a
# protected-core revalidation gate in front of mission resume. The persisted mission target is
# intentionally not overwritten by the core probe URL.
old_resume = '''            unifiedPendingAdigaStart = false\n            unifiedPendingJinhakStart = true\n            unifiedJinhakAutoCapture = false\n            val restoredMissionTargets = restoreJinhakMissionPersistence(sessionId, "activity-resume")\n            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()\n            status.text = if (lease?.restored == true) {\n                "이전 중단 감지: 암호화 로그인 세션과 mission ${restoredMissionTargets}개를 복구하고 진학사 에이전트를 체크포인트에서 재개합니다."\n            } else {\n                "이전 중단 감지: 저장된 브라우저 세션을 검증한 뒤 진학사 에이전트를 재개합니다."\n            }\n            webView.loadUrl(ProviderId.JINHAK.homeUrl)\n            true\n'''
new_resume = '''            unifiedPendingAdigaStart = false\n            unifiedPendingJinhakStart = false\n            unifiedJinhakAutoCapture = false\n            val restoredMissionTargets = restoreJinhakMissionPersistence(sessionId, "activity-resume")\n            val restoredAuthEvidence = restoreJinhakAuthRuntimeEvidence()\n            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()\n\n            // Never trust an in-memory verified flag across Activity/process recreation. Preserve\n            // the previous proof only as diagnostics, then require two fresh protected-core\n            // stability passes before startBatch() may run.\n            jinhakActivityResumeAuthRevalidations += 1\n            jinhakTransitionAuthChecks += 1\n            jinhakTransitionAuthGateActive = true\n            jinhakAuthVerifiedForBatch = false\n            jinhakProtectedCoreStablePasses = 0\n            jinhakCoreBootstrapState = "activity-resume-core-revalidate"\n            jinhakLastAuthEvidence = "activity-resume-revalidation-pending"\n            jinhakLoginRecoveryGeneration += 1\n            recordRuntimeEvent("jinhak-activity-resume-auth-revalidation", JSONObject()\n                .put("restoredMissionTargets", restoredMissionTargets)\n                .put("restoredAuthEvidence", restoredAuthEvidence)\n                .put("previouslyVerified", jinhakRuntimeAuthPreviousVerified)\n                .put("realAuthProbeResult", jinhakRealAuthProbeResult.take(80))\n                .put("realAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)\n                .put("credentialStored", credentialVault.has(ProviderId.JINHAK.wireName))\n                .put("credentialExported", false)\n                .put("sessionSecretExported", false))\n            persistJinhakAuthRuntimeEvidence()\n            persistJinhakAuthDiagnostics("activity-resume-auth-revalidation-start")\n\n            status.text = if (lease?.restored == true) {\n                "이전 중단 감지: mission ${restoredMissionTargets}개와 암호화 세션을 복구했습니다. 보호 경로 인증을 다시 확인한 뒤 기존 target을 재개합니다."\n            } else {\n                "이전 중단 감지: mission ${restoredMissionTargets}개를 복구했습니다. 보호 경로 인증을 다시 확인한 뒤 기존 target을 재개합니다."\n            }\n            val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()\n            if (coreProbe.isBlank()) {\n                jinhakAuthVerificationFailures += 1\n                jinhakCoreBootstrapState = "activity-resume-core-probe-missing"\n                persistJinhakAuthRuntimeEvidence()\n                persistJinhakAuthDiagnostics("activity-resume-core-probe-missing")\n                status.text = "진학사 보호 경로가 없어 재시작 세션을 안전하게 재개하지 않습니다."\n            } else {\n                webView.loadUrl(coreProbe)\n            }\n            true\n'''
main = replace_once(main, old_resume, new_resume, "Jinhak activity resume gate")

# Make the continuity behavior visible in auth diagnostics and final/live crawl diagnostics.
auth_anchor = '                    .put("realJinhakAuthRouteTransitions", jinhakRealAuthProbeRouteEvents.length())\n'
auth_extra = auth_anchor + '''                    .put("activityResumeAuthRevalidations", jinhakActivityResumeAuthRevalidations)\n                    .put("runtimeAuthEvidenceRestored", jinhakRuntimeAuthEvidenceRestored)\n                    .put("runtimeAuthPreviousVerified", jinhakRuntimeAuthPreviousVerified)\n'''
main = replace_once(main, auth_anchor, auth_extra, "auth diagnostics resume fields")

live_anchor = '                .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)\n                .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)\n'
live_extra = '                .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)\n                .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)\n                .put("activityResumeAuthRevalidations", jinhakActivityResumeAuthRevalidations)\n                .put("runtimeAuthEvidenceRestored", jinhakRuntimeAuthEvidenceRestored)\n'
main = replace_once(main, live_anchor, live_extra, "live diagnostics resume fields")

final_anchor = '                        .put("jinhakTransitionAuthChecks", jinhakTransitionAuthChecks)\n                        .put("jinhakSessionKeepAliveTicks", jinhakSessionKeepAliveTicks)\n'
final_extra = '                        .put("jinhakTransitionAuthChecks", jinhakTransitionAuthChecks)\n                        .put("activityResumeAuthRevalidations", jinhakActivityResumeAuthRevalidations)\n                        .put("runtimeAuthEvidenceRestored", jinhakRuntimeAuthEvidenceRestored)\n                        .put("runtimeAuthPreviousVerified", jinhakRuntimeAuthPreviousVerified)\n                        .put("realJinhakAuthProbeResult", jinhakRealAuthProbeResult.take(80))\n                        .put("realJinhakAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)\n                        .put("jinhakSessionKeepAliveTicks", jinhakSessionKeepAliveTicks)\n'
main = replace_once(main, final_anchor, final_extra, "final diagnostics resume fields")

MAIN.write_text(main)

# APK metadata must identify the patched build unambiguously.
gradle = GRADLE.read_text()
gradle = replace_once(gradle, 'versionCode = 109170', 'versionCode = 109180', "Gradle versionCode")
gradle = replace_once(gradle, 'versionName = "0.9.17"', 'versionName = "0.9.18"', "Gradle versionName")
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Collector v0.9.17 Real Jinhak Auth Gate"',
    'android:label="Admission Collector v0.9.18 Auth Resume Revalidation"',
    "manifest label",
)
MANIFEST.write_text(manifest)

# The current source correctly keeps Jinhak deterministic batch crawl disabled. The legacy
# main CI assertion still expects true and would reject the safety invariant on the next push.
workflow = WORKFLOW.read_text()
workflow = replace_once(
    workflow,
    "grep -q 'override val supportsBatchCrawl = true' \"$ADAPTER\"",
    "grep -q 'override val supportsBatchCrawl = false' \"$ADAPTER\"",
    "main workflow Jinhak batch safety assertion",
)
WORKFLOW.write_text(workflow)

print("v0.9.18 patch applied")
