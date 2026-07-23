package com.arturconrado.englishsprint.api

import com.arturconrado.englishsprint.domain.ServiceHealth
import com.arturconrado.englishsprint.domain.ServiceStatus
import com.arturconrado.englishsprint.generated.api.OperationsApi
import com.arturconrado.englishsprint.generated.dto.HealthResponse
import io.ktor.client.HttpClient

interface HealthApi {
    suspend fun getHealth(): ServiceHealth
}

class KtorHealthApi(
    baseUrl: String,
    client: HttpClient,
) : HealthApi {
    private val operations = OperationsApi(baseUrl, client)

    override suspend fun getHealth(): ServiceHealth {
        val response = operations.getHealth()
        if (!response.success) {
            return ServiceHealth(ServiceStatus.Unavailable)
        }

        val status = when (response.body().status) {
            HealthResponse.Status.alive -> ServiceStatus.Alive
        }
        return ServiceHealth(status)
    }
}
