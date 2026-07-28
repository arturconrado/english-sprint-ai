package com.arturconrado.englishsprint.domain

import kotlin.test.Test
import kotlin.test.assertEquals

class CorrectionRankerTest {
    @Test
    fun selectsTwoDistinctHighConfidenceCauses() {
        val selected = CorrectionRanker.select(
            listOf(
                candidate("grammar.verb_form", 0.95),
                candidate("grammar.article", 0.90),
                candidate("structure.missing_result", 0.90),
            ),
        )
        assertEquals(
            listOf("grammar.verb_form", "structure.missing_result"),
            selected.map { it.category },
        )
    }

    @Test
    fun lowConfidenceCandidateIsNotSelected() {
        assertEquals(emptyList(), CorrectionRanker.select(listOf(candidate("grammar.x", 0.5))))
    }

    private fun candidate(category: String, confidence: Double) = CorrectionCandidate(
        category = category,
        original = "original",
        recommended = "recommended",
        explanation = "explanation",
        communicationImpact = 0.9,
        recurrence = 0.8,
        goalRelevance = 0.9,
        confidence = confidence,
        retryFeasibility = 1.0,
    )
}
