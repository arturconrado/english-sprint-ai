package com.arturconrado.englishsprint

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.arturconrado.englishsprint.domain.VoiceSessionCommand
import com.arturconrado.englishsprint.domain.VoiceSessionState
import com.arturconrado.englishsprint.voice.VoiceSessionService
import com.arturconrado.englishsprint.voice.VoiceSessionSnapshot
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val activityScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var bindingJob: Job? = null
    private var serviceBinder: VoiceSessionService.LocalBinder? = null
    private var bound = false
    private var snapshot by mutableStateOf(VoiceSessionSnapshot())
    private var requestingPermission by mutableStateOf(false)

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { results ->
        requestingPermission = false
        if (requiredPermissions().all { results[it] == true || isGranted(it) }) {
            startVoiceService()
        } else {
            snapshot = VoiceSessionSnapshot(
                state = VoiceSessionState.Error("permission_denied", false),
                errorCode = "permission_denied",
            )
        }
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            serviceBinder = binder as? VoiceSessionService.LocalBinder
            bound = serviceBinder != null
            bindingJob?.cancel()
            bindingJob = activityScope.launch {
                serviceBinder?.snapshots?.collectLatest { snapshot = it }
            }
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            bindingJob?.cancel()
            serviceBinder = null
            bound = false
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            App(
                model = VoiceSessionUiModel(
                    state = if (requestingPermission) {
                        "REQUESTING_PERMISSION"
                    } else {
                        snapshot.state.displayName()
                    },
                    routeName = snapshot.routeName,
                    errorCode = snapshot.errorCode,
                    voiceAvailable = true,
                ),
                onCommand = ::onCommand,
            )
        }
    }

    override fun onStart() {
        super.onStart()
        bindVoiceService(createIfMissing = false)
    }

    override fun onStop() {
        if (bound) {
            unbindService(connection)
            bound = false
        }
        bindingJob?.cancel()
        serviceBinder = null
        super.onStop()
    }

    override fun onDestroy() {
        activityScope.cancel()
        super.onDestroy()
    }

    private fun onCommand(command: VoiceSessionCommand) {
        when (command) {
            VoiceSessionCommand.Start -> requestPermissionsAndStart()
            else -> serviceBinder?.command(command) ?: sendServiceCommand(command)
        }
    }

    private fun requestPermissionsAndStart() {
        val missing = requiredPermissions().filterNot(::isGranted)
        if (missing.isEmpty()) {
            startVoiceService()
        } else {
            requestingPermission = true
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun startVoiceService() {
        startForegroundService(
            Intent(this, VoiceSessionService::class.java)
                .setAction(VoiceSessionService.ACTION_START),
        )
        bindVoiceService(createIfMissing = true)
    }

    private fun sendServiceCommand(command: VoiceSessionCommand) {
        val action = when (command) {
            VoiceSessionCommand.Pause -> VoiceSessionService.ACTION_PAUSE
            VoiceSessionCommand.Resume -> VoiceSessionService.ACTION_RESUME
            VoiceSessionCommand.Finish -> VoiceSessionService.ACTION_FINISH
            VoiceSessionCommand.StopResponse,
            VoiceSessionCommand.Start,
            -> return
        }
        startService(Intent(this, VoiceSessionService::class.java).setAction(action))
    }

    private fun bindVoiceService(createIfMissing: Boolean) {
        if (bound) return
        bindService(
            Intent(this, VoiceSessionService::class.java),
            connection,
            if (createIfMissing) Context.BIND_AUTO_CREATE else 0,
        )
    }

    private fun requiredPermissions(): List<String> = buildList {
        add(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            add(Manifest.permission.BLUETOOTH_CONNECT)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            add(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private fun isGranted(permission: String): Boolean =
        checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED
}

private fun VoiceSessionState.displayName(): String = when (this) {
    VoiceSessionState.Idle -> "IDLE"
    VoiceSessionState.RequestingPermission -> "REQUESTING_PERMISSION"
    VoiceSessionState.Connecting -> "CONNECTING"
    VoiceSessionState.Ready -> "READY"
    VoiceSessionState.Listening -> "LISTENING"
    VoiceSessionState.Processing -> "PROCESSING"
    VoiceSessionState.Speaking -> "SPEAKING"
    VoiceSessionState.Paused -> "PAUSED"
    VoiceSessionState.AudioRouteLost -> "AUDIO_ROUTE_LOST"
    VoiceSessionState.Reconnecting -> "RECONNECTING"
    VoiceSessionState.Ending -> "ENDING"
    VoiceSessionState.Ended -> "ENDED"
    is VoiceSessionState.Error -> "ERROR"
}
