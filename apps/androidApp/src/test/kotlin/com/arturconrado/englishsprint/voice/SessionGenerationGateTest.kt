package com.arturconrado.englishsprint.voice

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionGenerationGateTest {
    @Test
    fun events_from_cancelled_or_reconnected_sessions_are_rejected() {
        val gate = SessionGenerationGate()
        val firstSession = gate.next()

        assertTrue(gate.accepts(firstSession))

        gate.invalidate()
        assertFalse(gate.accepts(firstSession))

        val reconnectedSession = gate.next()
        assertFalse(gate.accepts(firstSession))
        assertTrue(gate.accepts(reconnectedSession))
    }
}
