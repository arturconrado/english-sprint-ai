package com.arturconrado.englishsprint.domain

import kotlinx.datetime.Instant
import kotlin.time.Duration.Companion.hours

enum class ReviewType {
    TARGETED_CORRECTION,
    GENERIC_SKILL,
}

data class ReviewPlan(
    val missionId: String,
    val skillId: String,
    val correctionId: String?,
    val sourceAttemptId: String,
    val reviewType: ReviewType,
    val scheduledAt: Instant,
)

object ReviewScheduler {
    fun firstReview(
        missionId: String,
        skillId: String,
        correctionId: String?,
        sourceAttemptId: String,
        completedAt: Instant,
        contentRetained: Boolean,
    ): ReviewPlan {
        val targeted = contentRetained && correctionId != null
        return ReviewPlan(
            missionId = missionId,
            skillId = skillId,
            correctionId = if (targeted) correctionId else null,
            sourceAttemptId = sourceAttemptId,
            reviewType =
                if (targeted) ReviewType.TARGETED_CORRECTION else ReviewType.GENERIC_SKILL,
            scheduledAt = completedAt + 24.hours,
        )
    }
}
