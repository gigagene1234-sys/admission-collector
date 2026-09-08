from pathlib import Path

root = Path('.')
main = (root/'app/src/main/java/com/admissionhub/collector/MainActivity.kt').read_text()
manifest = (root/'app/src/main/AndroidManifest.xml').read_text()
gradle = (root/'app/build.gradle.kts').read_text()
excel = (root/'app/src/main/java/com/admissionhub/collector/score/UnifiedExcelScoreActivity.kt').read_text()
flex = (root/'app/src/main/java/com/admissionhub/collector/score/FlexibleTranscriptExtractor.kt').read_text()
auto = (root/'app/src/main/java/com/admissionhub/collector/canonical/OfficialEvidenceAutoLinker.kt').read_text()
material = (root/'app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt').read_text()
hub = (root/'app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt').read_text()
cred = (root/'app/src/main/java/com/admissionhub/collector/session/CredentialVault.kt').read_text()

assert 'private const val VERSION = "0.15.0"' in main
assert 'private const val BUILD_CODE = 115000' in main
assert 'versionCode = 115000' in gradle and 'versionName = "0.15.0"' in gradle
assert 'Admission Hub v0.15.0 Full Auto Evidence' in manifest
assert 'startAutomaticLoginAndCollectionSequence("manual-v0150-full-auto")' in main
assert 'app-launch-v0150-full-auto' in main
assert 'selectedSixAlreadyComplete() -> {' not in main
assert '어디가 + 진학사 자동 수집' in main
assert 'startupLoginStage = "adiga-check"' in main
assert 'beginStartupLoginProvider(ProviderId.JINHAK)' in main
assert 'unifiedPhase = "adiga"' in main and 'unifiedPhase = "jinhak"' in main
assert 'AndroidKeyStore' in cred and 'AES/GCM/NoPadding' in cred
assert 'AUTO_RECOGNIZED_DRAFT' in excel
assert 'FlexibleTranscriptExtractor.extract' in excel
assert 'flexibleSectionContextRecognition' in flex
assert 'OfficialEvidenceAutoLinker.relinkSelected' in material
assert 'autoRelinkedFromFullLocalAdiga' in auto
assert 'requiresSameRowOrExplicitTableScope' in (root/'app/src/main/java/com/admissionhub/collector/canonical/AdigaApplicationEvidenceAnalyzer.kt').read_text()
assert 'probabilityInferred' in auto and '.put("probabilityInferred", false)' in auto
assert 'officialVerified' in hub and 'directOfficialBound' in hub
assert 'AdigaAutoScoreMaterializer.materializeSelected(localStore, sessionId)' in main
# no credential/session secret offload from the new code
for text in (auto, flex, excel):
    lowered = text.lower()
    assert 'password' not in lowered
    assert 'credentialvault' not in lowered
print('v0.15.0 source contracts verified')
