package com.arturconrado.englishsprint.mission

import android.content.Context

data class StoredMissionSession(
    val sessionId: String,
)

/**
 * Stores only the backend session identifier. Firebase owns and rotates the
 * credential; an ID token is never copied into SharedPreferences or an Intent.
 */
class MissionSessionTokenStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun save(session: StoredMissionSession) {
        preferences.edit().putString(SESSION_ID, session.sessionId).apply()
    }

    fun load(): StoredMissionSession? =
        preferences.getString(SESSION_ID, null)?.let(::StoredMissionSession)

    fun clear() {
        preferences.edit().remove(SESSION_ID).apply()
    }

    private companion object {
        const val PREFERENCES = "mission_session_state"
        const val SESSION_ID = "session_id"
    }
}
