#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def need(text: str, needle: str, name: str):
    if needle not in text:
        raise SystemExit(f"missing contract: {name}: {needle}")

def forbid(text: str, needle: str, name: str):
    if needle in text:
        raise SystemExit(f"forbidden contract: {name}: {needle}")

build = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
topology = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt").read_text()
focused = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakFocusedSixPolicy.kt").read_text()
mission = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakApplicationMission.kt").read_text()
adapter = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakStorageOnlyPolicy.kt").read_text()
competition = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakStorageCompetitionMonitor.kt").read_text()

need(build, 'versionCode = 119000', 'version code')
need(build, 'versionName = "0.19.0"', 'version name')
need(manifest, 'Admission Hub v0.19 Storage Competition Monitor', 'app label')
need(policy, 'storage-only-competition-monitor-v0190', 'collection mode')
need(policy, '15L * 60L * 1000L', '15 minute foreground interval')
need(policy, '/jh/high3/early/four-year-university/library', 'exact protected library')
need(topology, 'fun missionSeeds(): List<String> = listOf(JinhakStorageOnlyPolicy.LIBRARY_URL)', 'single Jinhak seed')
need(focused, 'setOf(JinhakMissionLane.SAVED_APPLICATIONS)', 'storage-only required lane')
need(competition, 'genericCompetitionUnresolved', 'ambiguous competition preservation')
need(competition, 'derived-explicit-current-applicants-and-capacity', 'same-card count derivation')
need(mission, 'currentApplicationCompetition', 'current competition semantics')
need(adapter, '"currentApplicationCompetition", "genericCompetitionUnresolved"', 'competition-only card preservation')
need(main, 'single-webview-site-owned-storage-only-v0190', 'single WebView auth model')
need(main, 'pauseJinhakStorageForSiteLogin("page-started-login", url)', 'natural login page start')
need(main, 'pauseJinhakStorageForSiteLogin("page-finished-login", url)', 'natural login page finish')
need(main, 'webView.loadUrl(JinhakStorageOnlyPolicy.LIBRARY_URL)', 'direct library navigation')
need(main, 'scheduleJinhakStorageRefresh("snapshot-complete")', 'periodic refresh schedule')
need(main, '"jinhak-competition-snapshot"', 'competition snapshot record')
need(main, '.put("official", false)', 'Jinhak non-official marker')
need(main, '.put("probabilityInferred", false)', 'no new probability inference')
need(main, '.put("collectorOwnedJinhakLogin", false)', 'collector-owned login disabled')
need(main, '.put("dedicatedAuthUsedByV0190", false)', 'dedicated auth disabled for v0190')
forbid(main, 'startV0180DedicatedJinhakAuth("collector-network-login")', 'network login diversion')
forbid(main, 'startV0180DedicatedJinhakAuth("collector-navigation-login")', 'navigation login diversion')
forbid(main, 'startV0180DedicatedJinhakAuth("collector-page-started-login")', 'page-start login diversion')
forbid(main, 'startV0180DedicatedJinhakAuth("collector-page-finished-login")', 'page-finish login diversion')
forbid(main, 'startV0180DedicatedJinhakAuth("saved-credential:', 'Jinhak saved credential submit entry')
forbid(main, 'probabilityInferred", true', 'probability inference')

print('v0.19.0 source contracts verified')
