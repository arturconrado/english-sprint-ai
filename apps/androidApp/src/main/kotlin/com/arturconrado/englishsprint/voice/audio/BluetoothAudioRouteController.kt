package com.arturconrado.englishsprint.voice.audio

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull

class BluetoothAudioRouteController(
    context: Context,
    private val onRouteLost: () -> Unit,
) {
    private val applicationContext = context.applicationContext
    private val audioManager =
        applicationContext.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var activeDeviceId: Int? = null
    private var scoReceiver: BroadcastReceiver? = null

    private val deviceCallback = object : AudioDeviceCallback() {
        override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>) {
            val active = activeDeviceId ?: return
            if (removedDevices.any { it.id == active }) onRouteLost()
        }
    }

    @SuppressLint("MissingPermission")
    suspend fun acquire(): Boolean {
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        audioManager.registerAudioDeviceCallback(deviceCallback, null)
        val acquired = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val device = audioManager.availableCommunicationDevices.firstOrNull {
                it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                    it.type == AudioDeviceInfo.TYPE_BLE_HEADSET
            }
            if (device != null && audioManager.setCommunicationDevice(device)) {
                activeDeviceId = device.id
                true
            } else {
                false
            }
        } else {
            acquireLegacySco()
        }
        if (!acquired) release()
        return acquired
    }

    @Suppress("DEPRECATION")
    private suspend fun acquireLegacySco(): Boolean {
        if (!audioManager.isBluetoothScoAvailableOffCall) return false
        val result = CompletableDeferred<Boolean>()
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                val state = intent?.getIntExtra(
                    AudioManager.EXTRA_SCO_AUDIO_STATE,
                    AudioManager.SCO_AUDIO_STATE_ERROR,
                )
                when (state) {
                    AudioManager.SCO_AUDIO_STATE_CONNECTED -> result.complete(true)
                    AudioManager.SCO_AUDIO_STATE_DISCONNECTED,
                    AudioManager.SCO_AUDIO_STATE_ERROR,
                    -> if (!result.isCompleted) result.complete(false)
                }
            }
        }
        scoReceiver = receiver
        val filter = IntentFilter(AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            applicationContext.registerReceiver(
                receiver,
                filter,
                Context.RECEIVER_NOT_EXPORTED,
            )
        } else {
            applicationContext.registerReceiver(receiver, filter)
        }
        audioManager.startBluetoothSco()
        return withTimeoutOrNull(5_000) { result.await() } ?: false
    }

    @SuppressLint("MissingPermission")
    fun routeName(): String? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        audioManager.communicationDevice
            ?.takeIf {
                it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                    it.type == AudioDeviceInfo.TYPE_BLE_HEADSET
            }
            ?.productName
            ?.toString()
    } else {
        @Suppress("DEPRECATION")
        if (audioManager.isBluetoothScoOn) "Bluetooth SCO" else null
    }

    @Suppress("DEPRECATION")
    fun release() {
        runCatching { audioManager.unregisterAudioDeviceCallback(deviceCallback) }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            audioManager.clearCommunicationDevice()
        } else {
            audioManager.stopBluetoothSco()
        }
        scoReceiver?.let { receiver ->
            runCatching { applicationContext.unregisterReceiver(receiver) }
        }
        scoReceiver = null
        activeDeviceId = null
        audioManager.mode = AudioManager.MODE_NORMAL
    }
}
