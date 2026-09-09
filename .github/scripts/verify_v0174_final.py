from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).with_name("verify_v0174.py")

# Preserve every first-pass v0.17.4 invariant while accepting the hardened schema.
source = BASE.read_text()
source = source.replace(
    '"sandboxSchema": "const val SCHEMA_VERSION = 1" in sandbox,',
    '"sandboxSchema": "const val SCHEMA_VERSION = 2" in sandbox,'
)
namespace = {"__name__": "__main__", "__file__": str(BASE.resolve())}
exec(compile(source, str(BASE), "exec"), namespace, namespace)

main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
adapter = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt").read_text()
provider = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/ProviderId.kt").read_text()
slow = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSlowLanePool.kt").read_text()
sandbox = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakStrictHigh3Sandbox.kt").read_text()
grade = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt").read_text()
auth = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakHigh3AuthRoute.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakUserSessionPolicy.kt").read_text()
build = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()

checks = {
    "versionName": 'versionName = "0.17.4"' in build,
    "versionCode": "versionCode = 117400" in build,
    "manifestLabel": 'Admission Hub v0.17.4 Strict High3 Sandbox' in manifest,
    "sandboxSchema2": "const val SCHEMA_VERSION = 2" in sandbox,
    "gradeFenceSchema5": "const val SCHEMA_VERSION = 5" in grade,
    "authRouteSchema4": "const val SCHEMA_VERSION = 4" in auth,
    "gradeDecodeRounds12": "MAX_DECODE_ROUNDS = 12" in grade and "repeat(MAX_DECODE_ROUNDS + 1)" in grade,
    "authDecodeRounds12": "MAX_DECODE_ROUNDS = 12" in auth and "repeat(MAX_DECODE_ROUNDS)" in auth,
    "gradeFullUrlScan": "var candidate = normalize(url.take(MAX_SCAN_CHARS))" in grade,
    "gradeBackslashNormalization": "replace('\\\\', '/')" in grade,
    "memberLoginRequiresHigh3Return": "BLOCK_MEMBER_LOGIN_WITHOUT_HIGH3_RETURN" in sandbox and "JinhakHigh3AuthRoute.returnUrl(url)" in sandbox,
    "genericLoginBlocked": "BLOCK_GENERIC_LOGIN" in sandbox,
    "sharedRootBlocked": "BLOCK_SHARED_ROOT" in sandbox,
    "collectorNavigationHigh3Only": "fun allowsCollectorNavigation(url: String): Boolean = decision(url) == MainFrameDecision.ALLOW_HIGH3" in sandbox,
    "providerDefaultNotSharedRoot": 'JINHAK("jinhak", "진학사", "https://www.jinhak.com/")' not in provider,
    "adapterUsesStrictSandbox": "JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)" in adapter,
    "adapterRawRegexCompileSafe": 'Regex("""\\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|map|woff2?|ttf|eot|zip|hwp|hwpx|pdf)$"""' in adapter,
    "adapterIllegalEscapeAbsent": 'Regex("\\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|map|woff2?|ttf|eot|zip|hwp|hwpx|pdf)$"' not in adapter,
    "centralForegroundLoader": "private fun loadMainUrl(target: String, source: String = \"app-load\")" in main,
    "centralLoaderStrictDecision": "val decision = JinhakStrictHigh3Sandbox.decision(target)" in main,
    "centralLoaderBlocksOther": 'blockJinhakV0174MainFrame("central-$source", target, decision)' in main,
    "siteMemberExceptionStrict": "private fun loadJinhakV0174SiteMemberLogin" in main and "decision != JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN" in main,
    "physicalBackStrict": "if (provider == ProviderId.JINHAK) {\n            if (webView.canGoBack()) safeJinhakV0174Back()" in main,
    "spaHistoryFence": "override fun doUpdateVisitedHistory(view: WebView, url: String, isReload: Boolean)" in main and 'blockJinhakV0174MainFrame("spa-history", url, decision)' in main,
    "spaNeutralizes": 'loadMainUrl("about:blank", "spa-history-neutralize")' in main,
    "paginationRetryCentralized": "webView.loadUrl(retry.baseUrl)" not in main,
    "retryOriginCentralized": "webView.loadUrl(retryOrigin)" not in main,
    "failedRouteCentralized": "webView.loadUrl(failedRoute)" not in main,
    "directJinhakHomeAbsent": "webView.loadUrl(ProviderId.JINHAK.homeUrl)" not in main,
    "directCoreProbeAbsent": "webView.loadUrl(coreProbe)" not in main,
    "slowLaneStrictQueue": "JinhakStrictHigh3Sandbox.allowsCollectorNavigation(raw)" in slow,
    "slowLaneAllRequestFence": "JinhakStrictHigh3Sandbox.shouldBlockAnyRequest(target)" in slow,
    "slowLaneMainFrameFence": "request.isForMainFrame && !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(target)" in slow,
    "slowLanePageStartFence": "slow-lane-strict-high3-block" in slow,
    "slowLaneNoBroadHostAllow": 'host.endsWith(".jinhak.com")' not in slow,
    "userNoSharedRoot": "fun collectorMayUseSharedProductRoot(): Boolean = false" in policy,
    "userNoGenericRouter": "fun collectorMayUseGenericProductLoginRouter(): Boolean = false" in policy,
    "userNoAutoResume": "fun collectorMayAutoResumeAfterLogin(): Boolean = false" in policy,
    "userNoLoginVerify": "fun collectorMayVerifyLogin(): Boolean = false" in policy,
    "userNoCredentialRead": "fun collectorMayReadCredentials(): Boolean = false" in policy,
    "userNoCredentialSubmit": "fun collectorMaySubmitCredentials(): Boolean = false" in policy,
    "userNoLeaseRestore": "fun collectorMayRestoreJinhakAuthLease(): Boolean = false" in policy,
    "userNoLeaseCapture": "fun collectorMayCaptureJinhakAuthLease(): Boolean = false" in policy,
    "userNoSessionExtend": "fun collectorMayExtendJinhakSession(): Boolean = false" in policy,
    "probabilitySafety": "probabilityInferred" in main,
    "credentialExportSafety": '.put("credentialExported", false)' in main,
    "sessionSecretExportSafety": '.put("sessionSecretExported", false)' in main,
}

# After final patch, every ordinary foreground app-originated load is centralized.
# Raw calls are allowed only inside the central loader and the exact high3-bound site-member helper.
raw_load_positions = [m.start() for m in re.finditer(r"webView\.loadUrl\(", main)]
checks["rawForegroundLoadCountBounded"] = len(raw_load_positions) == 4
if raw_load_positions:
    helper_start = main.index("private fun loadMainUrl")
    helper_end = main.index("private fun loadJinhakV0174High3Only", helper_start)
    checks["rawForegroundLoadsConfinedToHelpers"] = all(helper_start <= p < helper_end for p in raw_load_positions)
else:
    checks["rawForegroundLoadsConfinedToHelpers"] = False

# Renderer replacement paths may use a different WebView instance, but persisted targets must
# be sanitized before reuse; an old raw mission origin is forbidden.
checks["rendererCurrentTargetSanitized"] = "JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget) ?: resumeUrl" in main
checks["rendererMissionOriginSanitized"] = "JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(jinhakMissionOriginRoute)" in main
checks["rendererCoreProbeSanitized"] = "JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(JinhakSiteTopology.protectedCoreProbeUrl())" in main
checks["noRawRendererMissionOrigin"] = "val missionOrigin = jinhakMissionOriginRoute.takeIf { it.isNotBlank() }" not in main

failed = [name for name, ok in checks.items() if not ok]
print(checks)
print({"rawForegroundWebViewLoadCalls": len(raw_load_positions)})
if failed:
    raise SystemExit("v0.17.4 FINAL source verification failed: " + ", ".join(failed))

print("v0.17.4 FINAL source verification passed: strict high3 route sandbox + central load primitive + physical back + SPA history + hidden slow lane + deep encoding fences")
