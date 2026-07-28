package com.arturconrado.englishsprint.voice

internal object VoiceEndpointPolicy {
    fun isAllowed(baseUrl: String, debug: Boolean): Boolean =
        debug || baseUrl.startsWith("https://")
}
