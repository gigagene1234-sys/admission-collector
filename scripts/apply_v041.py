from pathlib import Path

ROOT = Path('.')
MAIN_PATHS = [
    ROOT / 'MainActivity.kt',
    ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt',
]
BUILD = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'anchor not found: {label}')
    return text.replace(old, new, 1)


for path in MAIN_PATHS:
    s = path.read_text()
    s = s.replace('private const val VERSION = "0.4.0"', 'private const val VERSION = "0.4.1"')
    s = s.replace('private const val BUILD_CODE = 10400', 'private const val BUILD_CODE = 10410')

    s = replace_once(
        s,
        '    private var localRunId: String? = null\n',
        '''    private var localRunId: String? = null
    private val batchPersistedPageSignatureOwners = linkedMapOf<String, MutableMap<String, Int>>()
    private var batchAuditPagesScheduled = 0
    private var batchUniversityDiscoveryPagesScheduled = 0
''',
        f'v041 state fields {path}'
    )

    s = replace_once(
        s,
        '        batchLocalRecordsPersisted = 0\n        disarmBatchNavigationWatchdog()\n',
        '''        batchLocalRecordsPersisted = 0
        batchAuditPagesScheduled = 0
        batchUniversityDiscoveryPagesScheduled = 0
        batchPersistedPageSignatureOwners.clear()
        disarmBatchNavigationWatchdog()
''',
        f'v041 reset fields {path}'
    )

    old_collect = '''            batchSnapshots.put(stripNavigationLinksForExport(snapshot))
            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }
            val pageRecords = normalizeSnapshot(snapshot)
            RecordUtils.appendUniqueRecords(batchRecords, pageRecords)
            localRunId?.let { runId ->
                batchLocalRecordsPersisted += localStore.storeRecords(runId, provider.wireName, pageRecords)
                val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                localStore.markDocument(runId, navKey, "completed")
                when {
                    activeAction != null -> localStore.markPage(
                        runId, activeAction.familyKey, activeAction.requestedYear,
                        activeAction.page, activeAction.totalPages, "completed", activeAction.retry
                    )
                    plan != null -> localStore.markPage(
                        runId, plan.familyKey, plan.requestedYear,
                        1, plan.totalPages, "completed", 0
                    )
                }
            }
            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())

            if (activeAction == null) {
                enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())
                if (plan != null) enqueueCalculatedPageActions(snapshot, plan)
            } else {
                batchPageActionVisited.add(pageActionKey(activeAction))
                activeBatchPageAction = null
            }
'''
    new_collect = '''            val pageRecords = normalizeSnapshot(snapshot)
            if (activeAction != null && LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
                val duplicateOwner = persistedDuplicatePageOwner(activeAction, pageRecords)
                if (duplicateOwner != null && duplicateOwner != activeAction.page) {
                    activeBatchPageAction = null
                    status.text = "페이지 ${activeAction.page} 내용이 기존 ${duplicateOwner}쪽과 동일함: stale 응답으로 판정 후 재시도"
                    schedulePageActionRetry(activeAction, "stale-pagination-content")
                    return@collectSnapshot
                }
            }

            batchSnapshots.put(snapshotForLocalExport(snapshot))
            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }
            // University detail records can be large. SQLite is the authoritative local store;
            // avoid keeping a second in-memory copy during the long detail crawl.
            if (!(LOCAL_FIRST_BETA && snapshot.optString("providerPageType") == "adiga-university-detail")) {
                RecordUtils.appendUniqueRecords(batchRecords, pageRecords)
            }
            localRunId?.let { runId ->
                batchLocalRecordsPersisted += localStore.storeRecords(runId, provider.wireName, pageRecords)
                val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                localStore.markDocument(runId, navKey, "completed")
                when {
                    activeAction != null -> localStore.markPage(
                        runId, activeAction.familyKey, activeAction.requestedYear,
                        activeAction.page, activeAction.totalPages, "completed", activeAction.retry
                    )
                    plan != null -> localStore.markPage(
                        runId, plan.familyKey, plan.requestedYear,
                        1, plan.totalPages, "completed", 0
                    )
                }
            }
            if (activeAction != null) rememberAcceptedPageSignature(activeAction, pageRecords)
            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())

            // v0.4.0 only followed links from page 1 because pagination actions skipped
            // discovery. University-list pagination is safe and bounded (220 universities),
            // so collect detail URLs from every university-list page as well.
            val pageType = snapshot.optString("providerPageType")
            if (activeAction == null || pageType == "adiga-university-list") {
                enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())
            }
            if (activeAction == null) {
                if (plan != null) enqueueCalculatedPageActions(snapshot, plan)
            } else {
                batchPageActionVisited.add(pageActionKey(activeAction))
                activeBatchPageAction = null
            }
'''
    s = replace_once(s, old_collect, new_collect, f'v041 collect pipeline {path}')

    old_local_plan = '''            val localPlan = localStore.resumePlan(runId, plan.familyKey, plan.requestedYear, plan.totalPages)
            val pages = (localPlan.retry + localPlan.missing).distinct().sorted()
            batchLocalResumePlans += 1
            batchLocalPagesScheduled += pages.size
            batchLocalPagesSkipped += localPlan.completedCount
            status.text = "Local resume: ${pages.size}쪽 수집 / ${localPlan.completedCount}쪽 완료로 건너뜀"
            enqueuePageActions(baseUrl, plan, pages)
            return
'''
    new_local_plan = '''            val localPlan = localStore.resumePlan(runId, plan.familyKey, plan.requestedYear, plan.totalPages)
            val pages = linkedSetOf<Int>()
            pages.addAll(localPlan.retry)
            pages.addAll(localPlan.missing)

            // Checkpoint state alone is insufficient: v0.4.0 proved that a stale AJAX
            // response could be marked completed while another page's rows were stored.
            // Re-open any checkpoint that has no persisted row evidence, plus neighbors
            // so stale-content detection has a reference page on either side.
            val evidencePages = persistedPagesWithRecords(runId, plan.familyKey, plan.requestedYear)
            val evidenceMissing = (2..plan.totalPages).filter { it !in evidencePages }
            for (page in evidenceMissing) {
                for (candidate in (page - 1)..(page + 1)) {
                    if (candidate in 2..plan.totalPages) pages.add(candidate)
                }
            }
            batchAuditPagesScheduled += evidenceMissing.size

            // v0.4.0 already has all 220 university summary rows, but only page 1 links
            // were followed. Revisit the 21 remaining 2027 university-list pages solely
            // to discover detail URLs; completed detail documents are still skipped.
            if (plan.familyKey.contains("/ucp/uvt/uni/univView.do") && plan.requestedYear == 2027) {
                val discoveryPages = (2..plan.totalPages).toList()
                pages.addAll(discoveryPages)
                batchUniversityDiscoveryPagesScheduled += discoveryPages.size
            }

            val sortedPages = pages.distinct().sorted()
            batchLocalResumePlans += 1
            batchLocalPagesScheduled += sortedPages.size
            batchLocalPagesSkipped += (plan.totalPages - 1 - sortedPages.size).coerceAtLeast(0)
            status.text = "Local audit/resume: ${sortedPages.size}쪽 수집 / 증거누락 ${evidenceMissing.size}쪽 / 대학상세 발견 ${batchUniversityDiscoveryPagesScheduled}쪽"
            enqueuePageActions(baseUrl, plan, sortedPages)
            return
'''
    s = replace_once(s, old_local_plan, new_local_plan, f'v041 local audit plan {path}')

    helper_anchor = '    private fun loadNextBatchPage() {\n'
    helpers = r'''    private fun snapshotForLocalExport(snapshot: JSONObject): JSONObject {
        if (!(LOCAL_FIRST_BETA && provider == ProviderId.ADIGA &&
                snapshot.optString("providerPageType") == "adiga-university-detail")) {
            return stripNavigationLinksForExport(snapshot)
        }
        // Detailed tables are already normalized into durable SQLite records. Keep only
        // lightweight diagnostics here to prevent hundreds of university details from
        // being duplicated in RAM and again in the exported JSON.
        return JSONObject()
            .put("title", snapshot.optString("title"))
            .put("url", snapshot.optString("url"))
            .put("collectedAt", snapshot.optString("collectedAt"))
            .put("providerPageType", snapshot.optString("providerPageType"))
            .put("collectionPage", snapshot.optInt("collectionPage", 1))
            .put("pageState", snapshot.optJSONObject("pageState") ?: JSONObject())
            .put("listMeta", snapshot.optJSONObject("listMeta") ?: JSONObject())
            .put("discovery", snapshot.optJSONObject("discovery") ?: JSONObject())
    }

    private fun pageAuditCacheKey(familyKey: String, requestedYear: Int?): String =
        "$familyKey|year=${requestedYear ?: "unknown"}"

    private fun stableRecordMaterial(obj: JSONObject): String = listOf(
        obj.optString("recordType"),
        obj.optString("university"),
        obj.optString("department"),
        obj.optString("admission"),
        obj.optString("rawEvidence")
    ).joinToString("|")

    private fun normalizedPageSignature(records: JSONArray): String? {
        if (records.length() == 0) return null
        val parts = mutableListOf<String>()
        for (i in 0 until records.length()) {
            records.optJSONObject(i)?.let { parts += stableRecordMaterial(it) }
        }
        if (parts.isEmpty()) return null
        return RecordUtils.sha256(parts.sorted().joinToString("\n"))
    }

    private fun persistedPageSignatureOwners(action: BatchPageAction): MutableMap<String, Int> {
        val runId = localRunId ?: return linkedMapOf()
        val cacheKey = pageAuditCacheKey(action.familyKey, action.requestedYear)
        batchPersistedPageSignatureOwners[cacheKey]?.let { return it }

        val familyPath = action.familyKey.substringBefore('?')
        val grouped = linkedMapOf<Int, MutableList<String>>()
        val stored = localStore.loadRecords(runId)
        for (i in 0 until stored.length()) {
            val obj = stored.optJSONObject(i) ?: continue
            val source = obj.optString("sourcePage")
            if (!source.contains(familyPath)) continue
            if (action.requestedYear != null) {
                if (obj.isNull("year") || obj.optInt("year", -1) != action.requestedYear) continue
            }
            val page = obj.optInt("sourcePageNumber", -1)
            if (page < 1) continue
            grouped.getOrPut(page) { mutableListOf() }.add(stableRecordMaterial(obj))
        }
        val owners = linkedMapOf<String, Int>()
        for ((page, parts) in grouped) {
            if (parts.isNotEmpty()) owners[RecordUtils.sha256(parts.sorted().joinToString("\n"))] = page
        }
        batchPersistedPageSignatureOwners[cacheKey] = owners
        return owners
    }

    private fun persistedPagesWithRecords(runId: String, familyKey: String, requestedYear: Int?): Set<Int> {
        val familyPath = familyKey.substringBefore('?')
        val pages = linkedSetOf<Int>()
        val stored = localStore.loadRecords(runId)
        for (i in 0 until stored.length()) {
            val obj = stored.optJSONObject(i) ?: continue
            if (!obj.optString("sourcePage").contains(familyPath)) continue
            if (requestedYear != null) {
                if (obj.isNull("year") || obj.optInt("year", -1) != requestedYear) continue
            }
            val page = obj.optInt("sourcePageNumber", -1)
            if (page >= 1) pages.add(page)
        }
        return pages
    }

    private fun persistedDuplicatePageOwner(action: BatchPageAction, records: JSONArray): Int? {
        val signature = normalizedPageSignature(records) ?: return null
        return persistedPageSignatureOwners(action)[signature]
    }

    private fun rememberAcceptedPageSignature(action: BatchPageAction, records: JSONArray) {
        val signature = normalizedPageSignature(records) ?: return
        persistedPageSignatureOwners(action)[signature] = action.page
    }

'''
    s = replace_once(s, helper_anchor, helpers + helper_anchor, f'v041 helpers {path}')

    s = replace_once(
        s,
        '                .put("localRecordsPersistedThisSegment", batchLocalRecordsPersisted))\n',
        '''                .put("localRecordsPersistedThisSegment", batchLocalRecordsPersisted)
                .put("localAuditPagesScheduled", batchAuditPagesScheduled)
                .put("universityDiscoveryPagesScheduled", batchUniversityDiscoveryPagesScheduled))
''',
        f'v041 summary counters {path}'
    )

    path.write_text(s)

b = BUILD.read_text()
b = b.replace('versionCode = 10400', 'versionCode = 10410')
b = b.replace('versionName = "0.4.0"', 'versionName = "0.4.1"')
BUILD.write_text(b)

m = MANIFEST.read_text()
m = m.replace('android:label="Admission Collector v0.4.0 Local"', 'android:label="Admission Collector v0.4.1 Local"')
MANIFEST.write_text(m)

print('v0.4.1 completeness patch applied')
