from pathlib import Path

p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
text = p.read_text()
old = 'jinhakMissionCells.summary().optString("supervisorState") == "RECOVERING"'
new = 'jinhakMissionCells.diagnostics().optString("supervisorState") == "RECOVERING"'
count = text.count(old)
if count != 1:
    raise SystemExit(f'compile hotfix expected one match, found {count}')
p.write_text(text.replace(old, new, 1))
print('v0.11 compile hotfix applied')
