package com.arturconrado.englishsprint.telemetry

import android.content.Context
import android.os.Bundle
import com.google.firebase.analytics.FirebaseAnalytics
import com.google.firebase.crashlytics.FirebaseCrashlytics

class ProductTelemetry(context: Context) {
    private val analytics = FirebaseAnalytics.getInstance(context.applicationContext)
    private val crashlytics = FirebaseCrashlytics.getInstance()
    private var enabled = false

    fun setConsent(granted: Boolean) {
        enabled = granted
        analytics.setAnalyticsCollectionEnabled(granted)
        crashlytics.setCrashlyticsCollectionEnabled(granted)
    }

    fun event(name: String, properties: Map<String, String> = emptyMap()) {
        if (!enabled || name !in EVENT_ALLOWLIST) return
        val bundle = Bundle()
        properties
            .filterKeys { it in PROPERTY_ALLOWLIST }
            .forEach { (key, value) -> bundle.putString(key, value.take(64)) }
        analytics.logEvent(name, bundle)
    }

    private companion object {
        val EVENT_ALLOWLIST = setOf(
            "sign_in",
            "onboarding_completed",
            "diagnostic_started",
            "diagnostic_completed",
            "sprint_started",
            "mission_completed",
            "review_completed",
            "paywall_viewed",
            "purchase_completed",
            "support_requested",
            "account_deletion_requested",
        )
        val PROPERTY_ALLOWLIST = setOf(
            "status",
            "mission_slug",
            "day_number",
            "source",
            "error_code",
        )
    }
}
