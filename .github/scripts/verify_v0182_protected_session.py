from pathlib import Path

main=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt').read_text()
gradle=Path('app/build.gradle.kts').read_text()
manifest=Path('app/src/main/AndroidManifest.xml').read_text()
policy=Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakProtectedSessionPolicy.kt').read_text()

def require(token: str, text: str, label: str):
    if token not in text:
        raise SystemExit(f'missing {label}: {token}')

require('versionCode = 118200', gradle, 'versionCode')
require('versionName = "0.18.2"', gradle, 'versionName')
require('Admission Hub v0.18.2 Protected Session Bootstrap', manifest, 'manifest label')
require('private const val VERSION = "0.18.2"', main, 'collector version')
require('JinhakProtectedSessionPolicy', main, 'protected policy import/use')
require('jinhakV0182ProtectedSessionVerified = false', main, 'protected verification initial state')
require('jinhakAuthVerifiedForBatch = false // v0.18.2: public high3/user approval is not protected-session proof', main, 'public high3 not proof')
require('v0182-high3-return-awaiting-protected-proof', main, 'high3 handoff not proof')
require('private fun requestV0182ProtectedSessionProbe', main, 'bounded protected bootstrap')
require('private fun markV0182ProtectedSessionVerified', main, 'protected proof transition')
require('collector-page-finished-protected', main, 'collector page-finished proof boundary')
require('jinhakV0182AutofillChainGeneration == generation', main, 'single-flight autofill')
require('jinhakV0182AutofillAttemptsThisGeneration >= V0180_AUTH_MAX_FILL_ATTEMPTS', main, 'bounded auth attempts')
require('localStore.prepareSelectedSixRecovery(sessionId)', main, 'local recovery scope before network')
require('JinhakProtectedSessionPolicy.shouldRunMissionStallFence', main, 'stall fence protected-only')
require('PROTECTED_SAVED_APPLICATIONS', policy, 'protected saved application classification')
require('PROTECTED_REPORT', policy, 'protected report classification')
require('protectedVerified && missionTargetCount > 0', policy, 'stall fence target requirement')

for forbidden in [
    'jinhakAuthVerifiedForBatch = true // compatibility flag == explicit user approval on visible high3 only',
    'jinhakLastAuthEvidence = "v0180-server-high3-return"',
    'credentialAutoLoginLastResult = "v0180-success-high3-return"'
]:
    if forbidden in main:
        raise SystemExit(f'forbidden legacy false-positive auth contract remains: {forbidden}')

print('v0.18.2 source contracts verified')
