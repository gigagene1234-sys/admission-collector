from pathlib import Path

helper = Path('.github/scripts/patch_v0120.py')
source = helper.read_text()
replacements = {
    "main = replace_once(main, render_anchor, render_extra, 'decision summary render')": "main = main",
    "main = replace_once(main, card_old, card_new, 'score card text')": "main = main",
    "main = replace_once(main, show_detail_anchor, show_detail_new, 'score card detail')": "main = main",
    "'decision-panel': 'hubDecisionSummary' in main and '검증 환산' in main,": "'decision-panel': 'hubDecisionSummary' in main,",
    "'score-card': '대학 환산: 미확인' in main and '공식 입결: 미확인' in main and '종합: 판정 보류' in main,": "'score-card': True,",
}
for old, new in replacements.items():
    if old not in source:
        raise SystemExit('missing helper token: ' + old[:100])
    source = source.replace(old, new, 1)

# Execute the core patch in this process. It writes all non-brittle product changes.
ns = {'__name__': '__main__', '__file__': str(helper)}
exec(compile(source, str(helper), 'exec'), ns, ns)

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
main = main_path.read_text()

# Score summary line before the legacy status mirror.
anchor = '        if (::sessionState.isInitialized) {'
if main.count(anchor) != 1:
    raise SystemExit(f'sessionState anchor count={main.count(anchor)}')
block = '''        if (::hubDecisionSummary.isInitialized) {
            val profile = model.optJSONObject("studentScoreProfile") ?: JSONObject()
            val profileText = if (profile.optString("status") == "IMPORTED") "성적 프로필 등록" else "성적 프로필 미등록"
            hubDecisionSummary.text = "$profileText · 검증 환산 ${summary.optInt("verifiedConversions", 0)}/6 · 공식 입결 ${summary.optInt("officialOutcomeAvailable", 0)}/6 · 비교 가능 ${summary.optInt("comparableDecisions", 0)}/6 · 판정보류 ${summary.optInt("decisionHolds", 0)} · 진학사 예측자료 ${summary.optInt("predictionCollected", 0)}/6"
        }
'''
main = main.replace(anchor, block + anchor, 1)

# Score/decision content on each card.
official_line = '                    val official = card.optString("qualityLabel", "데이터 품질 확인 필요")\n'
if main.count(official_line) != 1:
    raise SystemExit(f'official line count={main.count(official_line)}')
score_vars = '''                    val scoreDecision = card.optJSONObject("scoreDecision") ?: JSONObject()
                    val conversion = scoreDecision.optString("conversionLabel", "대학 환산: 미확인")
                    val officialOutcome = scoreDecision.optString("officialOutcomeLabel", "공식 입결: 미확인")
                    val prediction = scoreDecision.optString("predictionLabel", "진학사 예측: 미확인")
                    val decision = scoreDecision.optString("decisionLabel", "종합: 판정 보류")
'''
main = main.replace(official_line, official_line + score_vars, 1)
old_return = r'                    "${index + 1}. $university\n$department\n$subtitle\n\n$capacity\n$coverage\n$official"'
new_return = r'                    "${index + 1}. $university\n$department\n$subtitle\n\n$capacity · $coverage\n$official\n$conversion\n$officialOutcome\n$prediction\n$decision"'
if main.count(old_return) != 1:
    raise SystemExit(f'card return count={main.count(old_return)}')
main = main.replace(old_return, new_return, 1)

# Score/decision evidence in card details.
detail_anchor = '            val updated = card.optString("updatedAt")'
if main.count(detail_anchor) != 1:
    raise SystemExit(f'detail anchor count={main.count(detail_anchor)}')
detail = '''            val scoreDecision = card.optJSONObject("scoreDecision") ?: JSONObject()
            append("\\n[성적·판정]\\n")
            append(scoreDecision.optString("conversionLabel", "대학 환산: 미확인")).append('\\n')
            append(scoreDecision.optString("officialOutcomeLabel", "공식 입결: 미확인")).append('\\n')
            append(scoreDecision.optString("predictionLabel", "진학사 예측: 미확인")).append('\\n')
            append(scoreDecision.optString("decisionLabel", "종합: 판정 보류")).append('\\n')
            val evaluation = scoreDecision.optJSONObject("evaluation")
            if (evaluation != null) append("판정 코드: ").append(evaluation.optString("decisionCode", "UNKNOWN")).append('\\n')
'''
main = main.replace(detail_anchor, detail + detail_anchor, 1)
main_path.write_text(main)

required = [
    'private const val VERSION = "0.12.0"',
    'private const val BUILD_CODE = 112000',
    'hubDecisionSummary',
    'localStore.scoreDecisionSummary',
    '대학 환산: 미확인',
    '공식 입결: 미확인',
    '종합: 판정 보류',
]
missing = [token for token in required if token not in main]
if missing:
    raise SystemExit('final v0.12 MainActivity postcondition failed: ' + ', '.join(missing))
print('v0.12 final robust patch applied')
