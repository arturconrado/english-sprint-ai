package com.arturconrado.englishsprint.domain

import com.arturconrado.englishsprint.generated.pedagogy.MissionEvent
import com.arturconrado.englishsprint.generated.pedagogy.MissionState
import com.arturconrado.englishsprint.generated.pedagogy.MissionTransitionKey
import com.arturconrado.englishsprint.generated.pedagogy.missionTerminalStates
import com.arturconrado.englishsprint.generated.pedagogy.missionTransitions

data class MissionSessionSnapshot(
    val sessionId: String,
    val missionId: String,
    val state: MissionState,
    val stateVersion: Long,
    val currentAttemptId: String? = null,
)

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
