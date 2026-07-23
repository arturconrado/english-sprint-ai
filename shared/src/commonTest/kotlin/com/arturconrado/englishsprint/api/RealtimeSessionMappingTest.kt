package com.arturconrado.englishsprint.api

import com.arturconrado.englishsprint.generated.dto.TerminationReason
import com.arturconrado.englishsprint.generated.dto.VoiceSessionMetadata
import com.arturconrado.englishsprint.generated.dto.VoiceSessionStatus
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Instant

class RealtimeSessionMappingTest {
    @Test
    fun generated_transport_metadata_is_mapped_to_stable_domain_data() {
        val instant = Instant.fromEpochMilliseconds(1_700_000_000_000)
        val domain = VoiceSessionMetadata(
            sessionId = "d11388ba-4026-454b-bb91-c0d22abef601",
            status = VoiceSessionStatus.ended,
            provider = "openai",
            model = "gpt-realtime-2.1-mini",
            createdAt = instant,
            updatedAt = instant,
            startedAt = instant,
            endedAt = instant,
            durationSeconds = 42,
            terminationReason = TerminationReason.user_finished,
        ).toDomain()

        assertEquals("ended", domain.status)
        assertEquals("openai", domain.provider)
        assertEquals(42, domain.durationSeconds)
        assertEquals("user_finished", domain.terminationReason)
    }
}
