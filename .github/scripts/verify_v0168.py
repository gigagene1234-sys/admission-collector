from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
AUTH = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakHigh3AuthRoute.kt").read_text()
EVENT = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakAuthEventState.kt").read_text()
GRADLE = (ROOT / "app/build.gradle.kts").read_text()
MANIFEST = (ROOT / "app/src/main/AndroidManifest.xml").read_text()


def require(token: str, text: str, label: str):
    if token not in text:
        raise SystemExit(f"missing {label}: {token}")


def forbid(token: str, text: str, label: str):
    if token in text:
        raise SystemExit(f"forbidden {label}: {token}")


require('versionCode = 116800', GRADLE, 'versionCode')
require('versionName = "0.16.8"', GRADLE, 'versionName')
require('Admission Hub v0.16.8 Event-Driven High3 Auth', MANIFEST, 'manifest label')
require('private const val VERSION = "0.16.8"', MAIN, 'runtime version')
require('private const val BUILD_CODE = 116800', MAIN, 'runtime build')

# Architecture: one pure route classifier, direct member login + high3 ReturnURL, passive wait.
for token in [
    'JinhakAuthEventState.action',
    'openJinhakDirectHigh3Auth',
    'markJinhakDirectAuthWait',
    'WAIT_FOR_SERVER_RETURN',
    'VERIFY_HIGH3_SESSION',
    'OBSERVE_WITHOUT_NAVIGATION',
    'v0168-real-auth-poll-suppressed',
    'v0168-startup-poll-suppressed',
    'jinhakV0168EventDrivenAuth',
    'jinhakV0168RecursiveAuthPolling',
    'jinhakV0168DomGradeUiMask',
]: require(token, MAIN, token)

for token in [
    'DROP_REQUEST',
    'OPEN_CANONICAL_HIGH3_AUTH_ONCE',
    'WAIT_FOR_SERVER_RETURN',
    'VERIFY_HIGH3_SESSION',
    'OBSERVE_WITHOUT_NAVIGATION',
]: require(token, EVENT, token)

for token in ['member.jinhak.com', 'ReturnURL', '/jh/high3']:
    require(token, AUTH, f'high3 auth contract {token}')

# Absolutely no grade-selector UI masking or forced grade click remains in product source.
for token in [
    'installJinhakHigh3DomProductFence',
    "style.setProperty('display','none','important')",
    "setAttribute('aria-hidden'",
    "setAttribute('tabindex','-1'",
    'stopImmediatePropagation',
    'high3-product-preflight',
    '__admissionVisualLowerGradeFenceInstalled',
]: forbid(token, MAIN, 'grade UI manipulation')

# The historical recursive recovery function may not exist at all.
forbid('private fun pollJinhakLoginRecovery', MAIN, 'recursive login recovery implementation')
forbid('handler.postDelayed({ pollJinhakLoginRecovery', MAIN, 'recursive login recovery scheduling')

# Event-driven replacements must not hide the WebView or force high3 load while waiting on member login.
def function_body(signature: str) -> str:
    start = MAIN.find(signature)
    if start < 0: raise SystemExit(f'function missing: {signature}')
    brace = MAIN.find('{', start)
    depth = 0; i = brace; in_s=False; triple=False; line=False; block=False
    while i < len(MAIN):
        ch=MAIN[i]; nxt=MAIN[i:i+2]; tri=MAIN[i:i+3]
        if line:
            if ch=='\n': line=False
            i+=1; continue
        if block:
            if nxt=='*/': block=False; i+=2; continue
            i+=1; continue
        if triple:
            if tri=='"""': triple=False; i+=3; continue
            i+=1; continue
        if in_s:
            if ch=='\\': i+=2; continue
            if ch=='"': in_s=False
            i+=1; continue
        if nxt=='//': line=True; i+=2; continue
        if nxt=='/*': block=True; i+=2; continue
        if tri=='"""': triple=True; i+=3; continue
        if ch=='"': in_s=True; i+=1; continue
        if ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0: return MAIN[start:i+1]
        i+=1
    raise SystemExit(f'function unterminated: {signature}')

for sig in [
    'private fun resumeAfterLogin()',
    'private fun attemptSavedCredentialLoginV0912Baseline(reason: String)',
    'private fun handleJinhakTransitionAuthGate(url: String)',
    'private fun handleJinhakRealAuthProbePageFinished(url: String)',
    'private fun scheduleJinhakRealAuthProbePoll(generation: Int',
]:
    body = function_body(sig)
    forbid('visibility = View.INVISIBLE', body, f'auth UI hide in {sig}')
    forbid('installJinhakHigh3DomProductFence', body, f'auth DOM mask in {sig}')

# Lower-grade transport drop must never navigate or change visibility.
body = function_body('private fun hardBlockJinhakLowerGradeNavigation')
forbid('loadUrl(', body, 'lower-grade hard block navigation')
forbid('visibility =', body, 'lower-grade hard block visibility mutation')
require('networkRequestAllowed', body, 'lower-grade network false evidence')
require('followLowerGrade', body, 'lower-grade follow false evidence')

# Jinhak startup poll is a suppression branch, not a scheduler.
body = function_body('private fun scheduleStartupLoginPoll')
require('expectedProvider == ProviderId.JINHAK', body, 'Jinhak startup poll suppression')
require('return', body, 'Jinhak startup poll early return')

# Evidence-safe admission semantics remain intact.
score = (ROOT / 'app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt').read_text()
require('.put("probabilityInferred", false)', score, 'probability false')

print('v0.16.8 source contracts verified')
