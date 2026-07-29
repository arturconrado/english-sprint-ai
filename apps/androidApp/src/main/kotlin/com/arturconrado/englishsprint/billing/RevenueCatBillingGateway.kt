package com.arturconrado.englishsprint.billing

import android.app.Activity
import android.content.Context
import com.arturconrado.englishsprint.BuildConfig
import com.revenuecat.purchases.CustomerInfo
import com.revenuecat.purchases.Offerings
import com.revenuecat.purchases.Purchases
import com.revenuecat.purchases.PurchasesConfiguration
import com.revenuecat.purchases.PurchasesError
import com.revenuecat.purchases.PurchaseParams
import com.revenuecat.purchases.interfaces.LogInCallback
import com.revenuecat.purchases.interfaces.PurchaseCallback
import com.revenuecat.purchases.interfaces.ReceiveCustomerInfoCallback
import com.revenuecat.purchases.interfaces.ReceiveOfferingsCallback
import com.revenuecat.purchases.models.StoreTransaction
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

class RevenueCatBillingGateway(private val context: Context) {
    val isConfigured: Boolean
        get() = BuildConfig.REVENUECAT_PUBLIC_API_KEY.isNotBlank()

    suspend fun identify(firebaseUserId: String) {
        check(isConfigured) { "revenuecat_not_configured" }
        if (!Purchases.isConfigured) {
            Purchases.configure(
                PurchasesConfiguration.Builder(
                    context.applicationContext,
                    BuildConfig.REVENUECAT_PUBLIC_API_KEY,
                )
                    .appUserID(firebaseUserId)
                    .automaticDeviceIdentifierCollectionEnabled(false)
                    .build(),
            )
            return
        }
        if (Purchases.sharedInstance.appUserID == firebaseUserId) return
        suspendCoroutine { continuation ->
            Purchases.sharedInstance.logIn(
                firebaseUserId,
                object : LogInCallback {
                    override fun onReceived(
                        customerInfo: CustomerInfo,
                        created: Boolean,
                    ) {
                        continuation.resume(Unit)
                    }

                    override fun onError(error: PurchasesError) {
                        continuation.resumeWithException(
                            IllegalStateException("revenuecat_login_failed:${error.code}"),
                        )
                    }
                },
            )
        }
    }

    suspend fun purchaseMonthly(activity: Activity): CustomerInfo {
        val offerings = offerings()
        val monthly = offerings.current?.monthly
            ?: offerings.current?.availablePackages?.firstOrNull()
            ?: error("revenuecat_monthly_package_unavailable")
        return suspendCoroutine { continuation ->
            Purchases.sharedInstance.purchase(
                PurchaseParams.Builder(activity, monthly).build(),
                object : PurchaseCallback {
                    override fun onCompleted(
                        storeTransaction: StoreTransaction,
                        customerInfo: CustomerInfo,
                    ) {
                        continuation.resume(customerInfo)
                    }

                    override fun onError(
                        error: PurchasesError,
                        userCancelled: Boolean,
                    ) {
                        continuation.resumeWithException(
                            IllegalStateException(
                                if (userCancelled) {
                                    "purchase_cancelled"
                                } else {
                                    "purchase_failed:${error.code}"
                                },
                            ),
                        )
                    }
                },
            )
        }
    }

    suspend fun restore(): CustomerInfo = suspendCoroutine { continuation ->
        Purchases.sharedInstance.restorePurchases(
            object : ReceiveCustomerInfoCallback {
                override fun onReceived(customerInfo: CustomerInfo) {
                    continuation.resume(customerInfo)
                }

                override fun onError(error: PurchasesError) {
                    continuation.resumeWithException(
                        IllegalStateException("purchase_restore_failed:${error.code}"),
                    )
                }
            },
        )
    }

    suspend fun signOut() {
        if (!Purchases.isConfigured) return
        suspendCoroutine { continuation ->
            Purchases.sharedInstance.logOut(
                object : ReceiveCustomerInfoCallback {
                    override fun onReceived(customerInfo: CustomerInfo) {
                        continuation.resume(Unit)
                    }

                    override fun onError(error: PurchasesError) {
                        continuation.resumeWithException(
                            IllegalStateException("revenuecat_logout_failed:${error.code}"),
                        )
                    }
                },
            )
        }
    }

    private suspend fun offerings(): Offerings = suspendCoroutine { continuation ->
        Purchases.sharedInstance.getOfferings(
            object : ReceiveOfferingsCallback {
                override fun onReceived(offerings: Offerings) {
                    continuation.resume(offerings)
                }

                override fun onError(error: PurchasesError) {
                    continuation.resumeWithException(
                        IllegalStateException("offerings_unavailable:${error.code}"),
                    )
                }
            },
        )
    }
}
