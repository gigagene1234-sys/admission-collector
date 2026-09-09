from pathlib import Path

ORIGINAL = Path(__file__).with_name("patch_v0174.py").resolve()
source = ORIGINAL.read_text()
old = 'text = replace_once(text, diag_anchor, diag_new, "v0174 diagnostics")'
new = '''diag_count = text.count(diag_anchor)
if diag_count < 1:
    raise SystemExit("v0174 diagnostics anchor missing")
text = text.replace(diag_anchor, diag_new)'''
if old not in source:
    raise SystemExit("v0174 retry wrapper could not locate diagnostics replacement")
source = source.replace(old, new, 1)
namespace = {
    "__name__": "__main__",
    "__file__": str(ORIGINAL),
}
exec(compile(source, str(ORIGINAL), "exec"), namespace, namespace)
