from pathlib import Path

p = Path(__file__).resolve().parent / 'apply_v083_concurrent_slow_lane.py'
text = p.read_text()
start = text.find('# Stop/cancel paths.')
end = text.find('# Diagnostics in sync-state payload.', start)
if start < 0 or end < 0:
    raise SystemExit('stop/cancel patch section not found')
replacement = r'''# Stop/cancel paths: modify each Kotlin function by scope to avoid ambiguous anchors.
def patch_kotlin_function(source: str, signature: str, old: str, new: str, label: str) -> str:
    start_idx = source.find(signature)
    if start_idx < 0:
        raise SystemExit(f'{label}: function signature missing')
    next_idx = source.find('\n    private fun ', start_idx + len(signature))
    if next_idx < 0:
        next_idx = len(source)
    block = source[start_idx:next_idx]
    if block.count(old) != 1:
        raise SystemExit(f'{label}: scoped anchor count={block.count(old)}')
    block = block.replace(old, new, 1)
    return source[:start_idx] + block + source[next_idx:]

m = patch_kotlin_function(
    m,
    '    private fun stopBatch(reason: String) {',
    '        disarmBatchNavigationWatchdog()\n',
    '        disarmBatchNavigationWatchdog()\n        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("batch-stopped")\n',
    'manual stop cancels slow lane'
)
m = patch_kotlin_function(
    m,
    '    private fun stopBatchForUnifiedFinish(reason: String) {',
    '        disarmBatchNavigationWatchdog()\n',
    '        disarmBatchNavigationWatchdog()\n        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("unified-finish")\n',
    'unified finish cancels slow lane'
)

'''
p.write_text(text[:start] + replacement + text[end:])
print('Rewrote v0.8.3 stop/cancel patching to function-scoped edits')
