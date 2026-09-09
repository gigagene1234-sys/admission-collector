from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).with_name("verify_v0174.py")

# Reuse the exhaustive verifier, updating only the sandbox schema expectation introduced by the
# second hardening pass.
source = BASE.read_text()
old = '"sandboxSchema": "const val SCHEMA_VERSION = 1" in sandbox,'
new = '"sandboxSchema": "const val SCHEMA_VERSION = 2" in sandbox,'
if old not in source:
    raise SystemExit("base v0174 verifier schema anchor missing")
source = source.replace(old, new, 1)
namespace = {"__name__": "__main__", "__file__": str(BASE.resolve())}
exec(compile(source, str(BASE), "exec"), namespace, namespace)

main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
slow = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSlowLanePool.kt").read_text()
sandbox = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakStrictHigh3Sandbox.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakUserSessionPolicy.kt").read_text()
provider = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/ProviderId.kt").read_text()

extra = {
    "sandboxSchema2": "const val SCHEMA_VERSION = 2" in sandbox,
    "memberLoginNeedsHigh3Return": "BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN" in sandbox and "JinhakHigh3AuthRoute.returnUrl(url)" in sandbox and "isAllowedHigh3Target(returnTarget)" in sandbox,
    "sharedRootNotProviderDefault": 'JINHAK("jinhak", "진학사", "https://www.jinhak.com/")' not in provider,
    "foregroundNoDirectHomeLoad": "webView.loadUrl(ProviderId.JINHAK.homeUrl)" not in main,
    "foregroundNoDirectCoreProbeLoad": "webView.loadUrl(coreProbe)" not in main,
    "foregroundNoDirectRetryOrigin": "webView.loadUrl(retryOrigin)" not in main,
    "foregroundNoDirectFailedRoute": "webView.loadUrl(failedRoute)" not in main,
    "strictProviderLoginFallback": "JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget) ?: JinhakStrictHigh3Sandbox.strictEntryUrl()" in main,
    "slowLaneStrictQueue": "JinhakStrictHigh3Sandbox.allowsCollectorNavigation(raw)" in slow,
    "slowLaneAllRequestLowerGradeFence": "JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)" in slow,
    "slowLaneMainFrameStrictFence": "request.isForMainFrame && !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(target)" in slow,
    "slowLanePageStartStrictFence": "slow-lane-strict-high3-block" in slow,
    "slowLaneNoBroadHostAllow": 'host.endsWith(".jinhak.com")' not in slow,
    "userNoSharedRoot": "fun collectorMayUseSharedProductRoot(): Boolean = false" in policy,
    "userNoGenericRouter": "fun collectorMayUseGenericProductLoginRouter(): Boolean = false" in policy,
    "userNoAutoResume": "fun collectorMayAutoResumeAfterLogin(): Boolean = false" in policy,
}
failed = [k for k, v in extra.items() if not v]
print(extra)
if failed:
    raise SystemExit("v0.17.4 hardening verification failed: " + ", ".join(failed))

# The allowed member-login branch is not a Collector destination. It is only a server-returned,
# high3-bound surface. App navigation continues to accept ALLOW_HIGH3 only.
assert "fun allowsCollectorNavigation(url: String): Boolean = decision(url) == MainFrameDecision.ALLOW_HIGH3" in sandbox
assert "returnTarget.isNullOrBlank()" in sandbox

# Remaining direct member-login load is permitted only after strict decision inside popup handoff.
popup_region = main[main.index("private fun handoff(target: String): Boolean"):]
popup_region = popup_region[:popup_region.index("override fun shouldOverrideUrlLoading")]
assert "MainFrameDecision.ALLOW_MEMBER_LOGIN -> webView.loadUrl(target)" in popup_region
assert "val decision = JinhakStrictHigh3Sandbox.decision(target)" in popup_region

print("v0.17.4 hardening verified: high3-bound member login only; foreground retry paths centralized; hidden slow lane fail-closed high3-only")
