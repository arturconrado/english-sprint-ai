package com.arturconrado.englishsprint.platform

interface FeatureFlagProvider {
    fun isEnabled(key: String): Boolean
}

interface AnalyticsSink {
    fun track(name: String, attributes: Map<String, String> = emptyMap())
}

interface KeyValueStore {
    fun read(key: String): String?
    fun write(key: String, value: String)
    fun remove(key: String)
}
