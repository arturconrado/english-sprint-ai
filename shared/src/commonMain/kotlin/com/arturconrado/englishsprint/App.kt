package com.arturconrado.englishsprint

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.arturconrado.englishsprint.domain.VoiceSessionCommand

data class VoiceSessionUiModel(
    val state: String = "IDLE",
    val routeName: String? = null,
    val errorCode: String? = null,
    val voiceAvailable: Boolean = false,
    val missions: List<MissionCardUiModel> = emptyList(),
    val selectedMissionId: String? = null,
    val missionsLoading: Boolean = false,
    val processingConsent: Boolean = false,
    val retentionConsent: Boolean = false,
    val analyticsConsent: Boolean = false,
    val notificationConsent: Boolean = true,
    val missionSessionState: String? = null,
    val accountConfigured: Boolean = true,
    val signedIn: Boolean = false,
    val productStage: String = "sign_in",
    val professionalGoal: String = "international_interviews",
    val englishContext: String = "weekly",
    val diagnosticStatus: String? = null,
    val sprintStatus: String? = null,
    val accessMode: String? = null,
    val billingStatus: String? = null,
    val remainingMinutes: Int = 0,
    val dueReviewCount: Int = 0,
    val availableMissionIds: Set<String> = emptySet(),
    val supportText: String = "",
    val deletionConfirmation: String = "",
    val accountOperationStatus: String? = null,
)

data class MissionCardUiModel(
    val id: String,
    val title: String,
    val objective: String,
    val durationMinutes: Int,
    val difficulty: String,
)

@Composable
fun App(
    model: VoiceSessionUiModel = VoiceSessionUiModel(),
    onCommand: (VoiceSessionCommand) -> Unit = {},
    onMissionSelected: (String) -> Unit = {},
    onProcessingConsentChanged: (Boolean) -> Unit = {},
    onRetentionConsentChanged: (Boolean) -> Unit = {},
    onAnalyticsConsentChanged: (Boolean) -> Unit = {},
    onNotificationConsentChanged: (Boolean) -> Unit = {},
    onProfessionalGoalChanged: (String) -> Unit = {},
    onEnglishContextChanged: (String) -> Unit = {},
    onStartMission: () -> Unit = {},
    onSignIn: () -> Unit = {},
    onStartDiagnostic: () -> Unit = {},
    onRefreshJourney: () -> Unit = {},
    onSubscribe: () -> Unit = {},
    onRestorePurchase: () -> Unit = {},
    onCompleteReview: () -> Unit = {},
    onSupportTextChanged: (String) -> Unit = {},
    onSubmitSupport: () -> Unit = {},
    onRequestExport: () -> Unit = {},
    onDeletionConfirmationChanged: (String) -> Unit = {},
    onDeleteAccount: () -> Unit = {},
    onSignOut: () -> Unit = {},
) {
    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(
                    16.dp,
                    Alignment.CenterVertically,
                ),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = "English Sprint AI",
                    style = MaterialTheme.typography.headlineMedium,
                )
                if (!model.voiceAvailable) {
                    Text(
                        text = "Voice unavailable on ${platformName()}",
                        style = MaterialTheme.typography.titleMedium,
                    )
                } else if (!model.accountConfigured) {
                    Text("Firebase configuration is required for this build.")
                } else if (!model.signedIn) {
                    Text("Sign in to keep your sprint, progress, and subscription secure.")
                    Button(onClick = onSignIn) {
                        Text("Continue with Google")
                    }
                } else if (model.missionSessionState != null) {
                    MissionSessionPanel(model, onCommand)
                } else if (model.productStage != "sprint") {
                    ProductSetup(
                        model = model,
                        onProcessingConsentChanged = onProcessingConsentChanged,
                        onRetentionConsentChanged = onRetentionConsentChanged,
                        onAnalyticsConsentChanged = onAnalyticsConsentChanged,
                        onNotificationConsentChanged = onNotificationConsentChanged,
                        onProfessionalGoalChanged = onProfessionalGoalChanged,
                        onEnglishContextChanged = onEnglishContextChanged,
                        onStartDiagnostic = onStartDiagnostic,
                        onRefreshJourney = onRefreshJourney,
                    )
                    AccountPanel(
                        model,
                        onSupportTextChanged,
                        onSubmitSupport,
                        onRequestExport,
                        onDeletionConfirmationChanged,
                        onDeleteAccount,
                        onSignOut,
                    )
                } else {
                    BillingPanel(
                        model,
                        onSubscribe,
                        onRestorePurchase,
                        onCompleteReview,
                    )
                    AccountPanel(
                        model,
                        onSupportTextChanged,
                        onSubmitSupport,
                        onRequestExport,
                        onDeletionConfirmationChanged,
                        onDeleteAccount,
                        onSignOut,
                    )
                    MissionCatalog(
                        model = model,
                        onMissionSelected = onMissionSelected,
                        onProcessingConsentChanged = onProcessingConsentChanged,
                        onRetentionConsentChanged = onRetentionConsentChanged,
                        onStartMission = onStartMission,
                    )
                }
            }
        }
    }
}

@Composable
private fun ProductSetup(
    model: VoiceSessionUiModel,
    onProcessingConsentChanged: (Boolean) -> Unit,
    onRetentionConsentChanged: (Boolean) -> Unit,
    onAnalyticsConsentChanged: (Boolean) -> Unit,
    onNotificationConsentChanged: (Boolean) -> Unit,
    onProfessionalGoalChanged: (String) -> Unit,
    onEnglishContextChanged: (String) -> Unit,
    onStartDiagnostic: () -> Unit,
    onRefreshJourney: () -> Unit,
) {
    Text("Set up your seven-day professional English sprint.")
    Text("Diagnosis: ${model.diagnosticStatus ?: "not started"}")
    OutlinedButton(
        onClick = {
            onProfessionalGoalChanged(
                when (model.professionalGoal) {
                    "international_interviews" -> "global_team_communication"
                    "global_team_communication" -> "technical_presentations"
                    else -> "international_interviews"
                },
            )
        },
    ) {
        Text("Goal: ${model.professionalGoal.replace('_', ' ')}")
    }
    OutlinedButton(
        onClick = {
            onEnglishContextChanged(
                when (model.englishContext) {
                    "rarely" -> "monthly"
                    "monthly" -> "weekly"
                    "weekly" -> "daily"
                    else -> "rarely"
                },
            )
        },
    ) {
        Text("English use: ${model.englishContext}")
    }
    ConsentRow(
        checked = model.processingConsent,
        text = "I consent to voice processing for personalized feedback.",
        onChanged = onProcessingConsentChanged,
    )
    ConsentRow(
        checked = model.retentionConsent,
        text = "Keep encrypted learning text for 30 days (optional).",
        onChanged = onRetentionConsentChanged,
    )
    ConsentRow(
        checked = model.analyticsConsent,
        text = "Share consented, content-free usage analytics (optional).",
        onChanged = onAnalyticsConsentChanged,
    )
    ConsentRow(
        checked = model.notificationConsent,
        text = "Remind me when 24h/3d/7d reviews are due.",
        onChanged = onNotificationConsentChanged,
    )
    if (model.diagnosticStatus in setOf(null, "ready", "failed", "expired")) {
        Button(
            enabled = model.processingConsent &&
                model.accessMode in setOf("free_beta", "paid_subscription"),
            onClick = onStartDiagnostic,
        ) {
            Text("Start free 10-minute diagnosis")
        }
        if (model.accessMode == "unavailable") {
            Text("The free beta cohort is currently full.")
        }
    }
    OutlinedButton(onClick = onRefreshJourney) {
        Text("Refresh diagnosis and plan")
    }
}

@Composable
private fun BillingPanel(
    model: VoiceSessionUiModel,
    onSubscribe: () -> Unit,
    onRestorePurchase: () -> Unit,
    onCompleteReview: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            when (model.accessMode) {
                "free_beta" -> Text(
                    "Free beta • ${model.remainingMinutes} min remaining",
                )
                "paid_subscription" -> Text(
                    "Paid plan • ${model.remainingMinutes} min remaining",
                )
                else -> Text("The free beta cohort is currently full.")
            }
            if (model.accessMode == "unavailable") {
                Text("Ask support to join when a beta place becomes available.")
            }
            if (model.dueReviewCount > 0) {
                Text("${model.dueReviewCount} review(s) ready")
                Button(
                    enabled = model.accessMode in setOf("free_beta", "paid_subscription"),
                    onClick = onCompleteReview,
                ) {
                    Text("Practice next review")
                }
            }
        }
    }
}

@Composable
private fun AccountPanel(
    model: VoiceSessionUiModel,
    onSupportTextChanged: (String) -> Unit,
    onSubmitSupport: () -> Unit,
    onRequestExport: () -> Unit,
    onDeletionConfirmationChanged: (String) -> Unit,
    onDeleteAccount: () -> Unit,
    onSignOut: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Account and support", style = MaterialTheme.typography.titleSmall)
            OutlinedTextField(
                value = model.supportText,
                onValueChange = onSupportTextChanged,
                label = { Text("Support request") },
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                enabled = model.supportText.length in 10..1000,
                onClick = onSubmitSupport,
            ) {
                Text("Send to support")
            }
            OutlinedButton(onClick = onRequestExport) {
                Text("Generate my data export")
            }
            OutlinedTextField(
                value = model.deletionConfirmation,
                onValueChange = onDeletionConfirmationChanged,
                label = { Text("Type DELETE MY ACCOUNT") },
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedButton(
                enabled = model.deletionConfirmation == "DELETE MY ACCOUNT",
                onClick = onDeleteAccount,
            ) {
                Text("Permanently delete account")
            }
            OutlinedButton(onClick = onSignOut) {
                Text("Sign out")
            }
            model.accountOperationStatus?.let { Text(it) }
        }
    }
}

@Composable
private fun MissionCatalog(
    model: VoiceSessionUiModel,
    onMissionSelected: (String) -> Unit,
    onProcessingConsentChanged: (Boolean) -> Unit,
    onRetentionConsentChanged: (Boolean) -> Unit,
    onStartMission: () -> Unit,
) {
    when {
        model.missionsLoading -> Text("Loading professional missions…")
        model.errorCode != null -> Text("Unable to load missions: ${model.errorCode}")
        model.missions.isEmpty() -> Text("No mission is available right now.")
        else -> {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                model.missions.forEach { mission ->
                    val available = mission.id in model.availableMissionIds &&
                        model.accessMode in setOf("free_beta", "paid_subscription")
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            if (available) onMissionSelected(mission.id)
                        },
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Text(mission.title, style = MaterialTheme.typography.titleMedium)
                            Text(mission.objective)
                            Text(
                                "${mission.durationMinutes} min • ${mission.difficulty}",
                                style = MaterialTheme.typography.bodySmall,
                            )
                            Text(
                                when {
                                    model.accessMode == "unavailable" ->
                                        "Free beta cohort full"
                                    available -> "Available today"
                                    else -> "Locked in your sprint"
                                },
                            )
                            if (available && model.selectedMissionId == mission.id) {
                                ConsentRow(
                                    checked = model.processingConsent,
                                    text = "I consent to voice processing for feedback.",
                                    onChanged = onProcessingConsentChanged,
                                )
                                ConsentRow(
                                    checked = model.retentionConsent,
                                    text = "Keep encrypted learning text for 30 days (optional).",
                                    onChanged = onRetentionConsentChanged,
                                )
                                Button(
                                    enabled = model.processingConsent,
                                    onClick = onStartMission,
                                ) {
                                    Text("Start mission")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ConsentRow(
    checked: Boolean,
    text: String,
    onChanged: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = onChanged)
        Text(text, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun MissionSessionPanel(
    model: VoiceSessionUiModel,
    onCommand: (VoiceSessionCommand) -> Unit,
) {
    Text(
        text = model.missionSessionState.orEmpty(),
        style = MaterialTheme.typography.titleMedium,
    )
    Text("Voice: ${model.state}")
    model.routeName?.let { Text("Audio: $it") }
    model.errorCode?.let { Text("Recoverable issue: $it") }
    VoiceControls(model.state, onCommand)
}

@Composable
private fun VoiceControls(
    state: String,
    onCommand: (VoiceSessionCommand) -> Unit,
) {
    when (state) {
        "IDLE", "ENDED", "ERROR" -> Button(
            onClick = { onCommand(VoiceSessionCommand.Start) },
        ) {
            Text("Start conversation")
        }

        "PAUSED" -> Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(onClick = { onCommand(VoiceSessionCommand.Resume) }) {
                Text("Resume")
            }
            OutlinedButton(onClick = { onCommand(VoiceSessionCommand.Finish) }) {
                Text("Finish")
            }
        }

        else -> Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(onClick = { onCommand(VoiceSessionCommand.Pause) }) {
                Text("Pause")
            }
            OutlinedButton(onClick = { onCommand(VoiceSessionCommand.Finish) }) {
                Text("Finish")
            }
        }
    }
}
