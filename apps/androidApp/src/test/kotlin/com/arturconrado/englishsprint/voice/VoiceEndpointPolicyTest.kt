package com.arturconrado.englishsprint.voice

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceEndpointPolicyTest {
    @Test
    fun debug_allows_local_http_but_release_requires_https() {
        assertTrue(VoiceEndpointPolicy.isAllowed("http://10.0.2.2:8000", debug = true))
        assertFalse(VoiceEndpointPolicy.isAllowed("http://example.test", debug = false))
        assertTrue(VoiceEndpointPolicy.isAllowed("https://api.example.test", debug = false))
    }
}
