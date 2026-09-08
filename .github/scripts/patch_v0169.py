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

for path, pairs in replacements.items():
    text = path.read_text()
    for old, new in pairs:
        if text.count(old) != 1:
            raise SystemExit(f"expected exactly one occurrence in {path}: {old}")
        text = text.replace(old, new)
    path.write_text(text)

print("v0.16.9 version patch applied; product logic unchanged")
