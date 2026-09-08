from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
auth = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakHigh3AuthRoute.kt").read_text()
fence = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt").read_text()
gradle = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()


def need(token: str, text: str, label: str):
    if token not in text:
        raise SystemExit(f"missing {label}: {token}")


def forbid(token: str, text: str, label: str):
    if token in text:
        raise SystemExit(f"forbidden {label}: {token}")


def block(start: str, end: str) -> str:
    a = main.find(start)
    b = main.find(end, a + len(start)) if a >= 0 else -1
    if a < 0 or b < 0:
        raise SystemExit(f"cannot extract block: {start} -> {end}")
    return main[a:b]

need('versionCode = 116700', gradle, 'versionCode')
need('versionName = "0.16.7"', gradle, 'versionName')
need('android:label="Admission Hub v0.16.7 Direct High3 Auth"', manifest, 'label')
need('private const val VERSION = "0.16.7"', main, 'runtime version')
need('private const val BUILD_CODE = 116700', main, 'runtime build code')

# Canonical login is the identity provider with an explicit high3 ReturnURL.
need('https://member.jinhak.com/MemberV3/MemberJoin/MemberLogIn.aspx', auth, 'member login root')
need('ReturnURL=', auth, 'ReturnURL')
need('isAllowedHigh3Target', auth, 'high3 target validator')
need('REWRITE_GENERIC_LOGIN', auth, 'generic login rewrite decision')
need('BLOCK_LOWER_GRADE', auth, 'lower grade transport decision')
need('JinhakHigh3AuthRoute.canonicalLoginUrl(currentBatchTarget)', main, 'provider direct login')
forbid('ProviderId.JINHAK -> "https://www.jinhak.com/jh/member/login"', main, 'generic login bootstrap')

# The old UI approach is completely absent, not merely hidden behind another condition.
for token in [
    'installJinhakHigh3DomProductFence',
    '__admissionVisualLowerGradeFenceInstalled',
    'jinhak-lower-grade-selector-hidden',
    "style.setProperty('display','none','important')",
    "setAttribute('aria-hidden','true')",
    "stopImmediatePropagation",
]:
    forbid(token, main, 'grade-selector UI masking')

# Lower-grade block is transport-only: no stopLoading, visibility mutation, loadUrl, or retry.
hard = block(
    '    private fun hardBlockJinhakLowerGradeNavigation(source: String, target: String) {',
    '    private fun openJinhakDirectHigh3Auth(reason: String, requestedTarget: String?) {'
)
for token in ['stopLoading', 'View.INVISIBLE', 'View.VISIBLE', 'loadUrl(', 'postDelayed', 'scheduleJinhak']:
    forbid(token, hard, 'lower-grade hard block side effect')
need('.put("networkRequestAllowed", false)', hard, 'transport deny evidence')
need('.put("visibilityMutation", false)', hard, 'no visibility mutation evidence')
need('.put("recoveryNavigationScheduled", false)', hard, 'no recovery navigation evidence')

# Direct member auth may navigate exactly once, but cannot manipulate visibility or grade DOM.
direct = block(
    '    private fun openJinhakDirectHigh3Auth(reason: String, requestedTarget: String?) {',
    '    private fun markJinhakDirectAuthWait(reason: String, url: String) {'
)
need('JinhakHigh3AuthRoute.canonicalLoginUrl(target)', direct, 'canonical member login construction')
need('webView.loadUrl(login)', direct, 'one direct login navigation')
need('jinhakV0167AuthWaitDuplicateSuppressions', direct, 'duplicate auth suppression')
for token in ['View.INVISIBLE', 'View.VISIBLE', 'evaluateJavascript', 'display:none', 'click()']:
    forbid(token, direct, 'direct auth UI mutation')

wait = block(
    '    private fun markJinhakDirectAuthWait(reason: String, url: String) {',
    '    private fun jinhakLowerGradeAuthFenceShouldTerminate(): Boolean {'
)
for token in ['loadUrl(', 'postDelayed', 'View.INVISIBLE', 'View.VISIBLE', 'evaluateJavascript']:
    forbid(token, wait, 'auth wait navigation/UI mutation')
need('.put("navigationPolling", false)', wait, 'no polling evidence')

# Legacy compatibility and protected-core verification are bounded by page events; the old recursive
# login-recovery poll function must not exist anywhere.
forbid('pollJinhakLoginRecovery(', main, 'recursive auth poller')
forbid('scheduleJinhakHigh3RouteIsolationRecovery', main, 'lower-grade recovery navigation')
compat = block(
    '    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {',
    '    private fun recoverJinhakLowerGradeLoginContext(source: String, detail: JSONObject = JSONObject()) {'
)
for token in ['checkSessionState', 'postDelayed', 'View.INVISIBLE', 'View.VISIBLE', 'loadUrl(']:
    forbid(token, compat, 'compatibility login loop/UI mutation')
need('ALLOW_CANONICAL_AUTH', compat, 'canonical member auth handling')

verify = block(
    '    private fun verifyRecoveredJinhakHigh3AndResume(url: String): Boolean {',
    '    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {'
)
need('JinhakGradeRouteFence.isHigh3(url)', verify, 'high3-only auth promotion')
need('jinhakV0912ProtectedCoreVerified += 1', verify, 'protected core evidence')
need('openJinhakDirectHigh3Auth("protected-high3-login-required", url)', verify, 'single direct auth fallback')
for token in ['View.INVISIBLE', 'View.VISIBLE', 'installJinhakHigh3DomProductFence']:
    forbid(token, verify, 'protected verifier UI mutation')

recovery = block(
    '    private fun scheduleJinhakLoginRecovery(reason: String) {',
    '    private fun completeJinhakVerifiedAuth(reason: String) {'
)
for token in ['postDelayed', 'pollJinhakLoginRecovery', 'View.INVISIBLE', 'View.VISIBLE']:
    forbid(token, recovery, 'single-shot recovery recursion/UI mutation')
need('JinhakHigh3AuthRoute.isMemberLoginSurface(current)', recovery, 'member auth wait recognition')
need('openJinhakDirectHigh3Auth', recovery, 'single-shot auth entry')

# Jinhak credential submission itself can fill the actual member login form once, but must not force
# navigation, invoke grade UI, or recursively probe after submission.
cred = block(
    '    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {',
    '    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {'
)
need('v0167-submitted-awaiting-server-high3-return', cred, 'submit waits for ReturnURL')
for token in ['webView.loadUrl(', 'scheduleJinhakLoginRecovery', 'installJinhakHigh3DomProductFence', 'high3-product-preflight']:
    forbid(token, cred, 'credential forced navigation/grade preflight')

# Diagnostics must expose the regression counters without secrets.
for token in [
    'jinhakV0167CanonicalAuthEntries',
    'jinhakV0167GenericLoginRewrites',
    'jinhakV0167LowerGradeTransportDrops',
    'jinhakV0167AuthWaitDuplicateSuppressions',
    'jinhakV0167AuthExitsToHigh3',
    'jinhakV0167GenericProductLoginBootstrap", false',
    'jinhakV0167DomGradeUiMask", false',
    'jinhakV0167RecursiveLoginPolling", false',
    'credentialExported", false',
    'sessionSecretExported", false',
]:
    need(token, main, 'diagnostic/safety contract')

# Grade fence remains transport-based and nested-return aware.
need('const val SCHEMA_VERSION = 4', fence, 'route fence schema')
need('URLDecoder.decode', fence, 'nested redirect decoding')
need('/jh/high1/', fence, 'high1 marker')
need('/jh/high2/', fence, 'high2 marker')
need('/jh/high12/', fence, 'high12 marker')

# Evidence-safe decision policy remains intact elsewhere in the product.
auto_score = (ROOT / "app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt").read_text()
need('.put("probabilityInferred", false)', auto_score, 'probability non-inference')

print('v0.16.7 product contracts verified')
