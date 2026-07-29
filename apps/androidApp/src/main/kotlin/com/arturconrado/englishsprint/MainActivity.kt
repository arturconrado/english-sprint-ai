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
import com.arturconrado.englishsprint.account.FirebaseAccountGateway
import com.arturconrado.englishsprint.api.KtorMissionApi
import com.arturconrado.englishsprint.api.KtorProductJourneyApi
import com.arturconrado.englishsprint.api.ProductConsents
import com.arturconrado.englishsprint.api.ProductNotificationPreferences
import com.arturconrado.englishsprint.api.ProductOnboarding
import com.arturconrado.englishsprint.billing.RevenueCatBillingGateway
import com.arturconrado.englishsprint.domain.Mission
import com.arturconrado.englishsprint.domain.DueReview
import com.arturconrado.englishsprint.domain.VoiceSessionCommand
import com.arturconrado.englishsprint.domain.VoiceSessionState
import com.arturconrado.englishsprint.mission.MissionSessionTokenStore
import com.arturconrado.englishsprint.mission.StoredMissionSession
import com.arturconrado.englishsprint.networking.createHttpClient
import com.arturconrado.englishsprint.notifications.ReviewReminderScheduler
import com.arturconrado.englishsprint.telemetry.ProductTelemetry
import com.arturconrado.englishsprint.voice.VoiceSessionService
import com.arturconrado.englishsprint.voice.VoiceSessionSnapshot
import java.util.UUID
import java.time.ZoneId
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
    private var analyticsConsent by mutableStateOf(false)
    private var notificationConsent by mutableStateOf(true)
    private var professionalGoal by mutableStateOf("international_interviews")
    private var englishContext by mutableStateOf("weekly")
    private var missionSessionState by mutableStateOf<String?>(null)
    private var signedIn by mutableStateOf(false)
    private var productStage by mutableStateOf("sign_in")
    private var diagnosticStatus by mutableStateOf<String?>(null)
    private var sprintStatus by mutableStateOf<String?>(null)
    private var accessMode by mutableStateOf<String?>(null)
    private var billingStatus by mutableStateOf<String?>(null)
    private var remainingMinutes by mutableStateOf(0)
    private var dueReviews by mutableStateOf<List<DueReview>>(emptyList())
    private var availableMissionIds by mutableStateOf<Set<String>>(emptySet())
    private var activeReviewId: String? = null
    private var supportText by mutableStateOf("")
    private var deletionConfirmation by mutableStateOf("")
    private var accountOperationStatus by mutableStateOf<String?>(null)
    private var pendingMissionStart = false
    private var pendingDiagnosticStart = false
    private var refreshingJourney = false
    private var handledSessionEnd = false
    private val httpClient by lazy { createHttpClient() }
    private val missionApi by lazy {
        KtorMissionApi(
            BuildConfig.REALTIME_API_BASE_URL.trimEnd('/'),
            httpClient,
        )
    }
    private val productApi by lazy {
        KtorProductJourneyApi(
            BuildConfig.REALTIME_API_BASE_URL.trimEnd('/'),
            httpClient,
        )
    }
    private val accountGateway by lazy { FirebaseAccountGateway(this) }
    private val billingGateway by lazy { RevenueCatBillingGateway(this) }
    private val productTelemetry by lazy { ProductTelemetry(this) }
    private val tokenStore by lazy { MissionSessionTokenStore(this) }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { results ->
        requestingPermission = false
        if (requiredPermissions().all { results[it] == true || isGranted(it) }) {
            when {
                pendingDiagnosticStart -> {
                    pendingDiagnosticStart = false
                    createDiagnosticAndStart()
                }
                pendingMissionStart -> {
                    pendingMissionStart = false
                    createMissionAndStart()
                }
            }
        } else {
            pendingMissionStart = false
            pendingDiagnosticStart = false
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
                    if (it.state == VoiceSessionState.Ended && !handledSessionEnd) {
                        handledSessionEnd = true
                        tokenStore.clear()
                        missionSessionState = null
                        if (it.missionState == "MISSION_COMPLETED") {
                            completeActiveReview()
                        } else {
                            activeReviewId = null
                            refreshJourney()
                        }
                    } else if (it.state !in setOf(
                            VoiceSessionState.Ended,
                            VoiceSessionState.Ending,
                        )
                    ) {
                        handledSessionEnd = false
                    }
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
                    analyticsConsent = analyticsConsent,
                    notificationConsent = notificationConsent,
                    missionSessionState = missionSessionState,
                    accountConfigured = accountGateway.isConfigured,
                    signedIn = signedIn,
                    productStage = productStage,
                    professionalGoal = professionalGoal,
                    englishContext = englishContext,
                    diagnosticStatus = diagnosticStatus,
                    sprintStatus = sprintStatus,
                    accessMode = accessMode,
                    billingStatus = billingStatus,
                    remainingMinutes = remainingMinutes,
                    dueReviewCount = dueReviews.size,
                    availableMissionIds = availableMissionIds,
                    supportText = supportText,
                    deletionConfirmation = deletionConfirmation,
                    accountOperationStatus = accountOperationStatus,
                ),
                onCommand = ::onCommand,
                onMissionSelected = {
                    selectedMissionId = it
                },
                onProcessingConsentChanged = { processingConsent = it },
                onRetentionConsentChanged = { retentionConsent = it },
                onAnalyticsConsentChanged = {
                    analyticsConsent = it
                    productTelemetry.setConsent(it)
                },
                onNotificationConsentChanged = {
                    notificationConsent = it
                    ReviewReminderScheduler.configure(this, it)
                    persistNotificationPreferences()
                },
                onProfessionalGoalChanged = { professionalGoal = it },
                onEnglishContextChanged = { englishContext = it },
                onStartMission = ::requestPermissionsAndStart,
                onSignIn = ::signIn,
                onStartDiagnostic = ::requestPermissionsAndStartDiagnostic,
                onRefreshJourney = ::refreshJourney,
                onSubscribe = ::subscribe,
                onRestorePurchase = ::restorePurchase,
                onCompleteReview = ::practiceNextReview,
                onSupportTextChanged = { supportText = it.take(1000) },
                onSubmitSupport = ::submitSupport,
                onRequestExport = ::requestExport,
                onDeletionConfirmationChanged = { deletionConfirmation = it.take(32) },
                onDeleteAccount = ::deleteAccount,
                onSignOut = ::signOut,
            )
        }
        signedIn = accountGateway.isSignedIn
        if (signedIn) {
            refreshJourney()
        } else {
            restoreSessionOrLoadCatalog()
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
        if (!signedIn || selectedMissionId == null || !processingConsent) return
        val missing = requiredPermissions().filterNot(::isGranted)
        if (missing.isEmpty()) {
            createMissionAndStart()
        } else {
            pendingMissionStart = true
            requestingPermission = true
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun requestPermissionsAndStartDiagnostic() {
        if (!signedIn || !processingConsent) return
        val missing = requiredPermissions().filterNot(::isGranted)
        if (missing.isEmpty()) {
            createDiagnosticAndStart()
        } else {
            pendingDiagnosticStart = true
            requestingPermission = true
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun createMissionAndStart() {
        val missionId = selectedMissionId ?: return
        missionsLoading = true
        activityScope.launch {
            var createdSessionId: String? = null
            runCatching {
                val token = accountGateway.idToken()
                val created = missionApi.createSession(
                    missionId = missionId,
                    firebaseIdToken = token,
                    idempotencyKey = UUID.randomUUID().toString(),
                )
                createdSessionId = created.session.sessionId
                val reservation = productApi.reserveVoiceUsage(
                    firebaseIdToken = token,
                    idempotencyKey = UUID.randomUUID().toString(),
                    requestedSeconds = 30 * 60,
                    purpose = "mission",
                )
                created to reservation
            }.onSuccess { (created, reservation) ->
                tokenStore.save(
                    StoredMissionSession(created.session.sessionId),
                )
                missionSessionState = created.session.state
                startVoiceService(
                    created.session.sessionId,
                    reservation.reservationId,
                )
            }.onFailure {
                createdSessionId?.let { sessionId ->
                    runCatching {
                        missionApi.cancel(
                            sessionId,
                            accountGateway.idToken(),
                            UUID.randomUUID().toString(),
                        )
                    }
                }
                snapshot = VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("mission_creation_failed", true),
                    errorCode = "mission_creation_failed",
                )
            }
            missionsLoading = false
        }
    }

    private fun startVoiceService(sessionId: String?, reservationId: String) {
        startForegroundService(
            Intent(this, VoiceSessionService::class.java)
                .setAction(VoiceSessionService.ACTION_START)
                .putExtra(VoiceSessionService.EXTRA_MISSION_SESSION_ID, sessionId)
                .putExtra(VoiceSessionService.EXTRA_USAGE_RESERVATION_ID, reservationId),
        )
        bindVoiceService(createIfMissing = true)
    }

    private fun restoreSessionOrLoadCatalog() {
        activityScope.launch {
            if (signedIn) tokenStore.load()?.let { stored ->
                runCatching {
                    missionApi.getSession(stored.sessionId, accountGateway.idToken())
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

    private fun signIn() {
        missionsLoading = true
        activityScope.launch {
            runCatching {
                accountGateway.signIn(this@MainActivity)
                billingGateway.takeIf { it.isConfigured }
                    ?.identify(checkNotNull(accountGateway.userId))
            }.onSuccess {
                signedIn = true
                refreshJourney()
            }.onFailure {
                snapshot = VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("google_sign_in_failed", true),
                    errorCode = "google_sign_in_failed",
                )
                missionsLoading = false
            }
        }
    }

    private fun createDiagnosticAndStart() {
        missionsLoading = true
        activityScope.launch {
            runCatching {
                val token = accountGateway.idToken()
                productApi.updateConsents(
                    token,
                    ProductConsents(
                        policyVersion = "beta-1",
                        pedagogicalProcessing = true,
                        analytics = analyticsConsent,
                        contentRetention = retentionConsent,
                        notifications = notificationConsent,
                    ),
                )
                productApi.updateOnboarding(
                    token,
                    ProductOnboarding(
                        professionalGoal = professionalGoal,
                        englishContext = englishContext,
                        timezone = ZoneId.systemDefault().id,
                    ),
                )
                productApi.updateNotificationPreferences(
                    token,
                    ProductNotificationPreferences(
                        enabled = notificationConsent,
                        dailyReminder = notificationConsent,
                        reviewReminder = notificationConsent,
                        timezone = ZoneId.systemDefault().id,
                        reminderHourLocal = 19,
                    ),
                )
                productTelemetry.setConsent(analyticsConsent)
                ReviewReminderScheduler.configure(this@MainActivity, notificationConsent)
                productTelemetry.event("onboarding_completed")
                productApi.startDiagnostic(token, UUID.randomUUID().toString())
                productApi.reserveVoiceUsage(
                    firebaseIdToken = token,
                    idempotencyKey = UUID.randomUUID().toString(),
                    requestedSeconds = 10 * 60,
                    purpose = "diagnostic",
                )
            }.onSuccess { reservation ->
                diagnosticStatus = "active"
                productTelemetry.event("diagnostic_started")
                startVoiceService(null, reservation.reservationId)
            }.onFailure {
                snapshot = VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("diagnostic_start_failed", true),
                    errorCode = "diagnostic_start_failed",
                )
            }
            missionsLoading = false
        }
    }

    private fun refreshJourney() {
        if (!signedIn || refreshingJourney) return
        refreshingJourney = true
        missionsLoading = true
        activityScope.launch {
            runCatching {
                val token = accountGateway.idToken(forceRefresh = true)
                billingGateway.takeIf { it.isConfigured }
                    ?.identify(checkNotNull(accountGateway.userId))
                val allowance = productApi.billingStatus(token)
                accessMode = allowance.accessMode
                billingStatus = allowance.status
                remainingMinutes = allowance.remainingSeconds / 60
                val diagnostic = runCatching { productApi.getDiagnostic(token) }.getOrNull()
                diagnosticStatus = diagnostic?.status
                if (diagnostic?.status == "completed") {
                    val sprint = runCatching { productApi.currentSprint(token) }
                        .getOrElse {
                            productApi.createSprint(token, UUID.randomUUID().toString())
                        }
                    sprintStatus = sprint.status
                    productStage = "sprint"
                    availableMissionIds = sprint.days
                        .filter { it.status == "available" }
                        .mapTo(mutableSetOf()) { it.missionId }
                    selectedMissionId = availableMissionIds.firstOrNull()
                    dueReviews = missionApi.listDueReviews(token)
                } else {
                    productStage = "setup"
                    dueReviews = emptyList()
                    availableMissionIds = emptySet()
                }
            }.onFailure {
                snapshot = VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("journey_refresh_failed", true),
                    errorCode = "journey_refresh_failed",
                )
            }
            restoreSessionOrLoadCatalog()
            refreshingJourney = false
        }
    }

    private fun subscribe() {
        activityScope.launch {
            runCatching {
                check(billingGateway.isConfigured) { "revenuecat_not_configured" }
                billingGateway.identify(checkNotNull(accountGateway.userId))
                billingGateway.purchaseMonthly(this@MainActivity)
                productApi.restoreBilling(
                    accountGateway.idToken(forceRefresh = true),
                    UUID.randomUUID().toString(),
                )
            }.onSuccess {
                productTelemetry.event("purchase_completed")
                refreshJourney()
            }.onFailure {
                snapshot = VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("purchase_failed", true),
                    errorCode = "purchase_failed",
                )
            }
        }
    }

    private fun restorePurchase() {
        activityScope.launch {
            runCatching {
                check(billingGateway.isConfigured) { "revenuecat_not_configured" }
                billingGateway.identify(checkNotNull(accountGateway.userId))
                billingGateway.restore()
                productApi.restoreBilling(
                    accountGateway.idToken(forceRefresh = true),
                    UUID.randomUUID().toString(),
                )
            }.onSuccess {
                refreshJourney()
            }.onFailure {
                snapshot = VoiceSessionSnapshot(
                    state = VoiceSessionState.Error("purchase_restore_failed", true),
                    errorCode = "purchase_restore_failed",
                )
            }
        }
    }

    private fun practiceNextReview() {
        val review = dueReviews.firstOrNull() ?: return
        activeReviewId = review.reviewId
        selectedMissionId = review.missionId
        requestPermissionsAndStart()
    }

    private fun completeActiveReview() {
        val reviewId = activeReviewId
        if (reviewId == null) {
            refreshJourney()
            return
        }
        activityScope.launch {
            runCatching {
                missionApi.completeReview(
                    reviewId,
                    accountGateway.idToken(forceRefresh = true),
                    UUID.randomUUID().toString(),
                )
            }.onSuccess {
                activeReviewId = null
                productTelemetry.event("review_completed")
                refreshJourney()
            }.onFailure {
                accountOperationStatus = "Review could not be completed."
            }
        }
    }

    private fun persistNotificationPreferences() {
        if (!signedIn) return
        activityScope.launch {
            runCatching {
                productApi.updateNotificationPreferences(
                    accountGateway.idToken(),
                    ProductNotificationPreferences(
                        enabled = notificationConsent,
                        dailyReminder = notificationConsent,
                        reviewReminder = notificationConsent,
                        timezone = ZoneId.systemDefault().id,
                        reminderHourLocal = 19,
                    ),
                )
            }
        }
    }

    private fun submitSupport() {
        if (supportText.length !in 10..1000) return
        activityScope.launch {
            runCatching {
                productApi.createSupportRequest(
                    firebaseIdToken = accountGateway.idToken(),
                    idempotencyKey = UUID.randomUUID().toString(),
                    category = "other",
                    description = supportText,
                )
            }.onSuccess {
                productTelemetry.event("support_requested")
                supportText = ""
                accountOperationStatus = "Support request sent."
            }.onFailure {
                accountOperationStatus = "Support request could not be sent."
            }
        }
    }

    private fun requestExport() {
        activityScope.launch {
            runCatching {
                val token = accountGateway.idToken(forceRefresh = true)
                productApi.requestAccountExport(token, UUID.randomUUID().toString())
                productApi.downloadAccountExport(token)
            }.onSuccess { export ->
                accountOperationStatus = "Export generated."
                startActivity(
                    Intent.createChooser(
                        Intent(Intent.ACTION_SEND)
                            .setType("application/json")
                            .putExtra(Intent.EXTRA_TEXT, export),
                        "Export English Sprint data",
                    ),
                )
            }.onFailure {
                accountOperationStatus = "Export could not be generated."
            }
        }
    }

    private fun deleteAccount() {
        if (deletionConfirmation != "DELETE MY ACCOUNT") return
        activityScope.launch {
            runCatching {
                productApi.requestAccountDeletion(
                    accountGateway.idToken(forceRefresh = true),
                    UUID.randomUUID().toString(),
                )
            }.onSuccess {
                productTelemetry.event("account_deletion_requested")
                runCatching { billingGateway.signOut() }
                accountGateway.signOut()
                tokenStore.clear()
                signedIn = false
                productStage = "sign_in"
                missionSessionState = null
                deletionConfirmation = ""
                accountOperationStatus = "Account deleted."
            }.onFailure {
                accountOperationStatus = "Account deletion could not be completed."
            }
        }
    }

    private fun signOut() {
        activityScope.launch {
            runCatching {
                productApi.revokeSessions(accountGateway.idToken(forceRefresh = true))
                billingGateway.signOut()
            }
            accountGateway.signOut()
            tokenStore.clear()
            signedIn = false
            productStage = "sign_in"
            missionSessionState = null
            dueReviews = emptyList()
            availableMissionIds = emptySet()
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
