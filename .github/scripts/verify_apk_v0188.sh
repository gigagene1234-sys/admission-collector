#!/usr/bin/env bash
set -euo pipefail
APK="app/build/outputs/apk/debug/app-debug.apk"
test -f "$APK"
apkanalyzer manifest version-code "$APK" | grep -qx '118800'
apkanalyzer manifest version-name "$APK" | grep -qx '0.18.8'
SIGNER="$(apksigner verify --print-certs "$APK" | awk -F': ' '/Signer #1 certificate SHA-256 digest:/ {print tolower($2); exit}')"
EXPECTED='db6cd5efceda108657662d06f857e5f0277301cb6ab97a75c8a01994c96e4995'
test "$SIGNER" = "$EXPECTED"
echo "v0.18.8 APK verified signer=$SIGNER"
