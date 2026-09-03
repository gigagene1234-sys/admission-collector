from pathlib import Path

main_p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
topology_p = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt')
gradle_p = Path('app/build.gradle.kts')
manifest_p = Path('app/src/main/AndroidManifest.xml')
main = main_p.read_text()
topology = topology_p.read_text()
gradle = gradle_p.read_text()
manifest = manifest_p.read_text()


def must_replace(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing replacement anchor: {label}')
    return text.replace(old, new, 1)

# Version metadata.
main = must_replace(main, 'private const val VERSION = "0.9.6"', 'private const val VERSION = "0.9.7"', 'version')
main = must_replace(main, 'private const val BUILD_CODE = 10960', 'private const val BUILD_CODE = 10970', 'build')
gradle = must_replace(gradle, 'versionCode = 10960', 'versionCode = 10970', 'gradle-code')
gradle = must_replace(gradle, 'versionName = "0.9.6"', 'versionName = "0.9.7"', 'gradle-name')
manifest = must_replace(
    manifest,
    'Admission Collector v0.9.6 Auth Resume Fence',
    'Admission Collector v0.9.7 Verified Auth Susi Core',
    'manifest-label'
)

# v0.9.7 diagnostics/state. Counters contain no credentials, cookies or tokens.
main = must_replace(
    main,
    '    private var crossVersionResumeBlocks = 0\n    private var startupAuthIndeterminatePolls = 0\n',
    '''    private var crossVersionResumeBlocks = 0
    private var staleSessionLeaseBypassesPrevented = 0
    private var loginRouteFallbackPauses = 0
    private var loginRouteFallbackCredentialPrompts = 0
    private var jinhakCoreScopeBlockedUrls = 0
    private val jinhakCoreScopeBlockedLaneCounts = linkedMapOf<String, Int>()
    private var jinhakAuthVerifiedForBatch = false
    private var jinhakCoreBootstrapState = "idle"
    private var startupJinhakProtectedProbeAttempted = false
    private var startupAuthIndeterminatePolls = 0
''',
    'v097-state-vars'
)

# Restored encrypted session data is only a cache hint. Never treat restoration as proof
# that the provider still accepts the session server-side.
old_direct = '''        if (startupLoginAdigaRestoredLease && startupLoginJinhakRestoredLease) {
            CookieManager.getInstance().flush()
            startupSessionPreflightBypassed = true
            startupLoginPreflightActive = false
            startupLoginPreflightVerified = true
            startupLoginStage = "stored-session-direct"
            startupLoginVerifiedAtMs = System.currentTimeMillis()
            startupLoginPollGeneration += 1
            unifiedButton.text = "통합 수집 시작 중"
            sessionState.text = "● 암호화 로그인 세션 복원 완료"
            status.text = "저장된 어디가·진학사 로그인 세션을 복원했습니다. 로그인 사전검사를 건너뛰고 통합 수집을 시작합니다."
            recordRuntimeEvent("startup-stored-session-direct", JSONObject()
                .put("trigger", startupLoginTrigger)
                .put("adigaRestored", true)
                .put("jinhakRestored", true)
                .put("credentialStoredLocally", credentialVault.has(ProviderId.ADIGA.wireName) || credentialVault.has(ProviderId.JINHAK.wireName))
                .put("credentialExported", false)
                .put("sessionSecretStoredLocally", true)
                .put("sessionSecretExported", false))
            handler.postDelayed({
                if (!unifiedRunning && !batchRunning && startupSessionPreflightBypassed) {
                    startUnifiedCollectionAuthenticated()
                }
            }, 300L)
            return
        }
'''
new_direct = '''        if (startupLoginAdigaRestoredLease && startupLoginJinhakRestoredLease) {
            CookieManager.getInstance().flush()
            staleSessionLeaseBypassesPrevented += 1
            startupSessionPreflightBypassed = false
            startupLoginStage = "stored-session-verification-required"
            sessionState.text = "△ 암호화 세션 복원 · 서버 인증 재검증 필요"
            status.text = "저장된 세션은 복원했지만 인증 성공으로 간주하지 않습니다. 보호 경로에서 실제 인증 상태를 확인합니다."
            recordRuntimeEvent("startup-stored-session-verification-required", JSONObject()
                .put("trigger", startupLoginTrigger)
                .put("adigaRestored", true)
                .put("jinhakRestored", true)
                .put("bypassPrevented", true)
                .put("credentialStoredLocally", credentialVault.has(ProviderId.ADIGA.wireName) || credentialVault.has(ProviderId.JINHAK.wireName))
                .put("credentialExported", false)
                .put("sessionSecretStoredLocally", true)
                .put("sessionSecretExported", false))
        }
'''
main = must_replace(main, old_direct, new_direct, 'remove-stored-session-direct-bypass')

# Reset per-bootstrap auth state so a second run in the same process cannot inherit a stale
# prompt or verification decision.
reset_anchor = '''        startupLoginUiOpenCount = 0
        startupLoginVerifiedAtMs = 0L
        startupSessionPreflightBypassed = false
'''
reset_new = '''        startupLoginUiOpenCount = 0
        startupLoginVerifiedAtMs = 0L
        startupSessionPreflightBypassed = false
        startupCredentialPromptedProvider = null
        credentialLoginSurfaceKey = ""
        credentialLoginSurfaceAttempts = 0
        credentialAwaitingLoginExitProvider = null
        credentialLoginSurfaceDetections = 0
        credentialAutoLoginSubmissions = 0
        credentialAutoLoginSuccesses = 0
        credentialAutoLoginFailures = 0
        credentialAutoLoginLastResult = ""
        credentialAutoLoginLastProvider = ""
        credentialAutoLoginLastAtMs = 0L
        loginRouteFallbackPauses = 0
        loginRouteFallbackCredentialPrompts = 0
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "auth-preflight"
        startupJinhakProtectedProbeAttempted = false
'''
main = must_replace(main, reset_anchor, reset_new, 'reset-v097-auth-state')

# Status text must describe the actual passive/protected-route verification model.
main = must_replace(
    main,
    '"자동 준비 1/3 · 어디가 로그인 세션을 확인합니다. 만료 시 로그인 화면을 자동으로 엽니다."',
    '"자동 준비 1/3 · 어디가 세션을 확인합니다. 저장 세션은 서버 응답으로 다시 검증합니다."',
    'adiga-preflight-status'
)
main = must_replace(
    main,
    '"자동 준비 2/3 · 진학사 로그인 세션을 확인합니다. 만료 시 로그인 화면을 자동으로 엽니다."',
    '"자동 준비 2/3 · 진학사 로그인 상태를 확인하고 필요하면 수시저장소 보호 경로로 검증합니다."',
    'jinhak-preflight-status'
)

# Replace permissive preflight fallback. Jinhak may become collection-ready only after
# actual authentication is observed or a protected read-only Susi route loads without
# redirecting to login. A real login URL is a pause/user-action signal, never success.
old_indeterminate = '''                // No rendered login surface: never navigate to login just because the auth
                // classifier is uncertain. After two stable probes, continue bootstrap and
                // let protected pages naturally redirect; the global surface detector then logs in.
                startupAuthIndeterminatePolls += 1
                if (!needsLogin && startupAuthIndeterminatePolls >= 2) {
                    recordRuntimeEvent("startup-login-provider-deferred", JSONObject()
                        .put("provider", expectedProvider.wireName)
                        .put("reason", "no-rendered-login-surface")
                        .put("forcedNavigation", false))
                    startupLoginPollGeneration += 1
                    startupLoginOpenAttempted = false
                    if (expectedProvider == ProviderId.ADIGA) {
                        sessionState.text = "△ 어디가 로그인 화면 없음 · 현재 화면 유지"
                        status.text = "어디가 로그인 화면을 강제로 열지 않고 진학사 확인으로 넘어갑니다. 보호 페이지에서 로그인 화면이 나타나면 자동 로그인합니다."
                        handler.postDelayed({ if (startupLoginPreflightActive) beginStartupLoginProvider(ProviderId.JINHAK) }, 200L)
                    } else {
                        sessionState.text = "△ 진학사 로그인 화면 없음 · 수집 중 감지 대기"
                        startupLoginPreflightActive = false
                        startupLoginPreflightVerified = true
                        startupLoginStage = "passive-login-surface-ready"
                        status.text = "로그인 화면 강제 이동 없이 통합 수집을 시작합니다. 수집 중 로그인 화면이 감지되는 즉시 자동 로그인합니다."
                        handler.postDelayed({ if (!unifiedRunning && !batchRunning) startUnifiedCollectionAuthenticated() }, 250L)
                    }
                    return@probeLoginSurface
                }
'''
new_indeterminate = '''                // v0.9.7: an indeterminate home page is never enough to approve the Jinhak
                // collection bootstrap. Verify a protected, read-only Susi route. If that
                // route redirects to login, keep the browser there and wait for credentials or
                // manual login; never advance the crawl and never mark the protected target failed.
                startupAuthIndeterminatePolls += 1
                if (startupAuthIndeterminatePolls >= 2) {
                    val currentUrl = webView.url.orEmpty()
                    if (isProviderLoginUrl(expectedProvider, currentUrl)) {
                        loginRouteFallbackPauses += 1
                        if (expectedProvider == ProviderId.JINHAK) {
                            jinhakAuthVerifiedForBatch = false
                            jinhakCoreBootstrapState = "login-route-wait"
                        }
                        recordRuntimeEvent("startup-login-route-wait", JSONObject()
                            .put("provider", expectedProvider.wireName)
                            .put("safePath", runtimeSafePath(currentUrl))
                            .put("renderedSurfaceDetected", false)
                            .put("proactiveLoginNavigation", false))
                        sessionState.text = "○ ${expectedProvider.displayName} 로그인 경로 감지 · 인증 대기"
                        if (credentialVault.has(expectedProvider.wireName)) {
                            status.text = "로그인 경로가 확인되었습니다. 현재 화면을 유지하며 저장 계정 자동입력용 로그인 폼 렌더링을 기다립니다."
                            scheduleLoginSurfaceDetection(expectedProvider, "startup-login-route-fallback")
                        } else if (startupCredentialPromptedProvider != expectedProvider) {
                            startupCredentialPromptedProvider = expectedProvider
                            loginRouteFallbackCredentialPrompts += 1
                            status.text = "로그인이 필요합니다. 이 기기에만 암호화 저장할 자동로그인 정보를 입력해주세요."
                            showCredentialDialog(expectedProvider, continueAfterSave = true)
                        }
                        scheduleStartupLoginPoll(expectedProvider, generation)
                        return@probeLoginSurface
                    }

                    if (expectedProvider == ProviderId.ADIGA) {
                        recordRuntimeEvent("startup-login-provider-deferred", JSONObject()
                            .put("provider", expectedProvider.wireName)
                            .put("reason", "public-baseline-no-login-surface")
                            .put("forcedNavigation", false))
                        startupLoginPollGeneration += 1
                        startupLoginOpenAttempted = false
                        sessionState.text = "△ 어디가 로그인 미확정 · 공개 기준자료 수집은 가능"
                        status.text = "어디가는 공개 기준자료 수집을 유지하고, 진학사 보호 경로 인증 검증으로 넘어갑니다."
                        handler.postDelayed({ if (startupLoginPreflightActive) beginStartupLoginProvider(ProviderId.JINHAK) }, 200L)
                        return@probeLoginSurface
                    }

                    val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
                    val currentCanonical = canonicalizeBatchUrl(currentUrl)
                    val probeCanonical = canonicalizeBatchUrl(coreProbe)
                    if (startupJinhakProtectedProbeAttempted && probeCanonical.isNotBlank() && currentCanonical == probeCanonical && !needsLogin) {
                        jinhakAuthVerifiedForBatch = true
                        jinhakCoreBootstrapState = "protected-route-authenticated"
                        recordRuntimeEvent("jinhak-protected-auth-probe-success", JSONObject()
                            .put("safePath", runtimeSafePath(currentUrl))
                            .put("loginUrl", false))
                        onStartupProviderAuthenticated(expectedProvider, generation)
                        return@probeLoginSurface
                    }
                    if (!startupJinhakProtectedProbeAttempted && coreProbe.isNotBlank()) {
                        startupJinhakProtectedProbeAttempted = true
                        startupAuthIndeterminatePolls = 0
                        startupLoginStage = "jinhak-protected-auth-probe"
                        jinhakCoreBootstrapState = "protected-route-probe"
                        recordRuntimeEvent("jinhak-protected-auth-probe-start", JSONObject()
                            .put("safePath", runtimeSafePath(coreProbe))
                            .put("readOnly", true)
                            .put("proactiveLoginNavigation", false))
                        sessionState.text = "△ 진학사 인증 미확정 · 수시저장소 보호 경로 확인"
                        status.text = "로그인 URL을 강제로 열지 않고 수시저장소를 읽기 전용으로 열어 서버 인증 상태를 검증합니다."
                        webView.loadUrl(coreProbe)
                        return@probeLoginSurface
                    }
                    if (startupJinhakProtectedProbeAttempted && startupAuthIndeterminatePolls >= 4 && coreProbe.isNotBlank()) {
                        startupAuthIndeterminatePolls = 0
                        recordRuntimeEvent("jinhak-protected-auth-probe-retry", JSONObject()
                            .put("safePath", runtimeSafePath(coreProbe))
                            .put("readOnly", true))
                        webView.loadUrl(coreProbe)
                        return@probeLoginSurface
                    }
                }
'''
main = must_replace(main, old_indeterminate, new_indeterminate, 'strict-protected-auth-preflight')

# Auth-success telemetry also establishes the Jinhak batch gate.
auth_success_anchor = '''        if (expectedProvider == ProviderId.ADIGA) startupLoginAdigaAuthenticated = true else startupLoginJinhakAuthenticated = true
        startupLoginPollGeneration += 1
'''
auth_success_new = '''        if (expectedProvider == ProviderId.ADIGA) {
            startupLoginAdigaAuthenticated = true
        } else {
            startupLoginJinhakAuthenticated = true
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "authenticated"
        }
        startupLoginPollGeneration += 1
'''
main = must_replace(main, auth_success_anchor, auth_success_new, 'jinhak-auth-batch-gate')
main = must_replace(
    main,
    '.put("bothProvidersAuthenticated", true)\n',
    '.put("bothProvidersAuthenticated", startupLoginAdigaAuthenticated && startupLoginJinhakAuthenticated)\n                .put("jinhakAuthenticatedForBatch", jinhakAuthVerifiedForBatch)\n',
    'truthful-auth-verified-event'
)

# Route-level login fallback. v0.9.6 waited only for a rendered DOM form; on the real device
# /member/login remained visible as a route while the form probe returned false. After bounded
# hydration waits, freeze the batch on that exact route/target instead of snapshotting/skipping.
old_guard_tail = '''            if (isProviderLoginUrl(expectedProvider, url) && attempt < 3) {
                val delay = when (attempt) { 0 -> 250L; 1 -> 650L; else -> 1_200L }
                handler.postDelayed({ continueBatchAfterRenderedLoginGuard(url, attempt + 1) }, delay)
                return@probeLoginSurface
            }
            disarmBatchNavigationWatchdog()
'''
new_guard_tail = '''            if (isProviderLoginUrl(expectedProvider, url) && attempt < 3) {
                val delay = when (attempt) { 0 -> 250L; 1 -> 650L; else -> 1_200L }
                handler.postDelayed({ continueBatchAfterRenderedLoginGuard(url, attempt + 1) }, delay)
                return@probeLoginSurface
            }
            if (isProviderLoginUrl(expectedProvider, url)) {
                loginRouteFallbackPauses += 1
                batchPausedForLogin = true
                batchCollecting = false
                batchNavigationWatchdogRecovery = false
                batchCloudFinalCheckInProgress = false
                disarmBatchNavigationWatchdog()
                hideBatchCover()
                if (expectedProvider == ProviderId.JINHAK) {
                    jinhakAuthVerifiedForBatch = false
                    jinhakCoreBootstrapState = "batch-login-route-wait"
                }
                recordRuntimeEvent("login-route-fallback-batch-pause", JSONObject()
                    .put("provider", expectedProvider.wireName)
                    .put("currentTarget", runtimeSafePath(currentBatchTarget))
                    .put("loginSafePath", runtimeSafePath(url))
                    .put("renderedSurfaceDetected", false)
                    .put("proactiveLoginNavigation", false))
                sessionState.text = "○ ${expectedProvider.displayName} 로그인 경로 감지 · 수집 대상 보존"
                if (credentialVault.has(expectedProvider.wireName)) {
                    status.text = "현재 수집 대상을 보존했습니다. 로그인 화면 렌더링을 기다리며 자동로그인을 재시도합니다."
                    scheduleLoginSurfaceDetection(expectedProvider, "batch-login-route-fallback")
                } else if (startupCredentialPromptedProvider != expectedProvider) {
                    startupCredentialPromptedProvider = expectedProvider
                    loginRouteFallbackCredentialPrompts += 1
                    status.text = "로그인이 필요합니다. 계정정보는 이 기기에만 암호화 저장되며 현재 수집 target은 유지됩니다."
                    showCredentialDialog(expectedProvider, continueAfterSave = true)
                } else {
                    status.text = "로그인 화면에서 인증을 완료하면 동일 수집 target을 자동으로 다시 엽니다."
                }
                return@probeLoginSurface
            }
            disarmBatchNavigationWatchdog()
'''
main = must_replace(main, old_guard_tail, new_guard_tail, 'login-route-fallback-batch-pause')

# When an authentication recovery succeeds, mark the Jinhak gate and retry the exact preserved target.
resume_anchor = '''            batchPausedForLogin = false
            showBatchCover()
            sessionState.text = "● 로그인 복구 / 동일 수집 브라우저"
'''
resume_new = '''            batchPausedForLogin = false
            if (provider == ProviderId.JINHAK) {
                jinhakAuthVerifiedForBatch = true
                jinhakCoreBootstrapState = "batch-auth-recovered"
            }
            showBatchCover()
            sessionState.text = "● 로그인 복구 / 동일 수집 브라우저"
'''
main = must_replace(main, resume_anchor, resume_new, 'resume-establish-auth-gate')

# The precheck must expose whether a restored lease was actually verified, not merely restored.
precheck_anchor = '''                    .put("credentialAutoLoginSuccessesAtBootstrap", credentialAutoLoginSuccesses)
                    .put("credentialExported", false)),
'''
precheck_new = '''                    .put("credentialAutoLoginSuccessesAtBootstrap", credentialAutoLoginSuccesses)
                    .put("staleSessionLeaseBypassesPrevented", staleSessionLeaseBypassesPrevented)
                    .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                    .put("loginRouteFallbackCredentialPrompts", loginRouteFallbackCredentialPrompts)
                    .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                    .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                    .put("credentialExported", false)),
'''
main = must_replace(main, precheck_anchor, precheck_new, 'precheck-v097-diagnostics')

# Live diagnostics: expose authentication/core-scope state while the run is still active.
live_anchor = '''                .put("noProgressFences", jinhakNoProgressFences)
                .put("secondsSinceMeaningfulProgress", sinceProgress ?: JSONObject.NULL)
'''
live_new = '''                .put("noProgressFences", jinhakNoProgressFences)
                .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
                .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                .put("credentialAutoLoginSubmissions", credentialAutoLoginSubmissions)
                .put("credentialAutoLoginSuccesses", credentialAutoLoginSuccesses)
                .put("credentialAutoLoginFailures", credentialAutoLoginFailures)
                .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                .put("loginRouteFallbackCredentialPrompts", loginRouteFallbackCredentialPrompts)
                .put("staleSessionLeaseBypassesPrevented", staleSessionLeaseBypassesPrevented)
                .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                .put("jinhakCoreScopeBlockedUrls", jinhakCoreScopeBlockedUrls)
                .put("jinhakCoreScopeBlockedLanes", JSONObject(jinhakCoreScopeBlockedLaneCounts as Map<*, *>))
                .put("secondsSinceMeaningfulProgress", sinceProgress ?: JSONObject.NULL)
'''
main = must_replace(main, live_anchor, live_new, 'live-v097-diagnostics')

# Final diagnostics add the same scope/auth evidence.
final_diag_anchor = '''                        .put("crossVersionResumeBlocks", crossVersionResumeBlocks)
                        .put("applicationBoundAgentActions", jinhakApplicationBoundActions)
'''
final_diag_new = '''                        .put("crossVersionResumeBlocks", crossVersionResumeBlocks)
                        .put("staleSessionLeaseBypassesPrevented", staleSessionLeaseBypassesPrevented)
                        .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                        .put("loginRouteFallbackCredentialPrompts", loginRouteFallbackCredentialPrompts)
                        .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                        .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                        .put("jinhakCoreScopeBlockedUrls", jinhakCoreScopeBlockedUrls)
                        .put("jinhakCoreScopeBlockedLanes", JSONObject(jinhakCoreScopeBlockedLaneCounts as Map<*, *>))
                        .put("applicationBoundAgentActions", jinhakApplicationBoundActions)
'''
main = must_replace(main, final_diag_anchor, final_diag_new, 'final-v097-diagnostics')

# Default Jinhak autonomous traversal is Susi-core only. Raw parsing support for strategy/media
# remains for user-opened pages, but these lanes are not enqueued by the autonomous frontier.
enqueue_anchor = '''    private fun enqueueDiscoveredLinks(links: JSONArray) {
        val frontierBatch = JSONArray()
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = canonicalizeBatchUrl(obj.optString("url"))
            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            enqueueDiscoveredUrl(url)
            frontierBatch.put(url)
'''
enqueue_new = '''    private fun recordJinhakCoreScopeBlock(url: String) {
        if (provider != ProviderId.JINHAK) return
        val lane = JinhakSiteTopology.lane(url).wireName
        jinhakCoreScopeBlockedUrls += 1
        jinhakCoreScopeBlockedLaneCounts[lane] = (jinhakCoreScopeBlockedLaneCounts[lane] ?: 0) + 1
    }

    private fun isJinhakDefaultCoreQueueUrl(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return true
        val allowed = JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)
        if (!allowed) recordJinhakCoreScopeBlock(url)
        return allowed
    }

    private fun enqueueDiscoveredLinks(links: JSONArray) {
        val frontierBatch = JSONArray()
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = canonicalizeBatchUrl(obj.optString("url"))
            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            if (!isJinhakDefaultCoreQueueUrl(url)) continue
            enqueueDiscoveredUrl(url)
            frontierBatch.put(url)
'''
main = must_replace(main, enqueue_anchor, enqueue_new, 'susi-core-discovered-link-filter')

# Direct queue helper also enforces scope in case another call site bypasses enqueueDiscoveredLinks.
direct_queue_anchor = '''    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (provider == ProviderId.JINHAK && batchQueued.size + batchVisited.size >= MAX_JINHAK_AUTONAV_PAGES) return
'''
direct_queue_new = '''    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) return
        if (provider == ProviderId.JINHAK && batchQueued.size + batchVisited.size >= MAX_JINHAK_AUTONAV_PAGES) return
'''
main = must_replace(main, direct_queue_anchor, direct_queue_new, 'susi-core-direct-queue-filter')

# Cloud frontier can contain old broad tasks. Never re-import a non-core Jinhak task.
cloud_claim_anchor = '''                        val url = canonicalizeBatchUrl(item.optString("url"))
                        val taskId = item.optString("taskId")
                        if (url.isBlank() || taskId.isBlank() || !isBatchNavigableProviderUrl(url)) continue
                        if (!batchVisited.contains(url) && batchQueued.add(url)) {
'''
cloud_claim_new = '''                        val url = canonicalizeBatchUrl(item.optString("url"))
                        val taskId = item.optString("taskId")
                        if (url.isBlank() || taskId.isBlank() || !isBatchNavigableProviderUrl(url)) continue
                        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) {
                            recordJinhakCoreScopeBlock(url)
                            continue
                        }
                        if (!batchVisited.contains(url) && batchQueued.add(url)) {
'''
main = must_replace(main, cloud_claim_anchor, cloud_claim_new, 'susi-core-cloud-claim-filter')

# Do not allow low-value reference pages to execute generic autonomous actions even on their
# first capture. Mission actions remain separately budgeted and unaffected.
low_value_anchor = '''                    if (snapshot.optString("providerPageType") == "jinhak-recommended-university") {
                        jinhakAllowAgentAction = false
                    }
'''
low_value_new = '''                    if (lowValueReference) {
                        jinhakAllowAgentAction = false
                    }
'''
main = must_replace(main, low_value_anchor, low_value_new, 'disable-low-value-generic-actions')

# Mark core bootstrap when the storage page actually appears. This does not invent identities;
# it only reports whether the protected origin page became reachable.
storage_anchor = '''                if (pageTypeNow == "jinhak-early-storage" && jinhakFirstPopulatedStorageAtMs == 0L) {
                    val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
'''
storage_new = '''                if (pageTypeNow == "jinhak-early-storage") {
                    jinhakAuthVerifiedForBatch = true
                    if (jinhakCoreBootstrapState != "saved-applications-populated") {
                        jinhakCoreBootstrapState = "saved-applications-reached"
                    }
                }
                if (pageTypeNow == "jinhak-early-storage" && jinhakFirstPopulatedStorageAtMs == 0L) {
                    val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
'''
main = must_replace(main, storage_anchor, storage_new, 'storage-core-bootstrap-state')
main = must_replace(
    main,
    '                    if (populated) jinhakFirstPopulatedStorageAtMs = System.currentTimeMillis()\n',
    '                    if (populated) {\n                        jinhakFirstPopulatedStorageAtMs = System.currentTimeMillis()\n                        jinhakCoreBootstrapState = "saved-applications-populated"\n                    }\n',
    'populated-core-bootstrap-state'
)

# Reset core-scope run counters at Jinhak batch start while preserving authenticated preflight state.
batch_reset_anchor = '''        jinhakReferenceRouteCaptureCounts.clear()
        jinhakReferenceRepeatSkips = 0
        jinhakNoProgressFences = 0
'''
batch_reset_new = '''        jinhakReferenceRouteCaptureCounts.clear()
        jinhakReferenceRepeatSkips = 0
        jinhakNoProgressFences = 0
        jinhakCoreScopeBlockedUrls = 0
        jinhakCoreScopeBlockedLaneCounts.clear()
        if (provider == ProviderId.JINHAK && jinhakAuthVerifiedForBatch) {
            jinhakCoreBootstrapState = "batch-core-start"
        }
'''
main = must_replace(main, batch_reset_anchor, batch_reset_new, 'batch-core-scope-reset')

# Topology: remove strategy from default seeds and expose an explicit default Susi-core allowlist.
topology = must_replace(
    topology,
    '''        "$ROOT/jh/high3/early/four-year-university/search",
        "$ROOT/jh/high3/univ-major/univ-info/univ-search",
        "$ROOT/jh/high3/univ-entrance-info/ipsi-analysis/ipsi-strategy"
''',
    '''        "$ROOT/jh/high3/early/four-year-university/search",
        "$ROOT/jh/high3/univ-major/univ-info/univ-search"
''',
    'remove-strategy-seed'
)
old_editorial = '''    fun shouldExpandEditorial(url: String, label: String = ""): Boolean {
        val lane = lane(url, label)
        return lane == JinhakMissionLane.STRATEGY ||
            lane == JinhakMissionLane.ADMISSION_KNOWLEDGE ||
            lane == JinhakMissionLane.UNIVERSITY_RESULT
    }
'''
new_editorial = '''    fun isDefaultSusiCoreTraversalUrl(url: String, label: String = ""): Boolean = when (lane(url, label)) {
        JinhakMissionLane.SAVED_APPLICATIONS,
        JinhakMissionLane.CURRENT_PREDICTION,
        JinhakMissionLane.MOCK_SUPPORT,
        JinhakMissionLane.ACTUAL_ADMIT,
        JinhakMissionLane.UNIVERSITY_RESULT,
        JinhakMissionLane.SCORE_ANALYSIS,
        JinhakMissionLane.REFERENCE -> true
        JinhakMissionLane.RECOMMENDATION,
        JinhakMissionLane.STRATEGY,
        JinhakMissionLane.ADMISSION_KNOWLEDGE,
        JinhakMissionLane.MEDIA,
        JinhakMissionLane.UNKNOWN -> false
    }

    fun shouldExpandEditorial(url: String, label: String = ""): Boolean {
        return lane(url, label) == JinhakMissionLane.UNIVERSITY_RESULT
    }
'''
topology = must_replace(topology, old_editorial, new_editorial, 'topology-susi-core-allowlist')

main_p.write_text(main)
topology_p.write_text(topology)
gradle_p.write_text(gradle)
manifest_p.write_text(manifest)
print('v0.9.7 patch applied')
