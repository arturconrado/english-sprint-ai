import pytest

from english_sprint_api.pedagogy.generated_state import MissionEvent, MissionState
from english_sprint_api.pedagogy.state_machine import (
    InvalidMissionTransition,
    MissionStateMachine,
)


def test_happy_path_is_deterministic() -> None:
    events = [
        MissionEvent.START_REQUESTED,
        MissionEvent.SESSION_STARTED,
        MissionEvent.SCENARIO_PRESENTED,
        MissionEvent.ATTEMPT_COMPLETED,
        MissionEvent.EVALUATION_QUEUED,
        MissionEvent.EVALUATION_SUCCEEDED,
        MissionEvent.CORRECTION_PREPARED,
        MissionEvent.CORRECTION_PRESENTED,
        MissionEvent.ATTEMPT_COMPLETED,
        MissionEvent.EVALUATION_QUEUED,
        MissionEvent.EVALUATION_SUCCEEDED,
        MissionEvent.TRANSFER_PRESENTED,
        MissionEvent.ATTEMPT_COMPLETED,
        MissionEvent.EVALUATION_QUEUED,
        MissionEvent.EVALUATION_SUCCEEDED,
        MissionEvent.SUMMARY_COMPLETED,
    ]
    state = MissionState.MISSION_IDLE
    for event in events:
        state = MissionStateMachine.reduce(state, event).current
    assert state is MissionState.MISSION_COMPLETED


def test_cancellation_is_idempotent() -> None:
    first = MissionStateMachine.reduce(
        MissionState.RETRY_WAITING,
        MissionEvent.CANCEL_REQUESTED,
    )
    second = MissionStateMachine.reduce(first.current, MissionEvent.CANCEL_REQUESTED)
    assert first.current is MissionState.MISSION_CANCELLED
    assert second.current is MissionState.MISSION_CANCELLED
    assert second.changed is False


def test_invalid_transition_does_not_advance() -> None:
    with pytest.raises(InvalidMissionTransition):
        MissionStateMachine.reduce(
            MissionState.FIRST_ATTEMPT_WAITING,
            MissionEvent.EVALUATION_SUCCEEDED,
        )
