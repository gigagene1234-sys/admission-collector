from pathlib import Path

p = Path(__file__).resolve().parent / 'apply_v084_report_context_bridge.py'
text = p.read_text()
old = '''a = once(a,
''' + "'''        val metrics = JinhakApplicationMission.semanticMetrics(text)\n'''" + ''',
''' + "'''        val metrics = JinhakReportYearGuard.annotate(\n            JinhakApplicationMission.semanticMetrics(text),\n            pageType,\n            inferredYear\n        )\n'''" + ", 'year guard metrics')"
new = '''metric_anchor = '        val metrics = JinhakApplicationMission.semanticMetrics(text)\\n'\nif metric_anchor not in a:\n    raise SystemExit('year guard metrics: anchor missing')\na = a.replace(metric_anchor, ''' + '"""' + '''        val metrics = JinhakReportYearGuard.annotate(\n            JinhakApplicationMission.semanticMetrics(text),\n            pageType,\n            inferredYear\n        )\n''' + '"""' + ''', 1)'''
if old not in text:
    raise SystemExit('old year guard metrics patch block not found')
p.write_text(text.replace(old, new, 1))
print('Adjusted v0.8.4 metric patch to the first generic report metrics anchor')
