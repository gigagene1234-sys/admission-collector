from pathlib import Path

source = Path('.github/scripts/patch_v0923.py').read_text()
needle = "    'jinhak-login-recovery',\n"
if needle not in source:
    raise SystemExit('retry precondition failed: obsolete required-token line not found')
source = source.replace(needle, '', 1)
exec(compile(source, '.github/scripts/patch_v0923.py', 'exec'), {'__name__': '__main__'})
