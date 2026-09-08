package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

/** Strict, local-only transcript import. No slot IDs, credentials or arbitrary JSON are retained. */
object StudentScoreImport {
    const val TEMPLATE = "학년,학기,교과,과목,등급,학점,성취도\n"
    fun parse(text: String, admissionYear: Int, complete: Boolean): JSONObject {
        require(admissionYear in 2000..2100) { "지원 학년도를 확인하세요." }
        require(text.length <= 1_000_000) { "성적 파일은 1MB 이하로 가져오세요." }
        val clean = text.removePrefix("\uFEFF").trim()
        require(clean.isNotEmpty()) { "과목별 성적을 입력하세요." }
        val rows = if (clean.startsWith("{")) {
            val j = JSONObject(clean)
            require(!j.has("academicYear") || j.getInt("academicYear") == admissionYear) { "성적 파일의 지원 학년도가 다릅니다." }
            j.getJSONArray("subjects")
        } else {
            val delimiter = if (clean.substringBefore('\n').contains('\t')) '\t' else ','
            val lines = csv(clean, delimiter)
            val aliases = mapOf("학년" to "gradeYear", "학기" to "semester", "교과" to "group", "과목" to "subject", "등급" to "grade", "학점" to "credits", "이수단위" to "credits", "성취도" to "achievement")
            val header = lines.first().map { aliases[it.trim()] ?: it.trim() }
            require(header.toSet().size == header.size) { "중복된 열 이름이 있습니다." }
            require(header.containsAll(listOf("gradeYear", "semester", "subject"))) { "학년·학기·과목 열이 필요합니다. 화면의 양식을 사용하세요." }
            JSONArray().also { result -> lines.drop(1).filter { row -> row.any { it.isNotBlank() } }.forEachIndexed { i, row ->
                require(row.size == header.size) { "${i + 2}행의 열 수가 다릅니다." }
                result.put(JSONObject().also { out -> header.forEachIndexed { n, key -> out.put(key, row[n].trim()) } })
            } }
        }
        require(rows.length() in 1..1000) { "과목은 1~1000행이어야 합니다." }
        val normalized = JSONArray()
        val identities = mutableSetOf<String>()
        var weighted = 0.0; var totalCredits = 0.0; var graded = 0; var missingCredits = 0; var ungraded = 0
        for (i in 0 until rows.length()) {
            val r = rows.getJSONObject(i)
            val year = r.optString("gradeYear").toIntOrNull()
            val semester = r.optString("semester").toIntOrNull()
            val subject = r.optString("subject").trim()
            require(year != null && year in 1..3 && semester != null && semester in 1..2 && subject.isNotBlank() && subject.length <= 120) { "${i + 1}행의 학년·학기·과목을 확인하세요." }
            require(identities.add("$year|$semester|$subject")) { "${i + 1}행: 같은 학년·학기·과목이 중복됩니다." }
            fun number(key: String): Double? {
                val value = if (r.isNull(key)) "" else r.optString(key).trim()
                if (value.isBlank() || value in setOf("-", "미기재")) return null
                return value.toDoubleOrNull()?.takeIf { it.isFinite() } ?: error("${i + 1}행: $key 숫자를 확인하세요.")
            }
            val grade = number("grade"); val credits = number("credits")
            require(grade == null || (grade in 1.0..9.0 && grade % 1.0 == 0.0)) { "${i + 1}행: 석차등급은 1~9 정수 또는 빈칸입니다." }
            require(credits == null || credits > 0.0 && credits <= 30.0) { "${i + 1}행: 학점은 0보다 커야 합니다." }
            val achievement = if (r.isNull("achievement")) "" else r.optString("achievement").trim().uppercase()
            require(achievement in setOf("", "A", "B", "C", "D", "E", "P")) { "${i + 1}행: 성취도를 확인하세요." }
            if (grade == null) ungraded++ else { graded++; if (credits == null) missingCredits++ else { weighted += grade * credits; totalCredits += credits } }

            val out = JSONObject().put("gradeYear", year).put("semester", semester).put("group", r.optString("group").take(60))
                .put("subject", subject).put("grade", grade ?: JSONObject.NULL).put("credits", credits ?: JSONObject.NULL).put("achievement", achievement)
            val distribution = r.optJSONObject("achievementDistribution")
            if (distribution != null) {
                val safe = JSONObject()
                for (letter in listOf("A", "B", "C", "D", "E")) {
                    if (!distribution.has(letter) || distribution.isNull(letter)) continue
                    val value = distribution.optDouble(letter, Double.NaN)
                    require(value.isFinite() && value in 0.0..100.0) { "${i + 1}행: 성취도별 분포 $letter 값을 확인하세요." }
                    safe.put(letter, value)
                }
                if (safe.length() > 0) out.put("achievementDistribution", safe)
            }
            normalized.put(out)
        }
        val payload = JSONObject().put("academicYear", admissionYear).put("subjects", normalized).put("completeTranscriptConfirmedByUser", complete)
        return payload.put("fingerprint", fingerprint(payload.toString())).put("status", "IMPORTED")
            .put("rowCount", normalized.length()).put("gradedRows", graded).put("ungradedRows", ungraded).put("missingCreditRows", missingCredits)
            .put("ownWeightedGrade", if (missingCredits == 0 && totalCredits > 0) weighted / totalCredits else JSONObject.NULL)
            .put("ownGradeLabel", "입력된 석차등급 과목의 학점 가중평균 · 대학 환산과 별도")
    }
    fun fingerprint(text: String): String = MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    private fun csv(text: String, delimiter: Char): List<List<String>> {
        val result = mutableListOf<List<String>>(); val row = mutableListOf<String>(); val field = StringBuilder(); var quoted = false; var i = 0
        fun endField() { row.add(field.toString()); field.setLength(0) }
        while (i < text.length) {
            val c = text[i]
            when {
                c == '"' && quoted && i + 1 < text.length && text[i + 1] == '"' -> { field.append('"'); i++ }
                c == '"' -> quoted = !quoted
                c == delimiter && !quoted -> endField()
                c == '\n' && !quoted -> { endField(); result.add(row.toList()); row.clear() }
                c == '\r' && !quoted -> Unit
                else -> field.append(c)
            }; i++
        }
        require(!quoted) { "닫히지 않은 따옴표가 있습니다." }
        endField(); result.add(row.toList()); return result
    }
}
