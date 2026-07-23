package com.arturconrado.englishsprint.api

import com.arturconrado.englishsprint.domain.RealtimeCallAnswer
import com.arturconrado.englishsprint.domain.VoiceSessionMetadata
import com.arturconrado.englishsprint.generated.dto.ProblemDetails
import com.arturconrado.englishsprint.generated.dto.VoiceSessionMetadata as GeneratedVoiceSessionMetadata
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType

interface RealtimeSessionApi {
    suspend fun createCall(
        sdpOffer: String,
        installationId: String,
        idempotencyKey: String,
    ): RealtimeCallAnswer

    suspend fun getCall(sessionId: String): VoiceSessionMetadata

    suspend fun deleteCall(
        sessionId: String,
        terminationReason: String = "user_finished",
    )
}

class RealtimeApiException(
    val statusCode: Int,
    val code: String,
    val retryable: Boolean,
) : RuntimeException(code)

class KtorRealtimeSessionApi(
    private val baseUrl: String,
    private val client: HttpClient,
) : RealtimeSessionApi {
    override suspend fun createCall(
        sdpOffer: String,
        installationId: String,
        idempotencyKey: String,
    ): RealtimeCallAnswer {
        val response = client.post("$baseUrl/v1/realtime/calls") {
            contentType(ContentType.parse("application/sdp"))
            header("X-Installation-Id", installationId)
            header("Idempotency-Key", idempotencyKey)
            setBody(sdpOffer)
        }
        ensureSuccess(response.status, response)
        val sessionId = requireNotNull(response.headers["X-Voice-Session-Id"]) {
            "Missing internal voice session identifier"
        }
        val location = requireNotNull(response.headers[HttpHeaders.Location]) {
            "Missing voice session location"
        }
        return RealtimeCallAnswer(
            sessionId = sessionId,
            location = location,
            sdpAnswer = response.bodyAsText(),
        )
    }

    override suspend fun getCall(sessionId: String): VoiceSessionMetadata {
        val response = client.get("$baseUrl/v1/realtime/calls/$sessionId")
        ensureSuccess(response.status, response)
        return response.body<GeneratedVoiceSessionMetadata>().toDomain()
    }

    override suspend fun deleteCall(sessionId: String, terminationReason: String) {
        val response = client.delete("$baseUrl/v1/realtime/calls/$sessionId") {
            header("X-Termination-Reason", terminationReason)
        }
        if (response.status != HttpStatusCode.NoContent) {
            ensureSuccess(response.status, response)
        }
    }

    private suspend fun ensureSuccess(
        status: HttpStatusCode,
        response: io.ktor.client.statement.HttpResponse,
    ) {
        if (status.value in 200..299) return
        val problem = runCatching { response.body<ProblemDetails>() }.getOrNull()
        throw RealtimeApiException(
            statusCode = status.value,
            code = problem?.code ?: "transport_error",
            retryable = problem?.retryable ?: (status.value >= 500),
        )
    }
}

internal fun GeneratedVoiceSessionMetadata.toDomain(): VoiceSessionMetadata =
    VoiceSessionMetadata(
        sessionId = sessionId,
        status = status.value,
        provider = provider,
        model = model,
        createdAt = createdAt.toString(),
        updatedAt = updatedAt.toString(),
        startedAt = startedAt?.toString(),
        endedAt = endedAt?.toString(),
        durationSeconds = durationSeconds,
        terminationReason = terminationReason?.value,
    )
