package com.arturconrado.englishsprint.domain

import com.arturconrado.englishsprint.pedagogy.generated.MissionEvent
import com.arturconrado.englishsprint.pedagogy.generated.MissionState
import com.arturconrado.englishsprint.pedagogy.generated.MissionTransitionKey
import com.arturconrado.englishsprint.pedagogy.generated.missionTerminalStates
import com.arturconrado.englishsprint.pedagogy.generated.missionTransitions

data class MissionSessionSnapshot(
    val sessionId: String,
    val missionId: String,
    val state: MissionState,
    val stateVersion: Long,
    val currentAttemptId: String? = null,
)

enum class MissionCommand {
    RepeatPrompt,
    NeedMoreTime,
    RequestHelp,
    Pause,
    Resume,
    StopResponse,
    Cancel,
    Finish,
}

sealed interface MissionEffect {
    data object PresentPrompt : MissionEffect
    data class ExtendAttemptTimer(val seconds: Int = 30) : MissionEffect
    data object PresentPartialHelp : MissionEffect
    data object PauseMedia : MissionEffect
    data object ResumeMedia : MissionEffect
    data object StopResponse : MissionEffect
    data object Cleanup : MissionEffect
    data object CompleteSummary : MissionEffect
}

data class MissionCommandContext(
    val state: MissionState,
    val stateVersion: Long,
    val extendedAttemptVersions: Set<Long> = emptySet(),
)

data class MissionCommandResult(
    val context: MissionCommandContext,
    val effects: List<MissionEffect>,
)

class InvalidMissionCommand(message: String) : IllegalStateException(message)

object MissionCommandBus {
    private val waitingStates = setOf(
        MissionState.FIRST_ATTEMPT_WAITING,
        MissionState.RETRY_WAITING,
        MissionState.TRANSFER_WAITING,
    )

    fun dispatch(
        context: MissionCommandContext,
        command: MissionCommand,
    ): MissionCommandResult = when (command) {
        MissionCommand.Cancel -> {
            val transition = MissionSessionReducer.reduce(
                context.state,
                MissionEvent.CANCEL_REQUESTED,
            )
            MissionCommandResult(
                context.copy(
                    state = transition.current,
                    stateVersion = context.stateVersion + if (transition.changed) 1 else 0,
                ),
                listOf(MissionEffect.Cleanup),
            )
        }
        MissionCommand.Finish -> {
            if (context.state != MissionState.MISSION_SUMMARIZING) {
                throw InvalidMissionCommand("Finish is only valid while summarizing")
            }
            MissionCommandResult(context, listOf(MissionEffect.CompleteSummary))
        }
        MissionCommand.Pause ->
            MissionCommandResult(context, listOf(MissionEffect.PauseMedia))
        MissionCommand.Resume ->
            MissionCommandResult(context, listOf(MissionEffect.ResumeMedia))
        MissionCommand.StopResponse ->
            MissionCommandResult(context, listOf(MissionEffect.StopResponse))
        MissionCommand.RepeatPrompt -> waiting(context, MissionEffect.PresentPrompt)
        MissionCommand.RequestHelp -> waiting(context, MissionEffect.PresentPartialHelp)
        MissionCommand.NeedMoreTime -> {
            requireWaiting(context)
            if (context.stateVersion in context.extendedAttemptVersions) {
                throw InvalidMissionCommand("The 30-second extension was already used")
            }
            MissionCommandResult(
                context.copy(
                    extendedAttemptVersions =
                        context.extendedAttemptVersions + context.stateVersion,
                ),
                listOf(MissionEffect.ExtendAttemptTimer()),
            )
        }
    }

    private fun waiting(
        context: MissionCommandContext,
        effect: MissionEffect,
    ): MissionCommandResult {
        requireWaiting(context)
        return MissionCommandResult(context, listOf(effect))
    }

    private fun requireWaiting(context: MissionCommandContext) {
        if (context.state !in waitingStates) {
            throw InvalidMissionCommand("This command requires an active attempt")
        }
    }
}

data class MissionStateTransition(
    val previous: MissionState,
    val event: MissionEvent,
    val current: MissionState,
    val changed: Boolean,
)

class InvalidMissionTransition(
    val state: MissionState,
    val event: MissionEvent,
) : IllegalStateException("Event $event is invalid while mission is $state")

object MissionSessionReducer {
    fun reduce(
        state: MissionState,
        event: MissionEvent,
    ): MissionStateTransition {
        if (event == MissionEvent.CANCEL_REQUESTED) {
            val target =
                if (state in missionTerminalStates) state else MissionState.MISSION_CANCELLED
            return MissionStateTransition(state, event, target, target != state)
        }
        if (event == MissionEvent.FAILURE_RECORDED) {
            val target =
                if (state in missionTerminalStates) state else MissionState.MISSION_FAILED
            return MissionStateTransition(state, event, target, target != state)
        }
        val target = missionTransitions[MissionTransitionKey(state, event)]
            ?: throw InvalidMissionTransition(state, event)
        return MissionStateTransition(state, event, target, target != state)
    }
}
