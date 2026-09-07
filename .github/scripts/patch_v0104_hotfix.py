from pathlib import Path

p = Path('.github/scripts/patch_v0104.py')
s = p.read_text()
old = '''# Replace the old rebuild function's direct latest-session lookup.
main = replace_once(
    main,
    ''' + "'''" + '''        val sessionId = localStore.latestUnifiedSession()
        if (sessionId.isNullOrBlank()) {
''' + "'''" + ''',
    ''' + "'''" + '''        val sessionId = canonicalHubSessionId()
        if (sessionId.isNullOrBlank()) {
''' + "'''" + ''',
    'rebuild uses reusable hub session'
)
'''
new = '''# Replace the old rebuild function's direct latest-session lookup, scoped to that function only.
_rebuild_start = main.index('    private fun rebuildCanonicalHubFromLatestSessionIfReady(trigger: String) {')
_rebuild_end = main.index('    private fun refreshHubState(', _rebuild_start)
_rebuild_section = main[_rebuild_start:_rebuild_end]
_old_lookup = "        val sessionId = localStore.latestUnifiedSession()\\n        if (sessionId.isNullOrBlank()) {\\n"
_new_lookup = "        val sessionId = canonicalHubSessionId()\\n        if (sessionId.isNullOrBlank()) {\\n"
if _rebuild_section.count(_old_lookup) != 1:
    raise SystemExit(f'rebuild uses reusable hub session: scoped match count={_rebuild_section.count(_old_lookup)}')
_rebuild_section = _rebuild_section.replace(_old_lookup, _new_lookup, 1)
main = main[:_rebuild_start] + _rebuild_section + main[_rebuild_end:]
'''
if old not in s:
    raise SystemExit('expected v0.10.4 unscoped lookup patch block not found')
p.write_text(s.replace(old, new, 1))
print('v0.10.4 patch helper scoped lookup hotfix applied')
