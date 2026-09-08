from pathlib import Path

path = Path('app/src/main/java/com/admissionhub/collector/score/UnifiedExcelScoreActivity.kt')
text = path.read_text()

replacements = [
    ('else -> error("실제 .xls 또는 .xlsx 형식이 아닙니다.")',
     'else -> throw IllegalArgumentException("실제 .xls 또는 .xlsx 형식이 아닙니다.")'),
    ('?: error("학년·학기·과목 열을 자동으로 확정하지 못했습니다. 고급 열 연결을 사용하면 직접 지정할 수 있습니다.")',
     '?: throw IllegalArgumentException("학년·학기·과목 열을 자동으로 확정하지 못했습니다. 고급 열 연결을 사용하면 직접 지정할 수 있습니다.")'),
    ('private fun error(message: String) = AlertDialog.Builder(this).setTitle("학생부 입력 확인").setMessage(message).setPositiveButton("확인", null).show()',
     'private fun showError(message: String) { AlertDialog.Builder(this).setTitle("학생부 입력 확인").setMessage(message).setPositiveButton("확인", null).show() }'),
]

for old, new in replacements:
    count = text.count(old)
    assert count == 1, f'expected one occurrence: {old[:80]} / found {count}'
    text = text.replace(old, new, 1)

# UI validation failures should return Unit, not AlertDialog.
text = text.replace('return error(', 'return showError(')
text = text.replace('.onFailure { error(', '.onFailure { showError(')
# Kotlin Android EditText exposes setSingleLine/isSingleLine; avoid synthetic singleLine property.
text = text.replace('singleLine = true', 'setSingleLine(true)')

assert 'return error(' not in text
assert '.onFailure { error(' not in text
assert 'singleLine = true' not in text
assert text.count('setSingleLine(true)') >= 2
assert 'private fun showError(message: String)' in text

path.write_text(text)
print('fixed UnifiedExcelScoreActivity compile errors')
