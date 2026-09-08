package com.admissionhub.collector.score

import com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/**
 * Narrow 2027 calculators encoded from the official Adiga tables collected by this app.
 * A calculator runs only for the named university/track and only when the current official
 * admission and recruitment-unit components are both present. Unsupported inputs remain HOLD.
 */
object OfficialUniversityScoreCalculator {
    data class Course(
        val year: Int, val semester: Int, val group: String, val subject: String,
        val grade: Int?, val credits: Double?, val achievement: String
    )

    fun calculate(candidate: JSONObject, profile: JSONObject): JSONObject {
        val official = AdigaApplicationEvidenceAnalyzer.analyze(candidate)
        val year = candidate.optInt("academicYear", 0)
        val university = candidate.optString("university")
        val admission = candidate.optString("admission")
        val department = candidate.optString("department")
        val source = official.optJSONArray("universityCurrentEvidenceSample")?.optJSONObject(0)?.optString("sourcePage").orEmpty()
        val base = JSONObject()
            .put("academicYear", year)
            .put("university", university)
            .put("admission", admission)
            .put("department", department)
            .put("formulaSource", source)
            .put("currentComponentsVerified", official.optBoolean("currentComponentsVerified", false))
            .put("directCurrentBinding", official.optInt("currentApplicationBoundCount", 0) > 0)
            .put("probabilityInferred", false)

        if (profile.optString("status") != "IMPORTED") return hold(base, "student-profile-not-imported", "학생부 과목 성적이 아직 가져와지지 않았습니다.")
        if (profile.optInt("academicYear", year) != year) return hold(base, "student-profile-year-mismatch", "학생부 프로필의 지원 학년도가 원서와 다릅니다.")
        val structuralCompleteness = StudentScoreDocumentCompleteness.assess(profile)
        val transcriptComplete = profile.optBoolean("completeTranscriptConfirmedByUser", false) ||
            profile.optBoolean("documentCompletenessVerified", false) ||
            structuralCompleteness.optBoolean("verified", false)
        base.put("documentCompleteness", structuralCompleteness)
            .put("documentCompletenessVerifiedAtCalculation", structuralCompleteness.optBoolean("verified", false))
        if (!transcriptComplete) return hold(base, "transcript-not-confirmed-complete", "가져온 과목·학기가 판단에 필요한 학생부 전체를 포함하는지 확인이 필요합니다.")
        if (!official.optBoolean("currentComponentsVerified", false)) return hold(base, "official-components-not-verified", "지원년도 공식 전형과 모집단위를 각각 확인한 뒤 환산합니다.")
        val courses = parseCourses(profile)
        if (courses.isEmpty()) return hold(base, "no-course-rows", "환산에 사용할 과목이 없습니다.")

        return when {
            year == 2027 && university.contains("우송") && normalize(admission).contains("교과면접") -> woosong(base, courses, interview = true)
            year == 2027 && university.contains("우송") && normalize(admission).contains("교과중심") -> woosong(base, courses, interview = false)
            year == 2027 && university.contains("한밭") && (normalize(admission).contains("교과일반") || normalize(admission).contains("지역인재교과")) -> hanbat(base, courses, department)
            year == 2027 && university.contains("한국교통") && normalize(admission).contains("학생부종합2") -> hold(base, "holistic-not-quantitative", "학생부종합Ⅱ는 공식 서류 정성평가 전형으로 학생부 등급만으로 대학 환산점수를 계산하지 않습니다.", notApplicable = true)
            else -> hold(base, "unsupported-official-formula", "현재 자동 계산기가 검증한 대학·전형 산식 범위 밖입니다. 수집된 공식 산식은 근거 화면에서 확인할 수 있습니다.")
        }
    }

    private fun woosong(base: JSONObject, all: List<Course>, interview: Boolean): JSONObject {
        val graded = eligibleThroughThirdFirst(all).filter { it.grade != null && groupKey(it.group) != null }
        val korean = graded.filter { groupKey(it.group) == "국어" }.sortedBy { it.grade }
        val mathEnglish = graded.filter { groupKey(it.group) in setOf("수학", "영어") }.sortedBy { it.grade }
        val socialScience = graded.filter { groupKey(it.group) in setOf("사회", "과학") }.sortedBy { it.grade }
        val quota = if (interview) 1 else 2
        val total = if (interview) 6 else 12
        if (korean.size < quota || mathEnglish.size < quota || socialScience.size < quota || graded.size < total) {
            return hold(base, "woosong-required-course-count-missing", "우송대 반영 과목 수를 채우지 못했습니다. 국어 ${quota}과목, 수학·영어 ${quota}과목, 사회·과학 ${quota}과목과 총 ${total}과목이 필요합니다.")
        }
        val selected = mutableListOf<Course>()
        fun takeUnique(source: List<Course>, count: Int) {
            for (c in source) if (c !in selected && selected.size < total && selected.count { it in source } < count) selected += c
        }
        selected += korean.take(quota)
        selected += mathEnglish.filterNot { it in selected }.take(quota)
        selected += socialScience.filterNot { it in selected }.take(quota)
        selected += graded.filterNot { it in selected }.sortedBy { it.grade }.take(total - selected.size)
        if (selected.size != total) return hold(base, "woosong-selection-incomplete", "우송대 반영 과목 선택을 완료하지 못했습니다.")
        val avg = selected.mapNotNull { it.grade }.average()

        val career = eligibleThroughThirdFirst(all).filter { groupKey(it.group) in setOf("국어", "수학", "영어", "사회", "과학") && it.grade == null && it.achievement in setOf("A", "B", "C") }
        if (career.size < 2) return hold(base, "woosong-career-subjects-missing", "진로선택 가산점에 필요한 A/B/C 성취도 과목 2개가 확인되지 않습니다.")
        val careerPoints = career.map { achievementPoint(it.achievement) }.sortedDescending().take(2)
        val careerBonus = 4.0 + careerPoints.sum()

        var creditBonus = 0.0
        var creditTotal: Double? = null
        if (!interview) {
            val creditCourses = eligibleThroughThirdFirst(all).filter { groupKey(it.group) in setOf("국어", "영어", "수학") }
            if (creditCourses.any { it.credits == null }) return hold(base, "woosong-credit-total-unknown", "교과중심 이수단위 가산점 판정을 위해 국어·영어·수학 과목의 학점/이수단위가 모두 필요합니다.")
            creditTotal = creditCourses.sumOf { it.credits ?: 0.0 }
            creditBonus = if (creditTotal >= 50.0) 50.0 else 0.0
        }
        val score = if (interview) 720.0 - (avg - 1.0) * 20.0 - 10.0 + careerBonus
        else 900.0 - (avg - 1.0) * 20.0 - 60.0 + creditBonus + careerBonus
        val max = if (interview) 720.0 else 900.0
        val detail = JSONObject()
            .put("formulaEvidence", if (interview) "2027 어디가: 교과면접 교과성적 만점 720 - (6과목 평균등급-1)×20 - 10 + 진로선택 가산점" else "2027 어디가: 교과중심 교과성적 만점 900 - (12과목 평균등급-1)×20 - 60 + 이수단위·진로선택 가산점")
            .put("selectedCourseCount", selected.size)
            .put("selectedAverageGrade", avg)
            .put("careerBonus", careerBonus)
            .put("creditBonus", creditBonus)
            .put("creditTotalKoreanEnglishMath", creditTotal ?: JSONObject.NULL)
            .put("selectedSubjects", JSONArray(selected.map { "${it.year}-${it.semester} ${it.group} ${it.subject} ${it.grade}" }))
        return verified(base, score, max, "우송대 2027 학생부 교과성적", if (interview) "adiga-2027-woosong-교과면접-v1" else "adiga-2027-woosong-교과중심-v1", detail)
    }

    private fun hanbat(base: JSONObject, all: List<Course>, department: String): JSONObject {
        val eligible = eligibleThroughThirdFirst(all).filter { groupKey(it.group) in setOf("국어", "영어", "수학", "사회", "과학") }
        val graded = eligible.filter { it.grade != null }
        fun scoreForGrade(g: Int): Double = when (g) { 1 -> 10.0; 2 -> 9.7; 3 -> 9.5; 4 -> 9.3; 5 -> 9.1; 6 -> 8.0; 7 -> 5.5; 8 -> 3.3; else -> 2.0 }
        fun groupAverage(key: String, count: Int): Double {
            val values = graded.filter { groupKey(it.group) == key }.map { scoreForGrade(it.grade!!) }.sortedDescending().take(count).toMutableList()
            while (values.size < count) values += 2.0
            return values.average()
        }
        val korean = groupAverage("국어", 3)
        val english = groupAverage("영어", 3)
        val math = groupAverage("수학", 3)
        val ss = graded.filter { groupKey(it.group) in setOf("사회", "과학") }.map { scoreForGrade(it.grade!!) }.sortedDescending().take(4).toMutableList().also { while (it.size < 4) it += 2.0 }.average()
        val weights = if (normalize(department).contains("자율전공학부")) doubleArrayOf(0.20, 0.25, 0.30, 0.25) else doubleArrayOf(0.20, 0.25, 0.35, 0.20)
        val generalA = korean * weights[0] + english * weights[1] + math * weights[2] + ss * weights[3]

        val careerScores = eligible.filter { it.grade == null && it.achievement in setOf("A", "B", "C") }
            .map { when (it.achievement) { "A" -> 10.0; "B" -> 9.5; else -> 9.1 } }.sortedDescending().take(3).toMutableList()
        while (careerScores.size < 3) careerScores += 9.1
        val careerB = careerScores.average()

        val creditRows = eligible
        val knownCredits = creditRows.mapNotNull { it.credits }.sum()
        val missingCredit = creditRows.any { it.credits == null }
        val weightC = when {
            knownCredits >= 100.0 -> 1.1
            missingCredit -> return hold(base, "hanbat-credit-weight-unknown", "한밭대 교과(군) 이수단위 가중치 판정을 위해 국어·영어·수학·사회·과학 과목의 학점/이수단위가 필요합니다.")
            else -> 1.0
        }
        val score = (generalA * 40.0 + careerB * 5.0) * weightC
        val detail = JSONObject()
            .put("formulaEvidence", "2027 어디가: {(일반교과 평균등급점수 A×40)+(진로선택 평균등급점수 B×5)}×교과군 이수단위 가중치 C")
            .put("generalAverageScoreA", generalA)
            .put("careerAverageScoreB", careerB)
            .put("creditWeightC", weightC)
            .put("knownEligibleCredits", knownCredits)
            .put("groupWeights", JSONArray(listOf(weights[0], weights[1], weights[2], weights[3])))
            .put("attendanceExcluded", true)
            .put("attendanceMax", 50)
            .put("fullStudentRecordTotalMaxWhenC11", 545)
        return verified(base, score, 495.0, "국립한밭대 2027 교과성적(출결 제외)", "adiga-2027-hanbat-student-record-v1", detail)
    }

    private fun parseCourses(profile: JSONObject): List<Course> {
        val a = profile.optJSONArray("subjects") ?: return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val r = a.optJSONObject(i) ?: return@mapNotNull null
            val grade = if (r.has("grade") && !r.isNull("grade")) r.optDouble("grade").toInt().takeIf { it in 1..9 } else null
            val credits = if (r.has("credits") && !r.isNull("credits")) r.optDouble("credits").takeIf { it.isFinite() && it > 0 } else null
            Course(r.optInt("gradeYear"), r.optInt("semester"), r.optString("group"), r.optString("subject"), grade, credits, r.optString("achievement").uppercase(Locale.ROOT))
        }
    }

    private fun eligibleThroughThirdFirst(all: List<Course>) = all.filter { it.year in 1..2 || (it.year == 3 && it.semester == 1) }
    private fun achievementPoint(v: String): Double = when (v) { "A" -> 3.0; "B" -> 1.5; "C" -> 0.5; else -> 0.0 }
    private fun groupKey(raw: String): String? {
        val n = normalize(raw)
        return when {
            "국어" in n -> "국어"
            "영어" in n -> "영어"
            "수학" in n -> "수학"
            "사회" in n || "역사" in n || "도덕" in n -> "사회"
            "과학" in n -> "과학"
            else -> null
        }
    }
    private fun normalize(v: String) = v
        .replace("Ⅰ", "1").replace("Ⅱ", "2")
        .replace("ⅰ", "1").replace("ⅱ", "2")
        .lowercase(Locale.ROOT)
        .replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\)]"), "")

    private fun verified(base: JSONObject, score: Double, max: Double, scale: String, version: String, detail: JSONObject): JSONObject = base
        .put("verified", true).put("status", "verified").put("scoreValue", score).put("maxScore", max)
        .put("scoreScale", scale).put("comparisonDirection", "higher-is-better")
        .put("formulaVersion", version).put("detail", detail)

    private fun hold(base: JSONObject, status: String, reason: String, notApplicable: Boolean = false): JSONObject = base
        .put("verified", false).put("status", status).put("scoreValue", JSONObject.NULL).put("maxScore", JSONObject.NULL)
        .put("scoreScale", JSONObject.NULL).put("comparisonDirection", JSONObject.NULL)
        .put("formulaVersion", JSONObject.NULL).put("notApplicable", notApplicable)
        .put("detail", JSONObject().put("reason", reason))
}
