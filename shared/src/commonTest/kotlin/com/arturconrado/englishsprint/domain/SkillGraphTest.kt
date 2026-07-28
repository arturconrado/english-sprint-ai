package com.arturconrado.englishsprint.domain

import kotlin.test.Test
import kotlin.test.assertEquals

class SkillGraphTest {
    @Test
    fun fullModelCanOnlyProduceWithHelp() {
        val result = SkillGraph.promote(
            SkillState.UNKNOWN,
            evidence(AttemptKind.RETRY, HelpLevel.FULL_MODEL),
        )
        assertEquals(SkillState.PRODUCED_WITH_HELP, result)
    }

    @Test
    fun transferNeedsChangedQuestion() {
        val sameQuestion = SkillGraph.promote(
            SkillState.UNKNOWN,
            evidence(AttemptKind.TRANSFER, HelpLevel.NO_HELP),
        )
        val changedQuestion = SkillGraph.promote(
            SkillState.UNKNOWN,
            evidence(AttemptKind.TRANSFER, HelpLevel.NO_HELP, questionChanged = true),
        )
        assertEquals(SkillState.RECOGNIZED, sameQuestion)
        assertEquals(SkillState.TRANSFERRED, changedQuestion)
    }

    @Test
    fun failureNeverDowngrades() {
        val result = SkillGraph.promote(
            SkillState.TRANSFERRED,
            evidence(AttemptKind.FIRST, HelpLevel.NO_HELP, confidence = 0.2),
        )
        assertEquals(SkillState.TRANSFERRED, result)
    }

    private fun evidence(
        kind: AttemptKind,
        helpLevel: HelpLevel,
        confidence: Double = 0.9,
        questionChanged: Boolean = false,
    ) = SkillEvidence(
        evidenceId = "evidence",
        skillId = "skill",
        attemptId = "attempt",
        attemptKind = kind,
        evaluationValid = true,
        confidence = confidence,
        helpLevel = helpLevel,
        questionChanged = questionChanged,
    )
}
