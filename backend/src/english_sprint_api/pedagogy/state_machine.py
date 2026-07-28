from dataclasses import dataclass

from english_sprint_api.pedagogy.generated_state import (
    TERMINAL_STATES,
    TRANSITIONS,
    MissionEvent,
    MissionState,
)


class InvalidMissionTransition(ValueError):
    def __init__(self, state: MissionState, event: MissionEvent) -> None:
        super().__init__(f"Event {event.value} is invalid while mission is {state.value}.")
        self.state = state
        self.event = event


@dataclass(frozen=True, slots=True)
class MissionTransition:
    previous: MissionState
    event: MissionEvent
    current: MissionState
    changed: bool


class MissionStateMachine:
    @staticmethod
    def reduce(state: MissionState, event: MissionEvent) -> MissionTransition:
        if event is MissionEvent.CANCEL_REQUESTED:
            target = state if state in TERMINAL_STATES else MissionState.MISSION_CANCELLED
            return MissionTransition(state, event, target, target is not state)
        if event is MissionEvent.FAILURE_RECORDED:
            target = state if state in TERMINAL_STATES else MissionState.MISSION_FAILED
            return MissionTransition(state, event, target, target is not state)
        mapped_target = TRANSITIONS.get((state, event))
        if mapped_target is None:
            raise InvalidMissionTransition(state, event)
        return MissionTransition(state, event, mapped_target, mapped_target is not state)
