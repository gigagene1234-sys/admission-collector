from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt"
text = STORE.read_text()

old = '''                val reviewInput = review.getJSONObject("input")
                if (reviewInput.has("ownScore") && !reviewInput.isNull("ownScore")) row.put("conversionLabel", "대학 환산 입력: ${reviewInput.optDouble("ownScore")} · ${if (review.optBoolean("comparisonReady")) "사용자 근거 확인" else "확인 필요"}")
                if (reviewInput.has("referenceScore") && !reviewInput.isNull("referenceScore")) row.put("officialOutcomeLabel", "입결 입력: ${reviewInput.optInt("outcomeYear")} ${reviewInput.optString("metricName")} ${reviewInput.optDouble("referenceScore")}")'''
new = '''                val evaluatedReviewInput = review.getJSONObject("input")
                if (evaluatedReviewInput.has("ownScore") && !evaluatedReviewInput.isNull("ownScore")) row.put("conversionLabel", "대학 환산 입력: ${evaluatedReviewInput.optDouble("ownScore")} · ${if (review.optBoolean("comparisonReady")) "사용자 근거 확인" else "확인 필요"}")
                if (evaluatedReviewInput.has("referenceScore") && !evaluatedReviewInput.isNull("referenceScore")) row.put("officialOutcomeLabel", "입결 입력: ${evaluatedReviewInput.optInt("outcomeYear")} ${evaluatedReviewInput.optString("metricName")} ${evaluatedReviewInput.optDouble("referenceScore")}")'''

if new not in text:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"review-input-collision anchor count={count}")
    text = text.replace(old, new, 1)

STORE.write_text(text)
