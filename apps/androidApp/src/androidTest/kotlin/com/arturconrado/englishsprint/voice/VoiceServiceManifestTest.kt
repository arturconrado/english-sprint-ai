package com.arturconrado.englishsprint.voice

import android.content.Context
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class VoiceServiceManifestTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test
    fun voice_service_is_private_non_sticky_and_has_required_foreground_types() {
        val service = context.packageManager.getServiceInfo(
            android.content.ComponentName(context, VoiceSessionService::class.java),
            PackageManager.ComponentInfoFlags.of(0),
        )
        val required = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK

        assertEquals(false, service.exported)
        assertEquals(required, service.foregroundServiceType and required)
    }

    @Test
    fun application_has_no_boot_receiver() {
        val packageInfo = context.packageManager.getPackageInfo(
            context.packageName,
            PackageManager.PackageInfoFlags.of(PackageManager.GET_RECEIVERS.toLong()),
        )

        assertTrue(packageInfo.receivers.isNullOrEmpty())
        assertNull(packageInfo.requestedPermissions?.find { it == "android.permission.RECEIVE_BOOT_COMPLETED" })
    }
}
