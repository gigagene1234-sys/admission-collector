from pathlib import Path

p = Path('scripts/apply_v083_mission_first.py')
s = p.read_text()
old = '''sync = replace_once(
    sync,
    '            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,',
    '            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\\n            UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED,\\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,',
    'auth transition consent state'
)
'''
new = '''auth_block = sync.index('        UnifiedSyncState.AUTH_REQUIRED to setOf(')
auth_tail = sync[auth_block:]
auth_tail = replace_once(
    auth_tail,
    '            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,',
    '            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,\\n            UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED,\\n            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,',
    'auth transition consent state'
)
sync = sync[:auth_block] + auth_tail
'''
if old not in s:
    raise SystemExit('ambiguous auth transition transformer block not found')
p.write_text(s.replace(old, new, 1))
print('Scoped v0.8.3 sync transformer to AUTH_REQUIRED block')
