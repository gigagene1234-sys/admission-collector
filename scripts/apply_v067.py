from pathlib import Path

ROOT = Path('.')
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
JINHAK = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# -----------------------------------------------------------------------------
# MainActivity: restore Jinhak to user-navigation/current-screen analysis.
# No site-wide autonomous traversal is permitted in v0.6.7.
# -----------------------------------------------------------------------------
for p in MAIN_FILES:
    m = p.read_text()
    m = m.replace('private const val VERSION = "0.6.6"', 'private const val VERSION = "0.6.7"', 1)
    m = m.replace('private const val BUILD_CODE = 10660', 'private const val BUILD_CODE = 10670', 1)

    pending_old = '''                if (unifiedRunning && unifiedPhase == "jinhak" && unifiedPendingJinhakStart && provider == ProviderId.JINHAK && !batchRunning) {\n                    unifiedPendingJinhakStart = false\n                    handler.postDelayed({\n                        if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()\n                    }, 450L)\n                    return\n                }\n'''
    pending_new = '''                if (unifiedRunning && unifiedPhase == "jinhak" && unifiedPendingJinhakStart && provider == ProviderId.JINHAK && !batchRunning) {\n                    unifiedPendingJinhakStart = false\n                    unifiedJinhakAutoCapture = true\n                    status.text = "통합 수집 2/2 · 진학사: 사용자가 직접 여는 입시 데이터 화면만 자동 분석·누적합니다."\n                    handler.postDelayed({\n                        if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) scheduleUnifiedJinhakAutoCapture(url)\n                    }, 450L)\n                    return\n                }\n'''
    if pending_old not in m:
        raise SystemExit(f'v067 pending Jinhak anchor missing: {p}')
    m = m.replace(pending_old, pending_new, 1)

    m = m.replace(
        'status.text = "이전 튕김/중단 감지: 진학사 완료 체크포인트를 건너뛰며 자동 탐색을 재개합니다."',
        'status.text = "이전 중단 감지: 진학사에서 사용자가 직접 여는 입시 화면의 자동 분석·누적을 재개합니다."',
        1
    )
    m = m.replace('batchButton.text = "진학사 자동 탐색 준비"', 'batchButton.text = "현재 진학사 화면 전체 분석·누적"', 1)
    m = m.replace(
        'status.text = "통합 수집 2/2 · 진학사 안전 자동 탐색 준비: 동일 도메인의 입시정보 링크를 스스로 순회합니다."',
        'status.text = "통합 수집 2/2 · 진학사 분석 대기: 원하는 수시저장소·추천대학·대학정보·리포트 화면을 직접 열면 자동 분석합니다."',
        1
    )
    m = m.replace('                collectCurrentPage()\n', '                collectCurrentPage(autoUnified = true)\n', 1)

    collect_marker = '    private fun collectCurrentPage() {\n'
    helper = '''    private fun isJinhakAutoCaptureRelevant(pageType: String): Boolean = pageType in setOf(\n        "jinhak-early-storage",\n        "jinhak-prediction-report",\n        "jinhak-mock-support-report",\n        "jinhak-actual-admit-report",\n        "jinhak-score-calc-report",\n        "jinhak-sat-minimum",\n        "jinhak-student-basic",\n        "jinhak-university-search",\n        "jinhak-recommended-university",\n        "jinhak-university-admission-info"\n    )\n\n    private fun collectCurrentPage(autoUnified: Boolean = false) {\n'''
    if collect_marker not in m:
        raise SystemExit(f'v067 collect marker missing: {p}')
    m = m.replace(collect_marker, helper, 1)

    snap_anchor = '''        collectSnapshot { snapshot ->\n            if (snapshot == null) return@collectSnapshot\n            val records = normalizeSnapshot(snapshot)\n'''
    snap_new = '''        collectSnapshot { snapshot ->\n            if (snapshot == null) return@collectSnapshot\n            val pageType = snapshot.optString("providerPageType")\n            if (provider == ProviderId.JINHAK && autoUnified && !isJinhakAutoCaptureRelevant(pageType)) {\n                recordRuntimeEvent("jinhak-nonadmission-page-skipped", JSONObject()\n                    .put("pageType", pageType.take(80))\n                    .put("safePath", runtimeSafePath(snapshot.optString("url"))))\n                status.text = "진학사 자동 분석 제외: 입시 데이터 화면이 아닌 ${pageType.ifBlank { "unclassified" }} 페이지입니다. 원하는 리포트/대학정보 화면을 여세요."\n                return@collectSnapshot\n            }\n            val records = normalizeSnapshot(snapshot)\n'''
    if snap_anchor not in m:
        raise SystemExit(f'v067 snapshot relevance anchor missing: {p}')
    m = m.replace(snap_anchor, snap_new, 1)

    digest_anchor = '''            .put("type", "jinhak-full-screen-analysis")\n            .put("pageType", snapshot.optString("providerPageType"))\n'''
    digest_new = '''            .put("type", "jinhak-full-screen-analysis")\n            .put("pageType", snapshot.optString("providerPageType"))\n            .put("analysisRelevance", if (isJinhakAutoCaptureRelevant(snapshot.optString("providerPageType"))) "admission-relevant" else "reference-or-editorial")\n'''
    if digest_anchor not in m:
        raise SystemExit(f'v067 digest anchor missing: {p}')
    m = m.replace(digest_anchor, digest_new, 1)

    p.write_text(m)

# -----------------------------------------------------------------------------
# JinhakAdapter: bounded current-screen analyzer + explicit page classification.
# -----------------------------------------------------------------------------
j = JINHAK.read_text()
j = j.replace('override val supportsBatchCrawl = true', 'override val supportsBatchCrawl = false', 1)

nav_start = j.index('    override fun isBatchNavigable(url: String): Boolean {')
nav_end = j.index('    override fun classify(snapshot: JSONObject): String {', nav_start)
j = j[:nav_start] + '    override fun isBatchNavigable(url: String): Boolean = false\n\n' + j[nav_end:]

heading_anchor = '''        }.replace(Regex("\\\\s+"), " ").trim()\n\n        // Global menus contain words such as 합격예측/수시저장소 on almost every page.\n'''
heading_new = '''        }.replace(Regex("\\\\s+"), " ").trim()\n        val pageTitle = snapshot.optString("title").replace(Regex("\\\\s+"), " ").trim()\n        val navigationError = Regex("^(?:302\\\\s+Found|404\\\\s+Not\\\\s+Found|500(?:\\\\s+Internal\\\\s+Server\\\\s+Error)?)$", RegexOption.IGNORE_CASE).matches(pageTitle)\n        val universityAdmissionInfo = Regex("^.{2,100}에 대한 모든 입시정보\\\\s*\\\\|\\\\s*대학정보\\\\s*\\\\|\\\\s*진학사$").containsMatchIn(pageTitle)\n        val editorialContent = Regex("(학과\\\\s*심층분석|대학\\\\s*심층분석|대학학과\\\\s*심층분석|지도로\\\\s*보는\\\\s*대학|대학교\\\\s*지도|캠퍼스맵)").containsMatchIn(pageTitle)\n\n        // Global menus contain words such as 합격예측/수시저장소 on almost every page.\n'''
if heading_anchor not in j:
    raise SystemExit('v067 classify heading anchor missing')
j = j.replace(heading_anchor, heading_new, 1)

when_anchor = '''        return when {\n            Regex("(login|signin|member/login)").containsMatchIn(url) || Regex("로그인.*비밀번호").containsMatchIn(headingText) -> "jinhak-login"\n            rootPage -> "jinhak-home"\n'''
when_new = '''        return when {\n            Regex("(login|signin|member/login)").containsMatchIn(url) || Regex("로그인.*비밀번호").containsMatchIn(headingText) -> "jinhak-login"\n            navigationError -> "jinhak-navigation-error"\n            universityAdmissionInfo -> "jinhak-university-admission-info"\n            editorialContent -> "jinhak-editorial-content"\n            rootPage -> "jinhak-home"\n'''
if when_anchor not in j:
    raise SystemExit('v067 classify when anchor missing')
j = j.replace(when_anchor, when_new, 1)

result_anchor = '''        val result = JSONArray()\n\n        if (pageType == "jinhak-early-storage") {\n'''
result_new = '''        val result = JSONArray()\n\n        if (pageType == "jinhak-university-admission-info") {\n            return normalizeUniversityAdmissionInfo(snapshot, observedAt)\n        }\n\n        if (pageType == "jinhak-early-storage" || pageType == "jinhak-recommended-university") {\n'''
if result_anchor not in j:
    raise SystemExit('v067 normalize page-type anchor missing')
j = j.replace(result_anchor, result_new, 1)

context_old = '''                val local = GenericAdmissionParser.inferContext(evidence)\n                val explicitUniversity = cleanStorageUniversity(cardObj?.optString("university"))\n                val explicitDepartment = cleanStorageDepartment(cardObj?.optString("department"))\n                val university = cleanStorageUniversity(local.university) ?: explicitUniversity\n                val department = cleanStorageDepartment(local.department) ?: explicitDepartment\n                val admission = cleanStorageAdmission(local.admission, evidence)\n'''
context_new = '''                val local = GenericAdmissionParser.inferContext(evidence)\n                val compact = if (pageType == "jinhak-recommended-university") compactRecommendationContext(evidence) else null\n                if (pageType == "jinhak-recommended-university" && compact == null) continue\n                val explicitUniversity = cleanStorageUniversity(cardObj?.optString("university"))\n                val explicitDepartment = cleanStorageDepartment(cardObj?.optString("department"))\n                val compactUniversity = cleanStorageUniversity(compact?.optString("university"))\n                val compactDepartment = cleanStorageDepartment(compact?.optString("department"))\n                val compactAdmission = compact?.optString("admission")?.takeIf { it.isNotBlank() }\n                val university = compactUniversity ?: cleanStorageUniversity(local.university) ?: explicitUniversity\n                val department = compactDepartment ?: cleanStorageDepartment(local.department) ?: explicitDepartment\n                val admission = compactAdmission ?: cleanStorageAdmission(local.admission, evidence)\n'''
if context_old not in j:
    raise SystemExit('v067 recommendation context anchor missing')
j = j.replace(context_old, context_new, 1)

metrics_anchor = '''                val cardMetrics = predictionMetrics(evidence)\n                val metricKeys = cardMetrics.keys().asSequence().filter { !cardMetrics.isNull(it) }.toList()\n'''
metrics_new = '''                val cardMetrics = predictionMetrics(evidence)\n                compact?.optString("admissionCategory")?.takeIf { it.isNotBlank() }?.let { cardMetrics.put("admissionCategory", it) }\n                compact?.optString("combinedAdmissionDepartmentLabel")?.takeIf { it.isNotBlank() }?.let { cardMetrics.put("combinedAdmissionDepartmentLabel", it) }\n                if (evidence.contains("수능최저")) cardMetrics.put("minimumRequirementDisplayed", true)\n                val metricKeys = cardMetrics.keys().asSequence().filter { !cardMetrics.isNull(it) }.toList()\n'''
if metrics_anchor not in j:
    raise SystemExit('v067 card metric anchor missing')
j = j.replace(metrics_anchor, metrics_new, 1)

context_source_anchor = '''                    .put("contextSource", when {\n                        local.university == null && explicitUniversity != null && local.department == null && explicitDepartment != null -> "scored-card-root+university+department-context"\n'''
context_source_new = '''                    .put("contextSource", when {\n                        compact != null -> "compact-recommendation-card"\n                        local.university == null && explicitUniversity != null && local.department == null && explicitDepartment != null -> "scored-card-root+university+department-context"\n'''
if context_source_anchor not in j:
    raise SystemExit('v067 context source anchor missing')
j = j.replace(context_source_anchor, context_source_new, 1)

skip_old = '''        if (pageType == "jinhak-home" || pageType == "jinhak-university-search" || pageType == "jinhak-curation" || pageType == "jinhak-other") {\n            return result\n        }\n'''
skip_new = '''        if (pageType == "jinhak-home" || pageType == "jinhak-university-search" || pageType == "jinhak-curation" ||\n            pageType == "jinhak-other" || pageType == "jinhak-editorial-content" || pageType == "jinhak-navigation-error") {\n            return result\n        }\n'''
if skip_old not in j:
    raise SystemExit('v067 skip-page anchor missing')
j = j.replace(skip_old, skip_new, 1)

scope_old = '''        "jinhak-actual-admit-report" -> "historical-result"\n        "jinhak-prediction-report", "jinhak-mock-support-report", "jinhak-recommended-university", "jinhak-early-storage" -> "current-prediction"\n'''
scope_new = '''        "jinhak-actual-admit-report", "jinhak-university-admission-info" -> "historical-result"\n        "jinhak-prediction-report", "jinhak-mock-support-report", "jinhak-recommended-university", "jinhak-early-storage" -> "current-prediction"\n'''
if scope_old not in j:
    raise SystemExit('v067 data-scope anchor missing')
j = j.replace(scope_old, scope_new, 1)

j = j.replace(
    'val short = Regex("""^[가-힣A-Za-z0-9·.()\\-]{2,24}대$""")',
    'val short = Regex("""^[가-힣A-Za-z0-9·.&+\\-]{2,24}대(?:\\([^)]+\\))?$""")',
    1
)

pred_start = j.index('    private fun predictionMetrics(text: String): JSONObject {')
pred_end = j.index('    private fun putNumber(obj: JSONObject, key: String, value: String?) {', pred_start)
new_helpers = r'''    private fun compactRecommendationContext(text: String): JSONObject? {
        val compact = text.replace(Regex("""\s+"""), " ").trim()
        val universityMatch = Regex("""^(?:[0-9]{1,2}\s*칸\s*)?([가-힣A-Za-z0-9·.&+\-]+(?:\([^)]+\))?)(?=\[)""").find(compact) ?: return null
        val university = universityMatch.groupValues.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() } ?: return null
        var tail = compact.substring(universityMatch.range.last + 1)
        val categoryMatch = Regex("""^\[([^\]]{1,20})\]""").find(tail)
        val category = categoryMatch?.groupValues?.getOrNull(1)?.trim()
        if (categoryMatch != null) tail = tail.substring(categoryMatch.range.last + 1)

        val combined = Regex("""^(.+?)(?=[0-9]{1,4}\s*명\s*내\s*점수)""").find(tail)
            ?.groupValues?.getOrNull(1)?.trim().orEmpty()
        if (combined.isBlank()) return null
        val admissionRegex = Regex("""^(지역인재교과|지역인재종합|교과일반|교과우수|교과중심|자기추천|창의인재\(면접형\)|교과면접|학교장추천|고른기회|기회균형|학생부교과|학생부종합|지역인재|자율전공|일반)""")
        val admissionMatch = admissionRegex.find(combined)
        val admission = admissionMatch?.groupValues?.getOrNull(1)?.trim()
        var department = if (admissionMatch != null) combined.substring(admissionMatch.range.last + 1) else combined
        department = department.replace(Regex("""^(?:\[[^\]]{1,30}\])+"""), "").trim()
        if (department.isBlank() || department.length > 100) return null

        return JSONObject()
            .put("university", university)
            .put("department", department)
            .put("admission", admission ?: JSONObject.NULL)
            .put("admissionCategory", category ?: JSONObject.NULL)
            .put("combinedAdmissionDepartmentLabel", combined)
    }

    private fun normalizeUniversityAdmissionInfo(snapshot: JSONObject, observedAt: String): JSONArray {
        val result = JSONArray()
        val title = snapshot.optString("title").replace(Regex("""\s+"""), " ").trim()
        val university = Regex("""^(.+?)에 대한 모든 입시정보\s*\|\s*대학정보\s*\|\s*진학사$""")
            .find(title)?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() } ?: return result
        val tables = snapshot.optJSONArray("tables") ?: return result

        for (ti in 0 until tables.length()) {
            val rows = tables.optJSONObject(ti)?.optJSONArray("rows") ?: continue
            if (rows.length() < 2) continue
            val header = rows.optJSONArray(0) ?: continue
            if (!header.optString(0).replace(" ", "").contains("전형/모집단위")) continue

            val yearColumns = mutableListOf<Pair<Int, Int>>()
            for (ci in 1 until header.length()) {
                val year = Regex("""(20[0-9]{2})\s*학년도""").find(header.optString(ci))
                    ?.groupValues?.getOrNull(1)?.toIntOrNull() ?: continue
                yearColumns += ci to year
            }
            if (yearColumns.isEmpty()) continue

            for (ri in 1 until rows.length()) {
                val row = rows.optJSONArray(ri) ?: continue
                val rowLabel = row.optString(0).replace(Regex("""\s+"""), " ").trim()
                if (rowLabel.isBlank()) continue
                val category = Regex("""^\[([^\]]{1,20})\]""").find(rowLabel)?.groupValues?.getOrNull(1)?.trim()

                for ((ci, year) in yearColumns) {
                    val rawValue = row.optString(ci).replace(Regex("""\s+"""), " ").trim()
                    if (rawValue.isBlank() || rawValue == "-") continue
                    val numeric = Regex("""-?[0-9]+(?:\.[0-9]+)?""").find(rawValue)?.value?.toDoubleOrNull()
                    val metrics = JSONObject()
                        .put("metricType", "competition")
                        .put("combinedAdmissionDepartmentLabel", rowLabel)
                        .put("admissionCategory", category ?: JSONObject.NULL)
                    if (numeric != null) metrics.put("competition", numeric) else metrics.put("rawValue", rawValue.take(120))

                    val record = JSONObject()
                        .put("recordType", "jinhak-historical-competition")
                        .put("providerPageType", "jinhak-university-admission-info")
                        .put("dataScope", "historical-result")
                        .put("year", year)
                        .put("university", university)
                        .put("department", JSONObject.NULL)
                        .put("admission", JSONObject.NULL)
                        .put("metrics", metrics)
                        .put("observedAt", observedAt)
                        .put("confidence", "medium")
                        .put("sourcePage", safePath(snapshot.optString("url")))
                        .put("rawEvidence", "$rowLabel | $year | $rawValue")
                    record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = false))
                    result.put(record)
                }
            }
        }
        return RecordUtils.dedupe(result)
    }

    private fun predictionMetrics(text: String): JSONObject {
        val metrics = JSONObject()
        putNumber(metrics, "universityCalculatedScore", Regex("(?:대학별\\s*)?(?:환산점수|산출점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        if (!metrics.has("universityCalculatedScore")) {
            putNumber(metrics, "universityCalculatedScore", Regex("내\\s*점수\\s*([0-9]+(?:\\.[0-9]+)?)\\s*점").find(text)?.groupValues?.getOrNull(1))
        }
        putNumber(metrics, "convertedGrade", Regex("(?:반영\\s*평균등급|환산등급|내\\s*등급)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "stabilityBars", Regex("(?<![0-9.])(?:합격안정성|칸수|칸\\s*수)?\\s*[:：]?\\s*([0-9]{1,2})\\s*칸").find(text)?.groupValues?.getOrNull(1))
        putNumber(metrics, "predictionProbability", Regex("(?:예상\\s*)?(?:합격률|합격확률|합격가능성)\\s*[:：]?\\s*([0-9]{1,3}(?:\\.[0-9]+)?)\\s*%").find(text)?.groupValues?.getOrNull(1))
        putText(metrics, "predictionLabel", Regex("(?:합격예측|합격가능성|지원판정|지원전략)?\\s*[:：]?\\s*(안정지원|안정|적정지원|적정|소신지원|소신|위험|상향|하향|불안)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "capacity", Regex("(?:모집인원|모집 인원)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        if (!metrics.has("capacity")) {
            putInt(metrics, "capacity", Regex("([0-9,]+)\\s*명\\s*내\\s*점수").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        }
        putInt(metrics, "mockApplicants", Regex("(?:모의지원자수|모의지원자 수|모의지원자)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putInt(metrics, "applicants", Regex("(?:현재\\s*)?(?:지원자수|지원자 수|실지원자수|실지원자 수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "mockCompetition", Regex("(?:모의지원\\s*)?경쟁률\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "myRank", Regex("(?:내\\s*순위|나의\\s*순위|현재\\s*순위)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        putNumber(metrics, "predictedCut", Regex("(?:예상\\s*합격선|예상\\s*컷|합격예상점수)\\s*[:：]?\\s*([0-9]+(?:\\.[0-9]+)?)").find(text)?.groupValues?.getOrNull(1))
        putInt(metrics, "additionalAdmits", Regex("(?:충원합격자수|충원합격자 수|충원인원|충원 인원|추가합격자수)\\s*[:：]?\\s*([0-9,]+)").find(text)?.groupValues?.getOrNull(1)?.replace(",", ""))
        return metrics
    }

'''
j = j[:pred_start] + new_helpers + j[pred_end:]
JINHAK.write_text(j)

# Version metadata.
g = GRADLE.read_text()
g = g.replace('versionCode = 10660', 'versionCode = 10670', 1)
g = g.replace('versionName = "0.6.6"', 'versionName = "0.6.7"', 1)
GRADLE.write_text(g)

man = MANIFEST.read_text()
man = man.replace(
    'Admission Collector v0.6.6 Memory-Safe Autonomous Explorer',
    'Admission Collector v0.6.7 Targeted Jinhak Analyzer',
    1
)
MANIFEST.write_text(man)

print('v0.6.7 patch applied')
