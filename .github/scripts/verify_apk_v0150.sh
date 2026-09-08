#!/usr/bin/env bash
set -euo pipefail
APK="app/build/outputs/apk/debug/app-debug.apk"
test -f "$APK"
AAPT="${ANDROID_HOME:-$ANDROID_SDK_ROOT}/build-tools/35.0.0/aapt"
APKSIGNER="${ANDROID_HOME:-$ANDROID_SDK_ROOT}/build-tools/35.0.0/apksigner"
BADGING="$($AAPT dump badging "$APK")"
grep -q "package: name='com.admissionhub.collector' versionCode='115000' versionName='0.15.0'" <<<"$BADGING"
grep -q "application-label:'Admission Hub v0.15.0 Full Auto Evidence'" <<<"$BADGING"
SIGNERS="$($APKSIGNER verify --print-certs "$APK")"
grep -qi 'db6cd5efceda108657662d06f857e5f0277301cb6ab97a75c8a01994c96e4995' <<<"${SIGNERS//:/}"
echo "v0.15.0 APK identity and stable signer verified"
