from pathlib import Path

# Apply the already hardened v0.12 product patch.
base = Path('.github/scripts/patch_v0120_final.py')
ns = {'__name__': '__main__', '__file__': str(base)}
exec(compile(base.read_text(), str(base), 'exec'), ns, ns)

# v0.12 intentionally raises card height to make room for score/outcome/prediction/decision lines.
# Keep the existing responsive-layout regression test aligned with the new product contract.
test = Path('app/src/test/java/com/admissionhub/collector/hub/HubFirstLayoutPolicyTest.kt')
s = test.read_text()
old = 'assertEquals(164, HubFirstLayoutPolicy.cardHeightDp(1200))'
new = 'assertEquals(236, HubFirstLayoutPolicy.cardHeightDp(1200))'
if s.count(old) != 1:
    raise SystemExit(f'HubFirstLayoutPolicyTest height anchor count={s.count(old)}')
test.write_text(s.replace(old, new, 1))
print('v0.12 responsive layout test expectation updated')
