from pathlib import Path
import hashlib, json, re, sqlite3
EXPECTED = {'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt': '068e9f20cd75edf9a271117f945be52859241771ef60da634a585ca98a0634e5', 'app/src/main/java/com/admissionhub/collector/canonical/CanonicalSixApplicationGraph.kt': '3784b0c519772748579c9169a961bfb60ef4761066fc2b3f28d1472de58b4302', 'app/src/main/java/com/admissionhub/collector/canonical/AdigaOfficialAdmissionEvidence.kt': '90ca45fe4bee2f2075ae287939e1800369eb9758fb5efde4289229642e50c459', 'app/src/main/java/com/admissionhub/collector/canonical/AdigaOfficialTableBindingPolicy.kt': 'cf3bb69a8b2413abae878155e0af7da4b4167bd928202668976273178b8f0cda', 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionCellSupervisor.kt': '27199ee1fa8beb083e2146506cd6c3f57513c0221db7e7f433300f60a896541d', 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionCoverageLedger.kt': '4f86f5c87c428ae9d80aabaa8328e53adee97abb105f2f869f6fce6e779fe8be', 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionTargetLedger.kt': '29f870c698ad767e7a9f6a6f11340723863b3817e2d89cee77e0deea5e74f2c2', 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakApplicationMission.kt': 'f0f277c0f59a2b05c32b15da5bafedb92b0df645aae5d77699d9918e46fe4980', 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakAuthDomainPolicy.kt': '460235228e7781b194f79f01b8124414745d454f7b4ff1e19e2f74a907d674d6', 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt': '667d5a49af366cd5c2753a50cdeab3b9db412acadd001d1177bc62100177e0fa', 'app/src/main/java/com/admissionhub/collector/sync/LocalRebindPolicy.kt': 'a6c5e373b294a871203e94179ca5cc04811c0a601223634acf769b35c67d75ed', 'app/src/main/java/com/admissionhub/collector/hub/HubFirstLayoutPolicy.kt': '717da7fbe153ceaaac142c3373f65f16973a5fd0f3be68904064f7dd456fb1d7'}
for path, expected in EXPECTED.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, "Cumulative core changed: " + path
root=Path('app/src/main/java/com/admissionhub/collector')
main=(root/'MainActivity.kt').read_text()
store=(root/'local/LocalCollectorStore.kt').read_text()
credential=(root/'session/CredentialVault.kt').read_text()
session=(root/'session/SecureSessionVault.kt').read_text()
assert 'private const val VERSION = "0.13.0"' in main and 'private const val BUILD_CODE = 113000' in main
assert '\n    10\n) {' in store and 'if (oldVersion < 10) ensureFoundationSchema(db)' in store
assert 'ReviewExportContract.append' in store and 'sourceCollectorVersion' in (root/'score/ReviewExportContract.kt').read_text()
assert 'if (identity !in selected) continue' in store
assert 'setContentView(ScrollView' in main and 'ScoreReviewUi' in main
for forbidden in ['credentials.password', 'credentials.username', 'credentialVault.save(', 'selected.pass', 'selected.submit.click', 'userJs', 'passJs']:
    assert forbidden not in main, 'Automatic credential injection remains: '+forbidden
for forbidden in ['Cipher', 'getCookie(', 'setCookie(', 'cookieHeader', 'fun save(', 'fun load(']:
    assert forbidden not in credential + session, 'Custom secret storage remains: '+forbidden
assert 'admission_local_credentials_v1' in credential and '.clear().commit()' in credential
assert 'admission_secure_session_bundle_v2' in session and 'admission_secure_session_v1' in session
assert 'removeAllCookies' not in credential+session and 'DELETE FROM' not in credential+session
# Execute the exact additive migration SQL against representative v9 data.
connection=sqlite3.connect(':memory:')
connection.executescript('CREATE TABLE score_student_profiles(profile_id TEXT PRIMARY KEY, source_json TEXT); CREATE TABLE hub_application_slots(slot INTEGER PRIMARY KEY, application_identity_key TEXT); CREATE TABLE records(id INTEGER PRIMARY KEY,json TEXT);')
connection.execute('INSERT INTO score_student_profiles VALUES (?,?)',('synthetic-profile','{"grade":3}'))
connection.executemany('INSERT INTO hub_application_slots VALUES (?,?)',[(i,'synthetic-'+str(i)) for i in range(1,7)])
connection.execute('INSERT INTO records VALUES (?,?)',(1,'{"fixture":true}'))
statements=re.findall(r'db.execSQL\("(CREATE TABLE IF NOT EXISTS application_review_[^"\n]+)"\)',store)
assert len(statements)==2
for _ in range(2):
    for sql in statements: connection.execute(sql)
assert connection.execute('SELECT count(*) FROM hub_application_slots').fetchone()[0]==6
assert connection.execute('SELECT source_json FROM score_student_profiles').fetchone()[0]=='{"grade":3}'
assert connection.execute('SELECT count(*) FROM records').fetchone()[0]==1
print('v0.13 cumulative core, credential boundary, export wiring, selected-six scope and additive migration checks passed')
