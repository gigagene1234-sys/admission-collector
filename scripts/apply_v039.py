from pathlib import Path

ROOT = Path('.')
main_paths = [
    ROOT / 'MainActivity.kt',
    ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt',
]

banner_anchor = '''        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(10, 10, 10, 10)
        }
'''
banner_replacement = banner_anchor + '''
        root.addView(TextView(this).apply {
            text = "Admission Collector v$VERSION · build 10039"
            gravity = Gravity.CENTER
            textSize = 13f
            setPadding(8, 6, 8, 6)
        }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ))
'''

for path in main_paths:
    s = path.read_text()
    s = s.replace('private const val VERSION = "0.3.8"', 'private const val VERSION = "0.3.9"')
    if 'Admission Collector v$VERSION · build 10039' not in s:
        if banner_anchor not in s:
            raise SystemExit(f'buildUi root anchor not found: {path}')
        s = s.replace(banner_anchor, banner_replacement, 1)
    path.write_text(s)

build = ROOT / 'app/build.gradle.kts'
s = build.read_text()
s = s.replace('versionCode = 15', 'versionCode = 10039')
s = s.replace('versionName = "0.3.8"', 'versionName = "0.3.9"')
build.write_text(s)

manifest = ROOT / 'app/src/main/AndroidManifest.xml'
s = manifest.read_text()
s = s.replace('android:label="Admission Collector"', 'android:label="Admission Collector v0.3.9"')
manifest.write_text(s)

worker = ROOT / 'cloudflare/src/index.js'
s = worker.read_text()
s = s.replace('version: "0.3.8"', 'version: "0.3.9"')
worker.write_text(s)

# Verify both Kotlin copies remain byte-identical.
if main_paths[0].read_bytes() != main_paths[1].read_bytes():
    raise SystemExit('MainActivity copies diverged')

checks = {
    main_paths[0]: ['private const val VERSION = "0.3.9"', 'Admission Collector v$VERSION · build 10039'],
    build: ['versionCode = 10039', 'versionName = "0.3.9"'],
    manifest: ['android:label="Admission Collector v0.3.9"'],
    worker: ['version: "0.3.9"', 'scopeProviderFingerprint'],
}
for path, needles in checks.items():
    text = path.read_text()
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'missing {needle!r} in {path}')

print('v0.3.9 install-verification patch applied')
