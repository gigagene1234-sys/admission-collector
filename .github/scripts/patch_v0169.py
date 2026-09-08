from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

replacements = {
    ROOT / "app/build.gradle.kts": [
        ('versionCode = 116800', 'versionCode = 116900'),
        ('versionName = "0.16.8"', 'versionName = "0.16.9"'),
    ],
    ROOT / "app/src/main/AndroidManifest.xml": [
        ('android:label="Admission Hub v0.16.8 Event-Driven High3 Auth"', 'android:label="Admission Hub v0.16.9 Event-Driven High3 Auth"'),
    ],
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt": [
        ('private const val VERSION = "0.16.8"', 'private const val VERSION = "0.16.9"'),
        ('private const val BUILD_CODE = 116800', 'private const val BUILD_CODE = 116900'),
    ],
}

changed = False
for path, pairs in replacements.items():
    text = path.read_text()
    for old, new in pairs:
        old_count = text.count(old)
        new_count = text.count(new)
        if old_count == 1 and new_count == 0:
            text = text.replace(old, new)
            changed = True
        elif old_count == 0 and new_count == 1:
            pass
        else:
            raise SystemExit(f"unexpected version token state in {path}: old={old_count}, new={new_count}")
    path.write_text(text)

print("v0.16.9 version patch ready; changed=" + str(changed).lower() + "; product logic unchanged")
