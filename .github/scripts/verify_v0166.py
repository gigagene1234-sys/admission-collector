from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
grade = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt").read_text()
gradle = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()
dash = (ROOT / "app/src/main/java/com/admissionhub/collector/hub/AdmissionDashboardActivity.kt").read_text()
materializer = (ROOT / "app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt").read_text()

required_main = [
    'private const val VERSION = "0.16.6"',
    'private const val BUILD_CODE = 116600',
    'override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse?',
    'request.isForMainFrame && JinhakGradeRouteFence.isBlockedLowerGrade(target)',
    'blockedJinhakLowerGradeResponse()',
    'jinhak-v0166-lower-grade-hard-block',
    '.put("networkRequestAllowed", false)',
    '.put("followLowerGrade", false)',
    'jinhak-v0166-return-to-protected-high3',
    '.put("oneShot", true)',
    'webView.visibility = View.VISIBLE',
    'v0166-shared-login-visual-fence',
    'v0166-authenticated-handoff-to-protected-high3',
    'if (JinhakGradeRouteFence.isBlockedLowerGrade(v0165Current))',
    'if (JinhakGradeRouteFence.isBlockedLowerGrade(currentUrl))',
    '!JinhakGradeRouteFence.isBlockedLowerGrade(retry)',
    'JinhakGradeRouteFence.protectedHigh3Core().ifBlank { ProviderId.JINHAK.homeUrl }',
    'JinhakGradeRouteFence.isHigh3(url) && lane == com.admissionhub.collector.jinhak.JinhakMissionLane.UNKNOWN',
    'jinhakV0166LowerGradeRequestsIntercepted',
    'jinhakV0166LowerGradeNavigationsHardBlocked',
    'jinhakV0166LowerGradeRecoveryDispatches',
]
for token in required_main:
    assert token in main, token

for forbidden in [
    'jinhak-v0912-hidden-auth-transition',
    '.put("blockedBeforeAuth", false)',
    'Authentication transitions are handled by the v0.9.12 compatibility path above.',
]:
    assert forbidden not in main, forbidden

assert 'const val SCHEMA_VERSION = 3' in grade
assert 'repeat(3)' in grade
assert 'URLDecoder.decode(context' in grade
assert 'versionCode = 116600' in gradle
assert 'versionName = "0.16.6"' in gradle
assert 'android:label="Admission Hub v0.16.6 High3 Route Isolation"' in manifest

# Evidence-safety contracts must remain intact.
for token in ['relation', 'probabilityInferred', 'disclaimer', 'missing', 'warnings', 'risks']:
    assert token in dash, token
assert '.put("probabilityInferred", false)' in materializer
assert 'Jinhak→official' not in main

print("v0.16.6 product contracts verified")
