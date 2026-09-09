#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).with_name("patch_v0190_storage_monitor.py")
source = path.read_text()
old = "t = replace_once(t, diag_anchor, diag_new, 'v0190 diagnostics')"
new = """diag_count = t.count(diag_anchor)\nif diag_count < 1:\n    raise SystemExit('v0190 diagnostics: expected at least one match')\nt = t.replace(diag_anchor, diag_new)"""
if old not in source:
    raise SystemExit("v0.19.0 patch wrapper: diagnostics replacement line not found")
source = source.replace(old, new, 1)
namespace = {"__file__": str(path), "__name__": "__main__"}
exec(compile(source, str(path), "exec"), namespace, namespace)
