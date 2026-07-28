package com.arturconrado.englishsprint.mission

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class StoredMissionSession(
    val sessionId: String,
    val bearerToken: String,
)

class MissionSessionTokenStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun save(session: StoredMissionSession) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val plaintext = "${session.sessionId}\n${session.bearerToken}".encodeToByteArray()
        val ciphertext = cipher.doFinal(plaintext)
        preferences.edit()
            .putString(IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString(CIPHERTEXT, Base64.encodeToString(ciphertext, Base64.NO_WRAP))
            .apply()
    }

    fun load(): StoredMissionSession? {
        val encodedIv = preferences.getString(IV, null) ?: return null
        val encodedCiphertext = preferences.getString(CIPHERTEXT, null) ?: return null
        return runCatching {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                key(),
                GCMParameterSpec(128, Base64.decode(encodedIv, Base64.NO_WRAP)),
            )
            val value = cipher.doFinal(
                Base64.decode(encodedCiphertext, Base64.NO_WRAP),
            ).decodeToString()
            val separator = value.indexOf('\n')
            check(separator > 0)
            StoredMissionSession(
                sessionId = value.substring(0, separator),
                bearerToken = value.substring(separator + 1),
            )
        }.getOrElse {
            clear()
            null
        }
    }

    fun clear() {
        preferences.edit().remove(IV).remove(CIPHERTEXT).apply()
    }

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        val existing = keyStore.getKey(KEY_ALIAS, null) as? SecretKey
        if (existing != null) return existing
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE).run {
            init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build(),
            )
            generateKey()
        }
    }

    private companion object {
        const val PREFERENCES = "mission_session_credentials"
        const val IV = "iv"
        const val CIPHERTEXT = "ciphertext"
        const val KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "english_sprint_mission_session_v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
