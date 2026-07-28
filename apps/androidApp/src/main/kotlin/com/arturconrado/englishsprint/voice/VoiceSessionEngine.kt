package com.arturconrado.englishsprint.voice

import android.content.Context
import android.os.SystemClock
import com.arturconrado.englishsprint.api.RealtimeSessionApi
import com.arturconrado.englishsprint.api.MissionApi
import com.arturconrado.englishsprint.api.MissionCallAuthorization
import com.arturconrado.englishsprint.domain.MissionCommand
import com.arturconrado.englishsprint.domain.AttemptKind
import com.arturconrado.englishsprint.domain.HelpLevel
import com.arturconrado.englishsprint.domain.MissionAttempt
import com.arturconrado.englishsprint.domain.LocalVoiceCommand
import com.arturconrado.englishsprint.domain.VoiceSessionCommand
import com.arturconrado.englishsprint.domain.VoiceSessionEffect
import com.arturconrado.englishsprint.domain.VoiceSessionEvent
import com.arturconrado.englishsprint.domain.VoiceSessionReducer
import com.arturconrado.englishsprint.domain.VoiceSessionState
import com.arturconrado.englishsprint.voice.audio.BluetoothAudioRouteController
import com.arturconrado.englishsprint.voice.audio.VoiceAudioFocus
import com.arturconrado.englishsprint.voice.commands.LocalCommandDetector
import com.arturconrado.englishsprint.voice.commands.VoskLocalCommandDetector
import com.arturconrado.englishsprint.voice.rtc.RtcEvent
import com.arturconrado.englishsprint.voice.rtc.RtcSession
import com.arturconrado.englishsprint.voice.rtc.RtcSessionFactory
import java.util.UUID
import kotlin.time.Clock
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class VoiceSessionSnapshot(
    val state: VoiceSessionState = VoiceSessionState.Idle,
    val routeName: String? = null,
    val errorCode: String? = null,
    val missionState: String? = null,
)

class VoiceSessionEngine(
    context: Context,
    private val scope: CoroutineScope,
    private val api: RealtimeSessionApi,
    private val rtcFactory: RtcSessionFactory,
    private val installationId: String,
    private val missionApi: MissionApi? = null,
    private val missionAuthorization: MissionCallAuthorization? = null,
    private val onSnapshot: (VoiceSessionSnapshot) -> Unit,
) {
    private val mutex = Mutex()
    private val telemetry = VoiceTelemetry()
    private val audioRoute: BluetoothAudioRouteController =
        BluetoothAudioRouteController(context) {
            scheduleAudioRouteRecovery()
        }
    private val audioFocus: VoiceAudioFocus = VoiceAudioFocus(context) {
        scope.launch { command(VoiceSessionCommand.Pause) }
    }
    private val detector: LocalCommandDetector = VoskLocalCommandDetector(context, scope) {
        scope.launch { localCommand(it) }
    }
    private var state: VoiceSessionState = VoiceSessionState.Idle
    private var rtcSession: RtcSession? = null
    private var backendSessionId: String? = null
    private var reconnectJob: Job? = null
    private var routeRecoveryJob: Job? = null
    private val generationGate = SessionGenerationGate()
    private var closed = false
    private var attemptStartedAt: String? = null
    private var helpLevel = HelpLevel.NO_HELP
    private var usedTimeExtension = false
    private var canonicalMissionState: String? = null

    suspend fun start(): Unit = mutex.withLock {
        if (closed || state !in setOf(VoiceSessionState.Idle, VoiceSessionState.Ended)) return
        transition(VoiceSessionEvent.StartRequested)
        transition(VoiceSessionEvent.PermissionResult(granted = true))
        if (!audioFocus.acquire()) {
            fail("audio_focus_unavailable", recoverable = true)
            return
        }
        if (!audioRoute.acquire()) {
            fail("bluetooth_route_unavailable", recoverable = true)
            audioRoute.release()
            audioFocus.release()
            return
        }
        publish()
        runCatching { detector.start() }.onFailure {
            fail("offline_command_model_failed", recoverable = false)
            releaseNativeResources()
            return
        }
        connectRealtime()
    }

    suspend fun command(command: VoiceSessionCommand) {
        when (command) {
            VoiceSessionCommand.Start -> start()
            VoiceSessionCommand.Finish -> finish("user_finished")
            else -> mutex.withLock {
                when (command) {
                    VoiceSessionCommand.StopResponse -> {
                        transition(VoiceSessionEvent.UserSpeechStarted)
                    }

                    VoiceSessionCommand.Pause -> {
                        transition(VoiceSessionEvent.PauseRequested)
                        rtcSession?.pause()
                    }

                    VoiceSessionCommand.Resume -> {
                        if (state == VoiceSessionState.Paused) {
                            rtcSession?.resume()
                            transition(VoiceSessionEvent.ResumeRequested)
                        }
                    }

                    VoiceSessionCommand.Start,
                    VoiceSessionCommand.Finish,
                    -> Unit
                }
            }
        }
    }

    private suspend fun localCommand(command: LocalVoiceCommand) {
        telemetry.event("offline_command", mapOf("command" to command.name))
        when (command) {
            LocalVoiceCommand.StopResponse -> this.command(VoiceSessionCommand.StopResponse)
            LocalVoiceCommand.Pause -> this.command(VoiceSessionCommand.Pause)
            LocalVoiceCommand.Resume -> this.command(VoiceSessionCommand.Resume)
            LocalVoiceCommand.Finish -> finish("offline_command")
            LocalVoiceCommand.RepeatPrompt -> sendMissionCommand(MissionCommand.RepeatPrompt)
            LocalVoiceCommand.NeedMoreTime -> {
                sendMissionCommand(MissionCommand.NeedMoreTime)
                usedTimeExtension = true
            }

            LocalVoiceCommand.RequestHelp -> {
                sendMissionCommand(MissionCommand.RequestHelp)
                helpLevel = HelpLevel.FIRST_WORD
            }
        }
    }

    private suspend fun sendMissionCommand(command: MissionCommand) {
        val authorization = missionAuthorization ?: return
        val api = missionApi ?: return
        val canonical = api.getSession(
            authorization.sessionId,
            authorization.bearerToken,
        )
        api.sendCommand(
            sessionId = authorization.sessionId,
            token = authorization.bearerToken,
            idempotencyKey = UUID.randomUUID().toString(),
            command = command,
            stateVersion = canonical.stateVersion,
        )
        canonicalMissionState = canonical.state
        publish()
    }

    private suspend fun connectRealtime() {
        try {
            val generation = generationGate.next()
            val rtc = rtcFactory.create(
                onEvent = { event -> scope.launch { handleRtcEvent(generation, event) } },
                onAudioFrame = detector::offer,
            )
            rtcSession = rtc
            val offer = rtc.createOffer()
            val answer = api.createCall(
                sdpOffer = offer,
                installationId = installationId,
                idempotencyKey = UUID.randomUUID().toString(),
                missionAuthorization = missionAuthorization,
            )
            backendSessionId = answer.sessionId
            rtc.acceptAnswer(answer.sdpAnswer)
            transition(VoiceSessionEvent.Connected)
            transition(VoiceSessionEvent.ResponseEnded)
        } catch (_: Exception) {
            fail("realtime_connection_failed", recoverable = true)
            releaseCall("network_failure")
        }
    }

    private suspend fun handleRtcEvent(generation: Int, event: RtcEvent) = mutex.withLock {
        if (closed || !generationGate.accepts(generation)) return@withLock
        when (event) {
            RtcEvent.Connected -> {
                reconnectJob?.cancel()
                reconnectJob = null
                if (state == VoiceSessionState.Reconnecting) {
                    transition(VoiceSessionEvent.ResponseEnded)
                }
            }

            RtcEvent.Disconnected -> scheduleReconnect()
            RtcEvent.UserSpeechStarted -> {
                attemptStartedAt = Clock.System.now().toString()
                val interruptionStarted = SystemClock.elapsedRealtime()
                val wasResponding =
                    state == VoiceSessionState.Speaking ||
                        state == VoiceSessionState.Processing
                transition(VoiceSessionEvent.UserSpeechStarted)
                if (wasResponding) {
                    telemetry.duration(
                        "barge_in",
                        SystemClock.elapsedRealtime() - interruptionStarted,
                    )
                }
            }

            RtcEvent.UserSpeechEnded -> {
                transition(VoiceSessionEvent.UserSpeechEnded)
                scope.launch { submitAttempt() }
            }
            RtcEvent.ResponseStarted -> transition(VoiceSessionEvent.ResponseStarted)
            RtcEvent.ResponseEnded -> transition(VoiceSessionEvent.ResponseEnded)
            is RtcEvent.Failure -> fail(event.code, recoverable = true)
        }
    }

    private suspend fun submitAttempt() {
        val authorization = missionAuthorization ?: return
        val api = missionApi ?: return
        runCatching {
            val canonical = api.getSession(
                authorization.sessionId,
                authorization.bearerToken,
            )
            val kind = when (canonical.state) {
                "FIRST_ATTEMPT_WAITING" -> AttemptKind.FIRST
                "RETRY_WAITING" -> AttemptKind.RETRY
                "TRANSFER_WAITING" -> AttemptKind.TRANSFER
                else -> return
            }
            val completedAt = Clock.System.now().toString()
            api.createAttempt(
                sessionId = authorization.sessionId,
                token = authorization.bearerToken,
                idempotencyKey = UUID.randomUUID().toString(),
                attempt = MissionAttempt(
                    clientAttemptId = UUID.randomUUID().toString(),
                    stateVersion = canonical.stateVersion,
                    kind = kind,
                    helpLevel = helpLevel,
                    startedAt = attemptStartedAt ?: completedAt,
                    completedAt = completedAt,
                    usedTimeExtension = usedTimeExtension,
                ),
            )
        }.onSuccess { receipt ->
            canonicalMissionState = receipt.state
            attemptStartedAt = null
            helpLevel = HelpLevel.NO_HELP
            usedTimeExtension = false
            publish()
        }.onFailure {
            fail("attempt_submission_failed", recoverable = true)
        }
    }

    private fun scheduleReconnect() {
        if (reconnectJob?.isActive == true || closed) return
        telemetry.event("network_reconnect_started")
        transition(VoiceSessionEvent.ReconnectStarted)
        reconnectJob = scope.launch {
            val delays = VoiceRecoveryPolicy.networkBackoffMillis
            for ((index, backoff) in delays.withIndex()) {
                delay(backoff)
                if (state != VoiceSessionState.Reconnecting) return@launch
                if (index == 0) {
                    rtcSession?.restartIce()
                } else {
                    mutex.withLock {
                        releaseCall("network_failure")
                        transition(VoiceSessionEvent.ReconnectStarted)
                        connectRealtime()
                    }
                }
                if (state != VoiceSessionState.Reconnecting) return@launch
            }
            mutex.withLock {
                fail("network_recovery_exhausted", recoverable = true)
                finishLocked("network_failure")
            }
        }
    }

    private fun scheduleAudioRouteRecovery() {
        if (routeRecoveryJob?.isActive == true || closed) return
        telemetry.event("audio_route_lost")
        routeRecoveryJob = scope.launch {
            mutex.withLock {
                if (
                    closed ||
                    state == VoiceSessionState.Ending ||
                    state == VoiceSessionState.Ended
                ) {
                    return@launch
                }
                transition(VoiceSessionEvent.RouteLost)
                rtcSession?.pause()
                audioRoute.release()
            }
            repeat(VoiceRecoveryPolicy.bluetoothAttempts) {
                delay(VoiceRecoveryPolicy.bluetoothAttemptDelayMillis)
                if (audioRoute.acquire()) {
                    mutex.withLock {
                        if (closed) {
                            audioRoute.release()
                        } else {
                            rtcSession?.resume()
                            transition(VoiceSessionEvent.RouteRestored)
                            telemetry.event("audio_route_restored")
                        }
                    }
                    return@launch
                }
            }
            finish("route_lost_timeout")
        }
    }

    suspend fun finish(reason: String) = mutex.withLock {
        finishLocked(reason)
    }

    private suspend fun finishLocked(reason: String) {
        if (closed || state == VoiceSessionState.Ending || state == VoiceSessionState.Ended) return
        transition(VoiceSessionEvent.FinishRequested)
        reconnectJob?.cancel()
        reconnectJob = null
        routeRecoveryJob?.cancel()
        routeRecoveryJob = null
        releaseCall(reason)
        missionAuthorization?.let { authorization ->
            runCatching {
                missionApi?.cancel(
                    authorization.sessionId,
                    authorization.bearerToken,
                    UUID.randomUUID().toString(),
                )
            }
        }
        releaseNativeResources()
        closed = true
        transition(VoiceSessionEvent.CleanupCompleted)
    }

    private suspend fun releaseCall(reason: String) {
        generationGate.invalidate()
        rtcSession?.close()
        rtcSession = null
        backendSessionId?.let { sessionId ->
            runCatching { api.deleteCall(sessionId, reason) }
        }
        backendSessionId = null
    }

    private fun releaseNativeResources() {
        detector.close()
        rtcSession?.close()
        rtcSession = null
        audioRoute.release()
        audioFocus.release()
    }

    private fun transition(event: VoiceSessionEvent) {
        val result = VoiceSessionReducer.reduce(state, event)
        state = result.state
        applyImmediateEffects(result.effects)
        publish()
    }

    private fun applyImmediateEffects(effects: List<VoiceSessionEffect>) {
        effects.forEach { effect ->
            when (effect) {
                VoiceSessionEffect.CancelRemoteResponse -> rtcSession?.interruptResponse()
                VoiceSessionEffect.PauseMedia -> rtcSession?.pause()
                VoiceSessionEffect.ResumeMedia -> rtcSession?.resume()
                else -> Unit
            }
        }
    }

    private fun fail(code: String, recoverable: Boolean) {
        state = VoiceSessionState.Error(code, recoverable)
        publish()
    }

    private fun publish() {
        val error = (state as? VoiceSessionState.Error)?.code
        onSnapshot(
            VoiceSessionSnapshot(
                state = state,
                routeName = audioRoute.routeName(),
                errorCode = error,
                missionState = canonicalMissionState,
            ),
        )
    }
}
