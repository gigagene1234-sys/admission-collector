from pathlib import Path

p = Path(__file__).resolve().parent / 'apply_v083_concurrent_slow_lane.py'
text = p.read_text()
old = '''# Add lifecycle cleanup before buildUi.\nanchor = '    private fun buildUi() {\\n'\nif anchor not in m:\n    raise SystemExit('buildUi anchor missing')\nm = m.replace(anchor, '''    override fun onDestroy() {\n        if (::slowLanePool.isInitialized) slowLanePool.destroy()\n        super.onDestroy()\n    }\n\n''' + anchor, 1)\n'''
new = '''# Merge slow-lane cleanup into the existing lifecycle method.\nm = once(m,\n'''    override fun onDestroy() {\n        handler.removeCallbacksAndMessages(null)\n''',\n'''    override fun onDestroy() {\n        if (::slowLanePool.isInitialized) slowLanePool.destroy()\n        handler.removeCallbacksAndMessages(null)\n''', 'existing onDestroy slow lane cleanup')\n'''
if old not in text:
    raise SystemExit('old duplicate onDestroy patch section not found')
p.write_text(text.replace(old, new, 1))
print('Changed v0.8.3 lifecycle patch to merge into existing onDestroy')
