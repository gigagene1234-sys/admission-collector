from pathlib import Path

manifest = Path("app/src/main/AndroidManifest.xml")
text = manifest.read_text()
old = '''        <service
            android:name=".jinhak.JinhakNativeBridgeAccessibilityService"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
            android:exported="false">'''
new = '''        <service
            android:name=".jinhak.JinhakNativeBridgeAccessibilityService"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
            android:exported="true">'''
if old in text:
    manifest.write_text(text.replace(old, new, 1))
elif new not in text:
    raise SystemExit("v0.18.4 accessibility service declaration not found")

main = Path("app/src/main/java/com/admissionhub/collector/MainActivity.kt")
main_text = main.read_text()
# Kotlin interprets `$batchPageCount회` as one identifier. Keep the Korean unit outside the interpolation.
bad = '$batchPageCount회'
good = '${batchPageCount}회'
if bad in main_text:
    main.write_text(main_text.replace(bad, good))
elif good not in main_text:
    raise SystemExit("v0.18.4 Adiga snapshot count interpolation not found")

print("v0.18.4 accessibility export and Kotlin interpolation contracts ready")
