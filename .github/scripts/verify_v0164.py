from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text()

main = read('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle = read('app/build.gradle.kts')
manifest = read('app/src/main/AndroidManifest.xml')

assert 'versionCode = 116400' in gradle
assert 'versionName = "0.16.4"' in gradle
assert 'private const val VERSION = "0.16.4"' in main
assert 'private const val BUILD_CODE = 116400' in main
assert 'Admission Hub v0.16.4 v0.9.12 Auth Baseline' in manifest

# Regression baseline: v0.9.12 used passive rendered-form login and proved real-device Jinhak
# authentication/bootstrap. v0.16.4 must not let newer grade/product correction seize auth ownership.
assert 'private fun jinhakAuthCompatibilityWindowActive()' in main
assert '!jinhakAuthCompatibilityWindowActive()' in main
assert 'handleJinhakV0912AuthCompatibilityPage(url)' in main
assert 'private fun attemptSavedCredentialLoginV0912Baseline(reason: String)' in main
assert 'attemptSavedCredentialLoginV0912Baseline(reason)' in main
assert 'productStateChanged:false' in main
assert 'blockedBeforeAuth", false' in main
assert 'visibleToUser", false' in main
assert 'v0912-passive-login-protected-core-handoff' in main
assert 'v0912-protected-core-verified' in main
assert 'resumeBatchAfterVerifiedJinhakAuth("v0912-protected-core-verified")' in main
assert 'startBatch()' in main

# The shared Jinhak auth flow may transiently own internal routes while hidden; after high3 auth the
# collection grade fence remains active. Never promote a lower-grade route to authenticated evidence.
assert 'JinhakGradeRouteFence.isHigh3(url)' in main
assert 'jinhakAuthVerifiedForBatch = true' in main
assert 'jinhakLastAuthEvidence = "protected-core-stable-v0912-baseline"' in main
assert 'jinhak-post-auth-lower-grade-fenced' in main

# v0.16.2/v0.16.3 terminal/manual-gate regression is not allowed in the new compatibility functions.
start = main.index('private fun handleJinhakV0912AuthCompatibilityPage')
end = main.index('private fun attemptSavedCredentialLogin(which: ProviderId', start)
compat = main[start:end]
assert 'finishBatch("jinhak-lower-grade-login-fenced")' not in compat
assert 'finishUnifiedCollection("jinhak-lower-grade-login-fenced")' not in compat
assert 'automaticRecoveriesExhausted' not in compat
assert 'manualHigh3Gate' not in compat
assert 'phigh.click()' not in compat

# Real-device diagnostics must let the next export prove whether the working baseline path executed.
for token in [
    'jinhakV0912AuthCompatibilityTransitions',
    'jinhakV0912PassiveLoginSubmissions',
    'jinhakV0912ProtectedCoreHandoffs',
    'jinhakV0912ProtectedCoreVerified',
]:
    assert token in main

# Safety invariants: credentials remain local; auth diagnostics do not change evidence semantics.
assert 'AndroidKeyStore' in read('app/src/main/java/com/admissionhub/collector/session/CredentialVault.kt')
assert 'AES/GCM/NoPadding' in read('app/src/main/java/com/admissionhub/collector/session/CredentialVault.kt')
assert '.put("probabilityInferred", false)' in read('app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt')

print('v0.16.4 auth baseline product contracts verified')
