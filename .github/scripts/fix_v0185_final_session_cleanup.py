from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = MAIN.read_text()


def patch(old: str, new: str, label: str) -> None:
    global text
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise SystemExit(f"{label}: anchor missing")


# Final startBatch gate: route scope only. Never fall back into the old user-session/auth gate.
old_gate = '''        currentBatchTarget = if (provider == ProviderId.JINHAK && preserveJinhakMissionState && !currentBatchTarget.isNullOrBlank()) {
            currentBatchTarget
        } else if (provider == ProviderId.JINHAK) {
            JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)?.let(::canonicalizeBatchUrl)
        } else canonicalizeBatchUrl(url)
        if (provider == ProviderId.JINHAK) {
            val strict = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget)
                ?: JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)
            if (strict == null) {
                jinhakV0174PersistedTargetBlocks += 1
                batchRunning = false
                hideBatchCover()
                enterJinhakUserSessionGate("v0174-invalid-persisted-or-visible-target")
                return
            }
            currentBatchTarget = canonicalizeBatchUrl(strict)
        }'''
new_gate = '''        currentBatchTarget = if (provider == ProviderId.JINHAK && preserveJinhakMissionState && !currentBatchTarget.isNullOrBlank()) {
            currentBatchTarget
        } else if (provider == ProviderId.JINHAK) {
            canonicalizeBatchUrl(webView.url.orEmpty())
        } else canonicalizeBatchUrl(url)
        if (provider == ProviderId.JINHAK) {
            val visible = canonicalizeBatchUrl(webView.url.orEmpty())
            val selected = canonicalizeBatchUrl(currentBatchTarget.orEmpty())
            val target = selected.takeIf { JinhakManualStorageReportPolicy.isAllowedMissionUrl(it) }
                ?: visible.takeIf { JinhakManualStorageReportPolicy.isAllowedMissionUrl(it) }
            if (target == null) {
                batchRunning = false
                batchPausedForLogin = false
                hideBatchCover()
                stopCollectionKeepAlive()
                sessionState.text = "○ 수시 저장소 직접 진입 필요"
                status.text = "진학사 인증 상태는 확인하지 않습니다. 수시 저장소로 직접 이동한 뒤 리포트 탐색을 시작하세요."
                return
            }
            currentBatchTarget = target
        }'''
patch(old_gate, new_gate, "startBatch-final-route-gate")

# Live diagnostics must describe only traversal state. Legacy auth counters were confusing and made
# it appear that Admission Hub still owned the provider session even though those paths are disabled.
old_diag = '''                .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
                .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                .put("credentialAutoLoginSubmissions", credentialAutoLoginSubmissions)
                .put("credentialAutoLoginSuccesses", credentialAutoLoginSuccesses)
                .put("credentialAutoLoginFailures", credentialAutoLoginFailures)
                    .put("credentialAutoLoginSuppressedInFlight", credentialAutoLoginSuppressedInFlight)
                    .put("credentialAutoLoginSuppressedThrottle", credentialAutoLoginSuppressedThrottle)
                    .put("credentialAutoLoginSuppressedNoCredential", credentialAutoLoginSuppressedNoCredential)
                    .put("credentialAutoLoginSuppressedProbeLost", credentialAutoLoginSuppressedProbeLost)
                    .put("credentialAutoLoginSuppressedRetryLimit", credentialAutoLoginSuppressedRetryLimit)
                .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                .put("loginRouteFallbackCredentialPrompts", loginRouteFallbackCredentialPrompts)
                .put("staleSessionLeaseBypassesPrevented", staleSessionLeaseBypassesPrevented)
                .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)'''
new_diag = '''                .put("authOwnership", JinhakManualStorageReportPolicy.AUTH_OWNERSHIP)
                .put("authStateInferred", false)
                .put("autoLogin", false)
                .put("credentialStorage", false)
                .put("sessionRestore", false)
                .put("authProofCache", false)
                .put("storageVisible", JinhakManualStorageReportPolicy.isStorageEntry(webView.url))
                .put("reportVisible", JinhakManualStorageReportPolicy.isReportUrl(webView.url))
                .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)'''
patch(old_diag, new_diag, "remove-live-auth-diagnostics")

MAIN.write_text(text)
