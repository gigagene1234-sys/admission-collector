package com.admissionhub.collector.score

import com.admissionhub.collector.canonical.AdigaApplicationEvidenceAnalyzer
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/** Quantitative calculators encoded only for explicitly supported 2027 official formulas. */
object OfficialUniversityScoreCalculator {
    data class Course(
        val year: Int, val semester: Int, val group: String, val subject: String,
        val grade: Int?, val credits: Double?, val achievement: String,
        val achievementDistribution: JSONObject?
    )

    fun calculate(candidate: JSONObject, profile: JSONObject): JSONObject {
        val official = AdigaApplicationEvidenceAnalyzer.analyze(candidate)
        val year = candidate.optInt("academicYear", 0)
        val university = candidate.optString("university")
        val admission = candidate.optString("admission")
        val department = candidate.optString("department")
        val knownFormulaIdentity = isSupportedFormulaIdentity(year, university, admission)
        val evidenceSource = official.optJSONArray("universityCurrentEvidenceSample")?.optJSONObject(0)?.optString("sourcePage").orEmpty()
        val base = JSONObject()
            .put("academicYear", year).put("university", university).put("admission", admission).put("department", department)
            .put("formulaSource", evidenceSource.ifBlank { officialFormulaSource(year, university) })
            .put("currentComponentsVerified", official.optBoolean("currentComponentsVerified", false))
            .put("directCurrentBinding", official.optInt("currentApplicationBoundCount", 0) > 0)
            .put("formulaIdentityVerified", knownFormulaIdentity)
            .put("probabilityInferred", false)

        if (profile.optString("status") != "IMPORTED") return hold(base, "student-profile-not-imported", "학생부 과목 성적이 아직 가져와지지 않았습니다.")
        if (profile.optInt("academicYear", year) != year) return hold(base, "student-profile-year-mismatch", "학생부 프로필의 지원 학년도가 원서와 다릅니다.")
        val completeness = profile.optJSONObject("transcriptCompleteness") ?: TranscriptCompletenessPolicy.evaluate(profile)
        base.put("transcriptCompleteness", completeness)
        if (!completeness.optBoolean("acceptedForQuantitativeCalculation", false)) return hold(base, "transcript-not-confirmed-complete", "수시 반영 구간 1학년 1학기~3학년 1학기의 명시적 과목·학점 범위를 확인해야 합니다.")
        if (!official.optBoolean("currentComponentsVerified", false) && !knownFormulaIdentity) return hold(base, "official-components-not-verified", "지원년도 공식 전형과 모집단위를 각각 확인한 뒤 환산합니다.")
        val courses = parseCourses(profile)
        if (courses.isEmpty()) return hold(base, "no-course-rows", "환산에 사용할 과목이 없습니다.")

        return when {
            year == 2027 && university.contains("우송") && normalize(admission).contains("교과면접") -> woosong(base, courses, interview = true)
            year == 2027 && university.contains("우송") && normalize(admission).contains("교과중심") -> woosong(base, courses, interview = false)
            year == 2027 && university.contains("한밭") && (normalize(admission).contains("교과일반") || normalize(admission).contains("지역인재교과")) -> hanbat(base, courses, department)
            year == 2027 && university.contains("한국교통") && normalize(admission).contains("학생부종합2") -> hold(base, "holistic-not-quantitative", "학생부종합Ⅱ는 공식 서류 정성평가 전형으로 학생부 등급만으로 대학 환산점수를 계산하지 않습니다.", notApplicable = true)
            year == 2027 && university.contains("충남") && normalize(admission).contains("교과일반") -> cnu(base, courses)
            else -> hold(base, "unsupported-official-formula", "현재 자동 계산기가 검증한 대학·전형 산식 범위 밖입니다.")
        }
    }

    private fun isSupportedFormulaIdentity(year: Int, university: String, admission: String): Boolean {
        if (year != 2027) return false
        val a = normalize(admission)
        return (university.contains("우송") && (a.contains("교과면접") || a.contains("교과중심"))) ||
            (university.contains("한밭") && (a.contains("교과일반") || a.contains("지역인재교과"))) ||
            (university.contains("한국교통") && a.contains("학생부종합2")) ||
            (university.contains("충남") && a.contains("교과일반"))
    }

    private fun officialFormulaSource(year: Int, university: String): String = when {
        year == 2027 && university.contains("우송") -> "https://ent2.wsu.ac.kr/pass/susi02.php"
        year == 2027 && university.contains("한밭") -> "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr=2027&unvCd=0000039"
        year == 2027 && university.contains("한국교통") -> "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr=2027&unvCd=0000034"
        year == 2027 && university.contains("충남") -> "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr=2027&unvCd=0000029"
        else -> ""
    }

    private fun woosong(base: JSONObject, all: List<Course>, interview: Boolean): JSONObject {
        val graded = eligibleThroughThirdFirst(all).filter { it.grade != null && groupKey(it.group) != null }
        val korean = graded.filter { groupKey(it.group) == "국어" }.sortedBy { it.grade }
        val mathEnglish = graded.filter { groupKey(it.group) in setOf("수학", "영어") }.sortedBy { it.grade }
        val socialScience = graded.filter { groupKey(it.group) in setOf("사회", "과학") }.sortedBy { it.grade }
        val quota = if (interview) 1 else 2; val total = if (interview) 6 else 12
        if (korean.size < quota || mathEnglish.size < quota || socialScience.size < quota || graded.size < total) return hold(base, "woosong-required-course-count-missing", "우송대 반영 과목 수를 채우지 못했습니다.")
        val selected = mutableListOf<Course>()
        selected += korean.take(quota); selected += mathEnglish.filterNot { it in selected }.take(quota); selected += socialScience.filterNot { it in selected }.take(quota)
        selected += graded.filterNot { it in selected }.sortedBy { it.grade }.take(total - selected.size)
        if (selected.size != total) return hold(base, "woosong-selection-incomplete", "우송대 반영 과목 선택을 완료하지 못했습니다.")
        val avg = selected.mapNotNull { it.grade }.average()
        val career = eligibleThroughThirdFirst(all).filter { groupKey(it.group) in setOf("국어", "수학", "영어", "사회", "과학") && it.grade == null && it.achievement in setOf("A", "B", "C") }
        if (career.size < 2) return hold(base, "woosong-career-subjects-missing", "진로선택 가산점에 필요한 A/B/C 성취도 과목 2개가 확인되지 않습니다.")
        val careerBonus = 4.0 + career.map { achievementPoint(it.achievement) }.sortedDescending().take(2).sum()
        var creditBonus = 0.0; var creditTotal: Double? = null
        if (!interview) {
            val creditCourses = eligibleThroughThirdFirst(all).filter { groupKey(it.group) in setOf("국어", "영어", "수학") }
            if (creditCourses.any { it.credits == null }) return hold(base, "woosong-credit-total-unknown", "교과중심 이수단위 가산점 판정을 위한 학점이 필요합니다.")
            creditTotal = creditCourses.sumOf { it.credits ?: 0.0 }; creditBonus = if (creditTotal >= 50.0) 50.0 else 0.0
        }
        val score = if (interview) 720.0 - (avg - 1.0) * 20.0 - 10.0 + careerBonus else 900.0 - (avg - 1.0) * 20.0 - 60.0 + creditBonus + careerBonus
        val detail = JSONObject().put("formulaEvidence", if (interview) "2027 공식: 교과면접 6과목 평균등급·진로선택 가산점" else "2027 공식: 교과중심 12과목 평균등급·이수단위·진로선택 가산점")
            .put("selectedCourseCount", selected.size).put("selectedAverageGrade", avg).put("careerBonus", careerBonus).put("creditBonus", creditBonus)
            .put("creditTotalKoreanEnglishMath", creditTotal ?: JSONObject.NULL).put("selectedSubjects", JSONArray(selected.map { "${it.year}-${it.semester} ${it.group} ${it.subject} ${it.grade}" }))
        return verified(base, score, if (interview) 720.0 else 900.0, "우송대 2027 학생부 교과성적", if (interview) "official-2027-woosong-교과면접-v2" else "official-2027-woosong-교과중심-v2", detail)
    }

    private fun hanbat(base: JSONObject, all: List<Course>, department: String): JSONObject {
        val eligible = eligibleThroughThirdFirst(all).filter { groupKey(it.group) in setOf("국어", "영어", "수학", "사회", "과학") }
        val graded = eligible.filter { it.grade != null }
        fun scoreForGrade(g: Int): Double = when (g) { 1 -> 10.0; 2 -> 9.7; 3 -> 9.5; 4 -> 9.3; 5 -> 9.1; 6 -> 8.0; 7 -> 5.5; 8 -> 3.3; else -> 2.0 }
        fun groupAverage(key: String, count: Int): Double { val values = graded.filter { groupKey(it.group) == key }.map { scoreForGrade(it.grade!!) }.sortedDescending().take(count).toMutableList(); while (values.size < count) values += 2.0; return values.average() }
        val korean = groupAverage("국어", 3); val english = groupAverage("영어", 3); val math = groupAverage("수학", 3)
        val ss = graded.filter { groupKey(it.group) in setOf("사회", "과학") }.map { scoreForGrade(it.grade!!) }.sortedDescending().take(4).toMutableList().also { while (it.size < 4) it += 2.0 }.average()
        val weights = if (normalize(department).contains("자율전공학부")) doubleArrayOf(0.20, 0.25, 0.30, 0.25) else doubleArrayOf(0.20, 0.25, 0.35, 0.20)
        val generalA = korean * weights[0] + english * weights[1] + math * weights[2] + ss * weights[3]
        val careerScores = eligible.filter { it.grade == null && it.achievement in setOf("A", "B", "C") }.map { when (it.achievement) { "A" -> 10.0; "B" -> 9.5; else -> 9.1 } }.sortedDescending().take(3).toMutableList()
        while (careerScores.size < 3) careerScores += 9.1
        val careerB = careerScores.average(); val knownCredits = eligible.mapNotNull { it.credits }.sum(); val missingCredit = eligible.any { it.credits == null }
        val weightC = when { knownCredits >= 100.0 -> 1.1; missingCredit -> return hold(base, "hanbat-credit-weight-unknown", "한밭대 교과군 이수단위 가중치 판정을 위한 학점이 필요합니다."); else -> 1.0 }
        val score = (generalA * 40.0 + careerB * 5.0) * weightC
        val detail = JSONObject().put("formulaEvidence", "2027 공식: {(일반교과 평균등급점수 A×40)+(진로선택 평균등급점수 B×5)}×이수단위 가중치 C")
            .put("generalAverageScoreA", generalA).put("careerAverageScoreB", careerB).put("creditWeightC", weightC).put("knownEligibleCredits", knownCredits)
            .put("attendanceExcluded", true).put("attendanceMax", 50).put("fullStudentRecordTotalMaxWhenC11", 545)
        return verified(base, score, 495.0, "국립한밭대 2027 교과성적(출결 제외)", "official-2027-hanbat-student-record-v2", detail)
    }

    private fun cnu(base: JSONObject, all: List<Course>): JSONObject {
        val eligible = eligibleThroughThirdFirst(all).filter { cnuEligibleGroup(it.group) }
        if (eligible.isEmpty()) return hold(base, "cnu-no-eligible-courses", "충남대 반영 교과 과목을 확인하지 못했습니다.")
        if (eligible.any { it.credits == null }) return hold(base, "cnu-credit-missing", "충남대 교과성적 가중평균 계산을 위한 이수단위가 필요합니다.")
        var weighted = 0.0; var credits = 0.0
        val converted = JSONArray()
        for (course in eligible) {
            val convertedGrade = course.grade ?: when (course.achievement) {
                "A" -> 1
                "B" -> {
                    val d = course.achievementDistribution ?: return hold(base, "cnu-achievement-distribution-missing", "충남대 진로선택 B 성취도는 학교 학생분포(B+C)가 있어야 공식 변환등급을 계산할 수 있습니다.")
                    percentileGrade(d.optDouble("B", Double.NaN) + d.optDouble("C", Double.NaN)) ?: return hold(base, "cnu-achievement-distribution-invalid", "충남대 진로선택 성취도별 학생분포 값을 확인하세요.")
                }
                "C" -> {
                    val d = course.achievementDistribution ?: return hold(base, "cnu-achievement-distribution-missing", "충남대 진로선택 C 성취도는 학교 학생분포(C)가 있어야 공식 변환등급을 계산할 수 있습니다.")
                    percentileGrade(d.optDouble("C", Double.NaN)) ?: return hold(base, "cnu-achievement-distribution-invalid", "충남대 진로선택 성취도별 학생분포 값을 확인하세요.")
                }
                else -> continue
            }
            val points = 110.0 - convertedGrade * 10.0
            val credit = course.credits ?: continue
            weighted += points * credit; credits += credit
            converted.put(JSONObject().put("course", "${course.year}-${course.semester} ${course.subject}").put("rankGrade", convertedGrade).put("points", points).put("credits", credit))
        }
        if (credits <= 0.0) return hold(base, "cnu-no-weighted-credits", "충남대 환산에 사용할 이수단위가 없습니다.")
        val score = weighted / credits
        return verified(base, score, 100.0, "충남대 2027 학생부교과 교과성적", "official-adiga-2027-cnu-student-record-v1", JSONObject()
            .put("formulaEvidence", "2027 어디가: 반영교과 과목별 석차등급점수×이수단위 합 / 반영교과 전체 이수단위")
            .put("gradePointTable", "1=100,2=90,...,9=20").put("careerA", "1등급")
            .put("careerBC", "성취도별 누적 학생비율을 표준 석차등급 구간으로 변환").put("convertedCourses", converted).put("totalCredits", credits))
    }

    private fun percentileGrade(p: Double): Int? {
        if (!p.isFinite() || p !in 0.0..100.0) return null
        return when { p <= 4.0 -> 1; p <= 11.0 -> 2; p <= 23.0 -> 3; p <= 40.0 -> 4; p <= 60.0 -> 5; p <= 77.0 -> 6; p <= 89.0 -> 7; p <= 96.0 -> 8; else -> 9 }
    }

    private fun cnuEligibleGroup(raw: String): Boolean {
        val n = normalize(raw)
        if (listOf("체육", "예술", "교양").any { it in n }) return false
        return listOf("국어", "수학", "영어", "한국사", "사회", "역사", "도덕", "과학", "기술가정", "제2외국어", "한문").any { it in n }
    }

    private fun parseCourses(profile: JSONObject): List<Course> {
        val a = profile.optJSONArray("subjects") ?: return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val r = a.optJSONObject(i) ?: return@mapNotNull null
            val grade = if (r.has("grade") && !r.isNull("grade")) r.optDouble("grade").toInt().takeIf { it in 1..9 } else null
            val credits = if (r.has("credits") && !r.isNull("credits")) r.optDouble("credits").takeIf { it.isFinite() && it > 0 } else null
            Course(r.optInt("gradeYear"), r.optInt("semester"), r.optString("group"), r.optString("subject"), grade, credits,
                r.optString("achievement").uppercase(Locale.ROOT), r.optJSONObject("achievementDistribution"))
        }
    }

    private fun eligibleThroughThirdFirst(all: List<Course>) = all.filter { it.year in 1..2 || (it.year == 3 && it.semester == 1) }
    private fun achievementPoint(v: String): Double = when (v) { "A" -> 3.0; "B" -> 1.5; "C" -> 0.5; else -> 0.0 }
    private fun groupKey(raw: String): String? { val n = normalize(raw); return when { "국어" in n -> "국어"; "영어" in n -> "영어"; "수학" in n -> "수학"; "사회" in n || "역사" in n || "도덕" in n -> "사회"; "과학" in n -> "과학"; else -> null } }
    private fun normalize(v: String) = v.replace("Ⅰ", "1").replace("Ⅱ", "2").replace("ⅰ", "1").replace("ⅱ", "2").lowercase(Locale.ROOT).replace(Regex("[\\s·・ㆍ_\\-\\/\\[\\]\\(\\)]"), "")
    private fun verified(base: JSONObject, score: Double, max: Double, scale: String, version: String, detail: JSONObject): JSONObject = base
        .put("verified", true).put("status", "verified").put("scoreValue", score).put("maxScore", max).put("scoreScale", scale).put("comparisonDirection", "higher-is-better").put("formulaVersion", version).put("detail", detail)
    private fun hold(base: JSONObject, status: String, reason: String, notApplicable: Boolean = false): JSONObject = base
        .put("verified", false).put("status", status).put("scoreValue", JSONObject.NULL).put("maxScore", JSONObject.NULL).put("scoreScale", JSONObject.NULL).put("comparisonDirection", JSONObject.NULL)
        .put("formulaVersion", JSONObject.NULL).put("notApplicable", notApplicable).put("detail", JSONObject().put("reason", reason))
}
