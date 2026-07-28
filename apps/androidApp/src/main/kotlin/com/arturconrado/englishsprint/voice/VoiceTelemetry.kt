package com.arturconrado.englishsprint.voice

import android.util.Log

internal class VoiceTelemetry {
    fun event(name: String, attributes: Map<String, String> = emptyMap()) {
        val sanitized = attributes.entries
            .sortedBy { it.key }
            .joinToString(",") { "${it.key}=${it.value}" }
        Log.i(TAG, "event=$name${if (sanitized.isEmpty()) "" else ",$sanitized"}")
    }

    fun duration(name: String, milliseconds: Long) {
        Log.i(TAG, "metric=$name,duration_ms=$milliseconds")
    }

    private companion object {
        const val TAG = "EnglishSprintVoice"
    }
}
