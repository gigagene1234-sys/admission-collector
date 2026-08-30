from pathlib import Path

p = Path('app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt')
t = p.read_text()
lines = t.splitlines()
out = []
for line in lines:
    if '.replace(Regex("\\s+"), " ")' in line:
        line = line.replace('Regex("\\s+")', 'Regex("""\\s+""")')
    if 'Regex("^(?:지역인재교과|' in line:
        line = line.replace('Regex("', 'Regex("""', 1)
        if line.rstrip().endswith('"),'):
            idx = line.rfind('"),')
            line = line[:idx] + '"""),' + line[idx+3:]
    if 'val polluted = Regex("' in line and 'Regex("""' not in line:
        line = line.replace('Regex("', 'Regex("""', 1)
        idx = line.rfind('")')
        if idx >= 0:
            line = line[:idx] + '""")' + line[idx+2:]
    if 'val token = Regex("' in line and 'Regex("""' not in line:
        line = line.replace('Regex("', 'Regex("""', 1)
        idx = line.rfind('")')
        if idx >= 0:
            line = line[:idx] + '""")' + line[idx+2:]
    out.append(line)

fixed = '\n'.join(out) + ('\n' if t.endswith('\n') else '')
# Guard only exact illegal ordinary-string forms. Raw Kotlin strings intentionally begin Regex(""".
for bad in ['Regex("\\s+")', 'Regex("^(?:지역인재교과']:
    if bad in fixed:
        raise SystemExit(f'unfixed Kotlin regex literal: {bad}')
p.write_text(fixed)
print('v0.5.4 Kotlin regex literals fixed')
