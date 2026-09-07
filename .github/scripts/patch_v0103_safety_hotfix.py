from pathlib import Path

path = Path('app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt')
text = path.read_text()

replacements = [
    (
        '        val departmentSupportFingerprints = linkedMapOf<String, MutableSet<String>>()\n',
        '',
        'department support map'
    ),
    (
        '                        departmentSupportFingerprints.getOrPut(app.identityKey) { linkedSetOf() }.add(c.getString(0))\n',
        '',
        'department support capture'
    ),
    (
        '                        addAll(departmentSupportFingerprints[app.identityKey].orEmpty())\n',
        '',
        'department support accepted mutation'
    ),
]
for old, new, label in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, found {count}')
    text = text.replace(old, new, 1)

# Department-summary is shared department evidence and must not be assigned to one
# application identity solely because a separate official table proved the track.
if 'departmentSupportFingerprints' in text:
    raise SystemExit('shared department support mutation remains')
path.write_text(text)
print('v0.10.3 shared-department acceptance safety hotfix applied')
