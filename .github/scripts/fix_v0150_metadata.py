from pathlib import Path

p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s = p.read_text()
old = '.put("bothProviderLeasesRestoredAtBootstrap", true)'
new = '''.put("bothProviderLeasesRestoreAttemptedAtBootstrap", true)
                .put("adigaLeaseRestoredAtBootstrap", startupLoginAdigaRestoredLease)
                .put("jinhakLeaseRestoredAtBootstrap", startupLoginJinhakRestoredLease)'''
if s.count(old) != 1:
    raise SystemExit(f'expected one metadata field, found {s.count(old)}')
s = s.replace(old, new, 1)
p.write_text(s)
print('v0.15 lease metadata corrected')
