from pathlib import Path

main_p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
store_p = Path('app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt')
service_p = Path('app/src/main/java/com/admissionhub/collector/CollectionKeepAliveService.kt')
gradle_p = Path('app/build.gradle.kts')
manifest_p = Path('app/src/main/AndroidManifest.xml')

main = main_p.read_text()
store = store_p.read_text()
service = service_p.read_text()
gradle = gradle_p.read_text()
manifest = manifest_p.read_text()


def must_replace(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing replacement anchor: {label}')
    return text.replace(old, new, 1)

# Version metadata.
main = must_replace(main, 'private const val VERSION = "0.9.7"', 'private const val VERSION = "0.9.8"', 'version')
main = must_replace(main, 'private const val BUILD_CODE = 10970', 'private const val BUILD_CODE = 10980', 'build')
gradle = must_replace(gradle, 'versionCode = 10970', 'versionCode = 10980', 'gradle-code')
gradle = must_replace(gradle, 'versionName = "0.9.7"', 'versionName = "0.9.8"', 'gradle-name')
manifest = must_replace(
    manifest,
    'Admission Collector v0.9.7 Verified Auth Susi Core',
    'Admission Collector v0.9.8 Auth Recovery KeepAlive',
    'manifest-label'
)

# Auth recovery diagnostics/state. No secret/cookie/form values are persisted.
state_anchor = '''    private var startupJinhakProtectedProbeAttempted = false
    private var startupAuthIndeterminatePolls = 0
    private var jinhakBatchStartCount = 0
'''
state_new = '''    private var startupJinhakProtectedProbeAttempted = false
    private var startupAuthIndeterminatePolls = 0
    private var jinhakProtectedCoreStablePasses = 0
    private var jinhakTransitionAuthGateActive = false
    private var jinhakLoginRecoveryGeneration = 0
    private var jinhakLoginRecoveryPolls = 0
    private var jinhakReauthCycles = 0
    private var jinhakAuthVerificationFailures = 0
    private var jinhakTransitionAuthChecks = 0
    private var jinhakLastCoreVerifiedAtMs = 0L
    private var jinhakLastAuthEvidence = "none"
    private var jinhakSessionKeepAliveTicks = 0
    private var jinhakSessionKeepAliveBackgroundTicks = 0
    private var jinhakSessionExtensionClicks = 0
    private var jinhakBatchStartCount = 0
'''
main = must_replace(main, state_anchor, state_new, 'v098-state')

const_anchor = '''        private const val LOGIN_PREFLIGHT_DOM_SETTLE_MS = 300L
        private const val LOGIN_PREFLIGHT_POLL_MS = 1_500L
        private const val MAX_CLOUD_FRONTIER_CLAIM_ATTEMPTS = 3
'''
const_new = '''        private const val LOGIN_PREFLIGHT_DOM_SETTLE_MS = 300L
        private const val LOGIN_PREFLIGHT_POLL_MS = 1_500L
        private const val JINHAK_LOGIN_RECOVERY_POLL_MS = 1_500L
        private const val JINHAK_CORE_AUTH_STABLE_PASSES = 2
        private const val MAX_CLOUD_FRONTIER_CLAIM_ATTEMPTS = 3
'''
main = must_replace(main, const_anchor, const_new, 'v098-constants')

# Keep the session-extension loop alive while a unified/batch/preflight run is active, even
# when the Activity loses foreground focus. The foreground service keeps the process priority;
# this runnable now keeps the browser-side extension/recovery logic alive too.
keepalive_old = '''    private val sessionKeepAlive = object : Runnable {
        override fun run() {
            attemptSessionExtension()
            handler.postDelayed(this, 45_000L)
        }
    }
'''
keepalive_new = '''    private val sessionKeepAlive = object : Runnable {
        override fun run() {
            val active = unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive
            if (active) {
                if (provider == ProviderId.JINHAK) {
                    jinhakSessionKeepAliveTicks += 1
                    if (!hasWindowFocus()) jinhakSessionKeepAliveBackgroundTicks += 1
                }
                attemptSessionExtension()
                if (provider == ProviderId.JINHAK) {
                    val current = webView.url.orEmpty()
                    if (batchPausedForLogin || jinhakTransitionAuthGateActive || isProviderLoginUrl(ProviderId.JINHAK, current)) {
                        scheduleJinhakLoginRecovery("session-keepalive")
                    } else if (batchRunning) {
                        checkSessionState { needsLogin, _ ->
                            if (batchRunning && provider == ProviderId.JINHAK && needsLogin) {
                                batchPausedForLogin = true
                                jinhakAuthVerifiedForBatch = false
                                jinhakCoreBootstrapState = "keepalive-login-recovery"
                                jinhakReauthCycles += 1
                                persistJinhakAuthDiagnostics("keepalive-needs-login")
                                scheduleJinhakLoginRecovery("keepalive-needs-login")
                            }
                        }
                    }
                    persistJinhakAuthDiagnostics("session-keepalive")
                }
            }
            handler.postDelayed(this, 45_000L)
        }
    }
'''
main = must_replace(main, keepalive_old, keepalive_new, 'background-keepalive-runnable')

# A login form disappearing is NOT authentication proof. v0.9.7 could mark a transient SPA
# transition as success. Keep the submitted credential in pending-verification state until a
# protected Susi core route is stably reachable.
false_success_old = '''                if (!authenticated && !needsLogin && !loginSurface && credentialAwaitingLoginExitProvider == provider) {
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
false_success_new = '''                if (!authenticated && !needsLogin && !loginSurface && credentialAwaitingLoginExitProvider == provider) {
                    credentialAutoLoginLastResult = "submitted-awaiting-provider-verification"
                    credentialAutoLoginLastProvider = provider.wireName
                    credentialAutoLoginLastAtMs = now
                    if (provider == ProviderId.JINHAK) {
                        jinhakAuthVerifiedForBatch = false
                        jinhakCoreBootstrapState = "credential-submitted-awaiting-core-verification"
                    }
                }
'''
main = must_replace(main, false_success_old, false_success_new, 'remove-surface-exit-auth-proof')

# After a credential submission, Jinhak verification continues even when the DOM classifier is
# indeterminate. This closes the dead state where both needsLogin/authenticated were false.
post_submit_old = '''                        } else if (needsLogin) {
                            scheduleLoginSurfaceDetection(which, "post-submit")
                        }
                    }
                }, 1_100L)
'''
post_submit_new = '''                        } else if (needsLogin) {
                            scheduleLoginSurfaceDetection(which, "post-submit")
                            if (which == ProviderId.JINHAK) scheduleJinhakLoginRecovery("post-submit-needs-login")
                        } else if (which == ProviderId.JINHAK) {
                            scheduleJinhakLoginRecovery("post-submit-provider-verification")
                        }
                    }
                }, 1_100L)
'''
main = must_replace(main, post_submit_old, post_submit_new, 'post-submit-verification-loop')

# Reset v0.9.8 auth recovery state on a fresh login/collection bootstrap.
reset_anchor = '''        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "auth-preflight"
        startupJinhakProtectedProbeAttempted = false

        // v0.9.2: restore the encrypted provider session bundles first.
'''
reset_new = '''        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "auth-preflight"
        startupJinhakProtectedProbeAttempted = false
        jinhakProtectedCoreStablePasses = 0
        jinhakTransitionAuthGateActive = false
        jinhakLoginRecoveryGeneration += 1
        jinhakLoginRecoveryPolls = 0
        jinhakReauthCycles = 0
        jinhakAuthVerificationFailures = 0
        jinhakTransitionAuthChecks = 0
        jinhakLastCoreVerifiedAtMs = 0L
        jinhakLastAuthEvidence = "none"
        jinhakSessionKeepAliveTicks = 0
        jinhakSessionKeepAliveBackgroundTicks = 0
        jinhakSessionExtensionClicks = 0

        // v0.9.2: restore the encrypted provider session bundles first.
'''
main = must_replace(main, reset_anchor, reset_new, 'reset-v098-state')

# Do not count every 1.5s login-route poll as a distinct pause. Keep a separate poll counter.
route_old = '''                    if (isProviderLoginUrl(expectedProvider, currentUrl)) {
                        loginRouteFallbackPauses += 1
                        if (expectedProvider == ProviderId.JINHAK) {
                            jinhakAuthVerifiedForBatch = false
                            jinhakCoreBootstrapState = "login-route-wait"
                        }
'''
route_new = '''                    if (isProviderLoginUrl(expectedProvider, currentUrl)) {
                        if (expectedProvider == ProviderId.JINHAK) {
                            jinhakLoginRecoveryPolls += 1
                            jinhakProtectedCoreStablePasses = 0
                            if (jinhakCoreBootstrapState != "login-route-wait") {
                                loginRouteFallbackPauses += 1
                                jinhakReauthCycles += 1
                            }
                            jinhakAuthVerifiedForBatch = false
                            jinhakCoreBootstrapState = "login-route-wait"
                        } else {
                            loginRouteFallbackPauses += 1
                        }
'''
main = must_replace(main, route_old, route_new, 'login-route-counter-semantics')

# Protected-route verification must be stable across consecutive probes, not a single transient
# frame after the login form disappears.
core_old = '''                    if (startupJinhakProtectedProbeAttempted && probeCanonical.isNotBlank() && currentCanonical == probeCanonical && !needsLogin) {
                        jinhakAuthVerifiedForBatch = true
                        jinhakCoreBootstrapState = "protected-route-authenticated"
                        recordRuntimeEvent("jinhak-protected-auth-probe-success", JSONObject()
                            .put("safePath", runtimeSafePath(currentUrl))
                            .put("loginUrl", false))
                        onStartupProviderAuthenticated(expectedProvider, generation)
                        return@probeLoginSurface
                    }
'''
core_new = '''                    if (startupJinhakProtectedProbeAttempted && probeCanonical.isNotBlank() && currentCanonical == probeCanonical && !needsLogin && !isProviderLoginUrl(expectedProvider, currentUrl)) {
                        jinhakProtectedCoreStablePasses += 1
                        if (jinhakProtectedCoreStablePasses >= JINHAK_CORE_AUTH_STABLE_PASSES) {
                            jinhakAuthVerifiedForBatch = true
                            jinhakCoreBootstrapState = "protected-route-authenticated"
                            jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
                            jinhakLastAuthEvidence = "protected-core-stable"
                            recordRuntimeEvent("jinhak-protected-auth-probe-success", JSONObject()
                                .put("safePath", runtimeSafePath(currentUrl))
                                .put("loginUrl", false)
                                .put("stablePasses", jinhakProtectedCoreStablePasses))
                            onStartupProviderAuthenticated(expectedProvider, generation)
                        } else {
                            scheduleStartupLoginPoll(expectedProvider, generation)
                        }
                        return@probeLoginSurface
                    } else if (expectedProvider == ProviderId.JINHAK) {
                        jinhakProtectedCoreStablePasses = 0
                    }
'''
main = must_replace(main, core_old, core_new, 'stable-protected-core-auth')

# Record the evidence class that authenticated the provider. For Jinhak, protected-core stable
# verification is preferred; logout-control is still accepted when actually rendered.
auth_anchor = '''        } else {
            startupLoginJinhakAuthenticated = true
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "authenticated"
        }
'''
auth_new = '''        } else {
            startupLoginJinhakAuthenticated = true
            jinhakAuthVerifiedForBatch = true
            if (jinhakLastAuthEvidence == "none") jinhakLastAuthEvidence = "rendered-authenticated-control"
            if (jinhakLastCoreVerifiedAtMs == 0L && canonicalizeBatchUrl(webView.url.orEmpty()) == canonicalizeBatchUrl(JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty())) {
                jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
                jinhakLastAuthEvidence = "protected-core-stable"
            }
            jinhakCoreBootstrapState = "authenticated"
        }
'''
main = must_replace(main, auth_anchor, auth_new, 'auth-evidence-class')

# PRECHECK carries the new auth diagnostics.
precheck_anchor = '''                    .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                    .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                    .put("credentialExported", false)),
'''
precheck_new = '''                    .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                    .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                    .put("jinhakLastAuthEvidence", jinhakLastAuthEvidence)
                    .put("jinhakLastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                    .put("jinhakLoginRecoveryPolls", jinhakLoginRecoveryPolls)
                    .put("jinhakReauthCycles", jinhakReauthCycles)
                    .put("credentialExported", false)),
'''
main = must_replace(main, precheck_anchor, precheck_new, 'precheck-v098-auth-diagnostics')

# Revalidate Jinhak immediately after the Adiga phase instead of trusting authentication that may
# be several minutes old. The first protected Susi seed becomes the transition auth probe.
transition_state_anchor = '''        jinhakNormalizedCandidateBindingKeys.clear()
        jinhakNormalizedAmbiguousBindings = 0

        provider = ProviderId.JINHAK
'''
transition_state_new = '''        jinhakNormalizedCandidateBindingKeys.clear()
        jinhakNormalizedAmbiguousBindings = 0
        jinhakTransitionAuthGateActive = true
        jinhakAuthVerifiedForBatch = false
        jinhakProtectedCoreStablePasses = 0
        jinhakTransitionAuthChecks += 1
        jinhakCoreBootstrapState = "transition-core-revalidate"
        jinhakLastAuthEvidence = "transition-revalidation-pending"
        jinhakLoginRecoveryGeneration += 1

        provider = ProviderId.JINHAK
'''
main = must_replace(main, transition_state_anchor, transition_state_new, 'transition-auth-gate-state')

transition_tail_old = '''        status.text = "통합 수집 2/2 · 진학사 목적형 분석 준비: 저장대학→합격예측→모의지원→실제합격자→대학입결→성적/최저 순으로 우선 탐색합니다."
        webView.loadUrl(ProviderId.JINHAK.homeUrl)
    }

    private fun scheduleUnifiedJinhakAutoCapture(url: String) {
'''
transition_tail_new = '''        status.text = "통합 수집 2/2 · 진학사 보호 경로 인증을 다시 확인한 뒤 저장대학 미션을 시작합니다."
        val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull() ?: ProviderId.JINHAK.homeUrl
        currentBatchTarget = canonicalizeBatchUrl(coreProbe)
        persistJinhakAuthDiagnostics("transition-auth-probe-start")
        webView.loadUrl(coreProbe)
    }

    private fun persistJinhakAuthDiagnostics(trigger: String) {
        val sessionId = unifiedSessionId ?: return
        if (provider != ProviderId.JINHAK && unifiedPhase != "jinhak") return
        val secondsSinceCoreVerified = if (jinhakLastCoreVerifiedAtMs > 0L) {
            (System.currentTimeMillis() - jinhakLastCoreVerifiedAtMs).coerceAtLeast(0L) / 1000.0
        } else JSONObject.NULL
        runCatching {
            localStore.recordSyncState(
                sessionId,
                "JINHAK_AUTH_DIAGNOSTICS",
                ProviderId.JINHAK.wireName,
                JSONObject()
                    .put("trigger", trigger.take(80))
                    .put("safePath", runtimeSafePath(webView.url))
                    .put("currentTargetSafePath", runtimeSafePath(currentBatchTarget))
                    .put("authVerifiedForBatch", jinhakAuthVerifiedForBatch)
                    .put("coreBootstrapState", jinhakCoreBootstrapState)
                    .put("lastAuthEvidence", jinhakLastAuthEvidence)
                    .put("lastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                    .put("secondsSinceCoreVerified", secondsSinceCoreVerified)
                    .put("transitionAuthGateActive", jinhakTransitionAuthGateActive)
                    .put("batchRunning", batchRunning)
                    .put("batchPausedForLogin", batchPausedForLogin)
                    .put("loginRecoveryPolls", jinhakLoginRecoveryPolls)
                    .put("reauthCycles", jinhakReauthCycles)
                    .put("authVerificationFailures", jinhakAuthVerificationFailures)
                    .put("transitionAuthChecks", jinhakTransitionAuthChecks)
                    .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                    .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
                    .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                    .put("credentialAutoLoginSubmissions", credentialAutoLoginSubmissions)
                    .put("credentialAutoLoginSuccesses", credentialAutoLoginSuccesses)
                    .put("credentialAutoLoginFailures", credentialAutoLoginFailures)
                    .put("credentialAutoLoginLastResult", credentialAutoLoginLastResult.take(80))
                    .put("sessionKeepAliveTicks", jinhakSessionKeepAliveTicks)
                    .put("sessionKeepAliveBackgroundTicks", jinhakSessionKeepAliveBackgroundTicks)
                    .put("sessionExtensionClicks", jinhakSessionExtensionClicks)
                    .put("credentialExported", false)
                    .put("sessionSecretExported", false),
                batchPausedForLogin || jinhakTransitionAuthGateActive,
                false
            )
        }
    }

    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val generation = ++jinhakLoginRecoveryGeneration
        handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, 120L)
    }

    private fun pollJinhakLoginRecovery(reason: String, generation: Int) {
        if (provider != ProviderId.JINHAK || generation != jinhakLoginRecoveryGeneration) return
        val recoveryActive = startupLoginPreflightActive || jinhakTransitionAuthGateActive || (batchRunning && batchPausedForLogin)
        if (!recoveryActive) return
        jinhakLoginRecoveryPolls += 1
        val currentUrl = webView.url.orEmpty()
        if (isProviderLoginUrl(ProviderId.JINHAK, currentUrl)) {
            jinhakProtectedCoreStablePasses = 0
            if (jinhakCoreBootstrapState !in setOf("login-route-wait", "transition-login-wait", "batch-login-route-wait", "keepalive-login-recovery")) {
                loginRouteFallbackPauses += 1
                jinhakReauthCycles += 1
            }
            jinhakAuthVerifiedForBatch = false
            if (jinhakTransitionAuthGateActive) jinhakCoreBootstrapState = "transition-login-wait"
            else if (batchRunning) jinhakCoreBootstrapState = "batch-login-route-wait"
            persistJinhakAuthDiagnostics("$reason-login-route")
            probeLoginSurface(ProviderId.JINHAK) { probe ->
                if (provider != ProviderId.JINHAK || generation != jinhakLoginRecoveryGeneration) return@probeLoginSurface
                if (probe.optBoolean("detected", false)) {
                    if (credentialVault.has(ProviderId.JINHAK.wireName)) {
                        attemptSavedCredentialLogin(ProviderId.JINHAK, "persistent-$reason")
                    } else if (startupCredentialPromptedProvider != ProviderId.JINHAK) {
                        startupCredentialPromptedProvider = ProviderId.JINHAK
                        loginRouteFallbackCredentialPrompts += 1
                        showCredentialDialog(ProviderId.JINHAK, continueAfterSave = true)
                    }
                }
                handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, JINHAK_LOGIN_RECOVERY_POLL_MS)
            }
            return
        }

        val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
        val currentCanonical = canonicalizeBatchUrl(currentUrl)
        val coreCanonical = canonicalizeBatchUrl(coreProbe)
        if (coreCanonical.isBlank()) {
            jinhakAuthVerificationFailures += 1
            jinhakCoreBootstrapState = "core-auth-probe-missing"
            persistJinhakAuthDiagnostics("$reason-core-probe-missing")
            return
        }
        if (currentCanonical != coreCanonical) {
            jinhakProtectedCoreStablePasses = 0
            jinhakCoreBootstrapState = "recovery-core-probe-navigation"
            persistJinhakAuthDiagnostics("$reason-open-core-probe")
            webView.loadUrl(coreProbe)
            handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, JINHAK_LOGIN_RECOVERY_POLL_MS)
            return
        }

        checkSessionState { needsLogin, _ ->
            if (provider != ProviderId.JINHAK || generation != jinhakLoginRecoveryGeneration) return@checkSessionState
            val nowUrl = webView.url.orEmpty()
            if (needsLogin || isProviderLoginUrl(ProviderId.JINHAK, nowUrl)) {
                jinhakProtectedCoreStablePasses = 0
                jinhakAuthVerifiedForBatch = false
                jinhakCoreBootstrapState = "core-probe-login-required"
                persistJinhakAuthDiagnostics("$reason-core-probe-login-required")
                scheduleLoginSurfaceDetection(ProviderId.JINHAK, "persistent-$reason")
                handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, JINHAK_LOGIN_RECOVERY_POLL_MS)
                return@checkSessionState
            }
            jinhakProtectedCoreStablePasses += 1
            if (jinhakProtectedCoreStablePasses < JINHAK_CORE_AUTH_STABLE_PASSES) {
                jinhakCoreBootstrapState = "core-probe-stability-check"
                persistJinhakAuthDiagnostics("$reason-core-stability-${jinhakProtectedCoreStablePasses}")
                handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, JINHAK_LOGIN_RECOVERY_POLL_MS)
                return@checkSessionState
            }
            completeJinhakVerifiedAuth(reason)
        }
    }

    private fun completeJinhakVerifiedAuth(reason: String) {
        if (provider != ProviderId.JINHAK) return
        jinhakAuthVerifiedForBatch = true
        jinhakCoreBootstrapState = "protected-core-verified"
        jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
        jinhakLastAuthEvidence = "protected-core-stable"
        jinhakProtectedCoreStablePasses = 0
        if (credentialAwaitingLoginExitProvider == ProviderId.JINHAK) {
            credentialAwaitingLoginExitProvider = null
            credentialLoginSurfaceKey = ""
            credentialLoginSurfaceAttempts = 0
            if (credentialAutoLoginLastResult.startsWith("submitted")) {
                credentialAutoLoginSuccesses += 1
                credentialAutoLoginLastResult = "success-protected-core-verified"
                credentialAutoLoginLastProvider = ProviderId.JINHAK.wireName
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                recordRuntimeEvent("credential-auto-login-success", JSONObject()
                    .put("provider", ProviderId.JINHAK.wireName)
                    .put("successes", credentialAutoLoginSuccesses)
                    .put("verification", "protected-core-stable")
                    .put("credentialExported", false))
            }
        }
        runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }
        persistJinhakAuthDiagnostics("$reason-auth-verified")
        ++jinhakLoginRecoveryGeneration

        when {
            startupLoginPreflightActive -> {
                val generation = startupLoginPollGeneration
                onStartupProviderAuthenticated(ProviderId.JINHAK, generation)
            }
            jinhakTransitionAuthGateActive -> {
                jinhakTransitionAuthGateActive = false
                unifiedPendingJinhakStart = false
                status.text = "진학사 보호 경로 인증 재검증 완료 · 수시저장소 미션을 시작합니다."
                if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
            }
            batchRunning && batchPausedForLogin -> resumeBatchAfterVerifiedJinhakAuth(reason)
        }
    }

    private fun resumeBatchAfterVerifiedJinhakAuth(reason: String) {
        if (!batchRunning || provider != ProviderId.JINHAK) return
        batchPausedForLogin = false
        showBatchCover()
        sessionState.text = "● 진학사 인증 복구 · 동일 수집 target 재개"
        val retry = currentBatchTarget
        persistJinhakAuthDiagnostics("$reason-resume-target")
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)
            else loadNextBatchPage()
        }, 180L)
    }

    private fun handleJinhakTransitionAuthGate(url: String) {
        if (!unifiedRunning || unifiedPhase != "jinhak" || provider != ProviderId.JINHAK || !jinhakTransitionAuthGateActive || batchRunning) return
        runtimeLastSafePath = runtimeSafePath(url)
        scheduleJinhakLoginRecovery("transition-auth-gate")
    }

    private fun scheduleUnifiedJinhakAutoCapture(url: String) {
'''
main = must_replace(main, transition_tail_old, transition_tail_new, 'transition-core-auth-gate-and-helpers')

# The transition auth gate must run before the normal unifiedPendingJinhakStart branch.
onfinish_anchor = '''                if (unifiedRunning && unifiedPhase == "jinhak" && unifiedPendingJinhakStart && provider == ProviderId.JINHAK && !batchRunning) {
'''
onfinish_new = '''                if (unifiedRunning && unifiedPhase == "jinhak" && provider == ProviderId.JINHAK && jinhakTransitionAuthGateActive && !batchRunning) {
                    handleJinhakTransitionAuthGate(url)
                    return
                }
                if (unifiedRunning && unifiedPhase == "jinhak" && unifiedPendingJinhakStart && provider == ProviderId.JINHAK && !batchRunning) {
'''
main = must_replace(main, onfinish_anchor, onfinish_new, 'transition-gate-on-page-finished')

# A paused Jinhak batch must continuously recover; one page-finished session probe is not enough.
paused_old = '''                if (batchPausedForLogin) {
                    checkSessionState { needsLogin, authenticated ->
                        if (!needsLogin && authenticated) {
                            sessionState.text = "● 로그인 상태 복구 감지"
                            resumeAfterLogin()
                        }
                    }
                } else {
'''
paused_new = '''                if (batchPausedForLogin) {
                    if (provider == ProviderId.JINHAK) {
                        scheduleJinhakLoginRecovery("batch-paused-page-finished")
                    } else {
                        checkSessionState { needsLogin, authenticated ->
                            if (!needsLogin && authenticated) {
                                sessionState.text = "● 로그인 상태 복구 감지"
                                resumeAfterLogin()
                            }
                        }
                    }
                } else {
'''
main = must_replace(main, paused_old, paused_new, 'persistent-paused-login-recovery')

# v0.9.7 route fallback scheduled only four DOM probes. Use the persistent recovery loop for
# Jinhak, so a slowly hydrated login surface can never strand the run indefinitely.
batch_fallback_old = '''                if (credentialVault.has(expectedProvider.wireName)) {
                    status.text = "현재 수집 대상을 보존했습니다. 로그인 화면 렌더링을 기다리며 자동로그인을 재시도합니다."
                    scheduleLoginSurfaceDetection(expectedProvider, "batch-login-route-fallback")
                } else if (startupCredentialPromptedProvider != expectedProvider) {
'''
batch_fallback_new = '''                if (credentialVault.has(expectedProvider.wireName)) {
                    status.text = "현재 수집 대상을 보존했습니다. 로그인 화면이 늦게 렌더링되어도 계속 감지해 자동로그인 후 동일 target을 재개합니다."
                    if (expectedProvider == ProviderId.JINHAK) scheduleJinhakLoginRecovery("batch-login-route-fallback")
                    else scheduleLoginSurfaceDetection(expectedProvider, "batch-login-route-fallback")
                } else if (startupCredentialPromptedProvider != expectedProvider) {
'''
main = must_replace(main, batch_fallback_old, batch_fallback_new, 'persistent-batch-route-fallback')

# start/stop foreground collection also controls the browser keepalive callback.
start_keepalive_old = '''    private fun startCollectionKeepAlive() {
        runCatching { startForegroundService(Intent(this, CollectionKeepAliveService::class.java)) }
    }

    private fun stopCollectionKeepAlive() {
        runCatching { stopService(Intent(this, CollectionKeepAliveService::class.java)) }
    }
'''
start_keepalive_new = '''    private fun startCollectionKeepAlive() {
        runCatching { startForegroundService(Intent(this, CollectionKeepAliveService::class.java)) }
        handler.removeCallbacks(sessionKeepAlive)
        handler.postDelayed(sessionKeepAlive, 5_000L)
    }

    private fun stopCollectionKeepAlive() {
        runCatching { stopService(Intent(this, CollectionKeepAliveService::class.java)) }
        if (!unifiedRunning && !startupLoginPreflightActive && !jinhakTransitionAuthGateActive) {
            handler.removeCallbacks(sessionKeepAlive)
        }
    }
'''
main = must_replace(main, start_keepalive_old, start_keepalive_new, 'foreground-service-browser-keepalive')

# Count explicit provider session-extension clicks for diagnostics.
extension_old = '''                if (result == "true") {
                    CookieManager.getInstance().flush()
                    sessionState.text = "● 로그인 세션 자동 연장"
                }
'''
extension_new = '''                if (result == "true") {
                    CookieManager.getInstance().flush()
                    if (provider == ProviderId.JINHAK) {
                        jinhakSessionExtensionClicks += 1
                        persistJinhakAuthDiagnostics("session-extension-click")
                    }
                    sessionState.text = "● 로그인 세션 자동 연장"
                }
'''
main = must_replace(main, extension_old, extension_new, 'session-extension-click-diagnostic')

# Do not stop browser keepalive just because the Activity loses foreground focus while a run is
# active. This was the background-session hole in v0.9.7.
onpause_old = '''    override fun onPause() {
        handler.removeCallbacks(sessionKeepAlive)
        CookieManager.getInstance().flush()
        super.onPause()
    }
'''
onpause_new = '''    override fun onPause() {
        handler.removeCallbacks(sessionKeepAlive)
        if (unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive) {
            handler.postDelayed(sessionKeepAlive, 5_000L)
        }
        CookieManager.getInstance().flush()
        super.onPause()
    }
'''
main = must_replace(main, onpause_old, onpause_new, 'background-keepalive-onpause')

# Final crawl diagnostics include auth recovery/keepalive state.
final_diag_anchor = '''                        .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                        .put("jinhakCoreScopeBlockedUrls", jinhakCoreScopeBlockedUrls)
'''
final_diag_new = '''                        .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                        .put("jinhakLastAuthEvidence", jinhakLastAuthEvidence)
                        .put("jinhakLastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                        .put("jinhakLoginRecoveryPolls", jinhakLoginRecoveryPolls)
                        .put("jinhakReauthCycles", jinhakReauthCycles)
                        .put("jinhakAuthVerificationFailures", jinhakAuthVerificationFailures)
                        .put("jinhakTransitionAuthChecks", jinhakTransitionAuthChecks)
                        .put("jinhakSessionKeepAliveTicks", jinhakSessionKeepAliveTicks)
                        .put("jinhakSessionKeepAliveBackgroundTicks", jinhakSessionKeepAliveBackgroundTicks)
                        .put("jinhakSessionExtensionClicks", jinhakSessionExtensionClicks)
                        .put("jinhakCoreScopeBlockedUrls", jinhakCoreScopeBlockedUrls)
'''
main = must_replace(main, final_diag_anchor, final_diag_new, 'final-v098-auth-diag')

# Unified exports expose the latest auth diagnostics even if zero Jinhak snapshots were captured.
store_old = '''        out.put("jinhakDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_CRAWL_DIAGNOSTICS"))
        return out
'''
store_new = '''        out.put("jinhakDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_CRAWL_DIAGNOSTICS"))
            .put("jinhakAuthDiagnosticsSummary", latestSyncStateDetail(sessionId, "JINHAK_AUTH_DIAGNOSTICS"))
        return out
'''
store = must_replace(store, store_old, store_new, 'export-auth-diagnostics')

# Foreground-service notification now matches automatic re-auth behavior.
service = must_replace(
    service,
    '.setContentText("백그라운드 수집을 유지하고 있습니다. 로그인 만료 시 앱에서 갱신하세요.")',
    '.setContentText("백그라운드 수집·세션 연장을 유지하며 만료 시 target을 보존해 자동 재인증합니다.")',
    'service-notification'
)

main_p.write_text(main)
store_p.write_text(store)
service_p.write_text(service)
gradle_p.write_text(gradle)
manifest_p.write_text(manifest)
print('v0.9.8 patch applied')
