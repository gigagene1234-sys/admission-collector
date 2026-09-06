from pathlib import Path

path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
text = path.read_text()
old = '            .setTitle("$slot번 지원안 선택")'
new = '            .setTitle("${slot}번 지원안 선택")'
count = text.count(old)
if count != 1:
    raise SystemExit(f'expected one slot-title interpolation bug, found {count}')
path.write_text(text.replace(old, new, 1))
print('v0.10.0 compile hotfix applied')
