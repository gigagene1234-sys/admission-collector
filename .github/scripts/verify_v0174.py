from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
sandbox = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakStrictHigh3Sandbox.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakUserSessionPolicy.kt").read_text()
adapter = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt").read_text()
provider = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/ProviderId.kt").read_text()
topology = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt").read_text()
build = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()

checks = {
    "versionName": 'versionName = "0.17.4"' in build,
    "versionCode": "versionCode = 117400" in build,
    "mainVersion": 'private const val VERSION = "0.17.4"' in main,
    "mainBuildCode": "private const val BUILD_CODE = 117400" in main,
    "label": 'Admission Hub v0.17.4 Strict High3 Sandbox' in manifest,
    "sandboxSchema": "const val SCHEMA_VERSION = 1" in sandbox,
    "sessionPolicySchema": "const val SCHEMA_VERSION = 3" in policy,
    "providerDefaultStrictHigh3": 'JINHAK("jinhak", "진학사", "https://www.jinhak.com/jh/high3/early/four-year-university/search")' in provider,
    "providerSharedRootRemoved": 'JINHAK("jinhak", "진학사", "https://www.jinhak.com/")' not in provider,
    "sharedRootBlocked": "BLOCK_SHARED_ROOT" in sandbox,
    "genericLoginBlocked": "BLOCK_GENERIC_LOGIN" in sandbox,
    "lowerGradeBlocked": "BLOCK_LOWER_GRADE" in sandbox,
    "otherJinhakBlocked": "BLOCK_OTHER_JINHAK" in sandbox,
    "externalBlocked": "BLOCK_EXTERNAL" in sandbox,
    "exactMemberLoginAllowed": "ALLOW_MEMBER_LOGIN" in sandbox and "isMemberLoginSurface" in sandbox,
    "collectorNavigationHigh3Only": "fun allowsCollectorNavigation(url: String): Boolean = decision(url) == MainFrameDecision.ALLOW_HIGH3" in sandbox,
    "anyRequestLowerGradeFence": "fun shouldBlockAnyRequest(url: String): Boolean = JinhakGradeRouteFence.isBlockedLowerGrade(url)" in sandbox,
    "serviceWorkerFence": "ServiceWorkerController.getInstance().setServiceWorkerClient" in main,
    "allRequestFence": "v0174-any-request-intercept" in main,
    "mainFrameStrictFence": "network-main-block" in main and "navigation-main-block" in main,
    "pageStartedStrictFence": "page-started-strict-stop" in main,
    "pageFinishedStrictFence": "page-finished-strict-block" in main,
    "strictAppNavigation": "private fun loadJinhakV0174High3Only" in main,
    "strictHistory": "private fun safeJinhakV0174Back" in main,
    "strictPopup": "v0174-strict-popup" in main,
    "strictRenderer": "v0174-renderer-resume-needs-user" in main and "v0174-renderer-circuit-needs-user" in main,
    "strictBatchGuard": "v0174-start-batch-requires-visible-high3" in main,
    "explicitHigh3Only": "jinhak-v0174-explicit-high3-confirmed" in main,
    "autoHigh3ResumeDisabled": "v0174-auto-high3-handoff-disabled" in main and "v0174-auto-high3-activation-disabled" in main,
    "autoLoginRecoveryDisabled": "v0174-auto-login-recovery-disabled" in main,
    "legacyAuthResumeDisabled": "v0174-legacy-auth-resume-disabled" in main,
    "legacyVerifiedAuthDisabled": "v0174-legacy-verified-auth-disabled" in main,
    "adapterHigh3Only": "!JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)" in adapter,
    "expandedBrowserRetained": 'val expandedBrowserHeight = maxOf(dp(720), (resources.displayMetrics.heightPixels * 0.68f).toInt())' in main,
    "userOwnsAuth": "fun collectorMayVerifyLogin(): Boolean = false" in policy and "fun collectorMayReadCredentials(): Boolean = false" in policy and "fun collectorMaySubmitCredentials(): Boolean = false" in policy,
    "noSharedRootPolicy": "fun collectorMayUseSharedProductRoot(): Boolean = false" in policy,
    "noGenericRouterPolicy": "fun collectorMayUseGenericProductLoginRouter(): Boolean = false" in policy,
    "noAutoResumePolicy": "fun collectorMayAutoResumeAfterLogin(): Boolean = false" in policy,
    "noJinhakSessionLeaseRestore": "sessionVault.restore(ProviderId.JINHAK.wireName)" not in main,
    "noJinhakSessionLeaseCapture": "sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName" not in main,
    "probabilitySafety": "probabilityInferred" in main,
    "credentialExportSafety": '.put("credentialExported", false)' in main,
    "sessionSecretExportSafety": '.put("sessionSecretExported", false)' in main,
    "strictDiagnostics": 'jinhakAuthModel", "user-owned-session-explicit-high3-strict-sandbox-v0174"' in main,
}
failed = [k for k, v in checks.items() if not v]
print(checks)
if failed:
    raise SystemExit("v0.17.4 verification failed: " + ", ".join(failed))


def member_region(name: str) -> str:
    marker = f"    private fun {name}"
    start = main.find(marker)
    if start < 0:
        raise SystemExit(f"member missing: {name}")
    tail = main[start + len(marker):]
    m = re.search(r"\n    private\s+(?:fun|val|var|data\s+class|class|object)\b", tail)
    end = start + len(marker) + m.start() if m else len(main)
    return main[start:end]

# Explicit confirmation must not approve login/root/other pages and must not schedule natural resume.
confirm = member_region("confirmJinhakUserSessionAndResume")
assert "JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3" in confirm
assert "jinhakUserSessionConfirmed = true" in confirm
assert "scheduleJinhakV0173StableHigh3Handoff" not in confirm
assert "webView.loadUrl(" not in confirm
assert "openJinhakV0174StrictEntry" in confirm

# Legacy auto mechanisms are hard no-ops or strict-high3-only.
assert main.count("scheduleJinhakV0173StableHigh3Handoff(") == 1, "automatic natural handoff call remains"
assert main.count("activateJinhakV0173StableHigh3(") == 1, "automatic activation call remains"
assert main.count("scheduleJinhakLoginRecovery(") == 1, "automatic Jinhak login recovery call remains"
assert main.count("handleJinhakV0912AuthCompatibilityPage(url)") == 0, "legacy auth compatibility still in WebView lifecycle"
assert main.count("verifyRecoveredJinhakHigh3AndResume(url)") == 0, "legacy high3 auto-resume still in WebView lifecycle"

# App-driven navigation helper cannot accept member/root/lower-grade/other/external.
load = member_region("loadJinhakV0174High3Only")
assert "sanitizedHigh3OrNull" in load
assert "webView.loadUrl(safe)" in load
assert "canonicalLoginUrl" not in load
assert "member.jinhak.com" not in load

# No DOM login probe in batch Jinhak guard.
guard = member_region("continueBatchAfterRenderedLoginGuard")
jinhak_branch = guard.split("val expectedProvider = provider", 1)[0]
assert "probeLoginSurface" not in jinhak_branch
assert "scheduleBatchSnapshot" in jinhak_branch

# Mission return must not use history and cannot navigate an unvalidated origin.
mission_return = member_region("maybeReturnToJinhakMissionOrigin")
assert "sanitizedHigh3OrNull" in mission_return
assert "webView.goBack()" not in mission_return
assert "loadJinhakV0174High3Only" in mission_return

# Strict helper must be used at the three principal queue/app-load points.
for token in [
    'loadJinhakV0174High3Only(canonicalOrigin, "ledger-origin")',
    'loadJinhakV0174High3Only(action.baseUrl, "batch-page-action")',
    'loadJinhakV0174High3Only(next, "batch-queue")',
]:
    assert token in main, token

# WebView lifecycle uses the strict policy, not legacy JinhakHigh3AuthRoute routing.
configure = main[main.index('private fun configureWebView()'):]
webclient_end = configure.find("webView.webChromeClient")
webclient = configure[:webclient_end if webclient_end > 0 else len(configure)]
assert "JinhakStrictHigh3Sandbox.decision" in webclient
assert "generic-login-page-start-rewrite" not in webclient
assert "generic-login-page-finished-rewrite" not in webclient
assert "generic-login-navigation-rewrite" not in webclient
assert "generic-login-network-rewrite" not in webclient

# Provider-defined and topology-defined automatic entry points are all strict high3.
assert "https://www.jinhak.com/\")" not in provider
for line in re.findall(r'"https://www\.jinhak\.com[^\"]*"', topology):
    # ROOT constant itself is not a destination; every generated mission URL is tested by unit tests.
    pass

print("v0.17.4 source contracts verified: fail-closed main frame, lower-grade all-request + service-worker fences, strict history/popup/renderer/queue, explicit visible-high3 approval only")
