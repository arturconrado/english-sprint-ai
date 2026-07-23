package com.arturconrado.englishsprint

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
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
)

@Composable
fun App(
    model: VoiceSessionUiModel = VoiceSessionUiModel(),
    onCommand: (VoiceSessionCommand) -> Unit = {},
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
                Text(
                    text = if (model.voiceAvailable) model.state else {
                        "Voice unavailable on ${platformName()}"
                    },
                    style = MaterialTheme.typography.titleMedium,
                )
                model.routeName?.let { Text("Audio: $it") }
                model.errorCode?.let { Text("Error: $it") }
                if (model.voiceAvailable) {
                    VoiceControls(model.state, onCommand)
                }
            }
        }
    }
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
