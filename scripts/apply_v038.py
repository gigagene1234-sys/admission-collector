from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        if new in text:
            return text
        raise SystemExit(f"{label}: source pattern not found")
    if count != 1:
        raise SystemExit(f"{label}: expected one source pattern, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    next_text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count == 0:
        raise SystemExit(f"{label}: regex source pattern not found")
    return next_text


# ---------------------------------------------------------------------------
# Cloudflare Worker: global pending recovery + server-side completion guard.
# ---------------------------------------------------------------------------
worker_path = ROOT / "cloudflare/src/index.js"
worker = worker_path.read_text()
worker = replace_once(worker, 'version: "0.3.6"', 'version: "0.3.8"', "worker health version")

status_route = '''      const statusMatch = url.pathname.match(/^\\/v1\\/runs\\/([^/]+)\\/status$/);\n      if (request.method === "GET" && statusMatch) {\n        const runId = decodeURIComponent(statusMatch[1]);\n        return getStatus(env, runId);\n      }\n'''
pending_route = status_route + '''\n      const pendingMatch = url.pathname.match(/^\\/v1\\/runs\\/([^/]+)\\/pending-pages$/);\n      if (request.method === "GET" && pendingMatch) {\n        const runId = decodeURIComponent(pendingMatch[1]);\n        const limit = boundedInt(url.searchParams.get("limit") || "500", 1, 500);\n        return getPendingPages(env, runId, limit);\n      }\n'''
if "pending-pages" not in worker:
    worker = replace_once(worker, status_route, pending_route, "pending-pages route")

old_latest = r'''async function getLatestActiveRun\(env, provider\) \{.*?\n\}\n\nasync function createRun'''
new_latest = '''async function getLatestActiveRun(env, provider) {
  const row = await env.DB.prepare(`
    SELECT r.run_id, r.provider, r.collector_version, r.status, r.created_at, r.updated_at,
           EXISTS(
             SELECT 1 FROM run_pages p
             WHERE p.run_id = r.run_id AND p.state != 'completed'
           ) AS has_pending
    FROM runs r
    WHERE r.provider = ?
      AND (
        r.status = 'collecting'
        OR EXISTS(
          SELECT 1 FROM run_pages p
          WHERE p.run_id = r.run_id AND p.state != 'completed'
        )
      )
    ORDER BY CASE WHEN r.status = 'collecting' THEN 0 ELSE 1 END,
             r.updated_at DESC
    LIMIT 1
  `).bind(provider).first();

  if (row && row.status !== "collecting" && Number(row.has_pending || 0) > 0) {
    const now = new Date().toISOString();
    await env.DB.prepare(`
      UPDATE runs
      SET status = 'collecting', completion_reason = NULL, updated_at = ?
      WHERE run_id = ?
    `).bind(now, row.run_id).run();
    row.status = "collecting";
    row.updated_at = now;
  }

  return json({
    runId: row?.run_id || null,
    provider: row?.provider || provider,
    collectorVersion: row?.collector_version || null,
    status: row?.status || null,
    updatedAt: row?.updated_at || null,
    recoveredPending: Number(row?.has_pending || 0) > 0,
  });
}

async function createRun'''
worker = regex_once(worker, old_latest, new_latest, "recoverable latest run")

finish_marker = '''        await assertRunExists(env, runId);\n\n        await env.DB.prepare(`\n          UPDATE runs\n'''
finish_guard = '''        await assertRunExists(env, runId);\n\n        if ((body.completionReason || "") === "completed") {\n          const pending = await env.DB.prepare(`\n            SELECT COUNT(*) AS pending_count\n            FROM run_pages\n            WHERE run_id = ? AND state != 'completed'\n          `).bind(runId).first();\n          const pendingCount = Number(pending?.pending_count || 0);\n          if (pendingCount > 0) {\n            return json({ error: "run_incomplete", runId, pendingPages: pendingCount }, 409);\n          }\n        }\n\n        await env.DB.prepare(`\n          UPDATE runs\n'''
if 'error: "run_incomplete"' not in worker:
    worker = replace_once(worker, finish_marker, finish_guard, "finish completeness guard")

pending_function = '''async function getPendingPages(env, runId, limit) {
  const run = await env.DB.prepare(`
    SELECT run_id FROM runs WHERE run_id = ? LIMIT 1
  `).bind(runId).first();
  if (!run) return json({ error: "run_not_found" }, 404);

  const countRow = await env.DB.prepare(`
    SELECT COUNT(*) AS pending_count
    FROM run_pages
    WHERE run_id = ? AND state != 'completed'
  `).bind(runId).first();

  const rows = await env.DB.prepare(`
    SELECT p.family_key, p.requested_year, p.page_number, p.state,
           p.retry_count, p.error_type, p.updated_at,
           (
             SELECT MAX(p2.page_number)
             FROM run_pages p2
             WHERE p2.run_id = p.run_id
               AND p2.family_key = p.family_key
               AND p2.requested_year = p.requested_year
           ) AS total_pages
    FROM run_pages p
    WHERE p.run_id = ? AND p.state != 'completed'
    ORDER BY p.requested_year DESC, p.family_key, p.page_number
    LIMIT ?
  `).bind(runId, limit).all();

  const retry = [];
  const deferred = [];
  const nowMs = Date.now();
  for (const row of rows.results || []) {
    const retryCount = Number(row.retry_count || 0);
    const errorType = row.error_type || null;
    const updatedMs = Date.parse(row.updated_at || "");
    const shouldDeferServerError =
      errorType === "server-error" &&
      retryCount >= 2 &&
      Number.isFinite(updatedMs) &&
      nowMs - updatedMs < SERVER_ERROR_RETRY_COOLDOWN_MS;
    const item = {
      familyKey: row.family_key,
      requestedYear: Number(row.requested_year) === -1 ? null : Number(row.requested_year),
      page: Number(row.page_number),
      totalPages: Number(row.total_pages || row.page_number),
      state: row.state,
      retryCount,
      errorType,
      updatedAt: row.updated_at,
    };
    if (shouldDeferServerError) {
      item.retryAfter = new Date(updatedMs + SERVER_ERROR_RETRY_COOLDOWN_MS).toISOString();
      deferred.push(item);
    } else {
      retry.push(item);
    }
  }

  const pendingCount = Number(countRow?.pending_count || 0);
  return json({
    runId,
    pendingCount,
    retryCount: retry.length,
    deferredCount: deferred.length,
    retry,
    deferred,
    serverErrorCooldownSeconds: Math.floor(SERVER_ERROR_RETRY_COOLDOWN_MS / 1000),
    truncated: pendingCount > (retry.length + deferred.length),
  });
}

'''
if "async function getPendingPages" not in worker:
    worker = replace_once(worker, "async function getResumePlan", pending_function + "async function getResumePlan", "pending-pages function")
worker_path.write_text(worker)


# ---------------------------------------------------------------------------
# Android Cloud client/coordinator.
# ---------------------------------------------------------------------------
client_path = ROOT / "app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadClient.kt"
client = client_path.read_text()
client_method = '''\n    fun getPendingPages(\n        runId: String,\n        callback: (Result<JSONObject>) -> Unit\n    ) = io.execute {\n        callback(runCatching {\n            get("/v1/runs/${encode(runId)}/pending-pages?limit=500")\n        })\n    }\n'''
if "fun getPendingPages(" not in client:
    client = replace_once(client, "\n    fun shutdown() {", client_method + "\n    fun shutdown() {", "client pending pages")
client_path.write_text(client)

coord_path = ROOT / "app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadCoordinator.kt"
coord = coord_path.read_text()
coord_methods = '''\n    fun pendingPages(callback: (Result<JSONObject>) -> Unit) {\n        val runId = synchronized(lock) { activeRunId }\n        val currentClient = synchronized(lock) { ensureClientLocked(); client }\n        if (runId.isNullOrBlank() || currentClient == null) {\n            callback(Result.failure(IllegalStateException("No active cloud run")))\n            return\n        }\n        currentClient.getPendingPages(runId, callback)\n    }\n\n    fun status(callback: (Result<JSONObject>) -> Unit) {\n        val runId = synchronized(lock) { activeRunId }\n        val currentClient = synchronized(lock) { ensureClientLocked(); client }\n        if (runId.isNullOrBlank() || currentClient == null) {\n            callback(Result.failure(IllegalStateException("No active cloud run")))\n            return\n        }\n        currentClient.getStatus(runId, callback)\n    }\n'''
if "fun pendingPages(" not in coord:
    coord = replace_once(coord, "\n    fun snapshotStatus(): JSONObject", coord_methods + "\n    fun snapshotStatus(): JSONObject", "coordinator pending/status")
coord_path.write_text(coord)


# ---------------------------------------------------------------------------
# Adiga fingerprints: preserve old row hash but scope it by record year.
# ---------------------------------------------------------------------------
adiga_path = ROOT / "app/src/main/java/com/admissionhub/collector/provider/AdigaAdapter.kt"
adiga = adiga_path.read_text()
adiga = adiga.replace('.put("sourceRowFingerprint", rowFingerprint("university-summary", row))', '.put("sourceRowFingerprint", scopedRowFingerprint("university-summary", pageYear, row))')
adiga = adiga.replace('.put("sourceRowFingerprint", rowFingerprint("department-summary", row))', '.put("sourceRowFingerprint", scopedRowFingerprint("department-summary", pageYear, row))')
adiga = adiga.replace('.put("sourceRowFingerprint", rowFingerprint("disabled-admissions-index", row))', '.put("sourceRowFingerprint", scopedRowFingerprint("disabled-admissions-index", year, row))')
adiga = adiga.replace('.put("sourceRowFingerprint", rowFingerprint(type, row))', '.put("sourceRowFingerprint", scopedRowFingerprint(type, null, row))')
if "private fun scopedRowFingerprint" not in adiga:
    adiga = replace_once(
        adiga,
        '    private fun rowFingerprint(type: String, row: JSONArray): String =\n        RecordUtils.sha256("$type|${rowToEvidence(row)}")',
        '    private fun scopedRowFingerprint(type: String, year: Int?, row: JSONArray): String =\n        "yr:${year ?: "na"}:${rowFingerprint(type, row)}"\n\n    private fun rowFingerprint(type: String, row: JSONArray): String =\n        RecordUtils.sha256("$type|${rowToEvidence(row)}")',
        "year-scoped Adiga fingerprint helper"
    )
if '.put("sourceRowFingerprint", rowFingerprint' in adiga:
    raise SystemExit("unscoped Adiga sourceRowFingerprint remains")
adiga_path.write_text(adiga)


# ---------------------------------------------------------------------------
# MainActivity: global pending pages first + server-global final verification.
# ---------------------------------------------------------------------------
main_paths = [
    ROOT / "MainActivity.kt",
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
]
for path in main_paths:
    text = path.read_text()
    text = text.replace('private const val VERSION = "0.3.7"', 'private const val VERSION = "0.3.8"')
    if "batchCloudFinalCheckInProgress" not in text:
        text = replace_once(
            text,
            "    private var batchNavigationWatchdogRecovery = false\n",
            "    private var batchNavigationWatchdogRecovery = false\n    private var batchCloudFinalCheckInProgress = false\n",
            f"{path.name} final-check state"
        )

    old_callback = '''        cloudOffload.beginOrResume(provider.wireName, VERSION) { runId ->\n            runOnUiThread {\n                if (!batchRunning) return@runOnUiThread\n                enqueueProviderSeeds()\n                status.text = if (runId != null) {\n                    "Cloud 체크포인트 연결: ${runId.take(8)}… / 기본 정보영역 ${batchQueue.size}개 탐색"\n                } else {\n                    "로컬 안전모드: 기본 정보영역 ${batchQueue.size}개 탐색"\n                }\n                checkSessionState { needsLogin, _ ->\n                    if (needsLogin) {\n                        pauseBatchForLogin()\n                    } else {\n                        val startUrl = currentBatchTarget\n                        if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)\n                        else loadNextBatchPage()\n                    }\n                }\n            }\n        }\n'''
    new_callback = '''        cloudOffload.beginOrResume(provider.wireName, VERSION) { runId ->\n            runOnUiThread {\n                if (!batchRunning) return@runOnUiThread\n                prepareCloudRecoveryAndStart(runId)\n            }\n        }\n'''
    if old_callback in text:
        text = text.replace(old_callback, new_callback, 1)
    elif "prepareCloudRecoveryAndStart(runId)" not in text:
        raise SystemExit(f"{path.name}: startBatch callback pattern not found")

    helpers = '''\n    private fun prepareCloudRecoveryAndStart(runId: String?) {\n        if (runId.isNullOrBlank() || !cloudOffload.isConfigured()) {\n            beginBatchNavigation(runId)\n            return\n        }\n        status.text = "Cloud 전체 미완료 체크포인트 확인 중…"\n        cloudOffload.pendingPages { result ->\n            runOnUiThread {\n                if (!batchRunning) return@runOnUiThread\n                val response = result.getOrNull()\n                if (response != null) {\n                    val scheduled = enqueueGlobalPendingRecovery(response)\n                    batchCloudPagesDeferred = response.optJSONArray("deferred")?.length() ?: 0\n                    status.text = "Cloud 전역 복구: ${scheduled}쪽 우선 재시도 / ${batchCloudPagesDeferred}쪽 cooldown 보류"\n                } else {\n                    status.text = "Cloud 전역 복구 조회 실패: 기존 목록 resume-plan으로 계속"\n                }\n                beginBatchNavigation(runId)\n            }\n        }\n    }\n\n    private fun beginBatchNavigation(runId: String?) {\n        enqueueProviderSeeds()\n        if (runId != null && batchPageActions.isEmpty()) {\n            status.text = "Cloud 체크포인트 연결: ${runId.take(8)}… / 기본 정보영역 ${batchQueue.size}개 탐색"\n        } else if (runId == null) {\n            status.text = "로컬 안전모드: 기본 정보영역 ${batchQueue.size}개 탐색"\n        }\n        checkSessionState { needsLogin, _ ->\n            if (needsLogin) {\n                pauseBatchForLogin()\n            } else if (batchPageActions.isNotEmpty()) {\n                loadNextBatchPage()\n            } else {\n                val startUrl = currentBatchTarget\n                if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)\n                else loadNextBatchPage()\n            }\n        }\n    }\n\n    private fun enqueueGlobalPendingRecovery(response: JSONObject): Int {\n        val retry = response.optJSONArray("retry") ?: JSONArray()\n        var scheduled = 0\n        for (i in 0 until retry.length()) {\n            val item = retry.optJSONObject(i) ?: continue\n            val familyKey = item.optString("familyKey")\n            val page = item.optInt("page", -1)\n            if (familyKey.isBlank() || page < 1) continue\n            val requestedYear = if (item.isNull("requestedYear")) null else item.optInt("requestedYear").takeIf { it > 0 }\n            val totalPages = item.optInt("totalPages", page).coerceAtLeast(page)\n            val baseUrl = recoveryUrlForPending(familyKey, requestedYear) ?: continue\n            val action = BatchPageAction(\n                baseUrl = baseUrl,\n                page = page,\n                familyKey = familyKey,\n                requestedYear = requestedYear,\n                totalPages = totalPages,\n                pageSize = 0,\n                totalItems = 0,\n                retry = 0\n            )\n            val key = pageActionKey(action)\n            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue\n            if (batchPageActionQueued.add(key)) {\n                batchPageActions.addFirst(action)\n                scheduled += 1\n            }\n        }\n        batchCloudPagesScheduled += scheduled\n        return scheduled\n    }\n\n    private fun recoveryUrlForPending(familyKey: String, requestedYear: Int?): String? {\n        if (provider != ProviderId.ADIGA) return null\n        val raw = if (familyKey.startsWith("http://") || familyKey.startsWith("https://")) {\n            familyKey\n        } else {\n            "https://www.adiga.kr" + if (familyKey.startsWith("/")) familyKey else "/$familyKey"\n        }\n        return if (requestedYear != null) withQueryParameter(raw, "searchSyr", requestedYear.toString()) else raw\n    }\n'''
    if "private fun prepareCloudRecoveryAndStart" not in text:
        text = replace_once(text, "\n    private fun armBatchNavigationWatchdog", helpers + "\n    private fun armBatchNavigationWatchdog", f"{path.name} global recovery helpers")

    # Reset final-check state at every new batch.
    reset_marker = "        batchNavigationWatchdogRecovery = false\n        disarmBatchNavigationWatchdog()\n"
    reset_repl = "        batchNavigationWatchdogRecovery = false\n        batchCloudFinalCheckInProgress = false\n        disarmBatchNavigationWatchdog()\n"
    if reset_repl not in text:
        text = replace_once(text, reset_marker, reset_repl, f"{path.name} final-check reset")

    # Queue exhaustion must be verified against the server-global checkpoint set.
    if "        verifyCloudCompletionOrFinish()\n    }\n\n    private fun executePendingBatchPageAction" not in text:
        text = replace_once(
            text,
            '        finishBatch("completed")\n    }\n\n    private fun executePendingBatchPageAction',
            '        verifyCloudCompletionOrFinish()\n    }\n\n    private fun executePendingBatchPageAction',
            f"{path.name} server-global finish hook"
        )

    final_verify = '''\n    private fun verifyCloudCompletionOrFinish(drainAttempt: Int = 0) {\n        if (!batchRunning || batchPausedForLogin) return\n        if (!cloudOffload.isConfigured()) {\n            finishBatch("completed")\n            return\n        }\n        if (batchCloudFinalCheckInProgress) return\n        batchCloudFinalCheckInProgress = true\n        status.text = "Cloud Queue 및 전체 체크포인트 최종 검증 중…"\n        cloudOffload.status { statusResult ->\n            runOnUiThread {\n                if (!batchRunning) {\n                    batchCloudFinalCheckInProgress = false\n                    return@runOnUiThread\n                }\n                val run = statusResult.getOrNull()?.optJSONObject("run")\n                val uploaded = run?.optInt("uploaded_chunks", 0) ?: 0\n                val processed = run?.optInt("processed_chunks", 0) ?: 0\n                if (run != null && processed < uploaded && drainAttempt < 20) {\n                    batchCloudFinalCheckInProgress = false\n                    status.text = "Cloud Queue 반영 대기: $processed/$uploaded"\n                    handler.postDelayed({ verifyCloudCompletionOrFinish(drainAttempt + 1) }, 500L)\n                    return@runOnUiThread\n                }\n                cloudOffload.pendingPages { pendingResult ->\n                    runOnUiThread {\n                        batchCloudFinalCheckInProgress = false\n                        if (!batchRunning) return@runOnUiThread\n                        val response = pendingResult.getOrNull()\n                        if (response == null) {\n                            finishBatch("cloud-verification-failed")\n                            return@runOnUiThread\n                        }\n                        val deferred = response.optJSONArray("deferred") ?: JSONArray()\n                        batchCloudPagesDeferred = deferred.length()\n                        val scheduled = enqueueGlobalPendingRecovery(response)\n                        if (scheduled > 0) {\n                            status.text = "Cloud 미완료 ${scheduled}쪽을 완료 판정 전에 우선 복구합니다."\n                            handler.postDelayed({ loadNextBatchPage() }, 120L)\n                            return@runOnUiThread\n                        }\n                        if (batchCloudPagesDeferred > 0) {\n                            finishBatch("completed-with-deferred-errors")\n                        } else {\n                            finishBatch("completed")\n                        }\n                    }\n                }\n            }\n        }\n    }\n'''
    if "private fun verifyCloudCompletionOrFinish" not in text:
        text = replace_once(text, "\n    private fun executePendingBatchPageAction", final_verify + "\n    private fun executePendingBatchPageAction", f"{path.name} final cloud verification")

    # Never close a server run unless server-global verification reached true completed.
    text = text.replace(
        "        if (batchCloudPagesDeferred == 0) {\n            cloudOffload.finish(",
        "        if (effectiveReason == \"completed\" && batchCloudPagesDeferred == 0) {\n            cloudOffload.finish("
    )
    old_status = '''        status.text = if (batchCloudPagesDeferred > 0) {\n            "수집 완료: 서버 오류 ${batchCloudPagesDeferred}쪽은 Cloud에 보류 / 나머지 완료 페이지는 유지됨"\n        } else {\n            "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"\n        }\n'''
    new_status = '''        status.text = when {\n            effectiveReason == "cloud-verification-failed" ->\n                "로컬 수집 종료: Cloud 최종 완결성 확인 실패 / 서버 run은 닫지 않고 유지합니다."\n            batchCloudPagesDeferred > 0 ->\n                "수집 종료: 서버 오류 ${batchCloudPagesDeferred}쪽은 Cloud에 보류 / 전체 완료로 확정하지 않습니다."\n            else ->\n                "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"\n        }\n'''
    if old_status in text:
        text = text.replace(old_status, new_status, 1)
    elif "Cloud 최종 완결성 확인 실패" not in text:
        raise SystemExit(f"{path.name}: finish status pattern not found")

    path.write_text(text)


# Gradle version.
gradle_path = ROOT / "app/build.gradle.kts"
gradle = gradle_path.read_text()
gradle = gradle.replace('versionCode = 14', 'versionCode = 15')
gradle = gradle.replace('versionName = "0.3.7"', 'versionName = "0.3.8"')
gradle_path.write_text(gradle)

# Final cross-file invariants.
root_main = main_paths[0].read_text()
app_main = main_paths[1].read_text()
if root_main != app_main:
    raise SystemExit("MainActivity root/app copies differ after v0.3.8 patch")
required = [
    'private const val VERSION = "0.3.8"',
    'private fun prepareCloudRecoveryAndStart',
    'private fun verifyCloudCompletionOrFinish',
    'Cloud 미완료',
]
for marker in required:
    if marker not in root_main:
        raise SystemExit(f"missing MainActivity invariant: {marker}")
if 'versionName = "0.3.8"' not in gradle or 'versionCode = 15' not in gradle:
    raise SystemExit("Gradle v0.3.8 version invariant failed")
if 'async function getPendingPages' not in worker_path.read_text():
    raise SystemExit("Worker pending-pages invariant failed")
if 'scopedRowFingerprint' not in adiga_path.read_text():
    raise SystemExit("Adiga year-scoped fingerprint invariant failed")

print("v0.3.8 global pending recovery + year-scoped fingerprint patch applied")
