package com.admissionhub.collector.jinhak

/**
 * v0.8.5 mission-first scheduler.
 *
 * A saved-application identity owns the navigation mission until its available
 * report lanes have been attempted. Generic editorial/reference navigation is
 * deliberately lower priority than same-application report actions.
 */
object JinhakMissionLaneSequencer {
    private val laneOrder = listOf(
        "current-prediction",
        "mock-support",
        "actual-admit",
        "score-analysis",
        "university-result",
        "strategy"
    )

    data class Selection(
        val candidate: JinhakAgentNavigator.Candidate?,
        val missionExhaustedAtOrigin: Boolean = false,
        val requestedLane: String = "reference"
    )

    fun laneForLabel(label: String, kind: String = ""): String {
        val material = "$label $kind"
        return when {
            Regex("실제\\s*합격자|과거\\s*입시결과").containsMatchIn(material) -> "actual-admit"
            Regex("모의\\s*지원|지원자\\s*분포").containsMatchIn(material) -> "mock-support"
            Regex("합격\\s*예측|합격\\s*안정성").containsMatchIn(material) -> "current-prediction"
            Regex("성적\\s*분석|성적\\s*산출|환산\\s*점수").containsMatchIn(material) -> "score-analysis"
            Regex("대학\\s*정보|전형\\s*정보|학과\\s*정보|입시\\s*결과|경쟁률").containsMatchIn(material) -> "university-result"
            Regex("입시\\s*전략|입시\\s*지식").containsMatchIn(material) -> "strategy"
            else -> "reference"
        }
    }

    fun laneRank(lane: String): Int {
        val index = laneOrder.indexOf(lane)
        return if (index >= 0) index else laneOrder.size + 1
    }

    fun choose(
        candidates: List<JinhakAgentNavigator.Candidate>,
        currentMissionKey: String?,
        coveredLanes: Set<String>,
        atMissionOrigin: Boolean
    ): Selection {
        fun safeMissionLane(candidate: JinhakAgentNavigator.Candidate): String =
            laneForLabel(candidate.label, candidate.kind)

        fun sortedMission(input: List<JinhakAgentNavigator.Candidate>): List<JinhakAgentNavigator.Candidate> =
            input.sortedWith(
                compareBy<JinhakAgentNavigator.Candidate> { laneRank(safeMissionLane(it)) }
                    .thenByDescending { it.promotedMissionAction }
                    .thenByDescending { it.missionPriority }
                    .thenBy { it.scanIndex }
            )

        if (currentMissionKey != null) {
            val sameBound = candidates.filter { it.applicationContext?.identityKey == currentMissionKey }
            val inheritedReportControls = if (atMissionOrigin) {
                emptyList()
            } else {
                candidates.filter {
                    it.applicationContext?.identityKey == null && safeMissionLane(it) != "reference"
                }
            }
            val sameMissionPool = sameBound + inheritedReportControls
            val missing = sortedMission(sameMissionPool).firstOrNull {
                val lane = safeMissionLane(it)
                lane != "reference" && lane !in coveredLanes
            }
            if (missing != null) return Selection(missing, false, safeMissionLane(missing))

            // On a report page, return to the origin before declaring the mission exhausted.
            if (!atMissionOrigin) return Selection(null, false, "reference")

            // At the saved-application origin the current card has no unvisited report lane.
            // Promote another application card directly before generic/reference actions.
            val nextMission = sortedMission(candidates.filter {
                val key = it.applicationContext?.identityKey
                key != null && key != currentMissionKey && safeMissionLane(it) != "reference"
            }).firstOrNull()
            return Selection(nextMission, true, nextMission?.let { safeMissionLane(it) } ?: "reference")
        }

        val firstMission = sortedMission(candidates.filter {
            it.applicationContext?.identityKey != null && safeMissionLane(it) != "reference"
        }).firstOrNull()
        if (firstMission != null) return Selection(firstMission, false, safeMissionLane(firstMission))

        // No application mission is available. Only now allow generic read navigation.
        val generic = candidates.sortedWith(
            compareByDescending<JinhakAgentNavigator.Candidate> { it.missionPriority }
                .thenBy { it.scanIndex }
        ).firstOrNull()
        return Selection(generic, false, generic?.let { safeMissionLane(it) } ?: "reference")
    }
}
