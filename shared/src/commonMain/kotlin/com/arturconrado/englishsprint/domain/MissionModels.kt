package com.arturconrado.englishsprint.domain

data class Mission(
    val id: String,
    val slug: String,
    val version: Int,
    val title: String,
    val description: String,
    val scenario: String,
    val initialQuestion: String,
    val transferQuestion: String,
    val targetSkills: List<String>,
    val expectedDurationMinutes: Int,
    val difficulty: String,
)

data class MissionSession(
    val sessionId: String,
    val missionId: String,
    val missionVersion: Int,
    val state: String,
    val stateVersion: Long,
    val processingConsent: Boolean,
    val contentRetentionConsent: Boolean,
    val voiceSessionId: String?,
    val createdAt: String,
    val updatedAt: String,
    val completedAt: String?,
)

data class CreatedMissionSession(
    val session: MissionSession,
    val bearerToken: String,
)

data class MissionAttempt(
    val clientAttemptId: String,
    val stateVersion: Long,
    val kind: AttemptKind,
    val helpLevel: HelpLevel,
    val startedAt: String,
    val completedAt: String,
    val usedTimeExtension: Boolean,
)

data class AttemptReceipt(
    val attemptId: String,
    val state: String,
    val stateVersion: Long,
    val evaluationStatus: String,
)

data class MissionSummary(
    val sessionId: String,
    val missionId: String,
    val state: String,
    val attemptCount: Int,
    val strength: String?,
    val primaryCorrection: String?,
    val skillState: SkillState?,
    val nextReviewAt: String?,
    val contentRetained: Boolean,
    val evidenceAvailable: Boolean,
)

data class UserSkill(
    val skillId: String,
    val slug: String,
    val state: SkillState,
    val updatedAt: String,
)

data class DueReview(
    val reviewId: String,
    val missionId: String,
    val skillId: String,
    val reviewType: ReviewType,
    val scheduledAt: String,
    val status: String,
)
