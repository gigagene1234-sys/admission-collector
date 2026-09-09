from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
POLICY = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakDedicatedAuthPolicy.kt"
STRICT = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakStrictHigh3Sandbox.kt"
VAULT = ROOT / "app/src/main/java/com/admissionhub/collector/session/CredentialVault.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"

main = MAIN.read_text()
policy = POLICY.read_text()
strict = STRICT.read_text()
vault = VAULT.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

required = {
    "versionName": 'versionName = "0.18.0"' in gradle,
    "versionCode": 'versionCode = 118000' in gradle,
    "manifestLabel": 'Admission Hub v0.18.0 Dedicated Auto Login' in manifest,
    "runtimeVersion": 'private const val VERSION = "0.18.0"' in main,
    "runtimeBuild": 'private const val BUILD_CODE = 118000' in main,
    "dedicatedAuthWebView": 'private lateinit var authWebView: WebView' in main,
    "dedicatedAuthHost": 'private lateinit var authHost: FrameLayout' in main,
    "authConfig": 'private fun configureDedicatedJinhakAuthWebView()' in main,
    "authStart": 'private fun startV0180DedicatedJinhakAuth' in main,
    "authAutofill": 'private fun attemptV0180JinhakAuthAutofill' in main,
    "authSuccess": 'private fun completeV0180DedicatedJinhakAuth' in main,
    "authRendererRecovery": 'private fun recreateV0180AuthWebView' in main,
    "currentLoginUrl": 'const val LOGIN_URL = "https://www.jinhak.com/jh/member/login"' in policy,
    "collectorLoginBlocked": 'BLOCK_GENERIC_LOGIN' in strict and 'allowsCollectorNavigation' in strict,
    "lowerGradePolicy": 'BLOCK_LOWER_GRADE' in policy and 'JinhakGradeRouteFence.isBlockedLowerGrade' in policy,
    "keystoreAesGcm": 'AndroidKeyStore' in vault and 'AES/GCM/NoPadding' in vault,
    "v0180Diagnostics": '.put("v0180DedicatedAuthWebView", true)' in main,
    "noRecursiveAuthPollingContract": '.put("v0180RecursiveAuthPolling", false)' in main,
    "collectorDoesNotOwnLogin": '.put("v0180CollectorOwnsLogin", false)' in main,
}
missing = [name for name, ok in required.items() if not ok]
if missing:
    raise SystemExit('missing v0.18.0 source contracts: ' + ', '.join(missing))

# v0.17.x intentionally disabled Jinhak local credential login. Those disable paths must be gone.
for forbidden in [
    'saved-credential-login-disabled',
    'Collector 계정 입력·저장을 사용하지 않습니다',
    'v0.17.0은 진학사 Collector 계정 입력·저장을 사용하지 않습니다',
]:
    if forbidden in main:
        raise SystemExit(f'legacy Jinhak credential-disable residue remains: {forbidden}')

# Collector WebView must redirect login to the dedicated auth path rather than loading it.
if 'startV0180DedicatedJinhakAuth("collector-network-login")' not in main:
    raise SystemExit('collector network login reroute missing')
if 'startV0180DedicatedJinhakAuth("collector-navigation-login")' not in main:
    raise SystemExit('collector navigation login reroute missing')
if 'startV0180DedicatedJinhakAuth("collector-page-started-login")' not in main:
    raise SystemExit('collector page-started login reroute missing')

# Auth is bounded/event-driven: no auth function may schedule itself recursively.
for fn in ['attemptV0180JinhakAuthAutofill', 'inspectV0180SubmittedLogin', 'startV0180DedicatedJinhakAuth']:
    m = re.search(rf'private fun {fn}\b.*?\n    \}}', main, re.S)
    if not m:
        raise SystemExit(f'cannot locate {fn}')
    body = m.group(0)
    if fn != 'attemptV0180JinhakAuthAutofill' and f'{fn}(' in body[body.find('{')+1:]:
        raise SystemExit(f'recursive auth function found: {fn}')
# Autofill may schedule only the next bounded attempt; max count is a constant.
if 'V0180_AUTH_MAX_FILL_ATTEMPTS = 3' not in main:
    raise SystemExit('bounded fill attempts contract missing')

# Do not export credential/form/cookie payloads from the new diagnostics block.
diag = re.search(r'\.put\("v0180DedicatedAuthWebView", true\).*?\.put\("v0180AuthLastSafePath", jinhakV0180AuthLastSafePath\)', main, re.S)
if not diag:
    raise SystemExit('v0.18.0 diagnostics block missing')
for forbidden in ['username', 'password', 'credential.username', 'credential.password', 'getCookie(', 'document.cookie']:
    if forbidden in diag.group(0):
        raise SystemExit(f'sensitive value exposed in v0.18.0 diagnostics: {forbidden}')

# Admission decision safety must remain fail-closed.
score_sources = '\n'.join(p.read_text(errors='ignore') for p in (ROOT / 'app/src/main/java').rglob('*.kt'))
if '.put("probabilityInferred", false)' not in score_sources:
    raise SystemExit('probabilityInferred=false safety contract missing')

print('v0.18.0 dedicated-auth source contracts verified')
