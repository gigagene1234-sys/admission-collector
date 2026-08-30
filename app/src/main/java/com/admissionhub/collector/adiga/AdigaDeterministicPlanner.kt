package com.admissionhub.collector.adiga

import com.admissionhub.collector.parser.RecordUtils

enum class AdigaTaskType {
    UNIVERSITY_DETAIL,
    DEPARTMENTS,
    ADMISSIONS,
    CURRENT_CRITERIA,
    HISTORICAL_RESULTS
}

data class AdigaPlanTask(
    val taskId: String,
    val academicYear: Int,
    val universityCode: String,
    val taskType: AdigaTaskType,
    val url: String
)

object AdigaDeterministicPlanner {
    private const val DETAIL_PATH = "/ucp/uvt/uni/univDetailSelection.do"

    fun plan(academicYear: Int, universityCodes: Collection<String>): List<AdigaPlanTask> {
        require(academicYear in 2000..2100)
        return universityCodes
            .asSequence()
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .distinct()
            .sorted()
            .flatMap { code ->
                AdigaTaskType.entries.asSequence().map { type ->
                    val url = detailUrl(academicYear, code, type)
                    AdigaPlanTask(
                        taskId = RecordUtils.sha256("adiga|$academicYear|$code|${type.name}"),
                        academicYear = academicYear,
                        universityCode = code,
                        taskType = type,
                        url = url
                    )
                }
            }
            .toList()
    }

    fun detailUrl(academicYear: Int, universityCode: String, taskType: AdigaTaskType): String {
        val menuId = when (taskType) {
            AdigaTaskType.UNIVERSITY_DETAIL -> "PCUVTINF2000"
            AdigaTaskType.DEPARTMENTS -> "PCUVTINF2000"
            AdigaTaskType.ADMISSIONS -> "PCUVTINF2000"
            AdigaTaskType.CURRENT_CRITERIA -> "PCUVTINF2000"
            AdigaTaskType.HISTORICAL_RESULTS -> "PCUVTINF2000"
        }
        return "https://www.adiga.kr$DETAIL_PATH?menuId=$menuId&searchSyr=$academicYear&unvCd=${universityCode.trim()}"
    }
}
