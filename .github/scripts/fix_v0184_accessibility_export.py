from pathlib import Path

p = Path("app/src/main/AndroidManifest.xml")
text = p.read_text()
old = '''        <service
            android:name=".jinhak.JinhakNativeBridgeAccessibilityService"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
            android:exported="false">'''
new = '''        <service
            android:name=".jinhak.JinhakNativeBridgeAccessibilityService"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
            android:exported="true">'''
if old in text:
    p.write_text(text.replace(old, new, 1))
elif new not in text:
    raise SystemExit("v0.18.4 accessibility service declaration not found")
print("v0.18.4 accessibility service export contract ready")
