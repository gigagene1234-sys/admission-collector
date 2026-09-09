from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakUserSessionPolicy.kt").read_text()
build = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()

def member_region(name: str) -> str:
    marker = f"    private fun {name}"
    start = main.find(marker)
    if start < 0:
        raise SystemExit(f"member missing: {name}")
    candidates = []
    for token in ["\n    private fun ", "\n    private val ", "\n    private var ", "\n    private data class ", "\n    private class ", "\n    private object "]:
        idx = main.find(token, start + len(marker))
        if idx >= 0:
            candidates.append(idx)
    end = min(candidates) if candidates else len(main)
    return main[start:end]

checks = {
    "versionName": 'versionName = "0.17.3"' in build,
    "versionCode": "versionCode = 117300" in build,
    "mainVersion": 'private const val VERSION = "0.17.3"' in main,
    "mainBuildCode": "private const val BUILD_CODE = 117300" in main,
    "label": 'Admission Hub v0.17.3 Natural High3 Handoff' in manifest,
    "policySchema2": "const val SCHEMA_VERSION = 2" in policy,
    "policyArmOnLogin": "ARM_AFTER_SITE_LOGIN" in policy and "confirmationDecision" in policy,
    "policyStaleCallback": "shouldIgnoreStaleLoginCallback" in policy,
    "resumeArmedState": "jinhakV0173ResumeArmed" in main,
    "naturalResume": "activateJinhakV0173StableHigh3" in main,
    "stabilityDelay": "stabilityMs\", 900" in main and "}, 900L)" in main,
    "staleCounter": "jinhakV0173StaleLoginCallbacksIgnored" in main,
    "noAutoBootstrapDiagnostic": '.put("v0173AutoBootstrapNavigations", 0)' in main,
    "sessionAuthority": '.put("jinhakSessionAuthority", "user")' in main,
    "policyNoVerify": 'fun collectorMayVerifyLogin(): Boolean = false' in policy,
    "policyNoCredentials": 'fun collectorMayReadCredentials(): Boolean = false' in policy and 'fun collectorMaySubmitCredentials(): Boolean = false' in policy,
    "policyNoLease": 'fun collectorMayRestoreJinhakAuthLease(): Boolean = false' in policy and 'fun collectorMayCaptureJinhakAuthLease(): Boolean = false' in policy,
    "policyNoExtend": 'fun collectorMayExtendJinhakSession(): Boolean = false' in policy,
    "lowerGradeFence": "hardBlockJinhakLowerGradeNavigation" in main and "JinhakGradeRouteFence.isBlockedLowerGrade" in main,
    "predictionSafety": "probabilityInferred" in main,
    "noCredentialExport": '.put("credentialExported", false)' in main,
    "noSessionSecretExport": '.put("sessionSecretExported", false)' in main,
}
failed = [k for k, v in checks.items() if not v]
print(checks)
if failed:
    raise SystemExit("v0.17.3 verification failed: " + ", ".join(failed))

confirm = member_region("confirmJinhakUserSessionAndResume")
assert "confirmationDecision(current)" in confirm
assert "ARM_AFTER_SITE_LOGIN" in confirm
assert "armJinhakV0173NaturalHigh3Resume" in confirm
assert "scheduleJinhakV0173StableHigh3Handoff" in confirm
assert "webView.loadUrl" not in confirm
assert "jinhakUserSessionConfirmed = true" not in confirm

activate = member_region("activateJinhakV0173StableHigh3")
assert "jinhakUserSessionConfirmed = true" in activate
assert "collectCurrentPage()" in activate
assert "webView.loadUrl" not in activate

breaker = member_region("breakJinhakLoginRedirectLoopAfterUserConfirmation")
assert "armJinhakV0173NaturalHigh3Resume" in breaker
assert "automaticBootstrapNavigation\", false" in breaker
assert "webView.loadUrl" not in breaker

compat = member_region("handleJinhakV0912AuthCompatibilityPage")
assert "isJinhakV0173StaleLoginCallback" in compat
assert "scheduleJinhakV0173StableHigh3Handoff" in compat

mark_wait = member_region("markJinhakDirectAuthWait")
assert "isJinhakV0173StaleLoginCallback" in mark_wait

transition_gate = member_region("handleJinhakTransitionAuthGate")
assert "isJinhakV0173StaleLoginCallback" in transition_gate

transition = member_region("transitionUnifiedToJinhak")
assert "currentBatchTarget = null" in transition
assert "currentBatchTarget = canonicalizeBatchUrl(JinhakSiteTopology.userSessionBootstrapUrl())" not in transition

begin = member_region("beginBatchNavigation")
assert "collectCurrentPage()" in begin
assert "canonicalizeBatchUrl(startUrl) == visible" in begin

# Critical negative contracts: no Jinhak credential/session lease access was reintroduced.
for token in [
    'sessionVault.restore(ProviderId.JINHAK.wireName)',
    'sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName',
]:
    assert token not in main, token

# The v0.17.2 failure was app-driven post-confirmation bootstrap. No v0.17.3
# handoff function may load the synthetic bootstrap route.
for name in [
    "confirmJinhakUserSessionAndResume",
    "activateJinhakV0173StableHigh3",
    "breakJinhakLoginRedirectLoopAfterUserConfirmation",
    "armJinhakV0173NaturalHigh3Resume",
    "scheduleJinhakV0173StableHigh3Handoff",
]:
    region = member_region(name)
    assert "userSessionBootstrapUrl" not in region, name
    assert "webView.loadUrl" not in region, name

print("v0.17.3 source contracts verified: login-page confirmation only arms, stale callbacks are ignored, stable natural high3 resumes in-place, and no synthetic post-login bootstrap is issued")
