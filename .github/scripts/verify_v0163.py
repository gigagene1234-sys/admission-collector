from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text()

main = read('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle = read('app/build.gradle.kts')
manifest = read('app/src/main/AndroidManifest.xml')
fence = read('app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt')
materializer = read('app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt')

assert 'versionCode = 116300' in gradle
assert 'versionName = "0.16.3"' in gradle
assert 'private const val VERSION = "0.16.3"' in main
assert 'private const val BUILD_CODE = 116300' in main
assert 'Admission Hub v0.16.3 High3 Recover' in manifest

# Regression from the real v0.16.2 device export: lower-grade blocking must not terminate Jinhak.
assert 'private fun recoverJinhakLowerGradeLoginContext' in main
assert 'MAX_JINHAK_LOWER_GRADE_HIGH3_RECOVERIES = 2' in main
assert 'JINHAK_LOWER_GRADE_HIGH3_RECOVERY' in main
assert 'JINHAK_HIGH3_LOGIN_GATE' in main
assert '.put("jinhakPhaseTerminated", false)' in main
assert 'reload-protected-high3-core-and-resume-auth' in main
assert 'authenticate-on-high3-login-then-resume-crawl' in main
assert 'private fun verifyRecoveredJinhakHigh3AndResume' in main
assert 'resumeBatchAfterVerifiedJinhakAuth("lower-grade-high3-recovered")' in main
assert 'protected-core-verified-after-lower-grade-recovery' in main
assert '진학사 고3·N수 인증 복구 완료 · 진학사 수집 엔진을 시작합니다.' in main
assert 'startBatch()' in main
assert 'jinhakLowerGradeManualGateActive' in main
assert 'jinhak-high3-login-gate-wait' in main
assert '고1·2 화면은 열지 않고 고3·N수 보호경로에서 인증을 다시 확인합니다.' in main

# The v0.16.2 terminal behavior must be gone from product logic.
assert 'finishBatch("jinhak-lower-grade-login-fenced")' not in main
assert 'finishUnifiedCollection("jinhak-lower-grade-login-fenced")' not in main
assert 'nextAction", "finish-jinhak-phase-without-login-retry"' not in main

# URL and DOM lower-grade fences remain intact while recovery is high3-only.
for token in ['/jh/high1/', '/jh/high2/', '/jh/high12/']:
    assert token in fence
assert 'JinhakGradeRouteFence.protectedHigh3Core()' in main
assert 'installJinhakHigh3DomProductFence' in main
assert '__admissionHigh3FenceInstalled' in main

# Source/evidence safety contracts remain unchanged.
assert 'AdigaFullEvidenceRescan.scanSelected(store, sessionId, selectedCandidates)' in materializer
assert '.put("historicalBindingRelaxed", false)' in materializer
assert '.put("slotsMutated", false)' in materializer
assert '.put("probabilityInferred", false)' in materializer
assert 'adigaOfficialEvidencePreserved' in main
assert 'probabilityInferred' in main

print('v0.16.3 product contracts verified')
