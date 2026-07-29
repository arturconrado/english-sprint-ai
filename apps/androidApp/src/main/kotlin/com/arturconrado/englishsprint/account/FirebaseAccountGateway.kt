package com.arturconrado.englishsprint.account

import android.app.Activity
import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import com.arturconrado.englishsprint.BuildConfig
import com.google.android.gms.tasks.Task
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

class FirebaseAccountGateway(context: Context) {
    private val applicationContext = context.applicationContext
    private val configurationAvailable =
        BuildConfig.FIREBASE_API_KEY.isNotBlank() &&
            BuildConfig.FIREBASE_APP_ID.isNotBlank() &&
            BuildConfig.FIREBASE_PROJECT_ID.isNotBlank() &&
            BuildConfig.FIREBASE_WEB_CLIENT_ID.isNotBlank()

    private val auth: FirebaseAuth? = if (configurationAvailable) {
        val app = FirebaseApp.getApps(applicationContext).firstOrNull()
            ?: FirebaseApp.initializeApp(
                applicationContext,
                FirebaseOptions.Builder()
                    .setApiKey(BuildConfig.FIREBASE_API_KEY)
                    .setApplicationId(BuildConfig.FIREBASE_APP_ID)
                    .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
                    .build(),
            )
        FirebaseAuth.getInstance(app)
    } else {
        null
    }

    val isConfigured: Boolean
        get() = auth != null

    val isSignedIn: Boolean
        get() = auth?.currentUser != null

    val userId: String?
        get() = auth?.currentUser?.uid

    suspend fun signIn(activity: Activity): String {
        val firebaseAuth = requireNotNull(auth) { "firebase_not_configured" }
        val option = GetGoogleIdOption.Builder()
            .setFilterByAuthorizedAccounts(false)
            .setServerClientId(BuildConfig.FIREBASE_WEB_CLIENT_ID)
            .setAutoSelectEnabled(false)
            .build()
        val credential = CredentialManager.create(activity)
            .getCredential(
                context = activity,
                request = GetCredentialRequest.Builder()
                    .addCredentialOption(option)
                    .build(),
            ).credential
        check(
            credential is CustomCredential &&
                credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL,
        ) { "unsupported_google_credential" }
        val google = GoogleIdTokenCredential.createFrom(credential.data)
        firebaseAuth.signInWithCredential(
            GoogleAuthProvider.getCredential(google.idToken, null),
        ).await()
        return idToken(forceRefresh = true)
    }

    suspend fun idToken(forceRefresh: Boolean = false): String {
        val user = requireNotNull(auth?.currentUser) { "firebase_sign_in_required" }
        return requireNotNull(user.getIdToken(forceRefresh).await().token) {
            "firebase_id_token_unavailable"
        }
    }

    fun signOut() {
        auth?.signOut()
    }
}

private suspend fun <T> Task<T>.await(): T = suspendCoroutine { continuation ->
    addOnSuccessListener(continuation::resume)
    addOnFailureListener(continuation::resumeWithException)
}
