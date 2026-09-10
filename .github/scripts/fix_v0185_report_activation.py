from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = MAIN.read_text()

replacements = [
    (
        "val rawMissionCandidates = if (JinhakStorageCompetitionPolicy.ENABLED) emptyList() else JinhakAgentNavigator.candidates(snapshot)",
        "val rawMissionCandidates = JinhakAgentNavigator.candidates(snapshot)",
        "enable-report-candidates",
    ),
    (
        '''            val jinhakStorageOnlySnapshot = provider == ProviderId.JINHAK && JinhakStorageCompetitionPolicy.ENABLED &&\n                snapshot.optString("providerPageType") == "jinhak-early-storage"\n            var jinhakExpandOutgoingLinks = !jinhakStorageOnlySnapshot\n            var jinhakAllowAgentAction = !jinhakStorageOnlySnapshot''',
        '''            val jinhakManualReportScope = provider == ProviderId.JINHAK && JinhakManualStorageReportPolicy.ENABLED\n            // v0.18.5 never expands the site's generic link graph. All autonomous movement is\n            // through JinhakAgentNavigator's same-card report actions / report-lane controls.\n            var jinhakExpandOutgoingLinks = !jinhakManualReportScope\n            var jinhakAllowAgentAction = true''',
        "disable-generic-link-expansion",
    ),
    (
        "jinhakExpandOutgoingLinks = jinhakExpandedNavigationStates.add(expansionIdentity.observationId)",
        "jinhakExpandOutgoingLinks = if (JinhakManualStorageReportPolicy.ENABLED) false else jinhakExpandedNavigationStates.add(expansionIdentity.observationId)",
        "keep-generic-expansion-disabled",
    ),
]

for old, new, label in replacements:
    count = text.count(old)
    if count == 0 and new in text:
        continue
    if count != 1:
        raise SystemExit(f"{label}: expected one old anchor, found {count}")
    text = text.replace(old, new, 1)

# The old 15-minute storage-only watcher must never seize control of v0.18.5 report traversal.
old = '''        if (provider == ProviderId.JINHAK && JinhakStorageCompetitionPolicy.ENABLED &&\n            jinhakV0182ProtectedSessionVerified && batchSnapshots.length() > 0) {\n            scheduleV0183StorageCompetitionRefresh()\n            return\n        }'''
new = '''        if (provider == ProviderId.JINHAK && JinhakManualStorageReportPolicy.ENABLED) {\n            // Manual-storage report mode is mission-driven. Do not enter the legacy storage-only\n            // periodic watcher while per-application report targets remain to be processed.\n        } else if (provider == ProviderId.JINHAK && JinhakStorageCompetitionPolicy.ENABLED &&\n            jinhakV0182ProtectedSessionVerified && batchSnapshots.length() > 0) {\n            scheduleV0183StorageCompetitionRefresh()\n            return\n        }'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("disable-storage-only-watcher: anchor missing")

MAIN.write_text(text)
