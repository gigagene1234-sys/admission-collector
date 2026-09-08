from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text()

main = read('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle = read('app/build.gradle.kts')
manifest = read('app/src/main/AndroidManifest.xml')
score = read('app/src/main/java/com/admissionhub/collector/score/OfficialUniversityScoreCalculator.kt')
materializer = read('app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt')
published = read('app/src/main/java/com/admissionhub/collector/score/OfficialPublishedOutcomeFallback.kt')
fence = read('app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt')

assert 'versionCode = 116200' in gradle
assert 'versionName = "0.16.2"' in gradle
assert 'private const val VERSION = "0.16.2"' in main
assert 'private const val BUILD_CODE = 116200' in main
assert 'Admission Hub v0.16.2 Jinhak Fail-Closed' in manifest

# Real-device regression: v0.16.1 recursively re-evaluated the hidden unsafe login DOM every 500 ms.
# v0.16.2 must terminalize the Jinhak phase instead of retrying that page.
assert 'private var jinhakLowerGradeLoginFenceLatched = false' in main
assert 'private fun terminateJinhakLowerGradeLoginLoop' in main
assert 'jinhak-lower-grade-login-terminal-fence' in main
assert 'loginPageReopenAllowed", false' in main
assert 'retrySuppressed", true' in main
assert 'finishBatch("jinhak-lower-grade-login-fenced")' in main
assert 'finishUnifiedCollection("jinhak-lower-grade-login-fenced")' in main
assert 'if (jinhakLowerGradeLoginFenceLatched) return' in main
assert 'which == ProviderId.JINHAK && jinhakLowerGradeLoginFenceLatched' in main
assert 'jinhakLowerGradeLoginFenceLatched = false' in main
assert 'webView.loadUrl("about:blank")' in main
assert 'page-finished-after-product-fence' in main
assert '180L' in main
assert 'installJinhakHigh3DomProductFence("unsafe-login-recheck")' not in main
assert '고1·고2 리다이렉트 차단 · 로그인 재시도 없이 고3 보호경로로 복귀합니다.' not in main

# Direct lower-grade URL and same-URL DOM product cases are both fail-closed during authentication.
assert 'terminateJinhakLowerGradeLoginLoop("lower-grade-navigation"' in main
assert 'terminateJinhakLowerGradeLoginLoop("lower-grade-redirect"' in main
assert 'terminateJinhakLowerGradeLoginLoop(' in main and '"unsafe-login-dom"' in main
for token in ['/jh/high1/', '/jh/high2/', '/jh/high12/']:
    assert token in fence

# Official evidence and transcript safety from v0.16.1 remain intact.
assert 'StudentScoreDocumentCompleteness.assess(profile)' in score
assert 'AdigaFullEvidenceRescan.scanSelected(store, sessionId, selectedCandidates)' in materializer
assert 'OfficialPublishedOutcomeFallback.materializeMissing(store, sessionId, selectedCandidates)' in materializer
assert '.put("jinhakPromoted", false)' in published
assert '.put("historicalBindingRelaxed", false)' in published
assert '.put("probabilityInferred", false)' in published
assert '.put("historicalBindingRelaxed", false)' in materializer
assert '.put("slotsMutated", false)' in materializer
assert '.put("probabilityInferred", false)' in materializer

print('v0.16.2 fail-closed Jinhak auth contracts verified')
