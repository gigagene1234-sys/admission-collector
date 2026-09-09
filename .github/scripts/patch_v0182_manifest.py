from pathlib import Path
p=Path('app/src/main/AndroidManifest.xml')
s=p.read_text()
old='android:label="Admission Hub v0.18.1 Focused Six Missions"'
new='android:label="Admission Hub v0.18.2 Protected Session Bootstrap"'
if s.count(old)!=1:
    raise SystemExit(f'expected one manifest label, got {s.count(old)}')
p.write_text(s.replace(old,new,1))
print('v0.18.2 manifest patched')
