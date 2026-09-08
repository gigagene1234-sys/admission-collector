#!/usr/bin/env bash
set -euo pipefail
APK="app/build/outputs/apk/debug/app-debug.apk"
test -f "$APK"
DUMP="$(aapt dump badging "$APK")"
echo "$DUMP" | grep -F "versionCode='116800'" >/dev/null
echo "$DUMP" | grep -F "versionName='0.16.8'" >/dev/null
echo "$DUMP" | grep -F "application-label:'Admission Hub v0.16.8 Event-Driven High3 Auth'" >/dev/null
apksigner verify --print-certs "$APK" >/tmp/apksigner-v0168.txt
grep -F "Signer #1 certificate SHA-256 digest:" /tmp/apksigner-v0168.txt >/dev/null
echo "v0.16.8 APK verified: version, label, signed package"
