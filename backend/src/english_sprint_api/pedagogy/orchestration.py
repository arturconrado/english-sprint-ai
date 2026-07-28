from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from english_sprint_api.pedagogy.generated_state import MissionEvent, MissionState
from english_sprint_api.pedagogy.state_machine import MissionStateMachine


class MissionCommand(StrEnum):
    REPEAT_PROMPT = "repeat_prompt"
    NEED_MORE_TIME = "need_more_time"
    REQUEST_HELP = "request_help"
    PAUSE = "pause"
    RESUME = "resume"
    STOP_RESPONSE = "stop_response"
    CANCEL = "cancel"
    FINISH = "finish"


class MissionEffect(StrEnum):
    PRESENT_PROMPT = "present_prompt"
    EXTEND_ATTEMPT_TIMER = "extend_attempt_timer"
    PRESENT_PARTIAL_HELP = "present_partial_help"
    PAUSE_MEDIA = "pause_media"
    RESUME_MEDIA = "resume_media"
    STOP_RESPONSE = "stop_response"
    CLEANUP = "cleanup"
    COMPLETE_SUMMARY = "complete_summary"


class AttemptKind(StrEnum):
    FIRST = "first"
    RETRY = "retry"
    TRANSFER = "transfer"


class StaleMissionEvent(ValueError):
    pass


class InvalidMissionCommand(ValueError):
    pass


WAITING_STATES = {
    MissionState.FIRST_ATTEMPT_WAITING,
    MissionState.RETRY_WAITING,
    MissionState.TRANSFER_WAITING,
}


@dataclass(slots=True)
class MissionSessionController:
    state: MissionState = MissionState.MISSION_IDLE
    state_version: int = 0
    attempt_count: int = 0
    _time_extension_versions: set[int] = field(default_factory=set)

    def transition(
        self,
        event: MissionEvent,
        expected_state_version: int,
    ) -> MissionState:
        if expected_state_version != self.state_version:
            raise StaleMissionEvent("Mission state version is stale.")
        result = MissionStateMachine.reduce(self.state, event)
        self.state = result.current
        if result.changed:
            self.state_version += 1
        return self.state

    def record_attempt(self, expected_state_version: int) -> AttemptKind:
        kind_by_state = {
            MissionState.FIRST_ATTEMPT_WAITING: AttemptKind.FIRST,
            MissionState.RETRY_WAITING: AttemptKind.RETRY,
            MissionState.TRANSFER_WAITING: AttemptKind.TRANSFER,
        }
        kind = kind_by_state.get(self.state)
        if kind is None:
            raise InvalidMissionCommand("The mission is not accepting an attempt.")
        if self.attempt_count >= 3:
            raise InvalidMissionCommand("The mission attempt limit was reached.")
        self.transition(MissionEvent.ATTEMPT_COMPLETED, expected_state_version)
        self.attempt_count += 1
        return kind

    def command(
        self,
        command: MissionCommand,
        expected_state_version: int,
    ) -> tuple[MissionEffect, ...]:
        if expected_state_version != self.state_version:
            raise StaleMissionEvent("Mission state version is stale.")
        if command is MissionCommand.CANCEL:
            self.transition(MissionEvent.CANCEL_REQUESTED, expected_state_version)
            return (MissionEffect.CLEANUP,)
        if command is MissionCommand.FINISH:
            if self.state is not MissionState.MISSION_SUMMARIZING:
                raise InvalidMissionCommand("Finish is only valid while summarizing.")
            return (MissionEffect.COMPLETE_SUMMARY,)
        if command is MissionCommand.PAUSE:
            return (MissionEffect.PAUSE_MEDIA,)
        if command is MissionCommand.RESUME:
            return (MissionEffect.RESUME_MEDIA,)
        if command is MissionCommand.STOP_RESPONSE:
            return (MissionEffect.STOP_RESPONSE,)
        if self.state not in WAITING_STATES:
            raise InvalidMissionCommand("This command requires an active attempt.")
        if command is MissionCommand.REPEAT_PROMPT:
            return (MissionEffect.PRESENT_PROMPT,)
        if command is MissionCommand.REQUEST_HELP:
            return (MissionEffect.PRESENT_PARTIAL_HELP,)
        if command is MissionCommand.NEED_MORE_TIME:
            if self.state_version in self._time_extension_versions:
                raise InvalidMissionCommand("The 30-second extension was already used.")
            self._time_extension_versions.add(self.state_version)
            return (MissionEffect.EXTEND_ATTEMPT_TIMER,)
        raise InvalidMissionCommand("Unsupported mission command.")
