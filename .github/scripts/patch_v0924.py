from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
SNAPSHOT = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
NAVIGATOR = ROOT / 'app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


main = MAIN.read_text()
snapshot = SNAPSHOT.read_text()
navigator = NAVIGATOR.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

required = [
    'private const val VERSION = "0.9.23"',
    'private const val BUILD_CODE = 109230',
    'JINHAK_SINGLE_WEBVIEW_STABILITY_MODE = true',
    'finishJinhakPostMissionLoginIfReady',
    'jinhak-post-mission-login-closure',
    'MAX_JINHAK_GENERIC_ACTIONS = 180',
    'JinhakMissionLaneSequencer.choose',
    'JinhakReportContextBridge.isReportAction',
]
missing = [x for x in required if x not in main]
if missing:
    raise SystemExit('v0.9.23 MainActivity precondition failed: ' + ', '.join(missing))

for token in [
    "var dynamicControl=!route || role==='tab' || a.tagName==='BUTTON' || missionLink;",
    "kind:missionLink?'mission-link-navigation':(missionBoundControl?'mission-bound-control':(role==='tab'?'tab-navigation':'read-navigation'))",
]:
    if token not in snapshot:
        raise SystemExit('v0.9.23 SnapshotScript precondition failed: ' + token)

if 'val requiresSameCard = candidate.applicationContext?.identityKey != null' not in navigator:
    raise SystemExit('v0.9.23 JinhakAgentNavigator precondition failed')

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.9.23"', 'private const val VERSION = "0.9.24"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 109230', 'private const val BUILD_CODE = 109240', 'main build code')
gradle = replace_once(gradle, 'versionCode = 109230', 'versionCode = 109240', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.9.23"', 'versionName = "0.9.24"', 'gradle version name')
manifest = replace_once(
    manifest,
    'Admission Collector v0.9.23 Mission Closure Auth Fence',
    'Admission Collector v0.9.24 Report Lane Mission Bridge',
    'manifest label'
)

# The v0.9.23 real-device export proved that report pages such as actual-admission and
# grade-calculation are visible, but they were reached only by the generic URL frontier.
# Static <a href> report tabs were therefore not candidates while a same-application mission
# was active. Promote only read-only report-family lane controls; do not broaden general links.
snapshot = replace_once(
    snapshot,
    "      var dynamicControl=!route || role==='tab' || a.tagName==='BUTTON' || missionLink;\n",
    """      var reportFamilyPage=isJinhakHost && /\\/jh\\/high3\\/early\\/four-year-university\\/report\\//i.test(location.pathname);\n      var reportLaneControl=reportFamilyPage && /(실제\\s*합격자|과거\\s*입시결과|모의\\s*지원|지원자\\s*분포|성적\\s*분석|성적\\s*산출|환산\\s*점수|합격\\s*예측|합격\\s*안정성)/i.test(label);\n      var dynamicControl=!route || role==='tab' || a.tagName==='BUTTON' || missionLink || reportLaneControl;\n""",
    'promote static report lane controls'
)
snapshot = replace_once(
    snapshot,
    "kind:missionLink?'mission-link-navigation':(missionBoundControl?'mission-bound-control':(role==='tab'?'tab-navigation':'read-navigation'))",
    "kind:missionLink?'mission-link-navigation':(missionBoundControl?'mission-bound-control':(reportLaneControl?'report-lane-navigation':(role==='tab'?'tab-navigation':'read-navigation')))",
    'tag report lane navigation kind'
)

# Give the executor an independent route fence. A stale report-lane candidate must never be
# replayed after leaving the report family, even though it intentionally has no card-local context.
navigator = replace_once(
    navigator,
    '        val requiresSameCard = candidate.applicationContext?.identityKey != null\n',
    '        val requiresSameCard = candidate.applicationContext?.identityKey != null\n        val requiresReportFamily = candidate.kind == "report-lane-navigation"\n',
    'report lane executor flag'
)
navigator = replace_once(
    navigator,
    '              var requireSameCard=${if (requiresSameCard) "true" else "false"};\n              var blocked=',
    '              var requireSameCard=${if (requiresSameCard) "true" else "false"};\n              var requireReportFamily=${if (requiresReportFamily) "true" else "false"};\n              if(requireReportFamily && !/\\/jh\\/high3\\/early\\/four-year-university\\/report\\//i.test(location.pathname)) return JSON.stringify({ok:false,reason:\'report-family-context-mismatch\'});\n              var blocked=',
    'report family execution fence'
)

# While an already Gate-A-bound application mission is active, a promoted report-family lane
# control belongs to the mission budget rather than the generic crawl budget. Identity still comes
# only from the existing mission/report bridge; the static control itself never invents identity.
main = replace_once(
    main,
    '        val missionBudgetedAction = ledgerTargetIdForAction != null || candidate.applicationContext?.identityKey != null\n',
    '''        val inheritedReportLaneAction = jinhakMissionContext?.identityKey != null &&
            candidate.kind == "report-lane-navigation" &&
            selection.requestedLane != "reference" &&
            JinhakReportContextBridge.isReportAction(candidate.label, candidate.kind)
        val missionBudgetedAction = ledgerTargetIdForAction != null || candidate.applicationContext?.identityKey != null || inheritedReportLaneAction
''',
    'mission budget for inherited report lane'
)

# Add one explicit diagnostic counter so the next real-device export can prove that the new path
# was actually exercised rather than merely succeeding through the generic frontier.
main = replace_once(
    main,
    '    private var jinhakReportBridgeConfirmed = 0\n    private var jinhakMissionAnchorActionsAttempted = 0\n',
    '    private var jinhakReportBridgeConfirmed = 0\n    private var jinhakInheritedReportLaneActions = 0\n    private var jinhakMissionAnchorActionsAttempted = 0\n',
    'report lane counter field'
)
main = replace_once(
    main,
    '        jinhakReportBridgeConfirmed = 0\n        jinhakMissionAnchorActionsAttempted = 0\n',
    '        jinhakReportBridgeConfirmed = 0\n        jinhakInheritedReportLaneActions = 0\n        jinhakMissionAnchorActionsAttempted = 0\n',
    'report lane counter reset'
)
main = replace_once(
    main,
    '        jinhakActiveMissionTargetId = ledgerTargetIdForAction\n',
    '''        if (inheritedReportLaneAction) {
            jinhakInheritedReportLaneActions += 1
            recordRuntimeEvent("jinhak-inherited-report-lane-action", JSONObject()
                .put("applicationIdentityHash", jinhakMissionContext?.identityKey?.take(24) ?: "")
                .put("requestedLane", selection.requestedLane)
                .put("label", candidate.label.take(80))
                .put("safePath", runtimeSafePath(route)))
        }
        jinhakActiveMissionTargetId = ledgerTargetIdForAction
''',
    'report lane counter increment'
)
main = replace_once(
    main,
    '                        .put("reportBridgeConfirmed", jinhakReportBridgeConfirmed)\n                        .put("consentGatesEncountered", jinhakConsentGatesEncountered)\n',
    '                        .put("reportBridgeConfirmed", jinhakReportBridgeConfirmed)\n                        .put("inheritedReportLaneActions", jinhakInheritedReportLaneActions)\n                        .put("consentGatesEncountered", jinhakConsentGatesEncountered)\n',
    'report lane diagnostics'
)

# Safety checks: no change to credential/session export policy and no Jinhak batch-crawl mode.
for forbidden in [
    '.put("password", credentials.password)',
    '.putString("processCookie"',
    '.putString("processToken"',
    'supportsBatchCrawl = true',
]:
    if forbidden in main:
        raise SystemExit('privacy/architecture invariant failed: ' + forbidden)

MAIN.write_text(main)
SNAPSHOT.write_text(snapshot)
NAVIGATOR.write_text(navigator)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('Applied v0.9.24 Report Lane Mission Bridge patch')
