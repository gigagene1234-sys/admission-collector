from pathlib import Path

p = Path(__file__).resolve().parent / 'apply_v083_concurrent_slow_lane.py'
text = p.read_text()
old = '''m = once(m,\n\'''        disarmBatchNavigationWatchdog()\n        webView.stopLoading()\n\''',\n\'''        disarmBatchNavigationWatchdog()\n        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("batch-stopped")\n        webView.stopLoading()\n\''', 'manual stop cancels slow lane')\n'''
new = '''m = once(m,\n\'''        batchCloudFinalCheckInProgress = false\n        disarmBatchNavigationWatchdog()\n        webView.stopLoading()\n        hideBatchCover()\n\''',\n\'''        batchCloudFinalCheckInProgress = false\n        disarmBatchNavigationWatchdog()\n        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("batch-stopped")\n        webView.stopLoading()\n        hideBatchCover()\n\''', 'manual stop cancels slow lane')\n'''
if old not in text:
    raise SystemExit('ambiguous stopBatch patch source anchor not found')
p.write_text(text.replace(old, new, 1))
print('Disambiguated v0.8.3 stopBatch patch anchor')
