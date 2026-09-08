from pathlib import Path

# MainActivity patches
p=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s=p.read_text()
s=s.replace('import com.admissionhub.collector.hub.HubDashboardModel\n', 'import com.admissionhub.collector.hub.HubDashboardModel\nimport com.admissionhub.collector.hub.AdmissionDashboardActivity\n', 1)
s=s.replace('private const val VERSION = "0.15.1"', 'private const val VERSION = "0.16.0"', 1)
s=s.replace('private const val BUILD_CODE = 115100', 'private const val BUILD_CODE = 116000', 1)

old='''        if (batchRunning && jinhakReauthCycles >= MAX_JINHAK_REAUTH_CYCLES) {'''
new='''        if ((batchRunning || unifiedRunning || jinhakTransitionAuthGateActive || startupLoginPreflightActive) && jinhakReauthCycles >= MAX_JINHAK_REAUTH_CYCLES) {'''
if old not in s: raise SystemExit('reauth anchor missing')
s=s.replace(old,new,1)

old='''        if (trigger != "ticker") runCatching { localStore.materializeSelectedPredictions(canonicalSession) }
        val scoreDecision = runCatching { localStore.scoreDecisionSummary(canonicalSession) }.getOrDefault(JSONObject())'''
new='''        if (trigger != "ticker") {
            // Official Adiga evidence must materialize independently from Jinhak login state.
            // The latest session can have thousands of official records while Jinhak is still on login.
            localStore.latestUnifiedSession()?.takeIf { it.isNotBlank() }?.let { latest ->
                runCatching { AdigaAutoScoreMaterializer.materializeSelected(localStore, latest) }
            }
            runCatching { localStore.materializeSelectedPredictions(canonicalSession) }
        }
        val scoreDecision = runCatching { localStore.scoreDecisionSummary(canonicalSession) }.getOrDefault(JSONObject())'''
if old not in s: raise SystemExit('dashboard materialize anchor missing')
s=s.replace(old,new,1)

old='''        hubAdvancedToggle = Button(this).apply { text = "고급 도구" }
        primaryActions.addView(hubAdvancedToggle, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))'''
new='''        val fullDashboardButton = Button(this).apply {
            text = "전체 대시보드"
            setOnClickListener { startActivity(Intent(this@MainActivity, AdmissionDashboardActivity::class.java)) }
        }
        primaryActions.addView(fullDashboardButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        hubAdvancedToggle = Button(this).apply { text = "고급 도구" }
        primaryActions.addView(hubAdvancedToggle, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))'''
if old not in s: raise SystemExit('dashboard button anchor missing')
s=s.replace(old,new,1)
p.write_text(s)

# UnifiedExcelScoreActivity: automatically accept structurally verified school exports.
p=Path('app/src/main/java/com/admissionhub/collector/score/UnifiedExcelScoreActivity.kt')
s=p.read_text()
old='''                recognized.maxWithOrNull(compareBy<JSONObject>(
                    { it.optInt("rowCount", 0) },
                    { it.optInt("gradedRows", 0) },
                    { if (it.optString("recognitionMode") == "wide-semester-columns") 1 else 0 }
                ))!!'''
new='''                recognized.maxWithOrNull(compareBy<JSONObject>(
                    { it.optInt("rowCount", 0) },
                    { it.optInt("gradedRows", 0) },
                    { if (it.optString("recognitionMode") == "wide-semester-columns") 1 else 0 }
                ))!!.also { chosen ->
                    val completeness = StudentScoreDocumentCompleteness.assess(chosen)
                    chosen.put("documentCompleteness", completeness)
                        .put("documentCompletenessVerified", completeness.optBoolean("verified", false))
                }'''
if old not in s: raise SystemExit('excel recognition anchor missing')
s=s.replace(old,new,1)
s=s.replace('''            isChecked = false
            root.addView(this)''','''            isChecked = profile.optBoolean("documentCompletenessVerified", false)
            isEnabled = !isChecked
            text = if (isChecked) "학교 Excel 구조에서 1-1~3-1 전체 학기 범위가 확인되었습니다." else "이 파일이 판단에 사용할 학생부 과목·학기를 빠짐없이 포함합니다."
            root.addView(this)''',1)
old='''        profile.put("sourceType", sourceFormat)
            .put("excelFileName", fileName.take(240))'''
new='''        profile.put("sourceType", sourceFormat)
            .put("documentCompleteness", source.optJSONObject("documentCompleteness") ?: JSONObject())
            .put("documentCompletenessVerified", source.optBoolean("documentCompletenessVerified", false))
            .put("excelFileName", fileName.take(240))'''
if old not in s: raise SystemExit('profile save anchor missing')
s=s.replace(old,new,1)
p.write_text(s)

# Score calculator accepts either explicit user confirmation or verified school-export structure.
p=Path('app/src/main/java/com/admissionhub/collector/score/OfficialUniversityScoreCalculator.kt')
s=p.read_text()
old='''        if (!profile.optBoolean("completeTranscriptConfirmedByUser", false)) return hold(base, "transcript-not-confirmed-complete", "가져온 과목·학기가 판단에 필요한 학생부 전체를 포함하는지 확인이 필요합니다.")'''
new='''        val transcriptComplete = profile.optBoolean("completeTranscriptConfirmedByUser", false) || profile.optBoolean("documentCompletenessVerified", false)
        if (!transcriptComplete) return hold(base, "transcript-not-confirmed-complete", "가져온 과목·학기가 판단에 필요한 학생부 전체를 포함하는지 확인이 필요합니다.")'''
if old not in s: raise SystemExit('score completeness anchor missing')
s=s.replace(old,new,1)
p.write_text(s)

# Manifest
p=Path('app/src/main/AndroidManifest.xml')
s=p.read_text()
s=s.replace('android:label="Admission Hub v0.15.1 Wide XLS + High3 Fence"','android:label="Admission Hub v0.16.0 Official Dashboard"',1)
anchor='''        <activity
            android:name=".score.UnifiedExcelScoreActivity"
            android:exported="false" />'''
insert='''        <activity
            android:name=".hub.AdmissionDashboardActivity"
            android:exported="false" />
        <activity
            android:name=".score.UnifiedExcelScoreActivity"
            android:exported="false" />'''
if anchor not in s: raise SystemExit('manifest activity anchor missing')
s=s.replace(anchor,insert,1)
p.write_text(s)

# Gradle version
p=Path('app/build.gradle.kts')
s=p.read_text().replace('versionCode = 115100','versionCode = 116000',1).replace('versionName = "0.15.1"','versionName = "0.16.0"',1)
p.write_text(s)
print('v0.16.0 product patch applied')
