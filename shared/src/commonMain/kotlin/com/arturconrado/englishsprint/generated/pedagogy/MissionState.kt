// Generated from contracts/pedagogy/mission-state-machine.json. Do not edit.
package com.arturconrado.englishsprint.generated.pedagogy

enum class MissionState {
    MISSION_IDLE,
    MISSION_STARTING,
    SCENARIO_PRESENTING,
    FIRST_ATTEMPT_WAITING,
    FIRST_ATTEMPT_RECEIVED,
    FIRST_ATTEMPT_EVALUATING,
    CORRECTION_PREPARING,
    CORRECTION_PRESENTING,
    RETRY_WAITING,
    RETRY_RECEIVED,
    RETRY_EVALUATING,
    TRANSFER_PRESENTING,
    TRANSFER_WAITING,
    TRANSFER_RECEIVED,
    TRANSFER_EVALUATING,
    MISSION_SUMMARIZING,
    MISSION_COMPLETED,
    MISSION_CANCELLED,
    MISSION_FAILED,
}

enum class MissionEvent {
    START_REQUESTED,
    SESSION_STARTED,
    SCENARIO_PRESENTED,
    ATTEMPT_COMPLETED,
    EVALUATION_QUEUED,
    EVALUATION_SUCCEEDED,
    EVALUATION_FAILED,
    CORRECTION_PREPARED,
    CORRECTION_PRESENTED,
    TRANSFER_PRESENTED,
    SUMMARY_COMPLETED,
    CANCEL_REQUESTED,
    FAILURE_RECORDED,
}

data class MissionTransitionKey(
    val state: MissionState,
    val event: MissionEvent,
)

val missionTerminalStates: Set<MissionState> = setOf(
    MissionState.MISSION_COMPLETED,
    MissionState.MISSION_CANCELLED,
    MissionState.MISSION_FAILED,
)

val missionTransitions: Map<MissionTransitionKey, MissionState> = mapOf(
    MissionTransitionKey(MissionState.MISSION_IDLE, MissionEvent.START_REQUESTED) to MissionState.MISSION_STARTING,
    MissionTransitionKey(MissionState.MISSION_STARTING, MissionEvent.SESSION_STARTED) to MissionState.SCENARIO_PRESENTING,
    MissionTransitionKey(MissionState.SCENARIO_PRESENTING, MissionEvent.SCENARIO_PRESENTED) to MissionState.FIRST_ATTEMPT_WAITING,
    MissionTransitionKey(MissionState.FIRST_ATTEMPT_WAITING, MissionEvent.ATTEMPT_COMPLETED) to MissionState.FIRST_ATTEMPT_RECEIVED,
    MissionTransitionKey(MissionState.FIRST_ATTEMPT_RECEIVED, MissionEvent.EVALUATION_QUEUED) to MissionState.FIRST_ATTEMPT_EVALUATING,
    MissionTransitionKey(MissionState.FIRST_ATTEMPT_EVALUATING, MissionEvent.EVALUATION_SUCCEEDED) to MissionState.CORRECTION_PREPARING,
    MissionTransitionKey(MissionState.FIRST_ATTEMPT_EVALUATING, MissionEvent.EVALUATION_FAILED) to MissionState.MISSION_SUMMARIZING,
    MissionTransitionKey(MissionState.CORRECTION_PREPARING, MissionEvent.CORRECTION_PREPARED) to MissionState.CORRECTION_PRESENTING,
    MissionTransitionKey(MissionState.CORRECTION_PRESENTING, MissionEvent.CORRECTION_PRESENTED) to MissionState.RETRY_WAITING,
    MissionTransitionKey(MissionState.RETRY_WAITING, MissionEvent.ATTEMPT_COMPLETED) to MissionState.RETRY_RECEIVED,
    MissionTransitionKey(MissionState.RETRY_RECEIVED, MissionEvent.EVALUATION_QUEUED) to MissionState.RETRY_EVALUATING,
    MissionTransitionKey(MissionState.RETRY_EVALUATING, MissionEvent.EVALUATION_SUCCEEDED) to MissionState.TRANSFER_PRESENTING,
    MissionTransitionKey(MissionState.RETRY_EVALUATING, MissionEvent.EVALUATION_FAILED) to MissionState.TRANSFER_PRESENTING,
    MissionTransitionKey(MissionState.TRANSFER_PRESENTING, MissionEvent.TRANSFER_PRESENTED) to MissionState.TRANSFER_WAITING,
    MissionTransitionKey(MissionState.TRANSFER_WAITING, MissionEvent.ATTEMPT_COMPLETED) to MissionState.TRANSFER_RECEIVED,
    MissionTransitionKey(MissionState.TRANSFER_RECEIVED, MissionEvent.EVALUATION_QUEUED) to MissionState.TRANSFER_EVALUATING,
    MissionTransitionKey(MissionState.TRANSFER_EVALUATING, MissionEvent.EVALUATION_SUCCEEDED) to MissionState.MISSION_SUMMARIZING,
    MissionTransitionKey(MissionState.TRANSFER_EVALUATING, MissionEvent.EVALUATION_FAILED) to MissionState.MISSION_SUMMARIZING,
    MissionTransitionKey(MissionState.MISSION_SUMMARIZING, MissionEvent.SUMMARY_COMPLETED) to MissionState.MISSION_COMPLETED,
)
