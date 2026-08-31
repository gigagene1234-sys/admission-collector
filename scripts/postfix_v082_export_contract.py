from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
text = p.read_text()

replacements = [
    ('contractVersion\\\":2', 'contractVersion\\\":3', 'contract version'),
    ('recommendedWorkbookSheets\\\":[\\\"Dashboard\\\",\\\"UnifiedRecords\\\"',
     'recommendedWorkbookSheets\\\":[\\\"Dashboard\\\",\\\"ApplicationMissions\\\",\\\"UnifiedRecords\\\"', 'mission sheet'),
    ('\\\"admission\\\",\\\"recordType\\\",\\\"observedAt\\\"',
     '\\\"admission\\\",\\\"applicationIdentityKey\\\",\\\"recordType\\\",\\\"observedAt\\\"', 'application row key'),
]
for old, new, label in replacements:
    if old not in text:
        raise SystemExit(f'export contract {label} anchor not found')
    text = text.replace(old, new, 1)

for required in ['contractVersion\\\":3', 'ApplicationMissions', 'applicationIdentityKey']:
    if required not in text:
        raise SystemExit('export contract post-fix missing '+required)
p.write_text(text)
print('Upgraded analysis-ready export contract to v3 with ApplicationMissions')
