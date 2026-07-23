package com.arturconrado.englishsprint.domain

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class SessionStateTest {
    @Test
    fun idle_is_the_initial_session_contract() {
        val state: SessionState = SessionState.Idle

        assertIs<SessionState.Idle>(state)
        assertEquals(SessionState.Idle, state)
    }
}
