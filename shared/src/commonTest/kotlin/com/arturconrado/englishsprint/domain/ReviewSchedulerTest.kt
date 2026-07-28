package com.arturconrado.englishsprint.domain

import kotlinx.datetime.Instant
import kotlin.test.Test
import kotlin.test.assertEquals

class ReviewSchedulerTest {
    @Test
    fun firstReviewIsScheduledAtPlus24Hours() {
        val review = ReviewScheduler.firstReview(
            missionId = "mission",
            skillId = "skill",
            correctionId = "correction",
            sourceAttemptId = "attempt",
            completedAt = Instant.parse("2026-07-28T18:00:00Z"),
            contentRetained = true,
        )
        assertEquals(Instant.parse("2026-07-29T18:00:00Z"), review.scheduledAt)
        assertEquals(ReviewType.TARGETED_CORRECTION, review.reviewType)
    }

    @Test
    fun reviewIsGenericWhenContentIsNotRetained() {
        val review = ReviewScheduler.firstReview(
            missionId = "mission",
            skillId = "skill",
            correctionId = "correction",
            sourceAttemptId = "attempt",
            completedAt = Instant.parse("2026-07-28T18:00:00Z"),
            contentRetained = false,
        )
        assertEquals(null, review.correctionId)
        assertEquals(ReviewType.GENERIC_SKILL, review.reviewType)
    }
}
