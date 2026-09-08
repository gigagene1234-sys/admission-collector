from pathlib import Path

root = Path('app/src/main/java/com/admissionhub/collector')
main = (root / 'MainActivity.kt').read_text()
credential = (root / 'session/CredentialVault.kt').read_text()
session = (root / 'session/SecureSessionVault.kt').read_text()
score_ui = (root / 'score/ScoreReviewUi.kt').read_text()
unified_excel = (root / 'score/UnifiedExcelScoreActivity.kt').read_text()
coverage = (root / 'jinhak/JinhakMissionCoverageLedger.kt').read_text()
topology = (root / 'jinhak/JinhakSiteTopology.kt').read_text()
manifest = Path('app/src/main/AndroidManifest.xml').read_text()
build = Path('app/build.gradle.kts').read_text()

# Product identity.
assert 'private const val VERSION = "0.14.2"' in main
assert 'private const val BUILD_CODE = 114200' in main
assert 'versionCode = 114200' in build and 'versionName = "0.14.2"' in build
assert 'Admission Hub v0.14.2 Unified Auto' in manifest
assert '.score.UnifiedExcelScoreActivity' in manifest

# One-screen Excel recognition/edit/save path.
for required in [
    '학생부 자동 분석 · 입력', 'autoRecognize(workbook)', '저장 + 6장 통합 분석',
    'LegacyXlsStudentScoreImport.parse', 'XlsxStudentScoreImport.parse',
    'AdigaAutoScoreMaterializer.materializeSelected', 'automaticRecognition'
]:
    assert required in unified_excel, 'Missing unified Excel behavior: ' + required
assert 'Excel 자동 분석 · 바로 입력' in score_ui
assert 'UnifiedExcelScoreActivity::class.java' in score_ui

# Encrypted local credential storage and actual auto-login wiring.
for required in [
    'AndroidKeyStore', 'AES/GCM/NoPadding', 'KeyGenParameterSpec',
    'fun save(', 'fun load(', 'data class Credential'
]:
    assert required in credential, 'Missing secure credential feature: ' + required
assert 'admission_secure_credentials_v2' in credential
assert 'credentialVault.load(which.wireName)' in main
assert 'credentialVault.save(which.wireName' in main
assert 'setValue(user,$userJson)' in main and 'setValue(pass,$passJson)' in main
assert 'credentialAutoLoginSubmissions += 1' in main
assert 'success-session-verified' in main
# Credentials must not be exported/cloud persisted by this feature.
for forbidden in ['cloudOffload', 'source_json', 'INSERT INTO', 'CookieManager']:
    assert forbidden not in credential, 'Credential vault crossed trust boundary: ' + forbidden

# Session persistence is metadata-only; native WebView owns cookies.
assert 'admission_auth_lease_metadata_v4' in session
assert 'containsSessionSecret' in session and 'cloudExportAllowed' in session
# Boolean metadata such as containsPassword=false is allowed; actual secret APIs/fields are not.
for forbidden in ['getCookie(', 'setCookie(', 'cookieHeader', 'credential.password', 'password =', 'password: String']:
    assert forbidden not in session, 'Session lease copied secret material: ' + forbidden

# Integrated Jinhak collection must include university-result and allow strategy/knowledge traversal.
assert '"university-result"' in coverage
core_fragment = coverage.split('val CORE_LANES = listOf(', 1)[1].split(')', 1)[0]
assert '"university-result"' in core_fragment
assert 'JinhakMissionLane.STRATEGY,' in topology
assert 'JinhakMissionLane.ADMISSION_KNOWLEDGE -> true' in topology
assert '$ROOT/jh/high3/ipsi-analysis/ipsi-strategy' in topology

# Preserve the core conservative official-score behavior added in v0.14.1.
calc = (root / 'score/OfficialUniversityScoreCalculator.kt').read_text()
assert '2027 && university.contains("우송")' in calc
assert '2027 && university.contains("한밭")' in calc
assert 'holistic-not-quantitative' in calc

print('v0.14.2 unified Excel, encrypted auto-login, integrated Jinhak traversal and score contracts passed')
