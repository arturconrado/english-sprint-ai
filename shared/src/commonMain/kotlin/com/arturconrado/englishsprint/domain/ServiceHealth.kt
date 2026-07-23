package com.arturconrado.englishsprint.domain

enum class ServiceStatus {
    Alive,
    Unavailable,
}

data class ServiceHealth(
    val status: ServiceStatus,
)
