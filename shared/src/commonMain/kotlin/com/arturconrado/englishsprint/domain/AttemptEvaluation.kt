package com.arturconrado.englishsprint.domain

data class CorrectionCandidate(
    val category: String,
    val original: String,
    val recommended: String,
    val explanation: String,
    val communicationImpact: Double,
    val recurrence: Double,
    val goalRelevance: Double,
    val confidence: Double,
    val retryFeasibility: Double,
) {
    val priority: Double
        get() =
            communicationImpact * 0.35 +
                recurrence * 0.20 +
                goalRelevance * 0.25 +
                confidence * 0.15 +
                retryFeasibility * 0.05

    val cause: String
        get() = category.substringBefore(".")
}

enum class HelpLevel {
    NO_HELP,
    FIRST_WORD,
    KEYWORDS,
    SHORT_MODEL,
    FULL_MODEL,
}

enum class RetryResult {
    NOT_ATTEMPTED,
    FAILED,
    PRODUCED_WITH_FULL_HELP,
    PRODUCED_WITH_PARTIAL_HELP,
    PRODUCED_SPONTANEOUSLY,
}

data class RetryPlan(
    val correctionId: String,
    val modelSentence: String,
    val maximumHelp: HelpLevel,
)

data class RetryEvidence(
    val attemptId: String,
    val correctionId: String,
    val helpLevel: HelpLevel,
    val result: RetryResult,
    val confidence: Double,
)
