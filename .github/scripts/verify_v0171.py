from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakUserSessionPolicy.kt").read_text()
build = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()

checks = {
    "versionName": 'versionName = "0.17.1"' in build,
    "versionCode": "versionCode = 117100" in build,
    "mainVersion": 'private const val VERSION = "0.17.1"' in main,
    "mainBuildCode": "private const val BUILD_CODE = 117100" in main,
    "label": 'Admission Hub v0.17.1 User-Owned Jinhak Session' in manifest,
    "policyImported": 'import com.admissionhub.collector.jinhak.JinhakUserSessionPolicy' in main,
    "policySchema": 'const val SCHEMA_VERSION = 1' in policy,
    "policyNoVerify": 'fun collectorMayVerifyLogin(): Boolean = false' in policy,
    "policyNoCredentials": 'fun collectorMayReadCredentials(): Boolean = false' in policy and 'fun collectorMaySubmitCredentials(): Boolean = false' in policy,
    "policyNoLease": 'fun collectorMayRestoreJinhakAuthLease(): Boolean = false' in policy and 'fun collectorMayCaptureJinhakAuthLease(): Boolean = false' in policy,
    "policyNoExtend": 'fun collectorMayExtendJinhakSession(): Boolean = false' in policy,
    "manualGate": 'private fun enterJinhakUserSessionGate(reason: String)' in main,
    "manualConfirm": 'private fun confirmJinhakUserSessionAndResume(reason: String)' in main,
    "startBatchGate": 'if (provider == ProviderId.JINHAK && !jinhakUserSessionConfirmed)' in main,
    "expandedBrowser": 'val expandedBrowserHeight = maxOf(dp(720), (resources.displayMetrics.heightPixels * 0.68f).toInt())' in main,
    "browserAlwaysUnderDashboard": 'text = "사이트 탐색 / 로그인"' in main and 'root.addView(browserStack' in main,
    "browserNotAdvanced": 'hubAdvancedPanel.addView(browserStack' not in main,
    "statusNotAdvanced": 'hubAdvancedPanel.addView(status)' not in main,
    "confirmButton": '진학사 로그인 완료 · 탐색 시작/재개' in main,
    "authModel": 'user-owned-session-login-assumed-v0171' in main,
    "sessionAuthorityDiagnostic": '.put("jinhakSessionAuthority", "user")' in main,
    "noDirectJinhakLeaseRestore": 'sessionVault.restore(ProviderId.JINHAK.wireName)' not in main,
    "noDirectJinhakLeaseCapture": 'sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName' not in main,
    "selectedSixUserGate": 'selected-six-recovery-user-session' in main,
    "transitionUserGate": 'enterJinhakUserSessionGate("unified-transition")' in main,
    "realAuthProbeDisabled": 'disabled-user-owned-session-v0171' in main,
    "targetRedirectNotFailure": 'A login redirect means user-session control, not a failed admission target.' in main,
    "predictionSafetyRetained": 'probabilityInferred' in main,
    "noCredentialExport": '.put("credentialExported", false)' in main,
    "noSessionSecretExport": '.put("sessionSecretExported", false)' in main,
}
failed = [k for k,v in checks.items() if not v]
print(checks)
if failed:
    raise SystemExit("v0.17.1 verification failed: " + ", ".join(failed))


def member_region(name: str) -> str:
    marker = f"    private fun {name}"
    start = main.find(marker)
    if start < 0:
        raise SystemExit(f"member missing: {name}")
    tail = main[start + len(marker):]
    m = re.search(r"\n    private\s+(?:fun|val|var|data\s+class|class|object)\b", tail)
    end = start + len(marker) + m.start() if m else len(main)
    return main[start:end]

# Critical negative contracts: Jinhak session ownership must not leak back through legacy entry points.
keep_start = main.index("    private val sessionKeepAlive = object : Runnable {")
keep_end = main.index("    private data class BatchPageAction(", keep_start)
keep = main[keep_start:keep_end]
assert 'attemptSessionExtension()' in keep  # Adiga still gets keep-alive.
# But it must be explicitly confined away from Jinhak.
assert 'active && provider != ProviderId.JINHAK' in keep
assert 'openJinhakDirectHigh3Auth(' not in keep
assert 'verifyRecoveredJinhakHigh3AndResume(' not in keep
assert 'checkSessionState {' not in keep
assert 'markJinhakDirectAuthWait(' not in keep

for name in [
    "markJinhakDirectAuthWait",
    "scheduleJinhakLoginRecovery",
    "verifyRecoveredJinhakHigh3AndResume",
    "completeJinhakVerifiedAuth",
    "handleJinhakTransitionAuthGate",
]:
    region = member_region(name)
    assert 'sessionVault.restore' not in region, name
    assert 'sessionVault.captureAuthenticated' not in region, name
    assert 'credentialVault.load' not in region, name
    assert 'evaluateJavascript' not in region, name

transition = member_region("transitionUnifiedToJinhak")
assert 'protectedHigh3Core' not in transition
assert 'auth-probe' not in transition.lower()
assert 'sessionVault.restore' not in transition
assert 'webView.loadUrl(ProviderId.JINHAK.homeUrl)' in transition

probe = member_region("startJinhakRealAuthProbe")
assert 'protectedHigh3Core' not in probe
assert 'webView.loadUrl(core)' not in probe
assert 'checkSessionState' not in probe

resume = member_region("resumeAfterLogin")
assert 'confirmJinhakUserSessionAndResume("legacy-resume-button")' in resume

attempt = member_region("attemptSavedCredentialLogin")
first_part = attempt[:900]
assert 'if (which == ProviderId.JINHAK)' in first_part
assert 'saved-credential-login-disabled' in first_part

# The app may still maintain Adiga auth metadata. Generic restore is allowed only with an explicit Jinhak-null guard.
for line in main.splitlines():
    if 'sessionVault.restore(which.wireName)' in line:
        assert 'which == ProviderId.JINHAK' in line and 'null else' in line, line

# Expanded browser must be outside the advanced panel and at least 68% screen height / 720dp.
assert main.index('root.addView(browserStack') > main.index('root.addView(hubDecisionSummary')
assert 'hubAdvancedPanel.addView(browserStack' not in main

print("v0.17.1 source contracts verified: user-owned Jinhak session, no Collector auth/lease/extension, explicit user confirmation, expanded always-visible browser")
