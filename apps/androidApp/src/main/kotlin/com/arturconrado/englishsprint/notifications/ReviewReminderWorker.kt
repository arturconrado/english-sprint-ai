package com.arturconrado.englishsprint.notifications

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.arturconrado.englishsprint.BuildConfig
import com.arturconrado.englishsprint.R
import com.arturconrado.englishsprint.account.FirebaseAccountGateway
import com.arturconrado.englishsprint.api.KtorMissionApi
import com.arturconrado.englishsprint.networking.createHttpClient
import java.util.concurrent.TimeUnit

class ReviewReminderWorker(
    appContext: Context,
    parameters: WorkerParameters,
) : CoroutineWorker(appContext, parameters) {
    override suspend fun doWork(): Result {
        val account = FirebaseAccountGateway(applicationContext)
        if (!account.isSignedIn) return Result.success()
        val client = createHttpClient()
        return try {
            val reviews = KtorMissionApi(
                BuildConfig.REALTIME_API_BASE_URL.trimEnd('/'),
                client,
            ).listDueReviews(account.idToken())
            if (reviews.isNotEmpty() && notificationsAllowed()) {
                showNotification(reviews.size)
            }
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        } finally {
            client.close()
        }
    }

    private fun notificationsAllowed(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            applicationContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun showNotification(reviewCount: Int) {
        val manager = applicationContext.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "Learning reviews",
                NotificationManager.IMPORTANCE_DEFAULT,
            ),
        )
        manager.notify(
            NOTIFICATION_ID,
            Notification.Builder(applicationContext, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle("Your English review is ready")
                .setContentText(
                    if (reviewCount == 1) {
                        "A short review is waiting in your sprint."
                    } else {
                        "$reviewCount short reviews are waiting in your sprint."
                    },
                )
                .setAutoCancel(true)
                .setCategory(Notification.CATEGORY_REMINDER)
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .build(),
        )
    }

    private companion object {
        const val CHANNEL_ID = "learning_reviews"
        const val NOTIFICATION_ID = 1002
    }
}

object ReviewReminderScheduler {
    private const val UNIQUE_WORK = "english-sprint-review-reminders"

    fun configure(context: Context, enabled: Boolean) {
        val manager = WorkManager.getInstance(context)
        if (!enabled) {
            manager.cancelUniqueWork(UNIQUE_WORK)
            return
        }
        val request = PeriodicWorkRequestBuilder<ReviewReminderWorker>(
            12,
            TimeUnit.HOURS,
        )
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .build()
        manager.enqueueUniquePeriodicWork(
            UNIQUE_WORK,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }
}
