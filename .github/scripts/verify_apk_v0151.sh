#!/usr/bin/env bash
set -euo pipefail
APK="app/build/outputs/apk/debug/app-debug.apk"
EXPECTED_SIGNER="db6cd5efceda108657662d06f857e5f0277301cb6ab97a75c8a01994c96e4995"

command -v aapt >/dev/null
command -v apksigner >/dev/null
test -f "$APK"

BADGING="$(aapt dump badging "$APK")"
grep -F "package: name='com.admissionhub.collector' versionCode='115100' versionName='0.15.1'" <<<"$BADGING"
grep -F "application-label:'Admission Hub v0.15.1 Wide XLS + High3 Fence'" <<<"$BADGING"

ACTUAL_SIGNER="$(apksigner verify --print-certs "$APK" | sed -n 's/^Signer #1 certificate SHA-256 digest: //p' | head -n1 | tr '[:upper:]' '[:lower:]')"
test "$ACTUAL_SIGNER" = "$EXPECTED_SIGNER"
echo "v0.15.1 APK identity and stable signer verified"
