from pathlib import Path

p = Path(__file__).resolve().parent / 'apply_v082_application_mission.py'
text = p.read_text()
old = '''a = once(a, '        val metrics = JSONObject()\\n        putNumber(metrics, "universityCalculatedScore",',
'''        val metrics = JinhakApplicationMission.semanticMetrics(text)
        putNumber(metrics, "universityCalculatedScore",''', 'adapter report semantic metrics base')'''
new = '''_report_metrics_old = '        val metrics = JSONObject()\\n        putNumber(metrics, "universityCalculatedScore",'
_report_metrics_new = ''' + "'''" + '''        val metrics = JinhakApplicationMission.semanticMetrics(text)
        putNumber(metrics, "universityCalculatedScore",''' + "'''" + '''
if _report_metrics_old not in a:
    raise SystemExit('adapter report semantic metrics base: anchor not found')
a = a.replace(_report_metrics_old, _report_metrics_new, 1)'''
if old not in text:
    raise SystemExit('v0.8.2 apply-script anchor to fix not found')
p.write_text(text.replace(old, new, 1))
print('Fixed v0.8.2 ambiguous report metrics patch anchor')
