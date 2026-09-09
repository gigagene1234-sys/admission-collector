from pathlib import Path

checks = {
    "app/build.gradle.kts": [
        'versionCode = 118300',
        'versionName = "0.18.3"',
    ],
    "app/src/main/AndroidManifest.xml": [
        'Admission Hub v0.18.3 Storage Competition Watch',
    ],
    "app/src/main/java/com/admissionhub/collector/jinhak/JinhakStorageCompetitionPolicy.kt": [
        'REFRESH_INTERVAL_MS = 15L * 60L * 1000L',
        '/jh/high3/early/four-year-university/library',
        'currentApplicationCompetition',
        'currentSemanticsVerified',
        '모의',
        '전년도',
    ],
    "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt": [
        'listOf(JinhakSiteTopology.protectedCoreProbeUrl())',
        'JinhakStorageCompetitionPolicy.ENABLED && !JinhakStorageCompetitionPolicy.isStorageUrl(url)',
        'jinhak-saved-application-competition-watch',
        'currentCompetitionSemanticsVerified',
        'sourceClass", "jinhak-user-viewed-derived',
    ],
    "app/src/main/java/com/admissionhub/collector/MainActivity.kt": [
        'private const val VERSION = "0.18.3"',
        'scheduleV0183StorageCompetitionRefresh',
        'v0183-periodic-storage-refresh',
        'val rawMissionCandidates = if (JinhakStorageCompetitionPolicy.ENABLED) emptyList()',
        'var jinhakExpandOutgoingLinks = !jinhakStorageOnlySnapshot',
        'var jinhakAllowAgentAction = !jinhakStorageOnlySnapshot',
        'v0183StorageOnlyMode',
    ],
}

for path, needles in checks.items():
    text = Path(path).read_text()
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"missing contract in {path}: {needle}")

adapter = Path("app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt").read_text()
if 'override fun seedUrls(): List<String> = JinhakSiteTopology.missionSeeds()' in adapter:
    raise SystemExit("legacy multi-route Jinhak mission seeds still active")

main = Path("app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
if 'currentApplicationCompetition", it)' not in adapter:
    raise SystemExit("current competition is not explicitly represented")
if '15분 후' not in main:
    raise SystemExit("watch cadence is not visible to the user")

print("v0.18.3 source contracts verified")
