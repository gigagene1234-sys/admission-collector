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


def patch_resume_integration(text: str) -> str:
    marker = "    private var batchCloudPlansPending = 0\n"
    if marker in text:
        return text

    text = replace_once(
        text,
        "    private var batchPaginationRetries = 0\n",
        "    private var batchPaginationRetries = 0\n"
        "    private var batchCloudPlansPending = 0\n"
        "    private var batchCloudResumePlans = 0\n"
        "    private var batchCloudPagesScheduled = 0\n"
        "    private var batchCloudPagesSkipped = 0\n",
        "cloud resume counters",
    )

    text = replace_once(
        text,
        '''        batchPageCount = 0\n        batchPaginationRetries = 0\n        currentBatchTarget = url\n        batchButton.text = "일괄 수집 중지"\n        cloudOffload.beginOrResume(provider.wireName, VERSION) { runId ->\n            if (runId != null) {\n                runOnUiThread {\n                    status.text = "Cloud 체크포인트 연결: ${runId.take(8)}… / 수집 시작"\n                }\n            }\n        }\n        enqueueProviderSeeds()\n        status.text = "일괄 수집 시작: 기본 정보영역 ${batchQueue.size}개를 포함해 탐색합니다."\n\n        checkSessionState { needsLogin, _ ->\n            if (needsLogin) {\n                pauseBatchForLogin()\n            } else {\n                scheduleBatchSnapshot()\n            }\n        }\n''',
        '''        batchPageCount = 0\n        batchPaginationRetries = 0\n        batchCloudPlansPending = 0\n        batchCloudResumePlans = 0\n        batchCloudPagesScheduled = 0\n        batchCloudPagesSkipped = 0\n        currentBatchTarget = url\n        batchButton.text = "일괄 수집 중지"\n        status.text = if (cloudOffload.isConfigured()) {\n            "Cloud 체크포인트 연결 준비 중…"\n        } else {\n            "Cloud 토큰 미설정: 로컬 안전모드로 수집 시작"\n        }\n        cloudOffload.beginOrResume(provider.wireName, VERSION) { runId ->\n            runOnUiThread {\n                if (!batchRunning) return@runOnUiThread\n                enqueueProviderSeeds()\n                status.text = if (runId != null) {\n                    "Cloud 체크포인트 연결: ${runId.take(8)}… / 기본 정보영역 ${batchQueue.size}개 탐색"\n                } else {\n                    "로컬 안전모드: 기본 정보영역 ${batchQueue.size}개 탐색"\n                }\n                checkSessionState { needsLogin, _ ->\n                    if (needsLogin) {\n                        pauseBatchForLogin()\n                    } else {\n                        scheduleBatchSnapshot()\n                    }\n                }\n            }\n        }\n''',
        "wait for cloud run before batch",
    )

    text = replace_once(
        text,
        '''    private fun loadNextBatchPage() {\n        if (!batchRunning || batchPausedForLogin) return\n\n        while (batchPageActions.isNotEmpty()) {\n''',
        '''    private fun loadNextBatchPage() {\n        if (!batchRunning || batchPausedForLogin) return\n        if (batchCloudPlansPending > 0) {\n            status.text = "Cloud resume 계획 확인 중: $batchCloudPlansPending개 목록"\n            handler.postDelayed({ loadNextBatchPage() }, 180)\n            return\n        }\n\n        while (batchPageActions.isNotEmpty()) {\n''',
        "wait for cloud resume plan",
    )

    old_enqueue = '''    private fun enqueueCalculatedPageActions(snapshot: JSONObject, plan: PaginationPlan) {\n        val baseUrl = canonicalizeBatchUrl(snapshot.optString("url"))\n        if (baseUrl.isBlank() || !isProviderUrl(baseUrl) || plan.totalPages <= 1) return\n        val planKey = "$baseUrl|${plan.totalItems}|${plan.pageSize}|${plan.totalPages}"\n        if (!batchPaginationPlanned.add(planKey)) return\n\n        for (page in 2..plan.totalPages) {\n            val action = BatchPageAction(\n                baseUrl = baseUrl,\n                page = page,\n                familyKey = plan.familyKey,\n                requestedYear = plan.requestedYear,\n                totalPages = plan.totalPages,\n                pageSize = plan.pageSize,\n                totalItems = plan.totalItems\n            )\n            val key = pageActionKey(action)\n            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue\n            if (batchPageActionQueued.add(key)) batchPageActions.addLast(action)\n        }\n    }\n'''
    new_enqueue = '''    private fun enqueueCalculatedPageActions(snapshot: JSONObject, plan: PaginationPlan) {\n        val baseUrl = canonicalizeBatchUrl(snapshot.optString("url"))\n        if (baseUrl.isBlank() || !isProviderUrl(baseUrl) || plan.totalPages <= 1) return\n        val planKey = "$baseUrl|${plan.totalItems}|${plan.pageSize}|${plan.totalPages}"\n        if (!batchPaginationPlanned.add(planKey)) return\n\n        if (!cloudOffload.isConfigured()) {\n            enqueuePageActions(baseUrl, plan, (2..plan.totalPages).toList())\n            return\n        }\n\n        batchCloudPlansPending += 1\n        cloudOffload.resumePlan(plan.familyKey, plan.requestedYear, plan.totalPages) { result ->\n            runOnUiThread {\n                batchCloudPlansPending = (batchCloudPlansPending - 1).coerceAtLeast(0)\n                if (!batchRunning) return@runOnUiThread\n\n                val response = result.getOrNull()\n                val pages = linkedSetOf<Int>()\n                if (response != null && !(response.optBoolean("truncated", false) && plan.totalPages > 500)) {\n                    val missing = response.optJSONArray("missing") ?: JSONArray()\n                    for (i in 0 until missing.length()) {\n                        val page = missing.optInt(i, -1)\n                        if (page in 2..plan.totalPages) pages.add(page)\n                    }\n                    val retry = response.optJSONArray("retry") ?: JSONArray()\n                    for (i in 0 until retry.length()) {\n                        val page = retry.optJSONObject(i)?.optInt("page", -1) ?: -1\n                        if (page in 2..plan.totalPages) pages.add(page)\n                    }\n                    batchCloudResumePlans += 1\n                    batchCloudPagesScheduled += pages.size\n                    val skipped = (plan.totalPages - 1 - pages.size).coerceAtLeast(0)\n                    batchCloudPagesSkipped += skipped\n                    status.text = "Cloud resume: ${pages.size}쪽 재수집 / ${skipped}쪽 완료로 건너뜀"\n                    enqueuePageActions(baseUrl, plan, pages.sorted())\n                } else {\n                    val fallback = (2..plan.totalPages).toList()\n                    enqueuePageActions(baseUrl, plan, fallback)\n                    status.text = "Cloud resume 확인 실패: 전체 페이지 안전 수집으로 전환"\n                }\n\n                handler.postDelayed({ loadNextBatchPage() }, 120)\n            }\n        }\n    }\n\n    private fun enqueuePageActions(baseUrl: String, plan: PaginationPlan, pages: Collection<Int>) {\n        for (page in pages) {\n            if (page !in 2..plan.totalPages) continue\n            val action = BatchPageAction(\n                baseUrl = baseUrl,\n                page = page,\n                familyKey = plan.familyKey,\n                requestedYear = plan.requestedYear,\n                totalPages = plan.totalPages,\n                pageSize = plan.pageSize,\n                totalItems = plan.totalItems\n            )\n            val key = pageActionKey(action)\n            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue\n            if (batchPageActionQueued.add(key)) batchPageActions.addLast(action)\n        }\n    }\n'''
    text = replace_once(text, old_enqueue, new_enqueue, "cloud resume page scheduler")

    text = replace_once(
        text,
        '''                .put("paginationRetries", batchPaginationRetries)\n                .put("paginationPlans", batchPaginationPlanned.size)\n''',
        '''                .put("paginationRetries", batchPaginationRetries)\n                .put("paginationPlans", batchPaginationPlanned.size)\n                .put("cloudResumePlans", batchCloudResumePlans)\n                .put("cloudPagesScheduled", batchCloudPagesScheduled)\n                .put("cloudPagesSkipped", batchCloudPagesSkipped)\n''',
        "cloud resume export summary",
    )

    text = replace_once(
        text,
        '''                .put("records", batchRecords.length())\n                .put("paginationRetries", batchPaginationRetries)\n        )\n''',
        '''                .put("records", batchRecords.length())\n                .put("paginationRetries", batchPaginationRetries)\n                .put("cloudResumePlans", batchCloudResumePlans)\n                .put("cloudPagesScheduled", batchCloudPagesScheduled)\n                .put("cloudPagesSkipped", batchCloudPagesSkipped)\n        )\n''',
        "cloud finish summary",
    )

    return text


for path in main_paths:
    original = path.read_text(encoding="utf-8")
    text = original
    if 'private const val VERSION = "0.3.2"' not in text:
        text = patch_main(text)
    text = patch_resume_integration(text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        print(f"patched: {path.relative_to(ROOT)}")
    else:
        print(f"already patched: {path.relative_to(ROOT)}")

build = ROOT / "app/build.gradle.kts"
text = build.read_text(encoding="utf-8")
if 'versionName = "0.3.2"' not in text:
    text = replace_once(text, "versionCode = 8", "versionCode = 9", "versionCode")
    text = replace_once(text, 'versionName = "0.3.1"', 'versionName = "0.3.2"', "versionName")
    build.write_text(text, encoding="utf-8")
    print("patched: app/build.gradle.kts")

if main_paths[0].read_text(encoding="utf-8") != main_paths[1].read_text(encoding="utf-8"):
    raise SystemExit("root and nested MainActivity.kt diverged")
