from pathlib import Path

p = Path('app/src/test/java/com/admissionhub/collector/jinhak/JinhakMissionCellSupervisorLeaseTest.kt')
if not p.exists():
    raise SystemExit('lease test file not generated')
s = p.read_text()
repls = {
    'JinhakMissionCellSupervisor(staleOwnershipMs = 100L)': 'JinhakMissionCellSupervisor(staleOwnershipMs = 1_000L)',
    'nowMs = 1_099L': 'nowMs = 1_999L',
    'nowMs = 1_100L': 'nowMs = 2_000L',
    'nowMs = 2_100L': 'nowMs = 3_000L',
    'nowMs = 2_101L': 'nowMs = 3_001L',
}
for old, new in repls.items():
    if old not in s:
        raise SystemExit('expected lease test token missing: ' + old)
    s = s.replace(old, new)
p.write_text(s)

g = Path('app/build.gradle.kts')
gs = g.read_text()
anchor = '    testImplementation("junit:junit:4.13.2")\n'
json_dep = '    testImplementation("org.json:json:20240303")\n'
if anchor not in gs:
    raise SystemExit('JUnit dependency anchor missing')
if json_dep not in gs:
    gs = gs.replace(anchor, anchor + json_dep, 1)
g.write_text(gs)
print('v0.10.4 lease test threshold + JVM org.json hotfix applied')
