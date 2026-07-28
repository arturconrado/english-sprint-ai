package com.arturconrado.englishsprint.domain

import com.arturconrado.englishsprint.pedagogy.generated.MissionEvent
import com.arturconrado.englishsprint.pedagogy.generated.MissionState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse

class MissionSessionReducerTest {
    @Test
    fun happyPathCompletesDeterministically() {
        val events = listOf(
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
        )
        val result = events.fold(MissionState.MISSION_IDLE) { state, event ->
            MissionSessionReducer.reduce(state, event).current
        }
        assertEquals(MissionState.MISSION_COMPLETED, result)
    }

    @Test
    fun cancellationIsIdempotent() {
        val first = MissionSessionReducer.reduce(
            MissionState.RETRY_WAITING,
            MissionEvent.CANCEL_REQUESTED,
        )
        val second = MissionSessionReducer.reduce(first.current, MissionEvent.CANCEL_REQUESTED)
        assertEquals(MissionState.MISSION_CANCELLED, second.current)
        assertFalse(second.changed)
    }

    @Test
    fun invalidEventCannotAdvance() {
        assertFailsWith<InvalidMissionTransition> {
            MissionSessionReducer.reduce(
                MissionState.FIRST_ATTEMPT_WAITING,
                MissionEvent.EVALUATION_SUCCEEDED,
            )
        }
    }
}
