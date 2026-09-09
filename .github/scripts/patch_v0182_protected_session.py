from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, got {count}: {old[:160]!r}")
    p.write_text(text.replace(old, new, 1))


def replace_all_checked(path: str, old: str, new: str, minimum: int = 1) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f"{path}: expected at least {minimum} matches, got {count}: {old[:160]!r}")
    p.write_text(text.replace(old, new))


replace_once(
    "app/build.gradle.kts",
    '        versionCode = 118100\n        versionName = "0.18.1"',
    '        versionCode = 118200\n        versionName = "0.18.2"'
)

replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '        private const val VERSION = "0.18.1"\n        private const val BUILD_CODE = 118100',
    '        private const val VERSION = "0.18.2"\n        private const val BUILD_CODE = 118200'
)

replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    'import com.admissionhub.collector.jinhak.JinhakFocusedSixPolicy\n',
    'import com.admissionhub.collector.jinhak.JinhakFocusedSixPolicy\nimport com.admissionhub.collector.jinhak.JinhakProtectedSessionPolicy\n'
)

replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''    private var jinhakV0181GenericActionsSuppressed = 0
    private var jinhakV0181ProtectedCoreStarts = 0
''',
    '''    private var jinhakV0181GenericActionsSuppressed = 0
    private var jinhakV0181ProtectedCoreStarts = 0
    private var jinhakV0182ProtectedSessionVerified = false
    private var jinhakV0182ProtectedSessionVerifications = 0
    private var jinhakV0182ProtectedBootstrapAttempts = 0
    private var jinhakV0182ProtectedBootstrapFailures = 0
    private var jinhakV0182ProtectedBootstrapGeneration = 0
    private var jinhakV0182High3ReturnsAwaitingProof = 0
    private var jinhakV0182AutofillChainGeneration = -1
    private var jinhakV0182AutofillAttemptsThisGeneration = 0
    private var jinhakV0182CredentialSubmitVerifiedSuccesses = 0
    private var jinhakV0182ManualHigh3Returns = 0
    private var jinhakV0182RecoveryScopePreparations = 0
'''
)

replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '        private const val V0180_AUTH_RENDERER_RESTART_LIMIT = 2',
    '''        private const val V0180_AUTH_RENDERER_RESTART_LIMIT = 2
        private const val V0182_PROTECTED_BOOTSTRAP_TIMEOUT_MS = 12_000L
        private const val V0182_MAX_PROTECTED_BOOTSTRAP_ATTEMPTS = 3'''
)

# New unified run must never inherit a protected-session verdict from an older browser state.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        jinhakBatchStartCount = 0
        jinhakNormalizedMissionSeedContexts.clear()''',
    '''        jinhakBatchStartCount = 0
        jinhakV0182ProtectedSessionVerified = false
        jinhakV0182ProtectedSessionVerifications = 0
        jinhakV0182ProtectedBootstrapAttempts = 0
        jinhakV0182ProtectedBootstrapFailures = 0
        jinhakV0182ProtectedBootstrapGeneration = 0
        jinhakV0182High3ReturnsAwaitingProof = 0
        jinhakV0182AutofillChainGeneration = -1
        jinhakV0182AutofillAttemptsThisGeneration = 0
        jinhakV0182CredentialSubmitVerifiedSuccesses = 0
        jinhakV0182ManualHigh3Returns = 0
        jinhakV0182RecoveryScopePreparations = 0
        jinhakNormalizedMissionSeedContexts.clear()'''
)

# One autofill chain per auth generation. onPageFinished may fire repeatedly but cannot create
# overlapping 12-attempt chains anymore.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''    private fun attemptV0180JinhakAuthAutofill(generation: Int, attempt: Int) {
        if (provider != ProviderId.JINHAK || generation != jinhakV0180AuthGeneration) return
        if (!::authHost.isInitialized || authHost.visibility != View.VISIBLE) return
        if (jinhakV0180AuthSubmitGeneration == generation) return
''',
    '''    private fun attemptV0180JinhakAuthAutofill(generation: Int, attempt: Int) {
        if (provider != ProviderId.JINHAK || generation != jinhakV0180AuthGeneration) return
        if (!::authHost.isInitialized || authHost.visibility != View.VISIBLE) return
        if (jinhakV0180AuthSubmitGeneration == generation) return
        if (attempt == 0) {
            if (jinhakV0182AutofillChainGeneration == generation) return
            jinhakV0182AutofillChainGeneration = generation
            jinhakV0182AutofillAttemptsThisGeneration = 0
        }
        if (jinhakV0182AutofillAttemptsThisGeneration >= V0180_AUTH_MAX_FILL_ATTEMPTS) return
        jinhakV0182AutofillAttemptsThisGeneration += 1
'''
)

replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        jinhakV0180AuthGeneration += 1
        jinhakV0180AuthSubmitGeneration = -1
        jinhakV0180AuthFillAttempt = 0
        jinhakV0180AuthHigh3ProbeGeneration = -1
        jinhakV0180AuthRendererRestarts = 0
''',
    '''        jinhakV0180AuthGeneration += 1
        jinhakV0180AuthSubmitGeneration = -1
        jinhakV0180AuthFillAttempt = 0
        jinhakV0180AuthHigh3ProbeGeneration = -1
        jinhakV0180AuthRendererRestarts = 0
        jinhakV0182AutofillChainGeneration = -1
        jinhakV0182AutofillAttemptsThisGeneration = 0
        jinhakV0182ProtectedSessionVerified = false
        jinhakAuthVerifiedForBatch = false
'''
)

# A public high3 return is only a handoff event, never authentication proof.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        jinhakV0180AuthState = "SUCCESS"
        jinhakV0180AuthSuccesses += 1
        if (jinhakV0180AuthSubmitGeneration == jinhakV0180AuthGeneration) {
            credentialAutoLoginSuccesses += 1
            credentialAutoLoginLastResult = "v0180-success-high3-return"
        }
        jinhakUserSessionConfirmed = true
        jinhakAuthVerifiedForBatch = true
        batchPausedForLogin = false
        jinhakTransitionAuthGateActive = false
        jinhakRealAuthResumeGatePending = false
        jinhakCoreBootstrapState = "v0180-dedicated-auth-high3"
        jinhakLastAuthEvidence = "v0180-server-high3-return"
        jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
''',
    '''        jinhakV0180AuthState = "HIGH3_RETURN_PENDING_PROTECTED"
        jinhakV0182High3ReturnsAwaitingProof += 1
        if (jinhakV0180AuthSubmitGeneration == jinhakV0180AuthGeneration) {
            credentialAutoLoginLastResult = "v0182-high3-return-awaiting-protected-proof"
        } else {
            jinhakV0182ManualHigh3Returns += 1
        }
        jinhakUserSessionConfirmed = true
        jinhakAuthVerifiedForBatch = false
        jinhakV0182ProtectedSessionVerified = false
        batchPausedForLogin = false
        jinhakTransitionAuthGateActive = false
        jinhakRealAuthResumeGatePending = false
        jinhakCoreBootstrapState = "v0182-high3-return-awaiting-protected-proof"
        jinhakLastAuthEvidence = "v0182-public-high3-return-not-auth-proof"
        jinhakLastCoreVerifiedAtMs = 0L
'''
)

replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '        sessionState.text = "● 진학사 자동 로그인 완료 · 고3 세션"\n        status.text = "진학사 로그인 완료 · 고3 전용 수집 WebView에서 자동 재개합니다."',
    '        sessionState.text = "● 고3 복귀 확인 · 보호영역 세션 검증 중"\n        status.text = "공개 고3 화면은 로그인 증거로 사용하지 않습니다. 저장지원 보호영역 접근을 확인한 뒤 수집을 시작합니다."'
)

replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        val target = JinhakSiteTopology.protectedCoreProbeUrl()
        jinhakV0181ProtectedCoreStarts += 1
        currentBatchTarget = target
        loadJinhakV0174High3Only(target, "v0181-auth-success-protected-core")
    }

    private fun recreateV0180AuthWebView''',
    '''        requestV0182ProtectedSessionProbe("auth-high3-return")
    }

    private fun requestV0182ProtectedSessionProbe(trigger: String) {
        if (provider != ProviderId.JINHAK || jinhakV0182ProtectedSessionVerified) return
        if (jinhakV0182ProtectedBootstrapAttempts >= V0182_MAX_PROTECTED_BOOTSTRAP_ATTEMPTS) {
            jinhakV0182ProtectedBootstrapFailures += 1
            jinhakAuthVerifiedForBatch = false
            jinhakCoreBootstrapState = "v0182-protected-session-unverified"
            jinhakLastAuthEvidence = "protected-core-proof-missing"
            recordRuntimeEvent("jinhak-v0182-protected-bootstrap-failed", JSONObject()
                .put("trigger", trigger.take(80))
                .put("attempts", jinhakV0182ProtectedBootstrapAttempts)
                .put("safePath", runtimeSafePath(webView.url.orEmpty())))
            startV0180DedicatedJinhakAuth("v0182-protected-proof-required")
            return
        }
        jinhakV0182ProtectedBootstrapAttempts += 1
        jinhakV0181ProtectedCoreStarts += 1
        val generation = ++jinhakV0182ProtectedBootstrapGeneration
        val target = JinhakSiteTopology.protectedCoreProbeUrl()
        currentBatchTarget = target
        jinhakCoreBootstrapState = "v0182-protected-core-probing"
        loadJinhakV0174High3Only(target, "v0182-protected-core-probe")
        handler.postDelayed({
            if (provider != ProviderId.JINHAK || generation != jinhakV0182ProtectedBootstrapGeneration || jinhakV0182ProtectedSessionVerified) return@postDelayed
            val current = webView.url.orEmpty()
            when {
                JinhakProtectedSessionPolicy.isProtectedProofUrl(current) -> markV0182ProtectedSessionVerified(current, "probe-timeout-current-protected")
                JinhakDedicatedAuthPolicy.isLoginSurface(current) -> startV0180DedicatedJinhakAuth("v0182-protected-probe-login")
                else -> requestV0182ProtectedSessionProbe("probe-timeout-retry")
            }
        }, V0182_PROTECTED_BOOTSTRAP_TIMEOUT_MS)
    }

    private fun markV0182ProtectedSessionVerified(url: String, trigger: String) {
        if (provider != ProviderId.JINHAK || !JinhakProtectedSessionPolicy.isProtectedProofUrl(url)) return
        if (!jinhakV0182ProtectedSessionVerified) {
            jinhakV0182ProtectedSessionVerifications += 1
            if (jinhakV0180AuthSubmitGeneration == jinhakV0180AuthGeneration) {
                jinhakV0182CredentialSubmitVerifiedSuccesses += 1
                credentialAutoLoginSuccesses += 1
                credentialAutoLoginLastResult = "v0182-success-protected-core-verified"
            }
        }
        jinhakV0182ProtectedSessionVerified = true
        jinhakAuthVerifiedForBatch = true
        jinhakV0180AuthState = "PROTECTED_SESSION_VERIFIED"
        jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
        jinhakCoreBootstrapState = "v0182-protected-session-verified"
        jinhakLastAuthEvidence = "protected-core-finished-in-collector"
        jinhakV0180AuthSuccesses = jinhakV0182ProtectedSessionVerifications
        batchPausedForLogin = false
        ++jinhakV0182ProtectedBootstrapGeneration
        unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->
            localStore.prepareSelectedSixRecovery(sessionId)
            jinhakV0182RecoveryScopePreparations += 1
        }
        recordRuntimeEvent("jinhak-v0182-protected-session-verified", JSONObject()
            .put("trigger", trigger.take(80))
            .put("safePath", runtimeSafePath(url))
            .put("pinnedIdentities", jinhakV0181PinnedIdentityKeys.size))
        persistJinhakAuthDiagnostics("v0182-protected-session-verified")
        if (!batchRunning) handler.post { startBatch() }
    }

    private fun recreateV0180AuthWebView'''
)

# The collector's page-finished event is the authoritative protected-session proof boundary.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''                if (provider == ProviderId.JINHAK) {
                    if (JinhakDedicatedAuthPolicy.isLoginSurface(url)) {''',
    '''                if (provider == ProviderId.JINHAK) {
                    if (JinhakProtectedSessionPolicy.isProtectedProofUrl(url)) {
                        markV0182ProtectedSessionVerified(url, "collector-page-finished-protected")
                    }
                    if (JinhakDedicatedAuthPolicy.isLoginSurface(url)) {'''
)

# Visible public high3 approval never sets the auth flag in v0.18.2.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '                jinhakAuthVerifiedForBatch = true // compatibility flag == explicit user approval on visible high3 only',
    '                jinhakAuthVerifiedForBatch = false // v0.18.2: public high3/user approval is not protected-session proof'
)
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''            currentBatchTarget = canonicalizeBatchUrl(visibleHigh3)
            jinhakAuthVerifiedForBatch = true
            jinhakCoreBootstrapState = "v0174-explicit-visible-high3-confirmed"
            jinhakLastAuthEvidence = "user-explicitly-approved-current-visible-high3"
            jinhakLastCoreVerifiedAtMs = 0L''',
    '''            currentBatchTarget = canonicalizeBatchUrl(visibleHigh3)
            jinhakAuthVerifiedForBatch = false
            jinhakCoreBootstrapState = "v0182-user-approved-high3-awaiting-protected-proof"
            jinhakLastAuthEvidence = "user-approved-public-high3-not-auth-proof"
            jinhakLastCoreVerifiedAtMs = 0L'''
)

# Focused-six scope is prepared locally before any network mission is allowed.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''            jinhakV0181PinnedIdentitySeeds = keys.size
            keys.forEach { identity -> jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() } }
            recordRuntimeEvent("jinhak-v0181-focused-six-activated", JSONObject()''',
    '''            jinhakV0181PinnedIdentitySeeds = keys.size
            keys.forEach { identity -> jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() } }
            unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->
                localStore.prepareSelectedSixRecovery(sessionId)
                jinhakV0182RecoveryScopePreparations += 1
            }
            recordRuntimeEvent("jinhak-v0181-focused-six-activated", JSONObject()'''
)

# No batch may initialize until a protected route has actually finished in the collector.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''    private fun startBatch() {
        if (provider == ProviderId.JINHAK && !jinhakUserSessionConfirmed) {
            enterJinhakUserSessionGate("start-batch")
            return
        }
        if (provider == ProviderId.JINHAK) {
            activateV0181PinnedSixFocus("start-batch")
''',
    '''    private fun startBatch() {
        if (provider == ProviderId.JINHAK) {
            activateV0181PinnedSixFocus("start-batch")
            if (!jinhakUserSessionConfirmed) {
                enterJinhakUserSessionGate("start-batch")
                return
            }
            if (!jinhakV0182ProtectedSessionVerified) {
                jinhakAuthVerifiedForBatch = false
                requestV0182ProtectedSessionProbe("start-batch")
                return
            }
'''
)

# The generic 60-second mission stall fence is illegal before protected proof and before at least
# one concrete mission target exists. Bootstrap/auth failures have their own bounded state machine.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''                if (elapsed >= JINHAK_NO_PROGRESS_FENCE_MS) {
                    val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
                    val ledgerOutstanding = jinhakMissionTargetLedger.outstandingCount()''',
    '''                val missionTargetCount = jinhakMissionTargetLedger.summary().optInt("targets", 0)
                if (elapsed >= JINHAK_NO_PROGRESS_FENCE_MS &&
                    JinhakProtectedSessionPolicy.shouldRunMissionStallFence(jinhakV0182ProtectedSessionVerified, missionTargetCount)) {
                    val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
                    val ledgerOutstanding = jinhakMissionTargetLedger.outstandingCount()'''
)

# Startup compatibility branch may only claim Jinhak auth when the actual current route is protected.
replace_once(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''        } else {
            startupLoginJinhakAuthenticated = true
            jinhakAuthVerifiedForBatch = true
            if (jinhakLastAuthEvidence == "none") jinhakLastAuthEvidence = "rendered-authenticated-control"''',
    '''        } else {
            startupLoginJinhakAuthenticated = JinhakProtectedSessionPolicy.isProtectedProofUrl(webView.url.orEmpty())
            jinhakAuthVerifiedForBatch = startupLoginJinhakAuthenticated
            if (startupLoginJinhakAuthenticated) {
                jinhakV0182ProtectedSessionVerified = true
                if (jinhakLastAuthEvidence == "none") jinhakLastAuthEvidence = "protected-route-rendered"
            }'''
)

# Diagnostics: make false-positive auth and bootstrap state externally visible.
replace_all_checked(
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
    '''                    .put("v0181ProtectedCoreStarts", jinhakV0181ProtectedCoreStarts)
                    .put("v0180RecursiveAuthPolling", false)''',
    '''                    .put("v0181ProtectedCoreStarts", jinhakV0181ProtectedCoreStarts)
                    .put("v0182ProtectedSessionVerified", jinhakV0182ProtectedSessionVerified)
                    .put("v0182ProtectedSessionVerifications", jinhakV0182ProtectedSessionVerifications)
                    .put("v0182ProtectedBootstrapAttempts", jinhakV0182ProtectedBootstrapAttempts)
                    .put("v0182ProtectedBootstrapFailures", jinhakV0182ProtectedBootstrapFailures)
                    .put("v0182High3ReturnsAwaitingProof", jinhakV0182High3ReturnsAwaitingProof)
                    .put("v0182AutofillAttemptsThisGeneration", jinhakV0182AutofillAttemptsThisGeneration)
                    .put("v0182CredentialSubmitVerifiedSuccesses", jinhakV0182CredentialSubmitVerifiedSuccesses)
                    .put("v0182ManualHigh3Returns", jinhakV0182ManualHigh3Returns)
                    .put("v0182RecoveryScopePreparations", jinhakV0182RecoveryScopePreparations)
                    .put("v0180RecursiveAuthPolling", false)''',
    minimum=1
)

print("v0.18.2 protected-session bootstrap patch applied")
