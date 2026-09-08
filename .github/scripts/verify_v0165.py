from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text()

main = read('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle = read('app/build.gradle.kts')
manifest = read('app/src/main/AndroidManifest.xml')
dashboard = read('app/src/main/java/com/admissionhub/collector/hub/AdmissionDashboardActivity.kt')
pipeline = read('app/src/main/java/com/admissionhub/collector/hub/PipelineCompletionModel.kt')

assert 'versionCode = 116500' in gradle
assert 'versionName = "0.16.5"' in gradle
assert 'private const val VERSION = "0.16.5"' in main
assert 'private const val BUILD_CODE = 116500' in main
assert 'Admission Hub v0.16.5 Login Handoff + Dashboard Gates' in manifest

# Preserve the v0.9.12-compatible passive redirect boundary from v0.16.4.
assert 'private fun jinhakAuthCompatibilityWindowActive()' in main
assert 'handleJinhakV0912AuthCompatibilityPage(url)' in main
assert 'private fun attemptSavedCredentialLoginV0912Baseline(reason: String)' in main
assert 'JinhakGradeRouteFence.isHigh3(url)' in main
assert 'jinhakAuthVerifiedForBatch = true' in main
assert 'resumeBatchAfterVerifiedJinhakAuth("v0912-protected-core-verified")' in main
assert 'productStateChanged:false' in main

# v0.16.5: when Collector-local credentials do not exist, keep the actual Jinhak login page stable
# instead of repeatedly taking navigation ownership away from device autofill / the user.
assert 'v0165-manual-login-stable-surface' in main
assert 'v0165-no-local-credential-manual-login' in main
assert 'jinhakV0165ManualLoginWaits' in main
assert 'jinhakV0165ManualLoginVerifiedHandoffs' in main
assert '사이트 로그인·동의 완료 후 계속' in main

# A verified protected high3 route is the success point for the independent real-site probe too.
assert 'jinhakV0165ProbeCompletedFromProtectedCore' in main
assert 'finishJinhakRealAuthProbe("protected-core-verified-v0165", success = true)' in main

# Dashboard makes completion gates and source separation explicit.
for token in [
    '① 세션 상태',
    '② 파이프라인 완성도',
    '③ HOLD/경고 원인 · 지원 6장',
    '④ 다음 액션',
    'probabilityInferred',
    '공식(어디가·대학)',
    '진학사(사용자 열람 추정)',
    'missing',
    'warnings',
    'risks',
    'disclaimer',
]:
    assert token in dashboard

for token in [
    '1. 진학사 로그인 확인',
    '2. 진학사 수집 시작',
    '3. 진학사 사용자 열람 자료',
    '4. 공식 근거',
    '5. 공식 환산',
    '6. 근거 안전 판단',
    '비교 가능 또는 근거가 명시된 HOLD',
]:
    assert token in pipeline

# Security/evidence invariants.
credential = read('app/src/main/java/com/admissionhub/collector/session/CredentialVault.kt')
assert 'AndroidKeyStore' in credential
assert 'AES/GCM/NoPadding' in credential
assert '.put("probabilityInferred", false)' in read('app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt')
assert 'jinhakPromotedToOfficial' not in pipeline

print('v0.16.5 login-handoff and dashboard-gate contracts verified')
