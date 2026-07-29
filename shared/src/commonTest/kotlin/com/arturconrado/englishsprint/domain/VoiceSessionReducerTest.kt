package com.arturconrado.englishsprint.domain

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class VoiceSessionReducerTest {
    @Test
    fun start_permission_and_connect_form_the_happy_path() {
        val requested = VoiceSessionReducer.reduce(
            VoiceSessionState.Idle,
            VoiceSessionEvent.StartRequested,
        )
        val connecting = VoiceSessionReducer.reduce(
            requested.state,
            VoiceSessionEvent.PermissionResult(granted = true),
        )
        val ready = VoiceSessionReducer.reduce(connecting.state, VoiceSessionEvent.Connected)

        assertEquals(VoiceSessionState.RequestingPermission, requested.state)
        assertEquals(listOf(VoiceSessionEffect.RequestPermissions), requested.effects)
        assertEquals(VoiceSessionState.Connecting, connecting.state)
        assertEquals(VoiceSessionState.Ready, ready.state)
    }

    @Test
    fun speech_during_playback_cancels_the_remote_response() {
        val transition = VoiceSessionReducer.reduce(
            VoiceSessionState.Speaking,
            VoiceSessionEvent.UserSpeechStarted,
        )

        assertEquals(VoiceSessionState.Listening, transition.state)
        assertEquals(listOf(VoiceSessionEffect.CancelRemoteResponse), transition.effects)
    }

    @Test
    fun speech_during_processing_also_cancels_the_stale_response() {
        val transition = VoiceSessionReducer.reduce(
            VoiceSessionState.Processing,
            VoiceSessionEvent.UserSpeechStarted,
        )

        assertEquals(VoiceSessionState.Listening, transition.state)
        assertEquals(listOf(VoiceSessionEffect.CancelRemoteResponse), transition.effects)
    }

    @Test
    fun listening_processing_speaking_and_pause_transitions_are_explicit() {
        val listening = VoiceSessionReducer.reduce(
            VoiceSessionState.Ready,
            VoiceSessionEvent.ResponseEnded,
        )
        val processing = VoiceSessionReducer.reduce(
            listening.state,
            VoiceSessionEvent.UserSpeechEnded,
        )
        val speaking = VoiceSessionReducer.reduce(
            processing.state,
            VoiceSessionEvent.ResponseStarted,
        )
        val paused = VoiceSessionReducer.reduce(
            speaking.state,
            VoiceSessionEvent.PauseRequested,
        )
        val resumed = VoiceSessionReducer.reduce(
            paused.state,
            VoiceSessionEvent.ResumeRequested,
        )

        assertEquals(VoiceSessionState.Listening, listening.state)
        assertEquals(VoiceSessionState.Processing, processing.state)
        assertEquals(VoiceSessionState.Speaking, speaking.state)
        assertEquals(VoiceSessionState.Paused, paused.state)
        assertEquals(listOf(VoiceSessionEffect.PauseMedia), paused.effects)
        assertEquals(VoiceSessionState.Listening, resumed.state)
        assertEquals(listOf(VoiceSessionEffect.ResumeMedia), resumed.effects)
    }

    @Test
    fun route_loss_never_falls_back_to_a_speaker_state() {
        val transition = VoiceSessionReducer.reduce(
            VoiceSessionState.Listening,
            VoiceSessionEvent.RouteLost,
        )

        assertEquals(VoiceSessionState.AudioRouteLost, transition.state)
        assertEquals(
            listOf(VoiceSessionEffect.PauseMedia, VoiceSessionEffect.RecoverAudioRoute),
            transition.effects,
        )
    }

    @Test
    fun route_reconnect_error_and_cleanup_transitions_are_bounded() {
        val restored = VoiceSessionReducer.reduce(
            VoiceSessionState.AudioRouteLost,
            VoiceSessionEvent.RouteRestored,
        )
        val reconnecting = VoiceSessionReducer.reduce(
            restored.state,
            VoiceSessionEvent.ReconnectStarted,
        )
        val failed = VoiceSessionReducer.reduce(
            reconnecting.state,
            VoiceSessionEvent.Failure("network_recovery_exhausted", true),
        )
        val ending = VoiceSessionReducer.reduce(
            failed.state,
            VoiceSessionEvent.FinishRequested,
        )
        val ended = VoiceSessionReducer.reduce(
            ending.state,
            VoiceSessionEvent.CleanupCompleted,
        )

        assertEquals(VoiceSessionState.Listening, restored.state)
        assertEquals(VoiceSessionState.Reconnecting, reconnecting.state)
        assertEquals(
            VoiceSessionState.Error("network_recovery_exhausted", true),
            failed.state,
        )
        assertEquals(VoiceSessionState.Ending, ending.state)
        assertEquals(listOf(VoiceSessionEffect.Cleanup), ending.effects)
        assertEquals(VoiceSessionState.Ended, ended.state)
    }

    @Test
    fun bilingual_commands_require_exact_high_confidence_matches() {
        assertEquals(
            LocalVoiceCommand.StopResponse,
            LocalVoiceCommandParser.parse("parar", 0.95),
        )
        assertEquals(
            LocalVoiceCommand.Resume,
            LocalVoiceCommandParser.parse(" Continuar ", 0.82),
        )
        assertEquals(
            LocalVoiceCommand.RepeatPrompt,
            LocalVoiceCommandParser.parse("repetir pergunta", 0.91),
        )
        assertEquals(
            LocalVoiceCommand.NeedMoreTime,
            LocalVoiceCommandParser.parse("more time", 0.93),
        )
        assertEquals(
            LocalVoiceCommand.RequestHelp,
            LocalVoiceCommandParser.parse("me ajude", 0.94),
        )
        assertNull(LocalVoiceCommandParser.parse("please stop now", 0.99))
        assertNull(LocalVoiceCommandParser.parse("stop!", 0.99))
        assertNull(LocalVoiceCommandParser.parse("unknown", 1.0))
        assertNull(LocalVoiceCommandParser.parse("finish", 0.81))
    }
}
