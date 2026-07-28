package com.arturconrado.englishsprint.domain

sealed interface VoiceSessionState {
    data object Idle : VoiceSessionState
    data object RequestingPermission : VoiceSessionState
    data object Connecting : VoiceSessionState
    data object Ready : VoiceSessionState
    data object Listening : VoiceSessionState
    data object Processing : VoiceSessionState
    data object Speaking : VoiceSessionState
    data object Paused : VoiceSessionState
    data object AudioRouteLost : VoiceSessionState
    data object Reconnecting : VoiceSessionState
    data object Ending : VoiceSessionState
    data object Ended : VoiceSessionState
    data class Error(
        val code: String,
        val recoverable: Boolean,
    ) : VoiceSessionState
}

enum class VoiceSessionCommand {
    Start,
    StopResponse,
    Pause,
    Resume,
    Finish,
}

enum class LocalVoiceCommand {
    StopResponse,
    Pause,
    Resume,
    Finish,
}

sealed interface VoiceSessionEvent {
    data object StartRequested : VoiceSessionEvent
    data class PermissionResult(val granted: Boolean) : VoiceSessionEvent
    data object Connected : VoiceSessionEvent
    data object UserSpeechStarted : VoiceSessionEvent
    data object UserSpeechEnded : VoiceSessionEvent
    data object ResponseStarted : VoiceSessionEvent
    data object ResponseEnded : VoiceSessionEvent
    data object PauseRequested : VoiceSessionEvent
    data object ResumeRequested : VoiceSessionEvent
    data object RouteLost : VoiceSessionEvent
    data object RouteRestored : VoiceSessionEvent
    data object ReconnectStarted : VoiceSessionEvent
    data object FinishRequested : VoiceSessionEvent
    data object CleanupCompleted : VoiceSessionEvent
    data class Failure(val code: String, val recoverable: Boolean) : VoiceSessionEvent
}

sealed interface VoiceSessionEffect {
    data object RequestPermissions : VoiceSessionEffect
    data object Connect : VoiceSessionEffect
    data object CancelRemoteResponse : VoiceSessionEffect
    data object PauseMedia : VoiceSessionEffect
    data object ResumeMedia : VoiceSessionEffect
    data object RecoverAudioRoute : VoiceSessionEffect
    data object Cleanup : VoiceSessionEffect
}

data class VoiceSessionTransition(
    val state: VoiceSessionState,
    val effects: List<VoiceSessionEffect> = emptyList(),
)

object VoiceSessionReducer {
    fun reduce(
        state: VoiceSessionState,
        event: VoiceSessionEvent,
    ): VoiceSessionTransition = when (event) {
        VoiceSessionEvent.StartRequested ->
            if (state == VoiceSessionState.Idle || state == VoiceSessionState.Ended) {
                VoiceSessionTransition(
                    VoiceSessionState.RequestingPermission,
                    listOf(VoiceSessionEffect.RequestPermissions),
                )
            } else {
                VoiceSessionTransition(state)
            }

        is VoiceSessionEvent.PermissionResult ->
            if (event.granted) {
                VoiceSessionTransition(
                    VoiceSessionState.Connecting,
                    listOf(VoiceSessionEffect.Connect),
                )
            } else {
                VoiceSessionTransition(VoiceSessionState.Error("permission_denied", false))
            }

        VoiceSessionEvent.Connected -> VoiceSessionTransition(VoiceSessionState.Ready)
        VoiceSessionEvent.UserSpeechStarted ->
            VoiceSessionTransition(
                VoiceSessionState.Listening,
                if (
                    state == VoiceSessionState.Speaking ||
                    state == VoiceSessionState.Processing
                ) {
                    listOf(VoiceSessionEffect.CancelRemoteResponse)
                } else {
                    emptyList()
                },
            )

        VoiceSessionEvent.UserSpeechEnded -> VoiceSessionTransition(VoiceSessionState.Processing)
        VoiceSessionEvent.ResponseStarted -> VoiceSessionTransition(VoiceSessionState.Speaking)
        VoiceSessionEvent.ResponseEnded -> VoiceSessionTransition(VoiceSessionState.Listening)
        VoiceSessionEvent.PauseRequested ->
            VoiceSessionTransition(
                VoiceSessionState.Paused,
                listOf(VoiceSessionEffect.PauseMedia),
            )

        VoiceSessionEvent.ResumeRequested ->
            VoiceSessionTransition(
                VoiceSessionState.Listening,
                listOf(VoiceSessionEffect.ResumeMedia),
            )

        VoiceSessionEvent.RouteLost ->
            VoiceSessionTransition(
                VoiceSessionState.AudioRouteLost,
                listOf(VoiceSessionEffect.PauseMedia, VoiceSessionEffect.RecoverAudioRoute),
            )

        VoiceSessionEvent.RouteRestored ->
            VoiceSessionTransition(
                VoiceSessionState.Listening,
                listOf(VoiceSessionEffect.ResumeMedia),
            )

        VoiceSessionEvent.ReconnectStarted -> VoiceSessionTransition(VoiceSessionState.Reconnecting)
        VoiceSessionEvent.FinishRequested ->
            VoiceSessionTransition(
                VoiceSessionState.Ending,
                listOf(VoiceSessionEffect.Cleanup),
            )

        VoiceSessionEvent.CleanupCompleted -> VoiceSessionTransition(VoiceSessionState.Ended)
        is VoiceSessionEvent.Failure ->
            VoiceSessionTransition(VoiceSessionState.Error(event.code, event.recoverable))
    }
}

object LocalVoiceCommandParser {
    private val commands = mapOf(
        "stop" to LocalVoiceCommand.StopResponse,
        "parar" to LocalVoiceCommand.StopResponse,
        "pause" to LocalVoiceCommand.Pause,
        "pausar" to LocalVoiceCommand.Pause,
        "resume" to LocalVoiceCommand.Resume,
        "continuar" to LocalVoiceCommand.Resume,
        "finish" to LocalVoiceCommand.Finish,
        "encerrar" to LocalVoiceCommand.Finish,
    )

    fun parse(transcript: String, confidence: Double): LocalVoiceCommand? {
        if (confidence < 0.82) return null
        val normalized = transcript.trim().lowercase()
        return commands[normalized]
    }
}

data class RealtimeCallAnswer(
    val sessionId: String,
    val location: String,
    val sdpAnswer: String,
)

data class VoiceSessionMetadata(
    val sessionId: String,
    val status: String,
    val provider: String,
    val model: String,
    val createdAt: String,
    val updatedAt: String,
    val startedAt: String?,
    val endedAt: String?,
    val durationSeconds: Int?,
    val terminationReason: String?,
)
