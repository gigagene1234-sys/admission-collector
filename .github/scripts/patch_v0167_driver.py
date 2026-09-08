from pathlib import Path

p = Path(__file__).with_name("patch_v0167.py")
src = p.read_text()
start_token = '''text = once(
    text,
    ''' + "'''" + '''        if (which == ProviderId.JINHAK) {
            installJinhakHigh3DomProductFence("credential-visual-only:$reason")'''
end_token = '\n\n# Replace the old recursive login recovery state machine'

# patch_v0167.py intentionally strips every UI-fence call before reaching this old exact-block
# cleanup. Remove that now-redundant cleanup stanza so the product patch is idempotent in ordering.
start = src.find(start_token)
if start >= 0:
    end = src.find(end_token, start)
    if end < 0:
        raise SystemExit("v0.16.7 driver: cleanup stanza end not found")
    src = src[:start] + src[end:]

compile(src, str(p), "exec")
ns = {"__file__": str(p), "__name__": "__main__"}
exec(compile(src, str(p), "exec"), ns, ns)
