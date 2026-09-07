package com.admissionhub.collector.sync

/**
 * Decides whether an interrupted browser collection should yield to a previously
 * complete, locally reusable canonical graph. No provider/session secret is involved.
 */
object LocalRebindPolicy {
    data class Input(
        val pinnedSlots: Int,
        val reusableCandidateCount: Int,
        val latestCandidateCount: Int,
        val latestStatus: String,
        val latestIsReusableSource: Boolean
    )

    fun preferLocalRebind(input: Input): Boolean =
        input.pinnedSlots == 6 && input.reusableCandidateCount >= 6

    fun suppressInterruptedBrowserResume(input: Input): Boolean {
        if (!preferLocalRebind(input)) return false
        val active = input.latestStatus.lowercase() in setOf("running", "jinhak", "adiga", "hub-publish")
        if (!active) return false
        // If the newest active session is itself a usable graph, preserve normal process-death resume.
        if (input.latestIsReusableSource && input.latestCandidateCount >= 6) return false
        return input.latestCandidateCount < 6 || !input.latestIsReusableSource
    }
}
