package com.arturconrado.englishsprint.voice.rtc

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaRecorder
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.webrtc.AudioSource
import org.webrtc.AudioTrack
import org.webrtc.DataChannel
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.audio.JavaAudioDeviceModule

class AndroidWebRtcSessionFactory(
    private val context: Context,
) : RtcSessionFactory {
    override fun create(
        onEvent: (RtcEvent) -> Unit,
        onAudioFrame: (RtcAudioFrame) -> Unit,
    ): RtcSession = AndroidWebRtcSession(
        context = context,
        onEvent = onEvent,
        onAudioFrame = onAudioFrame,
    )
}

private class AndroidWebRtcSession(
    context: Context,
    private val onEvent: (RtcEvent) -> Unit,
    onAudioFrame: (RtcAudioFrame) -> Unit,
) : RtcSession {
    private val applicationContext = context.applicationContext
    private val iceGatheringComplete = CompletableDeferred<Unit>()
    private val closed = AtomicBoolean(false)
    private val paused = AtomicBoolean(false)
    private val discardCurrentResponse = AtomicBoolean(false)
    private var remoteAudioTrack: AudioTrack? = null

    private val audioDeviceModule = JavaAudioDeviceModule.builder(applicationContext)
        .setAudioSource(MediaRecorder.AudioSource.VOICE_COMMUNICATION)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build(),
        )
        .setUseHardwareAcousticEchoCanceler(true)
        .setUseHardwareNoiseSuppressor(true)
        .setSamplesReadyCallback { samples ->
            onAudioFrame(
                RtcAudioFrame(
                    pcm16 = samples.data.copyOf(),
                    sampleRate = samples.sampleRate,
                    channelCount = samples.channelCount,
                ),
            )
        }
        .createAudioDeviceModule()

    private val factory: PeerConnectionFactory
    private val audioSource: AudioSource
    private val localAudioTrack: AudioTrack
    private val peerConnection: PeerConnection
    private var dataChannel: DataChannel

    init {
        initializeWebRtc(applicationContext)
        factory = PeerConnectionFactory.builder()
            .setAudioDeviceModule(audioDeviceModule)
            .createPeerConnectionFactory()
        audioSource = factory.createAudioSource(MediaConstraints())
        localAudioTrack = factory.createAudioTrack("english-sprint-microphone", audioSource)
        val configuration = PeerConnection.RTCConfiguration(emptyList()).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
        }
        peerConnection = requireNotNull(
            factory.createPeerConnection(configuration, createPeerObserver()),
        ) {
            "Unable to create the WebRTC peer connection"
        }
        peerConnection.addTrack(localAudioTrack, listOf("english-sprint"))
        dataChannel = peerConnection.createDataChannel("oai-events", DataChannel.Init())
        registerDataChannel(dataChannel)
    }

    override suspend fun createOffer(): String {
        val offer = CompletableDeferred<SessionDescription>()
        peerConnection.createOffer(
            object : SdpObserverAdapter() {
                override fun onCreateSuccess(description: SessionDescription) {
                    offer.complete(description)
                }

                override fun onCreateFailure(error: String) {
                    offer.completeExceptionally(IllegalStateException("offer_failed:$error"))
                }
            },
            MediaConstraints().apply {
                mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
            },
        )
        val description = withTimeout(8_000) { offer.await() }
        setLocalDescription(description)
        if (peerConnection.iceGatheringState() != PeerConnection.IceGatheringState.COMPLETE) {
            withTimeout(8_000) { iceGatheringComplete.await() }
        }
        return requireNotNull(peerConnection.localDescription).description
    }

    override suspend fun acceptAnswer(sdpAnswer: String) {
        val completed = CompletableDeferred<Unit>()
        peerConnection.setRemoteDescription(
            object : SdpObserverAdapter() {
                override fun onSetSuccess() {
                    completed.complete(Unit)
                }

                override fun onSetFailure(error: String) {
                    completed.completeExceptionally(IllegalStateException("answer_failed:$error"))
                }
            },
            SessionDescription(SessionDescription.Type.ANSWER, sdpAnswer),
        )
        withTimeout(8_000) { completed.await() }
    }

    private suspend fun setLocalDescription(description: SessionDescription) {
        val completed = CompletableDeferred<Unit>()
        peerConnection.setLocalDescription(
            object : SdpObserverAdapter() {
                override fun onSetSuccess() {
                    completed.complete(Unit)
                }

                override fun onSetFailure(error: String) {
                    completed.completeExceptionally(
                        IllegalStateException("local_description_failed:$error"),
                    )
                }
            },
            description,
        )
        withTimeout(8_000) { completed.await() }
    }

    override fun pause() {
        paused.set(true)
        localAudioTrack.setEnabled(false)
        remoteAudioTrack?.setEnabled(false)
    }

    override fun resume() {
        paused.set(false)
        localAudioTrack.setEnabled(true)
        if (!discardCurrentResponse.get()) {
            remoteAudioTrack?.setEnabled(true)
        }
    }

    override fun interruptResponse() {
        discardCurrentResponse.set(true)
        remoteAudioTrack?.setEnabled(false)
        sendEvent("""{"type":"response.cancel"}""")
        sendEvent("""{"type":"output_audio_buffer.clear"}""")
    }

    override fun restartIce() {
        peerConnection.restartIce()
    }

    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        dataChannel.unregisterObserver()
        dataChannel.close()
        dataChannel.dispose()
        peerConnection.close()
        peerConnection.dispose()
        localAudioTrack.dispose()
        audioSource.dispose()
        factory.dispose()
        audioDeviceModule.release()
    }

    private fun sendEvent(value: String) {
        if (dataChannel.state() != DataChannel.State.OPEN) return
        dataChannel.send(
            DataChannel.Buffer(
                ByteBuffer.wrap(value.toByteArray(StandardCharsets.UTF_8)),
                false,
            ),
        )
    }

    private fun registerDataChannel(channel: DataChannel) {
        channel.registerObserver(
            object : DataChannel.Observer {
                override fun onBufferedAmountChange(previousAmount: Long) = Unit

                override fun onStateChange() = Unit

                override fun onMessage(buffer: DataChannel.Buffer) {
                    if (buffer.binary) return
                    val bytes = ByteArray(buffer.data.remaining())
                    buffer.data.get(bytes)
                    val type = runCatching {
                        Json.parseToJsonElement(bytes.toString(StandardCharsets.UTF_8))
                            .jsonObject["type"]
                            ?.jsonPrimitive
                            ?.content
                    }.getOrNull()
                    when (type) {
                        "input_audio_buffer.speech_started" ->
                            onEvent(RtcEvent.UserSpeechStarted)

                        "input_audio_buffer.speech_stopped" ->
                            onEvent(RtcEvent.UserSpeechEnded)

                        "response.created" -> {
                            discardCurrentResponse.set(false)
                            if (!paused.get()) {
                                remoteAudioTrack?.setEnabled(true)
                            }
                            onEvent(RtcEvent.ResponseStarted)
                        }

                        "response.output_audio.delta" ->
                            onEvent(RtcEvent.ResponseStarted)

                        "response.done", "response.cancelled" ->
                            onEvent(RtcEvent.ResponseEnded)

                        "error" -> onEvent(RtcEvent.Failure("provider_event_error"))
                    }
                }
            },
        )
    }

    private fun createPeerObserver(): PeerConnection.Observer = object : PeerConnection.Observer {
        override fun onSignalingChange(state: PeerConnection.SignalingState) = Unit

        override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) {
            when (state) {
                PeerConnection.IceConnectionState.CONNECTED,
                PeerConnection.IceConnectionState.COMPLETED,
                -> onEvent(RtcEvent.Connected)

                PeerConnection.IceConnectionState.DISCONNECTED,
                PeerConnection.IceConnectionState.FAILED,
                PeerConnection.IceConnectionState.CLOSED,
                -> onEvent(RtcEvent.Disconnected)

                else -> Unit
            }
        }

        override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit

        override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {
            if (state == PeerConnection.IceGatheringState.COMPLETE) {
                iceGatheringComplete.complete(Unit)
            }
        }

        override fun onIceCandidate(candidate: IceCandidate) = Unit

        override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) = Unit

        override fun onAddStream(stream: MediaStream) = Unit

        override fun onRemoveStream(stream: MediaStream) = Unit

        override fun onDataChannel(channel: DataChannel) {
            dataChannel.unregisterObserver()
            dataChannel = channel
            registerDataChannel(channel)
        }

        override fun onRenegotiationNeeded() = Unit

        override fun onAddTrack(receiver: RtpReceiver, mediaStreams: Array<out MediaStream>) {
            remoteAudioTrack = receiver.track() as? AudioTrack
        }
    }

    private open class SdpObserverAdapter : SdpObserver {
        override fun onCreateSuccess(description: SessionDescription) = Unit
        override fun onSetSuccess() = Unit
        override fun onCreateFailure(error: String) = Unit
        override fun onSetFailure(error: String) = Unit
    }

    companion object {
        private val initialized = AtomicBoolean(false)

        private fun initializeWebRtc(context: Context) {
            if (initialized.compareAndSet(false, true)) {
                PeerConnectionFactory.initialize(
                    PeerConnectionFactory.InitializationOptions.builder(context)
                        .setEnableInternalTracer(false)
                        .createInitializationOptions(),
                )
            }
        }
    }
}
