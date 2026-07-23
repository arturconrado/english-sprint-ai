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
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.json)
    implementation(libs.stream.webrtc.android)
    implementation(libs.vosk.android)

    testImplementation(libs.junit4)
    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
}

tasks.named("preBuild").configure {
    dependsOn(downloadVoiceModels)
}
