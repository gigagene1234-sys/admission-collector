from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1))


def replace_all(path: Path, old: str, new: str, minimum: int = 1) -> None:
    text = path.read_text()
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f"{path}: expected at least {minimum} matches, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new))


main = Path("app/src/main/java/com/admissionhub/collector/MainActivity.kt")
excel = Path("app/src/main/java/com/admissionhub/collector/score/UnifiedExcelScoreActivity.kt")
gradle = Path("app/build.gradle.kts")
manifest = Path("app/src/main/AndroidManifest.xml")

# 1) Actual school XLS support: strict columns + section labels + wide 1학기/2학기 blocks.
replace_once(
    excel,
    '''                val structural = KoreanTranscriptAutoRecognizer.recognizeBest(
                    workbook = workbook,
                    admissionYear = sessionId?.let { id -> store.loadCanonicalApplicationCandidates(id).optJSONObject(0)?.optInt("academicYear") }
                        ?.takeIf { it in 2000..2100 } ?: 2027,
                    fileName = fileName,
                    sourceType = sourceFormat
                )
                when {
                    strict == null && structural == null -> throw IllegalArgumentException(
                        "Excel 파일은 열렸지만 학년·학기·과목 구조를 안전하게 확정하지 못했습니다."
                    )
                    strict == null -> structural!!
                    structural == null -> strict
                    structural.optInt("rowCount", 0) > strict.optInt("rowCount", 0) -> structural
                    else -> strict
                }
''',
    '''                val importYear = sessionId?.let { id -> store.loadCanonicalApplicationCandidates(id).optJSONObject(0)?.optInt("academicYear") }
                    ?.takeIf { it in 2000..2100 } ?: 2027
                val structural = KoreanTranscriptAutoRecognizer.recognizeBest(
                    workbook = workbook,
                    admissionYear = importYear,
                    fileName = fileName,
                    sourceType = sourceFormat
                )
                val wideSemester = KoreanWideSemesterTranscriptRecognizer.recognizeBest(
                    workbook = workbook,
                    admissionYear = importYear,
                    fileName = fileName,
                    sourceType = sourceFormat
                )
                val recognized = listOfNotNull(strict, structural, wideSemester)
                if (recognized.isEmpty()) throw IllegalArgumentException(
                    "Excel 파일은 열렸지만 학생부 과목 구조를 안전하게 확정하지 못했습니다."
                )
                recognized.maxWithOrNull(compareBy<JSONObject>(
                    { it.optInt("rowCount", 0) },
                    { it.optInt("gradedRows", 0) },
                    { if (it.optString("recognitionMode") == "wide-semester-columns") 1 else 0 }
                ))!!
'''
)

replace_once(
    excel,
    'info("자동 인식 방식: $recognitionMode · 학년/학기는 파일에 명시된 열·병합·구간 표지만 사용하고 추정하지 않습니다.")',
    'info("자동 인식 방식: $recognitionMode · 학년/학기는 파일에 명시된 열·병합·구간 또는 1학기/2학기 열 머리글만 사용하고 추정하지 않습니다.")'
)

# 2) Jinhak: never leave the high3 product for high1/high2/high12 while auth/collection is active.
replace_once(
    main,
    'import com.admissionhub.collector.jinhak.JinhakAuthDomainPolicy\n',
    'import com.admissionhub.collector.jinhak.JinhakAuthDomainPolicy\nimport com.admissionhub.collector.jinhak.JinhakGradeRouteFence\n'
)
replace_once(
    main,
    '    private var jinhakExternalNavigationsBlocked = 0\n',
    '    private var jinhakExternalNavigationsBlocked = 0\n    private var jinhakLowerGradeNavigationsBlocked = 0\n'
)

replace_once(
    main,
    '''    private fun currentAdapter(): ProviderAdapter = ProviderRegistry.adapter(provider)
''',
    '''    private fun jinhakHigh3FenceActive(): Boolean = provider == ProviderId.JINHAK &&
        (unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive || jinhakRealAuthProbeActive)

    private fun currentAdapter(): ProviderAdapter = ProviderRegistry.adapter(provider)
'''
)

replace_once(
    main,
    '''            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (batchRunning && provider == ProviderId.JINHAK && target.isNotBlank() && !ProviderRegistry.adapter(ProviderId.JINHAK).accepts(target)) {
''',
    '''            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (target.isNotBlank() && jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                    jinhakLowerGradeNavigationsBlocked += 1
                    recordRuntimeEvent("jinhak-lower-grade-navigation-blocked", JSONObject()
                        .put("targetSafePath", runtimeSafePath(target))
                        .put("currentSafePath", runtimeSafePath(view.url.orEmpty()))
                        .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core())))
                    status.text = "진학사 고1·고2 화면 이동 차단 · 고3 세션을 그대로 유지합니다."
                    return true
                }
                if (batchRunning && provider == ProviderId.JINHAK && target.isNotBlank() && !ProviderRegistry.adapter(ProviderId.JINHAK).accepts(target)) {
'''
)

replace_once(
    main,
    '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                if (jinhakRealAuthProbeActive && provider == ProviderId.JINHAK) {
''',
    '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
                    jinhakLowerGradeNavigationsBlocked += 1
                    view.stopLoading()
                    recordRuntimeEvent("jinhak-lower-grade-redirect-stopped", JSONObject()
                        .put("targetSafePath", runtimeSafePath(url))
                        .put("high3CoreSafePath", runtimeSafePath(JinhakGradeRouteFence.protectedHigh3Core())))
                    status.text = "진학사 고1·고2 리다이렉트 차단 · 로그인 재시도 없이 고3 보호경로로 복귀합니다."
                    val high3 = JinhakGradeRouteFence.protectedHigh3Core()
                    if (high3.isNotBlank()) handler.postDelayed({
                        if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(webView.url.orEmpty())) {
                            webView.loadUrl(high3)
                        }
                    }, 80L)
                    return
                }
                if (jinhakRealAuthProbeActive && provider == ProviderId.JINHAK) {
'''
)

replace_once(
    main,
    '''                    private fun handoff(target: String): Boolean {
                        if (target.isBlank() || target == "about:blank") return false
                        if (batchRunning && provider == ProviderId.JINHAK &&
''',
    '''                    private fun handoff(target: String): Boolean {
                        if (target.isBlank() || target == "about:blank") return false
                        if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(target)) {
                            jinhakLowerGradeNavigationsBlocked += 1
                            recordRuntimeEvent("jinhak-popup-lower-grade-navigation-blocked", JSONObject()
                                .put("targetSafePath", runtimeSafePath(target)))
                            handler.post { destroyTransientPopup("lower-grade-blocked") }
                            return true
                        }
                        if (batchRunning && provider == ProviderId.JINHAK &&
'''
)

# Reset and export the new diagnostic counter. This makes a real-device export prove the fence fired.
replace_once(
    main,
    '        jinhakExternalNavigationsBlocked = 0\n\n        // v0.9.2:',
    '        jinhakExternalNavigationsBlocked = 0\n        jinhakLowerGradeNavigationsBlocked = 0\n\n        // v0.9.2:'
)
replace_all(
    main,
    '.put("externalNavigationsBlocked", jinhakExternalNavigationsBlocked)',
    '.put("externalNavigationsBlocked", jinhakExternalNavigationsBlocked)\n                        .put("lowerGradeNavigationsBlocked", jinhakLowerGradeNavigationsBlocked)',
    minimum=2
)

# v0.15.1 metadata.
replace_once(main, '        private const val VERSION = "0.15.0"\n        private const val BUILD_CODE = 115000\n',
                    '        private const val VERSION = "0.15.1"\n        private const val BUILD_CODE = 115100\n')
replace_once(gradle, '        versionCode = 115000\n        versionName = "0.15.0"\n',
                     '        versionCode = 115100\n        versionName = "0.15.1"\n')
replace_once(manifest, 'android:label="Admission Hub v0.15.0 Dual Auto"',
                       'android:label="Admission Hub v0.15.1 Wide XLS + High3 Fence"')

print("v0.15.1 patch applied")
