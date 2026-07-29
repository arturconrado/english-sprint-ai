package com.arturconrado.englishsprint.api

import com.arturconrado.englishsprint.domain.AttemptKind
import com.arturconrado.englishsprint.domain.AttemptReceipt
import com.arturconrado.englishsprint.domain.CreatedMissionSession
import com.arturconrado.englishsprint.domain.DueReview
import com.arturconrado.englishsprint.domain.HelpLevel
import com.arturconrado.englishsprint.domain.Mission
import com.arturconrado.englishsprint.domain.MissionAttempt
import com.arturconrado.englishsprint.domain.MissionCommand
import com.arturconrado.englishsprint.domain.MissionSession
import com.arturconrado.englishsprint.domain.MissionSummary
import com.arturconrado.englishsprint.domain.ReviewType
import com.arturconrado.englishsprint.domain.SkillState
import com.arturconrado.englishsprint.domain.UserSkill
import com.arturconrado.englishsprint.generated.dto.AttemptKind as WireAttemptKind
import com.arturconrado.englishsprint.generated.dto.AttemptReceipt as WireAttemptReceipt
import com.arturconrado.englishsprint.generated.dto.CreateAttemptRequest
import com.arturconrado.englishsprint.generated.dto.CreateMissionSessionRequest
import com.arturconrado.englishsprint.generated.dto.HelpLevel as WireHelpLevel
import com.arturconrado.englishsprint.generated.dto.Mission as WireMission
import com.arturconrado.englishsprint.generated.dto.MissionCommand as WireMissionCommand
import com.arturconrado.englishsprint.generated.dto.MissionCommandRequest
import com.arturconrado.englishsprint.generated.dto.MissionSession as WireMissionSession
import com.arturconrado.englishsprint.generated.dto.MissionSummary as WireMissionSummary
import com.arturconrado.englishsprint.generated.dto.ReviewItem as WireReviewItem
import com.arturconrado.englishsprint.generated.dto.StateVersionRequest
import com.arturconrado.englishsprint.generated.dto.UserSkillState
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import kotlin.time.Instant

interface MissionApi {
    suspend fun listMissions(): List<Mission>

    suspend fun getMission(missionId: String): Mission

    suspend fun createSession(
        missionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
    ): CreatedMissionSession

    suspend fun getSession(sessionId: String, firebaseIdToken: String): MissionSession

    suspend fun createAttempt(
        sessionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
        attempt: MissionAttempt,
    ): AttemptReceipt

    suspend fun sendCommand(
        sessionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
        command: MissionCommand,
        stateVersion: Long,
    ): MissionSession

    suspend fun cancel(
        sessionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
    ): MissionSession

    suspend fun complete(
        sessionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
        stateVersion: Long,
    ): MissionSession

    suspend fun getSummary(sessionId: String, firebaseIdToken: String): MissionSummary

    suspend fun listSkills(firebaseIdToken: String): List<UserSkill>

    suspend fun listDueReviews(firebaseIdToken: String): List<DueReview>

    suspend fun completeReview(
        reviewId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
    )
}

class KtorMissionApi(
    private val baseUrl: String,
    private val client: HttpClient,
) : MissionApi {
    override suspend fun listMissions(): List<Mission> =
        client.get("$baseUrl/v1/missions").checked().body<List<WireMission>>().map { it.domain() }

    override suspend fun getMission(missionId: String): Mission =
        client.get("$baseUrl/v1/missions/$missionId").checked().body<WireMission>().domain()

    override suspend fun createSession(
        missionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
    ): CreatedMissionSession {
        val response = client.post("$baseUrl/v1/mission-sessions") {
            contentType(ContentType.Application.Json)
            bearer(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
            setBody(CreateMissionSessionRequest(missionId = missionId))
        }.checked()
        return CreatedMissionSession(response.body<WireMissionSession>().domain())
    }

    override suspend fun getSession(sessionId: String, firebaseIdToken: String): MissionSession =
        client.get("$baseUrl/v1/mission-sessions/$sessionId") {
            bearer(firebaseIdToken)
        }.checked().body<WireMissionSession>().domain()

    override suspend fun createAttempt(
        sessionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
        attempt: MissionAttempt,
    ): AttemptReceipt {
        val response = client.post("$baseUrl/v1/mission-sessions/$sessionId/attempts") {
            contentType(ContentType.Application.Json)
            bearer(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
            setBody(
                CreateAttemptRequest(
                    clientAttemptId = attempt.clientAttemptId,
                    stateVersion = attempt.stateVersion.toInt(),
                    kind = WireAttemptKind.valueOf(attempt.kind.name.lowercase()),
                    helpLevel = WireHelpLevel.valueOf(attempt.helpLevel.name),
                    startedAt = Instant.parse(attempt.startedAt),
                    completedAt = Instant.parse(attempt.completedAt),
                    usedTimeExtension = attempt.usedTimeExtension,
                ),
            )
        }.checked()
        return response.body<WireAttemptReceipt>().domain()
    }

    override suspend fun sendCommand(
        sessionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
        command: MissionCommand,
        stateVersion: Long,
    ): MissionSession {
        val response = client.post("$baseUrl/v1/mission-sessions/$sessionId/commands") {
            contentType(ContentType.Application.Json)
            bearer(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
            setBody(
                MissionCommandRequest(
                    command = checkNotNull(WireMissionCommand.decode(command.wireValue())),
                    stateVersion = stateVersion.toInt(),
                ),
            )
        }.checked()
        return response.body<WireMissionSession>().domain()
    }

    override suspend fun cancel(
        sessionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
    ): MissionSession =
        client.post("$baseUrl/v1/mission-sessions/$sessionId/cancel") {
            bearer(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
        }.checked().body<WireMissionSession>().domain()

    override suspend fun complete(
        sessionId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
        stateVersion: Long,
    ): MissionSession =
        client.post("$baseUrl/v1/mission-sessions/$sessionId/complete") {
            contentType(ContentType.Application.Json)
            bearer(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
            setBody(StateVersionRequest(stateVersion.toInt()))
        }.checked().body<WireMissionSession>().domain()

    override suspend fun getSummary(
        sessionId: String,
        firebaseIdToken: String,
    ): MissionSummary =
        client.get("$baseUrl/v1/mission-sessions/$sessionId/summary") {
            bearer(firebaseIdToken)
        }.checked().body<WireMissionSummary>().domain()

    override suspend fun listSkills(firebaseIdToken: String): List<UserSkill> =
        client.get("$baseUrl/v1/skills") {
            bearer(firebaseIdToken)
        }.checked().body<List<UserSkillState>>().map { it.domain() }

    override suspend fun listDueReviews(firebaseIdToken: String): List<DueReview> =
        client.get("$baseUrl/v1/reviews/due") {
            bearer(firebaseIdToken)
        }.checked().body<List<WireReviewItem>>().map { it.domain() }

    override suspend fun completeReview(
        reviewId: String,
        firebaseIdToken: String,
        idempotencyKey: String,
    ) {
        client.post("$baseUrl/v1/reviews/$reviewId/complete") {
            bearer(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
        }.checked()
    }

    private fun io.ktor.client.request.HttpRequestBuilder.bearer(token: String) {
        header("Authorization", "Bearer $token")
    }

    private suspend fun HttpResponse.checked(): HttpResponse {
        if (status.value in 200..299) return this
        throw RealtimeApiException(
            statusCode = status.value,
            code = "mission_transport_error",
            retryable = status == HttpStatusCode.Conflict || status.value >= 500,
        )
    }
}

private fun MissionCommand.wireValue(): String = when (this) {
    MissionCommand.RepeatPrompt -> "repeat_prompt"
    MissionCommand.NeedMoreTime -> "need_more_time"
    MissionCommand.RequestHelp -> "request_help"
    MissionCommand.Pause -> "pause"
    MissionCommand.Resume -> "resume"
    MissionCommand.StopResponse -> "stop_response"
    MissionCommand.Cancel -> "cancel"
    MissionCommand.Finish -> "finish"
}

private fun WireMission.domain() = Mission(
    id = id,
    slug = slug,
    version = version,
    title = title,
    description = description,
    scenario = scenario,
    initialQuestion = initialQuestion,
    transferQuestion = transferQuestion,
    targetSkills = targetSkills,
    expectedDurationMinutes = expectedDurationMinutes,
    difficulty = difficulty,
)

private fun WireMissionSession.domain() = MissionSession(
    sessionId = sessionId,
    missionId = missionId,
    missionVersion = missionVersion,
    state = state.value,
    stateVersion = stateVersion.toLong(),
    processingConsent = processingConsent,
    contentRetentionConsent = contentRetentionConsent,
    voiceSessionId = voiceSessionId,
    createdAt = createdAt.toString(),
    updatedAt = updatedAt.toString(),
    completedAt = completedAt?.toString(),
)

private fun WireAttemptReceipt.domain() = AttemptReceipt(
    attemptId = attemptId,
    state = state.value,
    stateVersion = stateVersion.toLong(),
    evaluationStatus = evaluationStatus.value,
)

private fun WireMissionSummary.domain() = MissionSummary(
    sessionId = sessionId,
    missionId = missionId,
    state = state.value,
    attemptCount = attemptCount,
    strength = strength,
    primaryCorrection = primaryCorrection,
    skillState = skillState?.let { SkillState.valueOf(it.value) },
    nextReviewAt = nextReviewAt?.toString(),
    contentRetained = contentRetained,
    evidenceAvailable = evidenceAvailable,
)

private fun UserSkillState.domain() = UserSkill(
    skillId = skillId,
    slug = slug,
    state = SkillState.valueOf(state.value),
    updatedAt = updatedAt.toString(),
)

private fun WireReviewItem.domain() = DueReview(
    reviewId = reviewId,
    missionId = missionId,
    skillId = skillId,
    reviewType = ReviewType.valueOf(reviewType.value.uppercase()),
    scheduledAt = scheduledAt.toString(),
    status = status.value,
)
