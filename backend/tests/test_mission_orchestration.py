import pytest

from english_sprint_api.pedagogy.generated_state import MissionEvent, MissionState
from english_sprint_api.pedagogy.orchestration import (
    AttemptKind,
    InvalidMissionCommand,
    MissionCommand,
    MissionEffect,
    MissionSessionController,
    StaleMissionEvent,
)


def waiting_controller() -> MissionSessionController:
    controller = MissionSessionController()
    controller.transition(MissionEvent.START_REQUESTED, 0)
    controller.transition(MissionEvent.SESSION_STARTED, 1)
    controller.transition(MissionEvent.SCENARIO_PRESENTED, 2)
    return controller


def test_help_and_repeat_do_not_create_attempts() -> None:
    controller = waiting_controller()
    assert controller.command(MissionCommand.REPEAT_PROMPT, 3) == (MissionEffect.PRESENT_PROMPT,)
    assert controller.command(MissionCommand.REQUEST_HELP, 3) == (
        MissionEffect.PRESENT_PARTIAL_HELP,
    )
    assert controller.attempt_count == 0
    assert controller.state is MissionState.FIRST_ATTEMPT_WAITING


def test_more_time_is_limited_to_one_extension_per_attempt() -> None:
    controller = waiting_controller()
    assert controller.command(MissionCommand.NEED_MORE_TIME, 3) == (
        MissionEffect.EXTEND_ATTEMPT_TIMER,
    )
    with pytest.raises(InvalidMissionCommand):
        controller.command(MissionCommand.NEED_MORE_TIME, 3)


def test_first_retry_and_transfer_are_exactly_three_attempts() -> None:
    controller = waiting_controller()
    assert controller.record_attempt(3) is AttemptKind.FIRST
    controller.transition(MissionEvent.EVALUATION_QUEUED, 4)
    controller.transition(MissionEvent.EVALUATION_SUCCEEDED, 5)
    controller.transition(MissionEvent.CORRECTION_PREPARED, 6)
    controller.transition(MissionEvent.CORRECTION_PRESENTED, 7)
    assert controller.record_attempt(8) is AttemptKind.RETRY
    controller.transition(MissionEvent.EVALUATION_QUEUED, 9)
    controller.transition(MissionEvent.EVALUATION_SUCCEEDED, 10)
    controller.transition(MissionEvent.TRANSFER_PRESENTED, 11)
    assert controller.record_attempt(12) is AttemptKind.TRANSFER
    assert controller.attempt_count == 3


def test_stale_event_is_rejected() -> None:
    controller = waiting_controller()
    with pytest.raises(StaleMissionEvent):
        controller.record_attempt(2)


def test_cancel_is_idempotent() -> None:
    controller = waiting_controller()
    assert controller.command(MissionCommand.CANCEL, 3) == (MissionEffect.CLEANUP,)
    assert controller.command(MissionCommand.CANCEL, 4) == (MissionEffect.CLEANUP,)
