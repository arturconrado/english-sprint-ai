package com.arturconrado.englishsprint.domain

import com.arturconrado.englishsprint.pedagogy.generated.MissionState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class MissionCommandBusTest {
    @Test
    fun helpDoesNotAdvancePedagogicalState() {
        val context = MissionCommandContext(MissionState.RETRY_WAITING, 8)
        val result = MissionCommandBus.dispatch(context, MissionCommand.RequestHelp)
        assertEquals(context, result.context)
        assertEquals(listOf(MissionEffect.PresentPartialHelp), result.effects)
    }

    @Test
    fun timeExtensionIsLimitedPerAttemptVersion() {
        val context = MissionCommandContext(MissionState.FIRST_ATTEMPT_WAITING, 3)
        val first = MissionCommandBus.dispatch(context, MissionCommand.NeedMoreTime)
        assertEquals(listOf(MissionEffect.ExtendAttemptTimer()), first.effects)
        assertFailsWith<InvalidMissionCommand> {
            MissionCommandBus.dispatch(first.context, MissionCommand.NeedMoreTime)
        }
    }

    @Test
    fun cancellationIsIdempotent() {
        val context = MissionCommandContext(MissionState.RETRY_WAITING, 8)
        val first = MissionCommandBus.dispatch(context, MissionCommand.Cancel)
        val second = MissionCommandBus.dispatch(first.context, MissionCommand.Cancel)
        assertEquals(MissionState.MISSION_CANCELLED, second.context.state)
        assertEquals(first.context.stateVersion, second.context.stateVersion)
    }
}
