from pathlib import Path

path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
m = path.read_text()

# v0.9.13 wrote same-card replay counters only in the final diagnostics bundle.
# A renderer-interrupted run therefore lost the very counters needed to evaluate
# replay recovery. Add them to the live JINHAK_CRAWL_DIAGNOSTICS checkpoint.
anchor = '''                .put("applicationAnchorReportConfirmed", jinhakReportConfirmedKeys.size)
                .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
'''
replacement = '''                .put("applicationAnchorReportConfirmed", jinhakReportConfirmedKeys.size)
                .put("sameCardReplayRetries", jinhakSameCardReplayRetries)
                .put("sameCardReplayRecovered", jinhakSameCardReplayRecovered)
                .put("sameCardReplayTerminalFailures", jinhakSameCardReplayTerminalFailures)
                .put("sameCardReplayResolutionCounts", JSONObject(jinhakSameCardReplayResolutionCounts as Map<*, *>))
                .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
'''
if anchor not in m:
    raise SystemExit('live Jinhak diagnostics anchor not found')
m = m.replace(anchor, replacement, 1)
path.write_text(m)
print('v0.9.14 live replay diagnostics patch applied')
