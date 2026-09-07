#!/usr/bin/env bash
set -euo pipefail
APK=app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/build-tools/35.0.0/aapt" dump badging "$APK" > "$RUNNER_TEMP/admission-v0130-metadata.txt"
"$ANDROID_HOME/build-tools/35.0.0/apksigner" verify --verbose --print-certs "$APK" > "$RUNNER_TEMP/admission-v0130-signer.txt"
grep -q "package: name='com.admissionhub.collector' versionCode='113000' versionName='0.13.0'" "$RUNNER_TEMP/admission-v0130-metadata.txt"
grep -q "application-label:'Admission Hub v0.13.0 Application Review'" "$RUNNER_TEMP/admission-v0130-metadata.txt"
grep -qi 'db6cd5efceda108657662d06f857e5f0277301cb6ab97a75c8a01994c96e4995' "$RUNNER_TEMP/admission-v0130-signer.txt"
echo 'APK package, version, label and stable signer verified'
