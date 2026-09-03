from pathlib import Path

main_p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle_p = Path('app/build.gradle.kts')
manifest_p = Path('app/src/main/AndroidManifest.xml')
main = main_p.read_text()
gradle = gradle_p.read_text()
manifest = manifest_p.read_text()


def must_replace(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing replacement anchor: {label}')
    return text.replace(old, new, 1)

main = must_replace(main, 'private const val VERSION = "0.9.5"', 'private const val VERSION = "0.9.6"', 'version')
main = must_replace(main, 'private const val BUILD_CODE = 10950', 'private const val BUILD_CODE = 10960', 'build')
gradle = must_replace(gradle, 'versionCode = 10950', 'versionCode = 10960', 'gradle-code')
gradle = must_replace(gradle, 'versionName = "0.9.5"', 'versionName = "0.9.6"', 'gradle-name')
manifest = must_replace(
    manifest,
    'Admission Collector v0.9.5 Passive Login Surface Auto Login',
    'Admission Collector v0.9.6 Auth Resume Fence',
    'manifest-label'
)

main = must_replace(
    main,
    '    private var credentialLoginSurfaceSeenAtMs = 0L\n    private var startupAuthIndeterminatePolls = 0\n',
    '''    private var credentialLoginSurfaceSeenAtMs = 0L
    private var credentialLoginSurfaceDetections = 0
    private var credentialAutoLoginSubmissions = 0
    private var credentialAutoLoginSuccesses = 0
    private var credentialAutoLoginFailures = 0
    private var credentialAutoLoginLastResult = ""
    private var credentialAutoLoginLastProvider = ""
    private var credentialAutoLoginLastAtMs = 0L
    private var batchRenderedLoginSurfacePauses = 0
    private var crossVersionResumeBlocks = 0
    private var startupAuthIndeterminatePolls = 0
''',
    'auth-telemetry-vars'
)

resume_anchor = '''        val session = localStore.unifiedStatus(sessionId)
        if (!requested || session.optString("status") != "running") return false
'''
resume_replacement = '''        val session = localStore.unifiedStatus(sessionId)
        if (!requested || session.optString("status") != "running") return false
        // v0.9.6: never continue a running unified session created by another collector
        // version. Cross-version resume mixes old navigation/auth state with new code and
        // makes login diagnostics impossible to interpret. Preserve the old local data by
        // stopping only the unified session envelope, then start a fresh current-version run.
        val sessionCollectorVersion = session.optString("collectorVersion")
        if (sessionCollectorVersion.isNotBlank() && sessionCollectorVersion != VERSION) {
            crossVersionResumeBlocks += 1
            localStore.updateUnifiedSession(
                sessionId,
                session.optString("phase", "interrupted"),
                "stopped",
                "cross-version-resume-blocked:$sessionCollectorVersion->$VERSION"
            )
            prefs.edit().putBoolean("resumeUnified", false).apply()
            recordRuntimeEvent(
                "cross-version-session-resume-blocked",
                JSONObject()
                    .put("fromVersion", sessionCollectorVersion.take(40))
                    .put("toVersion", VERSION)
                    .put("dataPreserved", true)
            )
            return false
        }
'''
main = must_replace(main, resume_anchor, resume_replacement, 'cross-version-resume-fence')

old_batch_finished = '''                if (batchRunning && !batchPausedForLogin) {
                    disarmBatchNavigationWatchdog()
                    if (batchNavigationWatchdogRecovery) {
                        batchNavigationWatchdogRecovery = false
                        return
                    }
                    val pending = pendingBatchPageAction
                    if (pending != null && sameBatchDocument(url, pending.baseUrl)) {
                        executePendingBatchPageAction()
                    } else {
                        scheduleBatchSnapshot()
                    }
                    return
                }
'''
new_batch_finished = '''                if (batchRunning && !batchPausedForLogin) {
                    // v0.9.6: authentication is a gate in front of snapshot processing. A
                    // protected target that redirects to a rendered login form must not be
                    // counted as a failed/visited document and skipped. Detect first, pause
                    // while keeping currentBatchTarget intact, then retry that exact target
                    // after the login surface disappears.
                    continueBatchAfterRenderedLoginGuard(url, 0)
                    return
                }
'''
main = must_replace(main, old_batch_finished, new_batch_finished, 'batch-page-auth-gate')

pause_anchor = '    private fun pauseBatchForLogin(autoOpenLogin: Boolean = true) {'
if pause_anchor not in main:
    raise SystemExit('missing replacement anchor: pause-helper-insertion')
new_helpers = r'''    private fun pauseBatchForRenderedLoginSurface(which: ProviderId, reason: String) {
        if (!batchRunning || batchPausedForLogin || provider != which) return
        batchRenderedLoginSurfacePauses += 1
        batchPausedForLogin = true
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        hideBatchCover()
        sessionState.text = "○ ${which.displayName} 로그인 화면 감지 · 자동 로그인 중"
        status.text = "현재 수집 대상을 보존한 채 로그인 처리를 기다립니다. 로그인 성공 후 같은 대상을 다시 엽니다."
        recordRuntimeEvent(
            "rendered-login-surface-batch-pause",
            JSONObject()
                .put("provider", which.wireName)
                .put("reason", reason.take(40))
                .put("currentTarget", runtimeSafePath(currentBatchTarget))
                .put("proactiveLoginNavigation", false)
        )
    }

    private fun continueBatchAfterRenderedLoginGuard(url: String, attempt: Int) {
        if (!batchRunning || batchPausedForLogin) return
        val expectedProvider = provider
        probeLoginSurface(expectedProvider) { probe ->
            if (!batchRunning || batchPausedForLogin || provider != expectedProvider) return@probeLoginSurface
            if (probe.optBoolean("detected", false)) {
                pauseBatchForRenderedLoginSurface(expectedProvider, "batch-page-finished")
                if (credentialVault.has(expectedProvider.wireName)) {
                    attemptSavedCredentialLogin(expectedProvider, "batch-login-surface")
                } else if (startupCredentialPromptedProvider != expectedProvider) {
                    startupCredentialPromptedProvider = expectedProvider
                    showCredentialDialog(expectedProvider, continueAfterSave = true)
                }
                return@probeLoginSurface
            }
            // A login-looking URL is only a reason to wait briefly for SPA hydration; it
            // is never treated as proof of logout and never triggers navigation by itself.
            if (isProviderLoginUrl(expectedProvider, url) && attempt < 3) {
                val delay = when (attempt) { 0 -> 250L; 1 -> 650L; else -> 1_200L }
                handler.postDelayed({ continueBatchAfterRenderedLoginGuard(url, attempt + 1) }, delay)
                return@probeLoginSurface
            }
            disarmBatchNavigationWatchdog()
            if (batchNavigationWatchdogRecovery) {
                batchNavigationWatchdogRecovery = false
                return@probeLoginSurface
            }
            val pending = pendingBatchPageAction
            if (pending != null && sameBatchDocument(url, pending.baseUrl)) {
                executePendingBatchPageAction()
            } else {
                scheduleBatchSnapshot()
            }
        }
    }

'''
main = main.replace(pause_anchor, new_helpers + pause_anchor, 1)

old_schedule = '''    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {
        if (provider != which) return
        val generation = ++credentialLoginSurfaceGeneration
        val delays = longArrayOf(100L, 420L, 1_050L, 2_300L)
        delays.forEach { delay ->
            handler.postDelayed({
                if (provider != which || generation != credentialLoginSurfaceGeneration) return@postDelayed
                probeLoginSurface(which) { probe ->
                    if (provider != which || generation != credentialLoginSurfaceGeneration) return@probeLoginSurface
                    if (!probe.optBoolean("detected", false)) return@probeLoginSurface
                    sessionState.text = "○ ${which.displayName} 로그인 화면 감지"
                    status.text = "${which.displayName} 로그인 폼을 실제 DOM에서 감지했습니다. 저장된 계정이 있으면 현재 화면에서 자동 로그인합니다."
'''
new_schedule = '''    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {
        if (provider != which) return
        val generation = ++credentialLoginSurfaceGeneration
        var detectionCounted = false
        val delays = longArrayOf(100L, 420L, 1_050L, 2_300L)
        delays.forEach { delay ->
            handler.postDelayed({
                if (provider != which || generation != credentialLoginSurfaceGeneration) return@postDelayed
                probeLoginSurface(which) { probe ->
                    if (provider != which || generation != credentialLoginSurfaceGeneration) return@probeLoginSurface
                    if (!probe.optBoolean("detected", false)) return@probeLoginSurface
                    if (!detectionCounted) {
                        detectionCounted = true
                        credentialLoginSurfaceDetections += 1
                        credentialAutoLoginLastProvider = which.wireName
                        credentialAutoLoginLastAtMs = System.currentTimeMillis()
                    }
                    if (batchRunning && !batchPausedForLogin) {
                        pauseBatchForRenderedLoginSurface(which, reason)
                    }
                    sessionState.text = "○ ${which.displayName} 로그인 화면 감지"
                    status.text = "${which.displayName} 로그인 폼을 실제 DOM에서 감지했습니다. 저장된 계정이 있으면 현재 화면에서 자동 로그인합니다."
'''
main = must_replace(main, old_schedule, new_schedule, 'surface-detection-telemetry-pause')

old_success = '''                if (!authenticated && !needsLogin && !loginSurface && credentialAwaitingLoginExitProvider == provider) {
                    authenticated = true
                    credentialAwaitingLoginExitProvider = null
                    credentialLoginSurfaceKey = ""
                    credentialLoginSurfaceAttempts = 0
                }
'''
new_success = '''                if (!authenticated && !needsLogin && !loginSurface && credentialAwaitingLoginExitProvider == provider) {
                    authenticated = true
                    credentialAutoLoginSuccesses += 1
                    credentialAutoLoginLastResult = "success-login-surface-exited"
                    credentialAutoLoginLastProvider = provider.wireName
                    credentialAutoLoginLastAtMs = now
                    recordRuntimeEvent(
                        "credential-auto-login-success",
                        JSONObject()
                            .put("provider", provider.wireName)
                            .put("successes", credentialAutoLoginSuccesses)
                            .put("credentialExported", false)
                    )
                    credentialAwaitingLoginExitProvider = null
                    credentialLoginSurfaceKey = ""
                    credentialLoginSurfaceAttempts = 0
                }
'''
main = must_replace(main, old_success, new_success, 'auto-login-success-telemetry')

old_error = '''            if (probe.optBoolean("credentialError", false) && credentialLoginSurfaceAttempts > 0) {
                sessionState.text = "△ ${which.displayName} 저장 계정 로그인 오류 감지"
                status.text = "저장된 계정으로 로그인한 뒤 오류 문구가 감지되어 반복 제출을 중지했습니다. 계정 설정을 확인해주세요."
                return@probeLoginSurface
            }
'''
new_error = '''            if (probe.optBoolean("credentialError", false) && credentialLoginSurfaceAttempts > 0) {
                if (credentialAutoLoginLastResult != "credential-error") credentialAutoLoginFailures += 1
                credentialAutoLoginLastResult = "credential-error"
                credentialAutoLoginLastProvider = which.wireName
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                credentialAwaitingLoginExitProvider = null
                sessionState.text = "△ ${which.displayName} 저장 계정 로그인 오류 감지"
                status.text = "저장된 계정으로 로그인한 뒤 오류 문구가 감지되어 반복 제출을 중지했습니다. 계정 설정을 확인해주세요."
                return@probeLoginSurface
            }
'''
main = must_replace(main, old_error, new_error, 'auto-login-error-telemetry')

old_result = '''                credentialAutoLoginInFlight = false
                val result = decodeJsString(encoded).take(80)
                recordRuntimeEvent("credential-auto-login-attempt", JSONObject()
'''
new_result = '''                credentialAutoLoginInFlight = false
                val result = decodeJsString(encoded).take(80)
                credentialAutoLoginLastResult = result
                credentialAutoLoginLastProvider = which.wireName
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                if (result.startsWith("submitted")) {
                    credentialAutoLoginSubmissions += 1
                } else {
                    credentialAutoLoginFailures += 1
                }
                recordRuntimeEvent("credential-auto-login-attempt", JSONObject()
'''
main = must_replace(main, old_result, new_result, 'auto-login-result-telemetry')

# Add final diagnostics. These values contain only booleans/counters/provider names/results;
# never usernames, passwords, cookies, tokens or form values.
diag_anchor = '                        .put("applicationBoundAgentActions", jinhakApplicationBoundActions)\n'
diag_replacement = '''                        .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
                        .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                        .put("credentialAutoLoginSubmissions", credentialAutoLoginSubmissions)
                        .put("credentialAutoLoginSuccesses", credentialAutoLoginSuccesses)
                        .put("credentialAutoLoginFailures", credentialAutoLoginFailures)
                        .put("credentialAutoLoginLastResult", credentialAutoLoginLastResult.take(80))
                        .put("credentialAutoLoginLastProvider", credentialAutoLoginLastProvider.take(20))
                        .put("credentialAutoLoginLastAtMs", credentialAutoLoginLastAtMs)
                        .put("batchRenderedLoginSurfacePauses", batchRenderedLoginSurfacePauses)
                        .put("crossVersionResumeBlocks", crossVersionResumeBlocks)
                        .put("applicationBoundAgentActions", jinhakApplicationBoundActions)
'''
main = must_replace(main, diag_anchor, diag_replacement, 'final-auth-diagnostics')

# Also expose the same auth counters in the PRECHECK block so a fresh-run export proves
# whether credentials were present before collection bootstrap. Later outcome counters are
# captured in jinhakDiagnosticsSummary.
pre_anchor = '                    .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)),\n'
pre_replacement = '''                    .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                    .put("loginSurfaceDetectionsAtBootstrap", credentialLoginSurfaceDetections)
                    .put("credentialAutoLoginSubmissionsAtBootstrap", credentialAutoLoginSubmissions)
                    .put("credentialAutoLoginSuccessesAtBootstrap", credentialAutoLoginSuccesses)
                    .put("credentialExported", false)),
'''
main = must_replace(main, pre_anchor, pre_replacement, 'precheck-auth-diagnostics')

main_p.write_text(main)
gradle_p.write_text(gradle)
manifest_p.write_text(manifest)
print('v0.9.6 patch applied')
