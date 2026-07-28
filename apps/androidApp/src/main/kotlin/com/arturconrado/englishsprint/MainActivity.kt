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
import com.arturconrado.englishsprint.api.KtorMissionApi
import com.arturconrado.englishsprint.domain.Mission
import com.arturconrado.englishsprint.domain.VoiceSessionCommand
import com.arturconrado.englishsprint.domain.VoiceSessionState
import com.arturconrado.englishsprint.mission.MissionSessionTokenStore
import com.arturconrado.englishsprint.mission.StoredMissionSession
import com.arturconrado.englishsprint.networking.createHttpClient
import com.arturconrado.englishsprint.voice.VoiceSessionService
import com.arturconrado.englishsprint.voice.VoiceSessionSnapshot
import java.util.UUID
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
    private var missionsLoading by mutableStateOf(true)
    private var missions by mutableStateOf<List<Mission>>(emptyList())
    private var selectedMissionId by mutableStateOf<String?>(null)
    private var processingConsent by mutableStateOf(false)
    private var retentionConsent by mutableStateOf(false)
    private var missionSessionState by mutableStateOf<String?>(null)
    private var pendingMissionStart = false
    private val httpClient by lazy { createHttpClient() }
    private val missionApi by lazy {
        KtorMissionApi(
            BuildConfig.REALTIME_API_BASE_URL.trimEnd('/'),
            httpClient,
        )
    }
    private val tokenStore by lazy { MissionSessionTokenStore(this) }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { results ->
        requestingPermission = false
        if (requiredPermissions().all { results[it] == true || isGranted(it) }) {
            if (pendingMissionStart) {
                pendingMissionStart = false
                createMissionAndStart()
            }
        } else {
            pendingMissionStart = false
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
                serviceBinder?.snapshots?.collectLatest {
                    snapshot = it
                    it.missionState?.let { state -> missionSessionState = state }
                }
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
                    missions = missions.map {
                        MissionCardUiModel(
                            id = it.id,
                            title = it.title,
                            objective = it.description,
                            durationMinutes = it.expectedDurationMinutes,
                            difficulty = it.difficulty,
                        )
                    },
                    selectedMissionId = selectedMissionId,
                    missionsLoading = missionsLoading,
                    processingConsent = processingConsent,
                    retentionConsent = retentionConsent,
                    missionSessionState = missionSessionState,
                ),
                onCommand = ::onCommand,
                onMissionSelected = {
                    selectedMissionId = it
                    processingConsent = false
                    retentionConsent = false
                },
                onProcessingConsentChanged = { processingConsent = it },
                onRetentionConsentChanged = { retentionConsent = it },
                onStartMission = ::requestPermissionsAndStart,
            )
        }
        restoreSessionOrLoadCatalog()
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
        httpClient.close()
        super.onDestroy()
    }

    private fun onCommand(command: VoiceSessionCommand) {
        when (command) {
            VoiceSessionCommand.Start -> requestPermissionsAndStart()
            else -> serviceBinder?.command(command) ?: sendServiceCommand(command)
        }
    }

    private fun requestPermissionsAndStart() {
        if (selectedMissionId == null || !processingConsent) return
        val missing = requiredPermissions().filterNot(::isGranted)
        if (missing.isEmpty()) {
            createMissionAndStart()
        } else {
            pendingMissionStart = true
            requestingPermission = true
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun createMissionAndStart() {
        val missionId = selectedMissionId ?: return
        missionsLoading = true
        activityScope.launch {
            runCatching {
                missionApi.createSession(
                    missionId = missionId,
                    installationId = installationId(),
                    idempotencyKey = UUID.randomUUID().toString(),
                    processingConsent = processingConsent,
                    contentRetentionConsent = retentionConsent,
                )
            }.onSuccess { created ->
                tokenStore.save(
                    StoredMissionSession(
                        created.session.sessionId,
                        created.bearerToken,
                    ),
                )
                missionSessionState = created.session.state
                startVoiceService(
                    created.session.sessionId,
                    created.bearerToken,
                )
            }.onFailure {
                snapshot = VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("mission_creation_failed", true),
                    errorCode = "mission_creation_failed",
                )
            }
            missionsLoading = false
        }
    }

    private fun startVoiceService(sessionId: String, token: String) {
        startForegroundService(
            Intent(this, VoiceSessionService::class.java)
                .setAction(VoiceSessionService.ACTION_START)
                .putExtra(VoiceSessionService.EXTRA_MISSION_SESSION_ID, sessionId)
                .putExtra(VoiceSessionService.EXTRA_MISSION_SESSION_TOKEN, token),
        )
        bindVoiceService(createIfMissing = true)
    }

    private fun restoreSessionOrLoadCatalog() {
        activityScope.launch {
            tokenStore.load()?.let { stored ->
                runCatching {
                    missionApi.getSession(stored.sessionId, stored.bearerToken)
                }.onSuccess { session ->
                    if (
                        session.state in setOf(
                            "MISSION_COMPLETED",
                            "MISSION_CANCELLED",
                            "MISSION_FAILED",
                        )
                    ) {
                        tokenStore.clear()
                    } else {
                        missionSessionState = session.state
                    }
                }.onFailure {
                    tokenStore.clear()
                }
            }
            runCatching { missionApi.listMissions() }
                .onSuccess { missions = it }
                .onFailure {
                    snapshot = VoiceSessionSnapshot(
                        state = VoiceSessionState.Error("mission_catalog_unavailable", true),
                        errorCode = "mission_catalog_unavailable",
                    )
                }
            missionsLoading = false
        }
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

    private fun installationId(): String {
        val preferences = getSharedPreferences("voice_installation", MODE_PRIVATE)
        return preferences.getString("anonymous_installation_id", null)
            ?: UUID.randomUUID().toString().also {
                preferences.edit().putString("anonymous_installation_id", it).apply()
            }
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
