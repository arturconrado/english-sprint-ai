package com.arturconrado.englishsprint.domain

enum class SkillState {
    UNKNOWN,
    RECOGNIZED,
    PRODUCED_WITH_HELP,
    PRODUCED_SPONTANEOUSLY,
    TRANSFERRED,
}

enum class AttemptKind {
    FIRST,
    RETRY,
    TRANSFER,
}

data class SkillEvidence(
    val evidenceId: String,
    val skillId: String,
    val attemptId: String,
    val attemptKind: AttemptKind,
    val evaluationValid: Boolean,
    val confidence: Double,
    val helpLevel: HelpLevel,
    val questionChanged: Boolean,
)

object SkillGraph {
    fun promote(current: SkillState, evidence: SkillEvidence): SkillState {
        val candidate = evidence.toState()
        return if (candidate.ordinal > current.ordinal) candidate else current
    }

    private fun SkillEvidence.toState(): SkillState {
        if (!evaluationValid || confidence < 0.70) return SkillState.UNKNOWN
        if (
            attemptKind == AttemptKind.TRANSFER &&
            questionChanged &&
            helpLevel != HelpLevel.FULL_MODEL
        ) {
            return SkillState.TRANSFERRED
        }
        if (
            attemptKind in setOf(AttemptKind.FIRST, AttemptKind.RETRY) &&
            helpLevel == HelpLevel.NO_HELP
        ) {
            return SkillState.PRODUCED_SPONTANEOUSLY
        }
        if (helpLevel != HelpLevel.NO_HELP) return SkillState.PRODUCED_WITH_HELP
        return SkillState.RECOGNIZED
    }
}
