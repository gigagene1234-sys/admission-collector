from pathlib import Path

PATHS = [
    Path('MainActivity.kt'),
    Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt'),
]

for path in PATHS:
    s = path.read_text()
    if 'private fun historicalMirrorUrl(url: String): String?' not in s:
        anchor = '''    private fun enqueueDiscoveredLinks(links: JSONArray) {
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = canonicalizeBatchUrl(obj.optString("url"))
            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            if (batchVisited.contains(url)) continue
            val runId = localRunId
            if (runId != null && localStore.isDocumentCompleted(runId, url)) continue
            if (batchQueued.add(url)) batchQueue.addLast(url)
            if (batchQueue.size + batchVisited.size >= MAX_BATCH_PAGES * 2) break
        }
    }
'''
        replacement = '''    private fun enqueueDiscoveredLinks(links: JSONArray) {
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = canonicalizeBatchUrl(obj.optString("url"))
            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            enqueueDiscoveredUrl(url)
            // One 2027 university-list pass is enough to discover university codes.
            // Mirror each 2027 university detail to 2026 so the same university's
            // 2025 actual-result section is collected without crawling the huge
            // duplicate 2026 department list.
            historicalMirrorUrl(url)?.let { mirror -> enqueueDiscoveredUrl(mirror) }
            if (batchQueue.size + batchVisited.size >= MAX_BATCH_PAGES * 2) break
        }
    }

    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (batchVisited.contains(url)) return
        val runId = localRunId
        if (runId != null && localStore.isDocumentCompleted(runId, url)) return
        if (batchQueued.add(url)) batchQueue.addLast(url)
    }

    private fun historicalMirrorUrl(url: String): String? {
        if (provider != ProviderId.ADIGA) return null
        return try {
            val uri = Uri.parse(url)
            if (uri.path != "/ucp/uvt/uni/univDetailSelection.do") return null
            if (uri.getQueryParameter("searchSyr") != "2027") return null
            val code = uri.getQueryParameter("unvCd")?.trim().orEmpty()
            if (!Regex("^0[0-9]{6}$").matches(code)) return null
            canonicalizeBatchUrl(withQueryParameter(url, "searchSyr", "2026"))
        } catch (_: Exception) { null }
    }
'''
        if anchor not in s:
            raise SystemExit(f'enqueueDiscoveredLinks anchor missing: {path}')
        s = s.replace(anchor, replacement, 1)
    path.write_text(s)

if PATHS[0].read_bytes() != PATHS[1].read_bytes():
    raise SystemExit('MainActivity copies diverged')

for path in PATHS:
    text = path.read_text()
    for needle in [
        'historicalMirrorUrl(url)?.let',
        'private fun historicalMirrorUrl(url: String): String?',
        'uri.getQueryParameter("searchSyr") != "2027"',
        'withQueryParameter(url, "searchSyr", "2026")',
    ]:
        if needle not in text:
            raise SystemExit(f'missing {needle!r} in {path}')

print('v0.4.0 2026 historical detail mirroring applied')
