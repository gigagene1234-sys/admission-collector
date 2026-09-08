#!/usr/bin/env bash
set -euo pipefail
APK="app/build/outputs/apk/debug/app-debug.apk"
EXPECTED_SIGNER="db6cd5efceda108657662d06f857e5f0277301cb6ab97a75c8a01994c96e4995"

SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
if [[ -z "$SDK_ROOT" ]]; then
  echo "Android SDK root is unavailable" >&2
  exit 1
fi
AAPT="${SDK_ROOT}/build-tools/35.0.0/aapt"
APKSIGNER="${SDK_ROOT}/build-tools/35.0.0/apksigner"
test -x "$AAPT"
test -x "$APKSIGNER"
test -f "$APK"

BADGING="$($AAPT dump badging "$APK")"
echo "$BADGING" | head -n 6
grep -F "package: name='com.admissionhub.collector' versionCode='115100' versionName='0.15.1'" <<<"$BADGING"
grep -F "application-label:'Admission Hub v0.15.1 Wide XLS + High3 Fence'" <<<"$BADGING"

ACTUAL_SIGNER="$($APKSIGNER verify --print-certs "$APK" | sed -n 's/^Signer #1 certificate SHA-256 digest: //p' | head -n1 | tr '[:upper:]' '[:lower:]')"
test "$ACTUAL_SIGNER" = "$EXPECTED_SIGNER"
echo "v0.15.1 APK identity and stable signer verified"
