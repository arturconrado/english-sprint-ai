package com.arturconrado.englishsprint.domain

object CorrectionRanker {
    fun select(candidates: List<CorrectionCandidate>): List<CorrectionCandidate> {
        val ordered = candidates.sortedWith(
            compareByDescending<CorrectionCandidate> { it.priority }
                .thenBy { it.category }
                .thenBy { it.original },
        )
        val primary = ordered.firstOrNull {
            it.priority >= 0.55 && it.confidence >= 0.65
        } ?: return emptyList()
        val secondary = ordered.firstOrNull {
            it !== primary &&
                it.cause != primary.cause &&
                it.priority >= 0.70 &&
                it.confidence >= 0.75
        }
        return listOfNotNull(primary, secondary)
    }
}
