package com.arturconrado.englishsprint.voice

internal object VoiceRecoveryPolicy {
    val networkBackoffMillis: List<Long> = listOf(1_000L, 3_000L)
    const val bluetoothAttempts: Int = 3
    const val bluetoothAttemptDelayMillis: Long = 5_000L
}
