from pathlib import Path

path = Path(__file__).with_name("apply_v038.py")
text = path.read_text()
old = '''    if reset_repl not in text:\n        text = replace_once(text, reset_marker, reset_repl, f"{path.name} final-check reset")\n'''
new = '''    if reset_repl not in text:\n        if reset_marker not in text:\n            raise SystemExit(f"{path.name}: final-check reset marker not found")\n        text = text.replace(reset_marker, reset_repl)\n'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("v0.3.8 reset patch block not found")
path.write_text(text)
print("v0.3.8 patch script prepared")
