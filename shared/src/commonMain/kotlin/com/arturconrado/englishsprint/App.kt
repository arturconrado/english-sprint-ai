package com.arturconrado.englishsprint

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
    val missionSessionState: String? = null,
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
    onStartMission: () -> Unit = {},
) {
    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier.padding(24.dp),
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
                } else if (model.missionSessionState != null) {
                    MissionSessionPanel(model, onCommand)
                } else {
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
            LazyColumn(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(model.missions, key = { it.id }) { mission ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { onMissionSelected(mission.id) },
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
                            if (model.selectedMissionId == mission.id) {
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
