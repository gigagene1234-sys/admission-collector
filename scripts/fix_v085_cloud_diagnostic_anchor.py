from pathlib import Path
import re

p = Path('scripts/apply_v085_mission_lane_sequencer.py')
t = p.read_text()
pattern = re.compile(r"old_cloud_diag = '''.*?m = at_least_once\(m, old_cloud_diag, new_cloud_diag, 'cloud outstanding diagnostics'\)\n", re.S)
replacement = '''cloud_failed_anchor = '.put("cloudFrontierCompletionFailed", cloudFrontierCompletionFailed)'
if cloud_failed_anchor not in m:
    raise SystemExit('cloud completion diagnostic anchor missing')
m = m.replace(
    cloud_failed_anchor,
    cloud_failed_anchor + '\\n                        .put("cloudFrontierOutstanding", (cloudFrontierClaimed - cloudFrontierCompleted).coerceAtLeast(0))'
)
'''
new, count = pattern.subn(replacement, t, count=1)
if count != 1:
    raise SystemExit(f'expected one cloud diagnostic patch stanza, found {count}')
p.write_text(new)
print('Adjusted v0.8.5 Cloud diagnostic patch to tolerate output-chain formatting')
