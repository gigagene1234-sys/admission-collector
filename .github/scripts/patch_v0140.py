from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    assert count == 1, f"{label}: expected exactly one match, found {count}"
    return text.replace(old, new, 1)

root = Path('app/src/main/java/com/admissionhub/collector')

# MainActivity is intentionally patched by bounded exact replacements rather than rewritten.
main_path = root / 'MainActivity.kt'
main = main_path.read_text()
main = replace_once(main, 'private const val VERSION = "0.13.0"', 'private const val VERSION = "0.14.0"', 'MainActivity VERSION')
main = replace_once(main, 'private const val BUILD_CODE = 113000', 'private const val BUILD_CODE = 114000', 'MainActivity BUILD_CODE')
main_path.write_text(main)

# Hub cards: preserve the canonical quality state, but replace the ambiguous label with a concrete
# evidence diagnosis derived only from persisted Adiga binding evidence.
hub_path = root / 'hub/HubDashboardModel.kt'
hub = hub_path.read_text()
hub = replace_once(hub, 'const val SCHEMA_VERSION = 2', 'const val SCHEMA_VERSION = 3', 'Hub schema')
hub = replace_once(
    hub,
    '        val binding = candidate.optJSONObject("adigaBinding") ?: JSONObject()\n        val university = candidate.nullableString("university")',
    '        val binding = candidate.optJSONObject("adigaBinding") ?: JSONObject()\n        val official = com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer.analyze(candidate)\n        val university = candidate.nullableString("university")',
    'Hub official analyzer wiring'
)
hub = replace_once(
    hub,
    '            .put("qualityState", quality).put("qualityLabel", qualityLabel(quality))\n            .put("coverageCount", coverage.optInt("coveredCount", 0))',
    '            .put("qualityState", quality).put("qualityLabel", official.optString("label", qualityLabel(quality)))\n            .put("officialEvidence", official)\n            .put("coverageCount", coverage.optInt("coveredCount", 0))',
    'Hub concrete quality label'
)
hub = replace_once(hub, '        "accepted" -> "공식 전형 연결 확인"', '        "accepted" -> "공식 전형·모집단위 직접 연결"', 'accepted label')
hub = replace_once(hub, '        "provisional" -> "공식 전형 연결 확인 필요"', '        "provisional" -> "공식자료 연결 근거를 항목별로 확인하세요"', 'provisional label')
hub = replace_once(hub, '        "provider-only" -> "진학사 중심 · 공식 결합 없음"', '        "provider-only" -> "진학사 중심 · 어디가 직접 결합 없음"', 'provider label')
hub_path.write_text(hub)

# Review engine: use the same concrete Adiga diagnosis when official application binding is incomplete.
review_path = root / 'score/ApplicationReviewEngine.kt'
review = review_path.read_text()
review = replace_once(
    review,
    '        val sourceReviewed = binding && input.optBoolean("sourceReviewConfirmed")\n        val completeProfile =',
    '        val sourceReviewed = binding && input.optBoolean("sourceReviewConfirmed")\n        val officialEvidence = com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer.analyze(candidate)\n        val completeProfile =',
    'review official analyzer'
)
review = replace_once(
    review,
    '        required(sourceReviewed, "공식 출처의 전형·학과·산식·입결 행 확인")',
    '''        if (!sourceReviewed) {
            val officialMissing = officialEvidence.optJSONArray("missing") ?: JSONArray()
            if (officialMissing.length() == 0) missing.put("공식 원문에서 전형·모집단위·연도와 현재 성적 기준을 사용자 확인")
            else for (i in 0 until officialMissing.length()) missing.put("어디가 연결: ${officialMissing.optString(i)}")
        }''',
    'review concrete missing evidence'
)
review = replace_once(
    review,
    '        return JSONObject().put("applicationIdentityKey", identity).put("academicYear", year).put("code", code).put("label", label)\n            .put("comparisonReady", comparisonReady)',
    '        return JSONObject().put("applicationIdentityKey", identity).put("academicYear", year).put("code", code).put("label", label)\n            .put("officialEvidence", officialEvidence)\n            .put("comparisonReady", comparisonReady)',
    'review output evidence'
)
review_path.write_text(review)

# Register the non-exported XLSX review activity and bump the visible product version.
manifest_path = Path('app/src/main/AndroidManifest.xml')
manifest = manifest_path.read_text()
manifest = replace_once(manifest, 'android:label="Admission Hub v0.13.0 Application Review"', 'android:label="Admission Hub v0.14.0 Adiga + XLSX"', 'manifest label')
manifest = replace_once(
    manifest,
    '        <activity\n            android:name=".MainActivity"',
    '        <activity\n            android:name=".score.XlsxImportActivity"\n            android:exported="false" />\n        <activity\n            android:name=".MainActivity"',
    'XLSX activity registration'
)
manifest_path.write_text(manifest)

build_path = Path('app/build.gradle.kts')
build = build_path.read_text()
build = replace_once(build, 'versionCode = 113000', 'versionCode = 114000', 'Gradle versionCode')
build = replace_once(build, 'versionName = "0.13.0"', 'versionName = "0.14.0"', 'Gradle versionName')
build_path.write_text(build)

print('v0.14 bounded source patch applied')
