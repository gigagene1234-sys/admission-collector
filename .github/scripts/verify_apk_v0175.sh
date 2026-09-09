#!/usr/bin/env bash
set -euo pipefail
APK="app/build/outputs/apk/debug/app-debug.apk"
AAPT="${ANDROID_HOME:-$ANDROID_SDK_ROOT}/build-tools/35.0.0/aapt"
APKSIGNER="${ANDROID_HOME:-$ANDROID_SDK_ROOT}/build-tools/35.0.0/apksigner"
test -f "$APK"
test -x "$AAPT"
test -x "$APKSIGNER"
BADGING="$($AAPT dump badging "$APK")"
echo "$BADGING" | grep -F "package: name='com.admissionhub.collector' versionCode='117500' versionName='0.17.5'" >/dev/null
echo "$BADGING" | grep -F "application-label:'Admission Hub v0.17.5 Runtime-Stable High3 Sandbox'" >/dev/null
SIGNER="$($APKSIGNER verify --print-certs "$APK" | sed -n 's/^Signer #1 certificate SHA-256 digest: //p' | head -n1 | tr 'A-F' 'a-f')"
test "$SIGNER" = "db6cd5efceda108657662d06f857e5f0277301cb6ab97a75c8a01994c96e4995"
echo "v0.17.5 APK verified: metadata + stable signer $SIGNER"
