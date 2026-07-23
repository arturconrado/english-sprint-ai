package com.arturconrado.englishsprint.domain

sealed interface SessionState {
    data object Idle : SessionState
    data object Preparing : SessionState
    data class Failed(val recoverable: Boolean) : SessionState
}
