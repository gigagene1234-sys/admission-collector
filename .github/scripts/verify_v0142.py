from pathlib import Path
import hashlib, re, sqlite3

# Collection/canonical components that v0.14.2 must not disturb. Mission coverage is intentionally
# excluded because v0.14.2 restores university-result to the required integrated lane set.
EXPECTED = {
    'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt': '068e9f20cd75edf9a271117f945be52859241771ef60da634a585ca98a0634e5',
    'app/src/main/java/com/admissionhub/collector/canonical/CanonicalSixApplicationGraph.kt': '3784b0c519772748579c9169a961bfb60ef4761066fc2b3f28d1472de58b4302',
    'app/src/main/java/com/admissionhub/collector/canonical/AdigaOfficialTableBindingPolicy.kt': 'cf3bb69a8b2413abae878155e0af7da4b4167bd928202668976273178b8f0cda',
    'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionCellSupervisor.kt': '27199ee1fa8beb083e2146506cd6c3f57513c0221db7e7f433300f60a896541d',
    'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionTargetLedger.kt': '29f870c698ad767e7a9f6a6f11340723863b3817e2d89cee77e0deea5e74f2c2',
    'app/src/main/java/com/admissionhub/collector/jinhak/JinhakApplicationMission.kt': 'f0f277c0f59a2b05c32b15da5bafedb92b0df645aae5d77699d9918e46fe4980',
    'app/src/main/java/com/admissionhub/collector/jinhak/JinhakAuthDomainPolicy.kt': '460235228e7781b194f79f01b8124414745d454f7b4ff1e19e2f74a907d674d6',
    'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt': '667d5a49af366cd5c2753a50cdeab3b9db412acadd001d1177bc62100177e0fa',
    'app/src/main/java/com/admissionhub/collector/sync/LocalRebindPolicy.kt': 'a6c5e373b294a871203e94179ca5cc04811c0a601223634acf769b35c67d75ed',
    'app/src/main/java/com/admissionhub/collector/hub/HubFirstLayoutPolicy.kt': '717da7fbe153ceaaac142c3373f65f16973a5fd0f3be68904064f7dd456fb1d7',
}
for path, expected in EXPECTED.items():
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert actual == expected, f'Cumulative core changed: {path}: {actual}'

root = Path('app/src/main/java/com/admissionhub/collector')
main = (root / 'MainActivity.kt').read_text()
store = (root / 'local/LocalCollectorStore.kt').read_text()
credential = (root / 'session/CredentialVault.kt').read_text()
session = (root / 'session/SecureSessionVault.kt').read_text()
coverage = (root / 'jinhak/JinhakMissionCoverageLedger.kt').read_text()
sequencer = (root / 'jinhak/JinhakMissionLaneSequencer.kt').read_text()
xlsx = (root / 'score/XlsxStudentScoreImport.kt').read_text()
xls = (root / 'score/LegacyXlsStudentScoreImport.kt').read_text()
excel_activity = (root / 'score/XlsxImportActivity.kt').read_text()
score_ui = (root / 'score/ScoreReviewUi.kt').read_text()
calculator = (root / 'score/OfficialUniversityScoreCalculator.kt').read_text()
materializer = (root / 'score/AdigaAutoScoreMaterializer.kt').read_text()
manifest = Path('app/src/main/AndroidManifest.xml').read_text()
build = Path('app/build.gradle.kts').read_text()

# Product identity.
assert 'versionCode = 114200' in build and 'versionName = "0.14.2"' in build
assert 'private const val VERSION = "0.14.2"' in main and 'private const val BUILD_CODE = 114200' in main
assert 'Admission Hub v0.14.2 One-Step + Auto Login' in manifest
assert '.score.XlsxImportActivity' in manifest and 'android:exported="false"' in manifest
assert 'org.apache.poi:poi:5.2.5' in build

# One-screen transcript UX: automatic parse -> visible editable rows -> save + six-card analysis.
for required in [
    'INTEGRATED_ANALYZE_EDIT_SAVE',
    '자동 분석된 학생부 · 바로 수정 가능',
    '현재 입력 다시 분석',
    '저장 + 6장 대학환산 · 공식입결 분석',
    'renderAnalysisResults',
    'AdigaAutoScoreMaterializer.materializeSelected',
    'HorizontalScrollView',
]:
    assert required in excel_activity, 'One-step transcript UI contract missing: ' + required
assert 'Excel 저장 전 확인' not in excel_activity
assert '학생부 Excel 분석 · 입력 · 대학환산 한 번에' in score_ui
for required in ['application/vnd.ms-excel', 'LegacyXlsStudentScoreImport.looksLikeXls', "bytes[0] == 'P'.code.toByte()"]:
    assert required in excel_activity, 'Excel format support lost: ' + required
for required in ['HSSFWorkbook', 'cachedFormulaResultType', 'OLE2', 'MAX_ROWS', 'MAX_COLUMNS']:
    assert required in xls, 'Legacy XLS safety contract missing: ' + required
for forbidden in ['FormulaEvaluator', 'evaluateFormulaCell', 'evaluateAllFormulaCells']:
    assert forbidden not in xls + xlsx, 'Formula execution introduced: ' + forbidden
for required in ['DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY', 'PRESERVE_NULL', 'MERGED_YEAR_SEMESTER_ONLY']:
    assert required in xlsx + excel_activity, 'Blank/formula/merge safety contract lost: ' + required

# Automatic login is local encrypted storage plus DOM form submission, not export-time credential leakage.
for required in [
    'AndroidKeyStore', 'AES/GCM/NoPadding', 'KeyGenParameterSpec', 'fun save(', 'fun load(',
    'admission_local_credentials_v2', 'credentialExportAllowed',
]:
    assert required in credential, 'Encrypted credential vault contract missing: ' + required
assert 'admission_local_credentials_v1' not in credential
assert '.edit().clear()' not in credential
for required in [
    'credentialVault.load(which.wireName)', 'credentialVault.save(which.wireName',
    '저장하고 자동 로그인', 'webView.evaluateJavascript(script)',
    'submitted-awaiting-provider-verification', 'credentialAutoLoginSubmissions += 1',
    'JSONObject.quote(credential.username)', 'JSONObject.quote(credential.password)',
]:
    assert required in main, 'Automatic login runtime contract missing: ' + required
assert 'Compatibility entry point for old recovery callers: manual login only.' not in main
assert '.put("credentialStorage", "android-keystore-aes-gcm")' in main
# Secrets may be injected only into the provider login page. They must never be attached to exported/cloud JSON.
for forbidden in [
    '.put("username", credential.username)', '.put("password", credential.password)',
    '.put("username", username.text', '.put("password", password.text',
    'sendDiagnostic("credential"', 'sendRecordCheckpoint("credential"'
]:
    assert forbidden not in main, 'Credential export/log path introduced: ' + forbidden
assert 'removeAllCookies' not in credential + session

# Integrated Jinhak collection must include the previously dropped university-result lane.
assert '"university-result"' in coverage
core_block = re.search(r'val CORE_LANES = listOf\((.*?)\)\n', coverage, re.S)
assert core_block, 'CORE_LANES not found'
for lane in ['saved-application','current-prediction','mock-support','actual-admit','score-analysis','university-result']:
    assert f'"{lane}"' in core_block.group(1), 'Missing integrated core lane: ' + lane
assert '"strategy"' not in core_block.group(1), 'Strategy should remain optional, not a crawl completion blocker'
assert '.put("strategyOptional", true)' in coverage
assert '"university-result"' in sequencer

# Score automation remains evidence-bounded and six slots remain immutable.
for required in ['woosong(', 'hanbat(', 'holistic-not-quantitative', 'unsupported-official-formula']:
    assert required in calculator, 'University score guard missing: ' + required
assert 'loadHubApplicationSlots' in materializer and 'upsertUniversityConversionResult' in materializer and 'storeOfficialAdmissionOutcome' in materializer
assert '.put("slotsMutated", false)' in materializer
for forbidden in ['replaceHub', 'saveHubApplicationSlot', 'deleteHub', 'primaryReference = true']:
    assert forbidden not in materializer, 'Automatic score materializer mutates user slots/reference: ' + forbidden

# Existing data stays additive; no DB-version jump or destructive migration is needed for this UX/auth patch.
assert '\n    10\n) {' in store and 'if (oldVersion < 10) ensureFoundationSchema(db)' in store
connection = sqlite3.connect(':memory:')
connection.executescript('CREATE TABLE score_student_profiles(profile_id TEXT PRIMARY KEY, source_json TEXT); CREATE TABLE hub_application_slots(slot INTEGER PRIMARY KEY, application_identity_key TEXT); CREATE TABLE records(id INTEGER PRIMARY KEY,json TEXT);')
connection.execute('INSERT INTO score_student_profiles VALUES (?,?)', ('synthetic-profile', '{"grade":3}'))
connection.executemany('INSERT INTO hub_application_slots VALUES (?,?)', [(i, 'synthetic-' + str(i)) for i in range(1, 7)])
connection.execute('INSERT INTO records VALUES (?,?)', (1, '{"fixture":true}'))
statements = re.findall(r'db.execSQL\("(CREATE TABLE IF NOT EXISTS application_review_[^"\n]+)"\)', store)
assert len(statements) == 2
for _ in range(2):
    for sql in statements: connection.execute(sql)
assert connection.execute('SELECT count(*) FROM hub_application_slots').fetchone()[0] == 6
assert connection.execute('SELECT source_json FROM score_student_profiles').fetchone()[0] == '{"grade":3}'
assert connection.execute('SELECT count(*) FROM records').fetchone()[0] == 1

print('v0.14.2 one-screen transcript, encrypted auto-login, restored integrated university-result lane, score guards and additive data checks passed')
