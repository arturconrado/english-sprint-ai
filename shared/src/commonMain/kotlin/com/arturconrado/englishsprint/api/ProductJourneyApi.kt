package com.arturconrado.englishsprint.api

import com.arturconrado.englishsprint.generated.dto.BillingStatus
import com.arturconrado.englishsprint.generated.dto.ConsentSettings
import com.arturconrado.englishsprint.generated.dto.Diagnostic
import com.arturconrado.englishsprint.generated.dto.CreateSupportRequest
import com.arturconrado.englishsprint.generated.dto.DataRightRequest
import com.arturconrado.englishsprint.generated.dto.OnboardingProfile
import com.arturconrado.englishsprint.generated.dto.NotificationPreferences
import com.arturconrado.englishsprint.generated.dto.ReserveVoiceUsageRequest
import com.arturconrado.englishsprint.generated.dto.SprintPlan
import com.arturconrado.englishsprint.generated.dto.SupportRequest
import com.arturconrado.englishsprint.generated.dto.VoiceUsageReservation
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType

data class ProductConsents(
    val policyVersion: String,
    val pedagogicalProcessing: Boolean,
    val analytics: Boolean,
    val contentRetention: Boolean,
    val notifications: Boolean,
)

data class ProductOnboarding(
    val professionalGoal: String,
    val englishContext: String,
    val timezone: String,
)

data class ProductNotificationPreferences(
    val enabled: Boolean,
    val dailyReminder: Boolean,
    val reviewReminder: Boolean,
    val timezone: String,
    val reminderHourLocal: Int,
)

data class DiagnosticState(
    val diagnosticId: String,
    val status: String,
    val promotionalSeconds: Int,
    val usedSeconds: Int,
)

data class SprintDayState(
    val dayNumber: Int,
    val missionId: String,
    val scheduledFor: String,
    val status: String,
)

data class SprintState(
    val sprintId: String,
    val status: String,
    val days: List<SprintDayState>,
)

data class BillingAllowance(
    val accessMode: String,
    val status: String,
    val remainingSeconds: Int,
    val freeBetaSecondsRemaining: Int,
    val promotionalSecondsRemaining: Int,
)

data class VoiceAllowanceReservation(
    val reservationId: String,
    val reservedSeconds: Int,
    val source: String,
    val remainingSeconds: Int,
)

interface ProductJourneyApi {
    suspend fun revokeSessions(firebaseIdToken: String)

    suspend fun updateConsents(
        firebaseIdToken: String,
        consents: ProductConsents,
    ): ProductConsents

    suspend fun updateOnboarding(
        firebaseIdToken: String,
        onboarding: ProductOnboarding,
    ): ProductOnboarding

    suspend fun updateNotificationPreferences(
        firebaseIdToken: String,
        preferences: ProductNotificationPreferences,
    ): ProductNotificationPreferences

    suspend fun startDiagnostic(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): DiagnosticState

    suspend fun getDiagnostic(firebaseIdToken: String): DiagnosticState

    suspend fun createSprint(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): SprintState

    suspend fun currentSprint(firebaseIdToken: String): SprintState

    suspend fun billingStatus(firebaseIdToken: String): BillingAllowance

    suspend fun restoreBilling(firebaseIdToken: String, idempotencyKey: String): BillingAllowance

    suspend fun reserveVoiceUsage(
        firebaseIdToken: String,
        idempotencyKey: String,
        requestedSeconds: Int,
        purpose: String,
    ): VoiceAllowanceReservation

    suspend fun createSupportRequest(
        firebaseIdToken: String,
        idempotencyKey: String,
        category: String,
        description: String,
    ): String

    suspend fun requestAccountExport(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): String

    suspend fun downloadAccountExport(firebaseIdToken: String): String

    suspend fun requestAccountDeletion(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): String
}

class KtorProductJourneyApi(
    private val baseUrl: String,
    private val client: HttpClient,
) : ProductJourneyApi {
    override suspend fun revokeSessions(firebaseIdToken: String) {
        client.post("$baseUrl/v1/account/sessions/revoke") {
            authenticated(firebaseIdToken)
        }.checked()
    }

    override suspend fun updateConsents(
        firebaseIdToken: String,
        consents: ProductConsents,
    ): ProductConsents {
        val wire = client.put("$baseUrl/v1/consents") {
            authenticated(firebaseIdToken)
            contentType(ContentType.Application.Json)
            setBody(
                ConsentSettings(
                    policyVersion = consents.policyVersion,
                    pedagogicalProcessing = consents.pedagogicalProcessing,
                    analytics = consents.analytics,
                    contentRetention = consents.contentRetention,
                    notifications = consents.notifications,
                ),
            )
        }.checked().body<ConsentSettings>()
        return wire.domain()
    }

    override suspend fun updateOnboarding(
        firebaseIdToken: String,
        onboarding: ProductOnboarding,
    ): ProductOnboarding {
        val wire = client.put("$baseUrl/v1/onboarding") {
            authenticated(firebaseIdToken)
            contentType(ContentType.Application.Json)
            setBody(
                OnboardingProfile(
                    professionalGoal = checkNotNull(
                        OnboardingProfile.ProfessionalGoal.entries.firstOrNull {
                            it.value == onboarding.professionalGoal
                        },
                    ),
                    englishContext = checkNotNull(
                        OnboardingProfile.EnglishContext.entries.firstOrNull {
                            it.value == onboarding.englishContext
                        },
                    ),
                    timezone = onboarding.timezone,
                ),
            )
        }.checked().body<OnboardingProfile>()
        return wire.domain()
    }

    override suspend fun updateNotificationPreferences(
        firebaseIdToken: String,
        preferences: ProductNotificationPreferences,
    ): ProductNotificationPreferences {
        val wire = client.put("$baseUrl/v1/notification-preferences") {
            authenticated(firebaseIdToken)
            contentType(ContentType.Application.Json)
            setBody(
                NotificationPreferences(
                    enabled = preferences.enabled,
                    dailyReminder = preferences.dailyReminder,
                    reviewReminder = preferences.reviewReminder,
                    timezone = preferences.timezone,
                    reminderHourLocal = preferences.reminderHourLocal,
                ),
            )
        }.checked().body<NotificationPreferences>()
        return wire.domain()
    }

    override suspend fun startDiagnostic(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): DiagnosticState =
        client.post("$baseUrl/v1/diagnostics") {
            authenticated(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
        }.checked().body<Diagnostic>().domain()

    override suspend fun getDiagnostic(firebaseIdToken: String): DiagnosticState =
        client.get("$baseUrl/v1/diagnostics") {
            authenticated(firebaseIdToken)
        }.checked().body<Diagnostic>().domain()

    override suspend fun createSprint(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): SprintState =
        client.post("$baseUrl/v1/sprints") {
            authenticated(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
        }.checked().body<SprintPlan>().domain()

    override suspend fun currentSprint(firebaseIdToken: String): SprintState =
        client.get("$baseUrl/v1/sprints/current") {
            authenticated(firebaseIdToken)
        }.checked().body<SprintPlan>().domain()

    override suspend fun billingStatus(firebaseIdToken: String): BillingAllowance =
        client.get("$baseUrl/v1/billing/status") {
            authenticated(firebaseIdToken)
        }.checked().body<BillingStatus>().domain()

    override suspend fun restoreBilling(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): BillingAllowance =
        client.post("$baseUrl/v1/billing/restore") {
            authenticated(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
        }.checked().body<BillingStatus>().domain()

    override suspend fun reserveVoiceUsage(
        firebaseIdToken: String,
        idempotencyKey: String,
        requestedSeconds: Int,
        purpose: String,
    ): VoiceAllowanceReservation =
        client.post("$baseUrl/v1/billing/reservations") {
            authenticated(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
            contentType(ContentType.Application.Json)
            setBody(
                ReserveVoiceUsageRequest(
                    requestedSeconds = requestedSeconds,
                    purpose = checkNotNull(
                        ReserveVoiceUsageRequest.Purpose.entries.firstOrNull {
                            it.value == purpose
                        },
                    ),
                ),
            )
        }.checked().body<VoiceUsageReservation>().domain()

    override suspend fun createSupportRequest(
        firebaseIdToken: String,
        idempotencyKey: String,
        category: String,
        description: String,
    ): String =
        client.post("$baseUrl/v1/support/requests") {
            authenticated(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
            contentType(ContentType.Application.Json)
            setBody(
                CreateSupportRequest(
                    category = checkNotNull(
                        CreateSupportRequest.Category.entries.firstOrNull {
                            it.value == category
                        },
                    ),
                    description = description,
                ),
            )
        }.checked().body<SupportRequest>().status.value

    override suspend fun requestAccountExport(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): String =
        client.post("$baseUrl/v1/account/export") {
            authenticated(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
        }.checked().body<DataRightRequest>().status.value

    override suspend fun downloadAccountExport(firebaseIdToken: String): String =
        client.get("$baseUrl/v1/account/export/content") {
            authenticated(firebaseIdToken)
        }.checked().bodyAsText()

    override suspend fun requestAccountDeletion(
        firebaseIdToken: String,
        idempotencyKey: String,
    ): String =
        client.post("$baseUrl/v1/account/deletion") {
            authenticated(firebaseIdToken)
            header("Idempotency-Key", idempotencyKey)
        }.checked().body<DataRightRequest>().status.value

    private fun io.ktor.client.request.HttpRequestBuilder.authenticated(token: String) {
        header("Authorization", "Bearer $token")
    }

    private suspend fun HttpResponse.checked(): HttpResponse {
        if (status.value in 200..299) return this
        throw RealtimeApiException(
            statusCode = status.value,
            code = "product_transport_error",
            retryable = status.value == 409 || status.value >= 500,
        )
    }
}

private fun ConsentSettings.domain() = ProductConsents(
    policyVersion = policyVersion,
    pedagogicalProcessing = pedagogicalProcessing,
    analytics = analytics,
    contentRetention = contentRetention,
    notifications = notifications,
)

private fun OnboardingProfile.domain() = ProductOnboarding(
    professionalGoal = professionalGoal.value,
    englishContext = englishContext.value,
    timezone = timezone,
)

private fun NotificationPreferences.domain() = ProductNotificationPreferences(
    enabled = enabled,
    dailyReminder = dailyReminder,
    reviewReminder = reviewReminder,
    timezone = timezone,
    reminderHourLocal = reminderHourLocal ?: 19,
)

private fun Diagnostic.domain() = DiagnosticState(
    diagnosticId = diagnosticId,
    status = status.value,
    promotionalSeconds = promotionalSeconds.value,
    usedSeconds = usedSeconds,
)

private fun SprintPlan.domain() = SprintState(
    sprintId = sprintId,
    status = status.value,
    days = days.map {
        SprintDayState(
            dayNumber = it.day,
            missionId = it.missionId,
            scheduledFor = it.scheduledFor?.toString().orEmpty(),
            status = it.status.value,
        )
    },
)

private fun BillingStatus.domain() = BillingAllowance(
    accessMode = accessMode.value,
    status = subscriptionStatus.value,
    remainingSeconds = remainingSeconds,
    freeBetaSecondsRemaining = freeBetaSecondsRemaining,
    promotionalSecondsRemaining = promotionalSecondsRemaining,
)

private fun VoiceUsageReservation.domain() = VoiceAllowanceReservation(
    reservationId = reservationId,
    reservedSeconds = reservedSeconds,
    source = source.value,
    remainingSeconds = remainingSeconds,
)
