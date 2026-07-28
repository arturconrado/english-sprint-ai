package com.arturconrado.englishsprint.voice

import org.junit.Assert.assertEquals
import org.junit.Test

class VoiceRecoveryPolicyTest {
    @Test
    fun network_recovery_is_bounded_to_ice_restart_and_one_rebuild() {
        assertEquals(listOf(1_000L, 3_000L), VoiceRecoveryPolicy.networkBackoffMillis)
        assertEquals(2, VoiceRecoveryPolicy.networkBackoffMillis.size)
    }

    @Test
    fun bluetooth_recovery_is_bounded_to_fifteen_seconds() {
        assertEquals(3, VoiceRecoveryPolicy.bluetoothAttempts)
        assertEquals(
            15_000L,
            VoiceRecoveryPolicy.bluetoothAttempts *
                VoiceRecoveryPolicy.bluetoothAttemptDelayMillis,
        )
    }
}
