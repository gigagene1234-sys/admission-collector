from pathlib import Path

ROOT = Path('.')
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# ---- MainActivity: invalidate hard watchdog after soft recovery and bump version. ----
for p in MAIN_FILES:
    m = p.read_text()
    m = m.replace('private const val VERSION = "0.6.4"', 'private const val VERSION = "0.6.5"', 1)
    m = m.replace('private const val BUILD_CODE = 10640', 'private const val BUILD_CODE = 10650', 1)

    old_soft = '''                    status.text = "진학사 로딩 지연 복구: 렌더된 DOM을 수집하고 다음 페이지로 진행합니다."\n                    batchNavigationWatchdogRecovery = true\n                    runCatching { webView.stopLoading() }\n'''
    new_soft = '''                    status.text = "진학사 로딩 지연 복구: 렌더된 DOM을 수집하고 다음 페이지로 진행합니다."\n                    // The 24s hard timer belongs to the same stalled navigation. Once a\n                    // meaningful DOM is accepted at 12s, invalidate that hard timer so it\n                    // cannot race the snapshot parser and skip a valid page.\n                    ++jinhakStallWatchdogGeneration\n                    batchNavigationWatchdogRecovery = true\n                    runCatching { webView.stopLoading() }\n'''
    if old_soft not in m:
        raise SystemExit(f'v065 soft-watchdog anchor missing: {p}')
    m = m.replace(old_soft, new_soft, 1)
    p.write_text(m)

# ---- SnapshotScript: deep Jinhak parsing only on genuine report/prediction surfaces. ----
s = SNAP.read_text()
old_start = '''  var jinhakCards=[];\n  var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0,departmentBoundRoots:0,departmentContextRoots:0,departmentMissingRoots:0};\n  if(/(^|\\.)jinhak\\.com$/i.test(location.hostname)){\n'''
new_start = '''  var jinhakCards=[];\n  var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0,departmentBoundRoots:0,departmentContextRoots:0,departmentMissingRoots:0};\n  var isJinhakHost=/(^|\\.)jinhak\\.com$/i.test(location.hostname);\n  var jinhakBarSignals=(bodyText.match(/[0-9]{1,2}\\s*칸/g)||[]).length;\n  var jinhakDeepPage=isJinhakHost && (\n    /(?:storage|save|predict|prediction|sapplysample|admitreport|resultreport|score|calc|report)/i.test(location.href) ||\n    jinhakBarSignals>=2 ||\n    /(?:내\\s*순위|예상\\s*(?:합격선|컷)|모의지원자\\s*수|지원판정|합격안정성)/i.test(bodyText)\n  );\n  if(jinhakDeepPage){\n'''
if old_start not in s:
    raise SystemExit('v065 Jinhak deep-page anchor missing')
s = s.replace(old_start, new_start, 1)

old_metric_loop = '    for(var ji=0;ji<metricNodes.length&&roots.length<120;ji++){\n'
new_metric_loop = '    for(var ji=0;ji<metricNodes.length&&roots.length<120&&jinhakCardStats.metricSeeds<650;ji++){\n'
if old_metric_loop not in s:
    raise SystemExit('v065 metric-loop anchor missing')
s = s.replace(old_metric_loop, new_metric_loop, 1)

old_tables = '''  var tables=[];\n  var captureHiddenDetail=/(^|\\.)jinhak\\.com$/i.test(location.hostname) || /\\/(?:ucp\\/uvt\\/uni\\/univDetailSelection|uct\\/acd\\/ade\\/criteriaAndResultPopup)\\.do$/i.test(location.pathname);\n  var tableNodes=document.querySelectorAll('table,[role=table]');\n  for(var ti=0;ti<tableNodes.length && tables.length<120;ti++){\n    var table=tableNodes[ti];\n    if(!captureHiddenDetail && !visible(table)) continue;\n    var rows=[];\n    var trNodes=table.querySelectorAll('tr,[role=row]');\n    for(var ri=0;ri<trNodes.length && rows.length<250;ri++){\n'''
new_tables = '''  var tables=[];\n  var captureHiddenDetail=(isJinhakHost&&jinhakDeepPage) || /\\/(?:ucp\\/uvt\\/uni\\/univDetailSelection|uct\\/acd\\/ade\\/criteriaAndResultPopup)\\.do$/i.test(location.pathname);\n  var maxCapturedTables=(isJinhakHost&&!jinhakDeepPage)?24:120;\n  var maxCapturedRows=(isJinhakHost&&!jinhakDeepPage)?100:250;\n  var tableNodes=document.querySelectorAll('table,[role=table]');\n  for(var ti=0;ti<tableNodes.length && tables.length<maxCapturedTables;ti++){\n    var table=tableNodes[ti];\n    if(!captureHiddenDetail && !visible(table)) continue;\n    var rows=[];\n    var trNodes=table.querySelectorAll('tr,[role=row]');\n    for(var ri=0;ri<trNodes.length && rows.length<maxCapturedRows;ri++){\n'''
if old_tables not in s:
    raise SystemExit('v065 table-budget anchor missing')
s = s.replace(old_tables, new_tables, 1)

old_blocks = '''  var blocks=[];\n  var blockNodes=document.querySelectorAll('article,.card,.item,.result,.list-item,.tbl_row,[class*=result],[class*=admission],[class*=score],[class*=grade],[class*=competition],[class*=apply],dl,section');\n  for(var bi=0;bi<blockNodes.length && blocks.length<300;bi++){\n'''
new_blocks = '''  var blocks=[];\n  var maxCapturedBlocks=(isJinhakHost&&!jinhakDeepPage)?100:300;\n  var blockNodes=document.querySelectorAll('article,.card,.item,.result,.list-item,.tbl_row,[class*=result],[class*=admission],[class*=score],[class*=grade],[class*=competition],[class*=apply],dl,section');\n  for(var bi=0;bi<blockNodes.length && blocks.length<maxCapturedBlocks;bi++){\n'''
if old_blocks not in s:
    raise SystemExit('v065 block-budget anchor missing')
s = s.replace(old_blocks, new_blocks, 1)

# Navigation remains comprehensive enough for autonomous traversal, but cap pathological menus.
old_nav_loop = '  for(var li=0;li<linkNodes.length;li++){\n'
new_nav_loop = '  var maxNavigationScan=(isJinhakHost&&!jinhakDeepPage)?1800:5000;\n  for(var li=0;li<linkNodes.length&&li<maxNavigationScan;li++){\n'
if old_nav_loop not in s:
    raise SystemExit('v065 navigation scan anchor missing')
s = s.replace(old_nav_loop, new_nav_loop, 1)

# Expose only a boolean diagnostic marker; no extra raw content.
old_discovery = '    discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length},\n'
new_discovery = '    discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length,jinhakDeepPage:jinhakDeepPage},\n'
if old_discovery not in s:
    raise SystemExit('v065 discovery marker anchor missing')
s = s.replace(old_discovery, new_discovery, 1)
SNAP.write_text(s)

# Version metadata.
g = GRADLE.read_text().replace('versionCode = 10640', 'versionCode = 10650', 1).replace('versionName = "0.6.4"', 'versionName = "0.6.5"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text().replace('Admission Collector v0.6.4 Crash Guard and Stall Recovery', 'Admission Collector v0.6.5 Safe Jinhak Explorer', 1)
MANIFEST.write_text(mf)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirror mismatch after v0.6.5 patch')

print('v0.6.5 lightweight navigation snapshot + deep-report guard applied')
