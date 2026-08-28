from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main_paths = [
    ROOT / "MainActivity.kt",
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_main(text: str) -> str:
    text = replace_once(
        text,
        "import com.admissionhub.collector.capture.SnapshotScript\n",
        "import com.admissionhub.collector.capture.SnapshotScript\nimport com.admissionhub.collector.cloud.CloudOffloadCoordinator\n",
        "cloud import",
    )
    text = replace_once(
        text,
        "    private lateinit var batchButton: Button\n",
        "    private lateinit var batchButton: Button\n    private lateinit var cloudOffload: CloudOffloadCoordinator\n",
        "cloud field",
    )
    text = replace_once(
        text,
        '        private const val VERSION = "0.3.1"\n',
        '        private const val VERSION = "0.3.2"\n',
        "version",
    )
    text = replace_once(
        text,
        "        super.onCreate(savedInstanceState)\n        buildUi()\n",
        "        super.onCreate(savedInstanceState)\n        cloudOffload = CloudOffloadCoordinator(this)\n        buildUi()\n",
        "coordinator init",
    )
    text = replace_once(
        text,
        '''        val save = Button(this).apply {\n            text = "JSON 저장"\n            setOnClickListener { saveJson() }\n        }\n        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))\n        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))\n''',
        '''        val save = Button(this).apply {\n            text = "JSON 저장"\n            setOnClickListener { saveJson() }\n        }\n        val cloudSettings = Button(this).apply {\n            text = "Cloud 설정"\n            setOnClickListener {\n                cloudOffload.showSettingsDialog(this@MainActivity) {\n                    status.text = if (cloudOffload.isConfigured()) {\n                        "Cloudflare Offload 설정됨"\n                    } else {\n                        "Cloudflare Offload 미설정: 로컬 수집 모드"\n                    }\n                }\n            }\n        }\n        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))\n        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))\n        actions2.addView(cloudSettings, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))\n''',
        "cloud settings button",
    )
    text = replace_once(
        text,
        '''        batchButton.text = "일괄 수집 중지"\n        enqueueProviderSeeds()\n''',
        '''        batchButton.text = "일괄 수집 중지"\n        cloudOffload.beginOrResume(provider.wireName, VERSION) { runId ->\n            if (runId != null) {\n                runOnUiThread {\n                    status.text = "Cloud 체크포인트 연결: ${runId.take(8)}… / 수집 시작"\n                }\n            }\n        }\n        enqueueProviderSeeds()\n''',
        "begin cloud run",
    )
    text = replace_once(
        text,
        '''                batchErrors.put(error)\n                status.text = if (activeAction != null) {\n''',
        '''                batchErrors.put(error)\n                cloudOffload.uploadError(\n                    provider = provider.wireName,\n                    familyKey = activeAction?.familyKey,\n                    requestedYear = activeAction?.requestedYear,\n                    page = activeAction?.page,\n                    retryCount = activeAction?.retry ?: 0,\n                    error = error\n                )\n                status.text = if (activeAction != null) {\n''',
        "page error upload",
    )
    text = replace_once(
        text,
        '''            batchSnapshots.put(stripNavigationLinksForExport(snapshot))\n            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }\n            RecordUtils.appendUniqueRecords(batchRecords, normalizeSnapshot(snapshot))\n            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())\n''',
        '''            batchSnapshots.put(stripNavigationLinksForExport(snapshot))\n            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }\n            val pageRecords = normalizeSnapshot(snapshot)\n            RecordUtils.appendUniqueRecords(batchRecords, pageRecords)\n            cloudOffload.uploadPage(\n                provider = provider.wireName,\n                records = pageRecords,\n                familyKey = activeAction?.familyKey ?: plan?.familyKey,\n                requestedYear = activeAction?.requestedYear ?: plan?.requestedYear,\n                page = activeAction?.page ?: if (plan != null) 1 else null,\n                retryCount = activeAction?.retry ?: 0\n            )\n            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())\n''',
        "page record upload",
    )
    text = replace_once(
        text,
        '''        batchErrors.put(JSONObject()\n            .put("url", action.baseUrl)\n            .put("type", type)\n            .put("page", action.page)\n            .put("totalPages", action.totalPages)\n            .put("familyKey", action.familyKey)\n            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)\n            .put("retryCount", action.retry))\n''',
        '''        val error = JSONObject()\n            .put("url", action.baseUrl)\n            .put("type", type)\n            .put("page", action.page)\n            .put("totalPages", action.totalPages)\n            .put("familyKey", action.familyKey)\n            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)\n            .put("retryCount", action.retry)\n        batchErrors.put(error)\n        cloudOffload.uploadError(\n            provider = provider.wireName,\n            familyKey = action.familyKey,\n            requestedYear = action.requestedYear,\n            page = action.page,\n            retryCount = action.retry,\n            error = error\n        )\n''',
        "pagination failure upload",
    )
    text = replace_once(
        text,
        '''        finalizeBatchJson(reason)\n        status.text = "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"\n''',
        '''        finalizeBatchJson(reason)\n        cloudOffload.finish(\n            reason = reason,\n            summary = JSONObject()\n                .put("attemptedPages", batchPageCount)\n                .put("successfulPages", batchSnapshots.length())\n                .put("errorPages", batchErrors.length())\n                .put("records", batchRecords.length())\n                .put("paginationRetries", batchPaginationRetries)\n        )\n        status.text = "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"\n''',
        "finish cloud run",
    )
    text = replace_once(
        text,
        '''            .put("duplicateYearViews", batchDuplicateYearViews)\n            .put("records", batchRecords)\n''',
        '''            .put("duplicateYearViews", batchDuplicateYearViews)\n            .put("cloudOffload", cloudOffload.snapshotStatus())\n            .put("records", batchRecords)\n''',
        "export cloud status",
    )
    text = replace_once(
        text,
        '''        webView.stopLoading()\n        webView.destroy()\n        super.onDestroy()\n''',
        '''        cloudOffload.shutdown()\n        webView.stopLoading()\n        webView.destroy()\n        super.onDestroy()\n''',
        "shutdown cloud",
    )
    return text


for path in main_paths:
    original = path.read_text(encoding="utf-8")
    if 'private const val VERSION = "0.3.2"' in original:
        print(f"already patched: {path.relative_to(ROOT)}")
        continue
    path.write_text(patch_main(original), encoding="utf-8")
    print(f"patched: {path.relative_to(ROOT)}")

build = ROOT / "app/build.gradle.kts"
text = build.read_text(encoding="utf-8")
if 'versionName = "0.3.2"' not in text:
    text = replace_once(text, "versionCode = 8", "versionCode = 9", "versionCode")
    text = replace_once(text, 'versionName = "0.3.1"', 'versionName = "0.3.2"', "versionName")
    build.write_text(text, encoding="utf-8")
    print("patched: app/build.gradle.kts")

if main_paths[0].read_text(encoding="utf-8") != main_paths[1].read_text(encoding="utf-8"):
    raise SystemExit("root and nested MainActivity.kt diverged")
