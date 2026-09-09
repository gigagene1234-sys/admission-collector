from pathlib import Path

main = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt').read_text()
topology = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt').read_text()
policy = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakFocusedSixPolicy.kt').read_text()
store = Path('app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt').read_text()
dashboard = Path('app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt').read_text()
gradle = Path('app/build.gradle.kts').read_text()

checks = {
    'versionName_0181': 'versionName = "0.18.1"' in gradle,
    'versionCode_118100': 'versionCode = 118100' in gradle,
    'collectorVersion_0181': 'private const val VERSION = "0.18.1"' in main,
    'focusedPolicyImported': 'import com.admissionhub.collector.jinhak.JinhakFocusedSixPolicy' in main,
    'pinnedSixActivatedBeforeBatch': 'activateV0181PinnedSixFocus("start-batch")' in main,
    'pinnedSixExpectedIdentities': 'jinhakV0181PinnedIdentityKeys.toSet()' in main,
    'genericRoutesSuppressed': 'jinhakV0181GenericRoutesSuppressed' in main,
    'genericActionsSuppressed': 'jinhakV0181GenericActionsSuppressed' in main,
    'protectedCoreAfterAuth': 'v0181-auth-success-protected-core' in main and 'JinhakSiteTopology.protectedCoreProbeUrl()' in main,
    'boundedAuthAttempts12': 'V0180_AUTH_MAX_FILL_ATTEMPTS = 12' in main,
    'noRecursiveAuthPolling': '.put("v0180RecursiveAuthPolling", false)' in main,
    'missionSeedsNoStrategy': '"$ROOT/jh/high3/ipsi-analysis/ipsi-strategy"' not in topology,
    'missionSeedsNoGenericUnivSearch': '"$ROOT/jh/high3/univ-major/univ-info/univ-search"' not in topology,
    'strategyNotDefaultTraversal': 'JinhakMissionLane.STRATEGY,\n        JinhakMissionLane.ADMISSION_KNOWLEDGE,\n        JinhakMissionLane.REFERENCE' in topology,
    'focusedPolicySixLanes': all(x in policy for x in [
        'SAVED_APPLICATIONS', 'CURRENT_PREDICTION', 'MOCK_SUPPORT',
        'ACTUAL_ADMIT', 'SCORE_ANALYSIS', 'UNIVERSITY_RESULT'
    ]),
    'editorialSuppressed': all(x in policy for x in ['/ipsi-knowledge', '/ipsi-analysis/ipsi-strategy', '/jinhak-tv']),
    'crossSessionScoreFallback': 'processedScoreIdentities' in store and 'CASE WHEN session_id=? THEN 0 ELSE 1 END' in store,
    'staleCardKeepsScoreEvidence': 'enrichScoreForDisplay(score).put("decisionLabel", "종합: 판정 보류 · canonical 연결 복구 필요")' in dashboard,
    'probabilityNotInferred': 'probabilityInferred' in store,
}

failed = [name for name, ok in checks.items() if not ok]
print(checks)
if failed:
    raise SystemExit('v0.18.1 contract failure: ' + ', '.join(failed))

seed_start = topology.index('fun missionSeeds()')
seed_end = topology.index('fun lane(', seed_start)
seed_block = topology[seed_start:seed_end]
if 'ipsi-strategy' in seed_block or 'ipsi-knowledge' in seed_block or 'univ-info/univ-search' in seed_block:
    raise SystemExit('open-world seed regressed into v0.18.1 missionSeeds')

# Product sources must continue to use the on-device vault and keep credential/session values out of exports.
if 'credentialVault.load(ProviderId.JINHAK.wireName)' not in main:
    raise SystemExit('Jinhak device-vault credential path missing')
if 'credentialExported' not in main or 'sessionSecretExported' not in main:
    raise SystemExit('credential/session export diagnostics missing')

print('v0.18.1 source contracts verified')
