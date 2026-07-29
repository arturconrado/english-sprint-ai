import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.isFile) file.inputStream().use(::load)
}
val localRealtimeApiBaseUrl =
    localProperties.getProperty("ENGLISH_SPRINT_API_BASE_URL") ?: "http://10.0.2.2:8000"
val realtimeApiBaseUrl = providers.gradleProperty("ENGLISH_SPRINT_API_BASE_URL")
    .orElse(localRealtimeApiBaseUrl)
fun localValue(name: String): String =
    providers.gradleProperty(name).orElse(localProperties.getProperty(name) ?: "").get()

fun quoted(value: String): String = "\"${value.replace("\\", "\\\\").replace("\"", "\\\"")}\""
val generatedVoiceAssets = layout.buildDirectory.dir("generated/voiceModels/assets")
val downloadVoiceModels by tasks.registering(Exec::class) {
    environment("VOICE_MODELS_DIR", generatedVoiceAssets.get().asFile.absolutePath)
    commandLine(rootProject.file("scripts/download-voice-models").absolutePath)
    outputs.dir(generatedVoiceAssets)
}

android {
    namespace = "com.arturconrado.englishsprint"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.arturconrado.englishsprint"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField(
            "String",
            "REALTIME_API_BASE_URL",
            "\"${realtimeApiBaseUrl.get()}\"",
        )
        buildConfigField("String", "FIREBASE_API_KEY", quoted(localValue("FIREBASE_API_KEY")))
        buildConfigField("String", "FIREBASE_APP_ID", quoted(localValue("FIREBASE_APP_ID")))
        buildConfigField("String", "FIREBASE_PROJECT_ID", quoted(localValue("FIREBASE_PROJECT_ID")))
        buildConfigField(
            "String",
            "FIREBASE_WEB_CLIENT_ID",
            quoted(localValue("FIREBASE_WEB_CLIENT_ID")),
        )
        buildConfigField(
            "String",
            "REVENUECAT_PUBLIC_API_KEY",
            quoted(localValue("REVENUECAT_PUBLIC_API_KEY")),
        )
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }

    sourceSets.named("main") {
        assets.srcDir(generatedVoiceAssets.get().asFile)
    }
}

dependencies {
    implementation(project(":shared"))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.fragment.ktx)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.json)
    implementation(libs.stream.webrtc.android)
    implementation(libs.vosk.android)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)
    implementation(libs.firebase.analytics)
    implementation(libs.firebase.crashlytics)
    implementation(libs.androidx.credentials)
    implementation(libs.androidx.credentials.play.services.auth)
    implementation(libs.googleid)
    implementation(libs.revenuecat.purchases)
    implementation(libs.androidx.work.runtime)

    testImplementation(libs.junit4)
    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
}

tasks.named("preBuild").configure {
    dependsOn(downloadVoiceModels)
}
