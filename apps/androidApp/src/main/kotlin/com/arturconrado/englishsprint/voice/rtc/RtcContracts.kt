package com.arturconrado.englishsprint.voice.rtc

data class RtcAudioFrame(
    val pcm16: ByteArray,
    val sampleRate: Int,
    val channelCount: Int,
)

sealed interface RtcEvent {
    data object Connected : RtcEvent
    data object Disconnected : RtcEvent
    data object UserSpeechStarted : RtcEvent
    data object UserSpeechEnded : RtcEvent
    data object ResponseStarted : RtcEvent
    data object ResponseEnded : RtcEvent
    data class Failure(val code: String) : RtcEvent
}

interface RtcSession {
    suspend fun createOffer(): String
    suspend fun acceptAnswer(sdpAnswer: String)
    fun pause()
    fun resume()
    fun interruptResponse()
    fun restartIce()
    fun close()
}

fun interface RtcSessionFactory {
    fun create(
        onEvent: (RtcEvent) -> Unit,
        onAudioFrame: (RtcAudioFrame) -> Unit,
    ): RtcSession
}
