from pathlib import Path
import hashlib, re, sqlite3

# Unchanged collection/auth/canonical identity core inherited from the verified v0.14 product.
EXPECTED = {
    'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt': '068e9f20cd75edf9a271117f945be52859241771ef60da634a585ca98a0634e5',
    'app/src/main/java/com/admissionhub/collector/canonical/CanonicalSixApplicationGraph.kt': '3784b0c519772748579c9169a961bfb60ef4761066fc2b3f28d1472de58b4302',
    'app/src/main/java/com/admissionhub/collector/canonical/AdigaOfficialTableBindingPolicy.kt': 'cf3bb69a8b2413abae878155e0af7da4b4167bd928202668976273178b8f0cda',
    'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionCellSupervisor.kt': '27199ee1fa8beb083e2146506cd6c3f57513c0221db7e7f433300f60a896541d',
    'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionCoverageLedger.kt': '4f86f5c87c428ae9d80aabaa8328e53adee97abb105f2f869f6fce6e779fe8be',
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
xlsx = (root / 'score/XlsxStudentScoreImport.kt').read_text()
excel_activity = (root / 'score/XlsxImportActivity.kt').read_text()
xls = (root / 'score/LegacyXlsStudentScoreImport.kt').read_text()
calculator = (root / 'score/OfficialUniversityScoreCalculator.kt').read_text()
materializer = (root / 'score/AdigaAutoScoreMaterializer.kt').read_text()
adiga_evidence = (root / 'canonical/AdigaOfficialAdmissionEvidence.kt').read_text()
adiga_diag = (root / 'canonical/AdigaApplicationEvidenceAnalyzer.kt').read_text()
historical = (root / 'canonical/AdigaHistoricalOutcomeExtractor.kt').read_text()
manifest = Path('app/src/main/AndroidManifest.xml').read_text()
build = Path('app/build.gradle.kts').read_text()

assert 'versionCode = 114100' in build and 'versionName = "0.14.1"' in build
assert 'org.apache.poi:poi:5.2.5' in build
assert 'Admission Hub v0.14.1 Excel + Adiga Score' in manifest
assert '.score.XlsxImportActivity' in manifest and 'android:exported="false"' in manifest
assert '\n    10\n) {' in store and 'if (oldVersion < 10) ensureFoundationSchema(db)' in store

# Real Excel format handling: both OLE2 XLS and OOXML XLSX, local/read-only, no formula execution.
for required in ['application/vnd.ms-excel', 'LegacyXlsStudentScoreImport.looksLikeXls', "bytes[0] == 'P'.code.toByte()", 'AdigaAutoScoreMaterializer.materializeSelected']:
    assert required in excel_activity, 'Missing Excel import contract: ' + required
for required in ['HSSFWorkbook', 'cachedFormulaResultType', 'OLE2', 'MAX_ROWS', 'MAX_COLUMNS']:
    assert required in xls, 'Missing XLS safety/format contract: ' + required
for forbidden in ['FormulaEvaluator', 'evaluateFormulaCell', 'evaluateAllFormulaCells']:
    assert forbidden not in xls + xlsx, 'Formula execution introduced: ' + forbidden
for required in ['DO_NOT_EVALUATE_USE_SAVED_CACHED_VALUE_ONLY', 'PRESERVE_NULL', 'MERGED_YEAR_SEMESTER_ONLY']:
    assert required in xlsx, 'XLSX safety contract lost: ' + required

# Official evidence semantics: component verification is distinct from direct same-row binding.
for required in ['rowCells', 'scopeCells', 'departmentCells', 'historicalOutcome']:
    assert required in adiga_evidence, 'Structured Adiga evidence missing: ' + required
for required in ['currentComponentsVerified', 'currentApplicationBoundCount', 'historicalOutcomes', 'automaticPromotion']:
    assert required in adiga_diag, 'Adiga diagnostic field missing: ' + required
assert '.put("automaticPromotion", false)' in adiga_diag
assert 'sameOfficialTableSegment' in adiga_evidence
for required in ['headersVerified', '50', '70', 'converted50', 'grade70']:
    assert required in historical, 'Historical outcome verification lost: ' + required

# Narrow score automation must never invent a holistic score or mutate the six user slots.
for required in ['woosong(', 'hanbat(', 'holistic-not-quantitative', 'unsupported-official-formula', 'currentComponentsVerified']:
    assert required in calculator, 'University calculator guard missing: ' + required
assert '학생부종합Ⅱ는 공식 서류 정성평가' in calculator
assert 'loadHubApplicationSlots' in materializer and 'upsertUniversityConversionResult' in materializer and 'storeOfficialAdmissionOutcome' in materializer
assert '.put("slotsMutated", false)' in materializer
for forbidden in ['replaceHub', 'saveHubApplicationSlot', 'deleteHub', 'primaryReference = true']:
    assert forbidden not in materializer, 'Automatic slot/reference mutation introduced: ' + forbidden

# Existing score export/read path remains present.
assert 'score_conversion_results' in store and 'score_official_outcomes' in store
assert 'conversionLabel' in store and 'officialOutcomeLabel' in store
assert 'conversionLabel' in main and 'officialOutcomeLabel' in main

# Credential/session boundary inherited from the verified v0.14 product.
for forbidden in ['credentials.password', 'credentials.username', 'credentialVault.save(', 'selected.pass', 'selected.submit.click', 'userJs', 'passJs']:
    assert forbidden not in main, 'Automatic credential injection remains: ' + forbidden
for forbidden in ['Cipher', 'getCookie(', 'setCookie(', 'cookieHeader', 'fun save(', 'fun load(']:
    assert forbidden not in credential + session, 'Custom secret storage remains: ' + forbidden
assert 'removeAllCookies' not in credential + session and 'DELETE FROM' not in credential + session

# DB version and additive local state remain unchanged.
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

print('v0.14.1 XLS/XLSX, Adiga structured outcome, score-calculation, slot immutability and credential boundary checks passed')
