#!/usr/bin/env bash
set -euo pipefail

APK="app/build/outputs/apk/debug/app-debug.apk"
EXPECTED_SIGNER="db6cd5efceda108657662d06f857e5f0277301cb6ab97a75c8a01994c96e4995"

test -f "$APK"

DUMP="$(aapt dump badging "$APK")"
echo "$DUMP" | grep -F "versionCode='116700'" >/dev/null
echo "$DUMP" | grep -F "versionName='0.16.7'" >/dev/null
echo "$DUMP" | grep -F "application-label:'Admission Hub v0.16.7 Direct High3 Auth'" >/dev/null

SIGNER="$(apksigner verify --print-certs "$APK" | awk -F': ' '/Signer #1 certificate SHA-256 digest:/ {gsub(":", "", $2); print tolower($2); exit}')"
test "$SIGNER" = "$EXPECTED_SIGNER"

echo "v0.16.7 APK verified: version, label, stable signer"
