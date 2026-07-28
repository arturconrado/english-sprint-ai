package com.arturconrado.englishsprint.voice

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import com.arturconrado.englishsprint.BuildConfig
import com.arturconrado.englishsprint.MainActivity
import com.arturconrado.englishsprint.api.KtorRealtimeSessionApi
import com.arturconrado.englishsprint.api.KtorMissionApi
import com.arturconrado.englishsprint.api.MissionCallAuthorization
import com.arturconrado.englishsprint.domain.VoiceSessionCommand
import com.arturconrado.englishsprint.domain.VoiceSessionState
import com.arturconrado.englishsprint.networking.createHttpClient
import com.arturconrado.englishsprint.voice.rtc.AndroidWebRtcSessionFactory
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull

class VoiceSessionService : Service() {
    private val serviceJob = SupervisorJob()
    private val scope = CoroutineScope(serviceJob + Dispatchers.Main.immediate)
    private val binder = LocalBinder()
    private val mutableSnapshots = MutableStateFlow(VoiceSessionSnapshot())
    private var engine: VoiceSessionEngine? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private lateinit var mediaSession: MediaSession
    private val httpClient by lazy { createHttpClient() }

    inner class LocalBinder : Binder() {
        val snapshots: StateFlow<VoiceSessionSnapshot>
            get() = mutableSnapshots

        fun command(command: VoiceSessionCommand) {
            dispatch(command)
        }
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        mediaSession = MediaSession(this, "EnglishSprintVoice").apply {
            setCallback(
                object : MediaSession.Callback() {
                    override fun onPlay() = dispatch(VoiceSessionCommand.Resume)
                    override fun onPause() = dispatch(VoiceSessionCommand.Pause)
                    override fun onStop() = dispatch(VoiceSessionCommand.Finish)
                },
            )
            isActive = true
        }
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startSession(
                intent.getStringExtra(EXTRA_MISSION_SESSION_ID),
                intent.getStringExtra(EXTRA_MISSION_SESSION_TOKEN),
            )
            ACTION_PAUSE -> dispatch(VoiceSessionCommand.Pause)
            ACTION_RESUME -> dispatch(VoiceSessionCommand.Resume)
            ACTION_FINISH -> finishSession(
                intent.getStringExtra(EXTRA_TERMINATION_REASON) ?: "notification_action",
            )
        }
        return START_NOT_STICKY
    }

    private fun startSession(
        missionSessionId: String?,
        missionSessionToken: String?,
    ) {
        startForeground(NOTIFICATION_ID, notification("CONNECTING", null))
        if (!requiredPermissionsGranted()) {
            updateSnapshot(
                VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("permission_denied", false),
                    errorCode = "permission_denied",
                ),
            )
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return
        }
        if (
            !VoiceEndpointPolicy.isAllowed(
                BuildConfig.REALTIME_API_BASE_URL,
                BuildConfig.DEBUG,
            )
        ) {
            updateSnapshot(
                VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("insecure_backend_url", false),
                    errorCode = "insecure_backend_url",
                ),
            )
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return
        }
        scope.launch {
            engine?.finish("server_shutdown")
            releaseWakeLock()
            acquireWakeLock()

            val preferences = getSharedPreferences("voice_installation", MODE_PRIVATE)
            val installationId = preferences.getString(INSTALLATION_ID_KEY, null)
                ?: UUID.randomUUID().toString().also {
                    preferences.edit().putString(INSTALLATION_ID_KEY, it).apply()
                }
            val newEngine = VoiceSessionEngine(
                context = this@VoiceSessionService,
                scope = scope,
                api = KtorRealtimeSessionApi(
                    baseUrl = BuildConfig.REALTIME_API_BASE_URL.trimEnd('/'),
                    client = httpClient,
                ),
                rtcFactory = AndroidWebRtcSessionFactory(this@VoiceSessionService),
                installationId = installationId,
                missionApi = KtorMissionApi(
                    baseUrl = BuildConfig.REALTIME_API_BASE_URL.trimEnd('/'),
                    client = httpClient,
                ),
                missionAuthorization = if (
                    missionSessionId != null && missionSessionToken != null
                ) {
                    MissionCallAuthorization(missionSessionId, missionSessionToken)
                } else {
                    null
                },
                onSnapshot = ::updateSnapshot,
            )
            engine = newEngine
            newEngine.start()
        }
    }

    private fun dispatch(command: VoiceSessionCommand) {
        if (command == VoiceSessionCommand.Finish) {
            finishSession("user_finished")
            return
        }
        scope.launch { engine?.command(command) }
    }

    private fun finishSession(reason: String) {
        scope.launch {
            engine?.finish(reason)
            releaseWakeLock()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun updateSnapshot(snapshot: VoiceSessionSnapshot) {
        mutableSnapshots.value = snapshot
        val stateName = snapshot.state.displayName()
        if (::mediaSession.isInitialized) {
            mediaSession.setPlaybackState(
                PlaybackState.Builder()
                    .setActions(
                        PlaybackState.ACTION_PLAY or
                            PlaybackState.ACTION_PAUSE or
                            PlaybackState.ACTION_STOP,
                    )
                    .setState(
                        if (snapshot.state == VoiceSessionState.Paused) {
                            PlaybackState.STATE_PAUSED
                        } else {
                            PlaybackState.STATE_PLAYING
                        },
                        PlaybackState.PLAYBACK_POSITION_UNKNOWN,
                        1f,
                    )
                    .build(),
            )
        }
        getSystemService(NotificationManager::class.java).notify(
            NOTIFICATION_ID,
            notification(stateName, snapshot.routeName),
        )
    }

    private fun notification(state: String, route: String?): Notification {
        val contentIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val paused = state == "PAUSED"
        val toggleAction = if (paused) ACTION_RESUME else ACTION_PAUSE
        val toggleLabel = if (paused) "Continue" else "Pause"
        return Notification.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setSmallIcon(com.arturconrado.englishsprint.R.drawable.ic_launcher)
            .setContentTitle("English Sprint AI")
            .setContentText(
                listOfNotNull(state, route).joinToString(" • "),
            )
            .setContentIntent(contentIntent)
            .setOngoing(state !in setOf("ENDED", "ERROR"))
            .setCategory(Notification.CATEGORY_SERVICE)
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .addAction(
                Notification.Action.Builder(
                    null,
                    toggleLabel,
                    serviceAction(toggleAction, 1),
                ).build(),
            )
            .addAction(
                Notification.Action.Builder(
                    null,
                    "Finish",
                    serviceAction(ACTION_FINISH, 2),
                ).build(),
            )
            .setStyle(
                Notification.MediaStyle()
                    .setMediaSession(mediaSession.sessionToken)
                    .setShowActionsInCompactView(0, 1),
            )
            .build()
    }

    private fun serviceAction(action: String, requestCode: Int): PendingIntent =
        PendingIntent.getService(
            this,
            requestCode,
            Intent(this, VoiceSessionService::class.java).setAction(action),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            NOTIFICATION_CHANNEL_ID,
            "Voice conversations",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Active English Sprint voice conversation"
            setSound(null, null)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun requiredPermissionsGranted(): Boolean {
        val permissions = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                add(Manifest.permission.BLUETOOTH_CONNECT)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        return permissions.all { checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }
    }

    private fun acquireWakeLock() {
        val powerManager = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "EnglishSprint:VoiceSession",
        ).apply {
            setReferenceCounted(false)
            acquire(MAX_SESSION_MILLIS)
        }
    }

    private fun releaseWakeLock() {
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        finishSession("app_removed")
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        runBlocking {
            withTimeoutOrNull(2_000) {
                engine?.finish("server_shutdown")
            }
        }
        releaseWakeLock()
        if (::mediaSession.isInitialized) {
            mediaSession.isActive = false
            mediaSession.release()
        }
        httpClient.close()
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "com.arturconrado.englishsprint.voice.START"
        const val ACTION_PAUSE = "com.arturconrado.englishsprint.voice.PAUSE"
        const val ACTION_RESUME = "com.arturconrado.englishsprint.voice.RESUME"
        const val ACTION_FINISH = "com.arturconrado.englishsprint.voice.FINISH"
        const val EXTRA_TERMINATION_REASON = "termination_reason"
        const val EXTRA_MISSION_SESSION_ID = "mission_session_id"
        const val EXTRA_MISSION_SESSION_TOKEN = "mission_session_token"
        private const val NOTIFICATION_CHANNEL_ID = "voice_session"
        private const val NOTIFICATION_ID = 1001
        private const val INSTALLATION_ID_KEY = "anonymous_installation_id"
        private const val MAX_SESSION_MILLIS = 30 * 60 * 1000L
    }
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
