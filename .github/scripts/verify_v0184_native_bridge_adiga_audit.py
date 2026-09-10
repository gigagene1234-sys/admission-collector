from pathlib import Path


def require(path: str, token: str) -> None:
    text = Path(path).read_text()
    if token not in text:
        raise SystemExit(f"missing {token!r} in {path}")


def forbid(path: str, token: str) -> None:
    text = Path(path).read_text()
    if token in text:
        raise SystemExit(f"forbidden {token!r} in {path}")


require("app/build.gradle.kts", 'versionCode = 118400')
require("app/build.gradle.kts", 'versionName = "0.18.4"')
require("app/src/main/AndroidManifest.xml", 'Admission Hub v0.18.4 Native Jinhak Bridge + Adiga Audit')
require("app/src/main/AndroidManifest.xml", 'com.jinhak.jinhakmobile.android')
require("app/src/main/AndroidManifest.xml", 'JinhakNativeBridgeAccessibilityService')
require("app/src/main/AndroidManifest.xml", 'android.permission.BIND_ACCESSIBILITY_SERVICE')
require("app/src/main/AndroidManifest.xml", '@xml/jinhak_native_bridge_accessibility')

bridge = "app/src/main/java/com/admissionhub/collector/jinhak/JinhakNativeAppBridge.kt"
service = "app/src/main/java/com/admissionhub/collector/jinhak/JinhakNativeBridgeAccessibilityService.kt"
require(bridge, 'OFFICIAL_APP_PACKAGE = "com.jinhak.jinhakmobile.android"')
require(bridge, 'sourceClass", "jinhak-user-viewed-native-app"')
require(bridge, 'credentialFieldsCaptured", false')
require(bridge, 'editableFieldsCaptured", false')
require(bridge, 'cookiesCaptured", false')
require(bridge, 'sessionSecretsCaptured", false')
require(bridge, 'probabilityInferred", false')
require(service, 'packageName != JinhakNativeAppBridge.OFFICIAL_APP_PACKAGE')
require(service, 'node.isPassword || node.isEditable')
forbid(service, 'performAction(')
forbid(service, 'ACTION_SET_TEXT')
forbid(service, 'ACTION_CLICK')

xml = "app/src/main/res/xml/jinhak_native_bridge_accessibility.xml"
require(xml, 'android:packageNames="com.jinhak.jinhakmobile.android"')
require(xml, 'android:canRetrieveWindowContent="true"')

main = "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
require(main, 'private const val VERSION = "0.18.4"')
require(main, 'private const val BUILD_CODE = 118400')
require(main, '진학사 앱 열기 (로그인 우회)')
require(main, '진학사 앱 저장소 관측 가져오기')
require(main, 'native-app://jinhak/susi-storage')
require(main, 'sameCardIdentityVerified", false')
require(main, 'adigaAttemptModel')
require(main, 'session-snapshot-attempts-vs-persisted-local-resume-v0184')
require(main, 'attemptedPagesMeaning')
require(main, 'adigaPagesCompletedAtStart')
require(main, 'adigaNewCompletedPagesThisRun')

adapter = "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt"
require(adapter, 'override fun seedUrls(): List<String> = listOf(JinhakSiteTopology.protectedCoreProbeUrl())')
require(adapter, 'JinhakStorageCompetitionPolicy.ENABLED && !JinhakStorageCompetitionPolicy.isStorageUrl(url)')

print("v0.18.4 source contracts verified")
