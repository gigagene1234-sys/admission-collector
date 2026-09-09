from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
topology = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakUserSessionPolicy.kt").read_text()
build = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()

checks = {
    "versionName": 'versionName = "0.17.2"' in build,
    "versionCode": "versionCode = 117200" in build,
    "mainVersion": 'private const val VERSION = "0.17.2"' in main,
    "mainBuildCode": "private const val BUILD_CODE = 117200" in main,
    "label": 'Admission Hub v0.17.2 Bootstrap-Safe Jinhak Session' in manifest,
    "publicBootstrap": 'fun userSessionBootstrapUrl(): String = "$ROOT/jh/high3/early/four-year-university/search"' in topology,
    "protectedCoreSeparate": 'fun protectedCoreProbeUrl(): String = "$ROOT/jh/high3/early/four-year-university/library"' in topology,
    "bootstrapFirstSeed": re.search(r'fun missionSeeds\(\): List<String> = listOf\(\s*userSessionBootstrapUrl\(\)', topology) is not None,
    "bootstrapCoreEligible": 'if (isUserSessionBootstrapUrl(url)) score = maxOf(score, 86)' in topology and 'if (isUserSessionBootstrapUrl(url)) return true' in topology,
    "loopBreaker": 'private fun breakJinhakLoginRedirectLoopAfterUserConfirmation(reason: String): Boolean' in main,
    "userAuthorityPreserved": '.put("userConfirmationPreserved", true)' in main,
    "noImmediateProtectedReplay": '.put("protectedTargetImmediatelyReplayed", false)' in main,
    "bootstrapOnPausedResume": 'webView.loadUrl(JinhakSiteTopology.userSessionBootstrapUrl())' in main,
    "deferralSet": 'jinhakV0172DeferredProtectedTargets' in main,
    "bootstrapCounter": 'jinhakV0172BootstrapStarts' in main,
    "deferralCounter": 'jinhakV0172ProtectedRetryDeferrals' in main,
    "loopBreakCounter": 'jinhakV0172LoginRedirectLoopBreaks' in main,
    "authModel": 'user-owned-session-login-assumed-v0172-bootstrap-safe' in main,
    "sessionAuthority": '.put("jinhakSessionAuthority", "user")' in main,
    "policyNoVerify": 'fun collectorMayVerifyLogin(): Boolean = false' in policy,
    "policyNoCredentials": 'fun collectorMayReadCredentials(): Boolean = false' in policy and 'fun collectorMaySubmitCredentials(): Boolean = false' in policy,
    "policyNoLease": 'fun collectorMayRestoreJinhakAuthLease(): Boolean = false' in policy and 'fun collectorMayCaptureJinhakAuthLease(): Boolean = false' in policy,
    "policyNoExtend": 'fun collectorMayExtendJinhakSession(): Boolean = false' in policy,
    "expandedBrowser": 'val expandedBrowserHeight = maxOf(dp(720), (resources.displayMetrics.heightPixels * 0.68f).toInt())' in main,
    "predictionSafety": 'probabilityInferred' in main,
    "noCredentialExport": '.put("credentialExported", false)' in main,
    "noSessionSecretExport": '.put("sessionSecretExported", false)' in main,
}
failed = [k for k, v in checks.items() if not v]
print(checks)
if failed:
    raise SystemExit("v0.17.2 verification failed: " + ", ".join(failed))


def member_region(name: str) -> str:
    marker = f"    private fun {name}"
    start = main.find(marker)
    if start < 0:
        raise SystemExit(f"member missing: {name}")
    tail = main[start + len(marker):]
    m = re.search(r"\n    private\s+(?:fun|val|var|data\s+class|class|object)\b", tail)
    end = start + len(marker) + m.start() if m else len(main)
    return main[start:end]

confirm = member_region("confirmJinhakUserSessionAndResume")
assert 'webView.loadUrl(retry)' not in confirm
assert 'val retry = currentBatchTarget' not in confirm
assert 'JinhakSiteTopology.userSessionBootstrapUrl()' in confirm
assert 'jinhakV0172ProtectedRetryDeferrals' in confirm
assert 'currentBatchTarget = null' in confirm

breaker = member_region("breakJinhakLoginRedirectLoopAfterUserConfirmation")
assert 'jinhakUserSessionConfirmed' in breaker
assert 'jinhakUserSessionConfirmed = false' not in breaker
assert 'jinhakAuthVerifiedForBatch = false' not in breaker
assert 'JinhakSiteTopology.userSessionBootstrapUrl()' in breaker
assert 'batchVisited.add(deferred)' in breaker

transition = member_region("transitionUnifiedToJinhak")
assert 'currentBatchTarget = canonicalizeBatchUrl(JinhakSiteTopology.userSessionBootstrapUrl())' in transition
assert 'protectedHigh3Core' not in transition

# Critical user-owned-session negative contracts retained from v0.17.1.
for token in [
    'sessionVault.restore(ProviderId.JINHAK.wireName)',
    'sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName',
]:
    assert token not in main, token

# The post-confirm redirect handling may classify a login surface for routing, but it
# must not turn that observation into a Collector authentication verdict.
assert 'collectorVerifiesLogin", false' in main
assert 'collectorExtendsJinhakSession", false' in main

# Lower-grade hard transport fence remains present.
assert 'hardBlockJinhakLowerGradeNavigation' in main
assert 'JinhakGradeRouteFence.isBlockedLowerGrade' in main

print("v0.17.2 source contracts verified: screen-recording loop fixed by public bootstrap + protected retry deferral; user session authority and safety contracts retained")
