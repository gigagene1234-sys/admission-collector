from pathlib import Path

p = Path(__file__).resolve().parent / 'apply_v083_concurrent_slow_lane.py'
text = p.read_text()
start = text.find('# Add lifecycle cleanup before buildUi.')
end = text.find('MAIN.write_text(m)', start)
if start < 0 or end < 0:
    raise SystemExit('v0.8.3 lifecycle patch section not found')
replacement = """# Merge slow-lane cleanup into the existing lifecycle method.
m = once(m,
    '''    override fun onDestroy() {\n        handler.removeCallbacksAndMessages(null)\n''',
    '''    override fun onDestroy() {\n        if (::slowLanePool.isInitialized) slowLanePool.destroy()\n        handler.removeCallbacksAndMessages(null)\n''',
    'existing onDestroy slow lane cleanup'
)

"""
p.write_text(text[:start] + replacement + text[end:])
print('Changed v0.8.3 lifecycle patch to merge into existing onDestroy')
