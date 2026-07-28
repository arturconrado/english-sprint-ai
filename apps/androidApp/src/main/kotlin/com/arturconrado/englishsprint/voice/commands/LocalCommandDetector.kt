package com.arturconrado.englishsprint.voice.commands

import android.content.Context
import android.os.SystemClock
import com.arturconrado.englishsprint.domain.LocalVoiceCommand
import com.arturconrado.englishsprint.domain.LocalVoiceCommandParser
import com.arturconrado.englishsprint.voice.rtc.RtcAudioFrame
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.vosk.Model
import org.vosk.Recognizer

interface LocalCommandDetector {
    suspend fun start()
    fun offer(frame: RtcAudioFrame)
    fun close()
}

class VoskLocalCommandDetector(
    context: Context,
    private val scope: CoroutineScope,
    private val onCommand: (LocalVoiceCommand) -> Unit,
) : LocalCommandDetector {
    private val applicationContext = context.applicationContext
    private val frames = Channel<RtcAudioFrame>(
        capacity = 32,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    private var englishModel: Model? = null
    private var portugueseModel: Model? = null
    private var englishRecognizer: Recognizer? = null
    private var portugueseRecognizer: Recognizer? = null
    private var processingJob: Job? = null
    private var lastCommandAt = 0L

    override suspend fun start() {
        val modelsRoot = withContext(Dispatchers.IO) {
            installModels(applicationContext)
        }
        englishModel = withContext(Dispatchers.IO) {
            Model(File(modelsRoot, ENGLISH_MODEL).absolutePath)
        }
        portugueseModel = withContext(Dispatchers.IO) {
            Model(File(modelsRoot, PORTUGUESE_MODEL).absolutePath)
        }
        englishRecognizer = Recognizer(
            requireNotNull(englishModel),
            TARGET_SAMPLE_RATE.toFloat(),
            """["stop","pause","resume","finish","repeat question","more time","help me","[unk]"]""",
        ).apply {
            setWords(true)
        }
        portugueseRecognizer = Recognizer(
            requireNotNull(portugueseModel),
            TARGET_SAMPLE_RATE.toFloat(),
            """["parar","pausar","continuar","encerrar","repetir pergunta","mais tempo","me ajude","[unk]"]""",
        ).apply {
            setWords(true)
        }
        processingJob = scope.launch(Dispatchers.Default) {
            for (frame in frames) {
                val pcm = resampleTo16KhzMono(frame)
                consume(englishRecognizer, pcm)
                consume(portugueseRecognizer, pcm)
            }
        }
    }

    override fun offer(frame: RtcAudioFrame) {
        frames.trySend(frame)
    }

    private fun consume(recognizer: Recognizer?, pcm: ByteArray) {
        if (recognizer == null || !recognizer.acceptWaveForm(pcm, pcm.size)) return
        val result = runCatching {
            Json.parseToJsonElement(recognizer.result).jsonObject
        }.getOrNull() ?: return
        val text = result["text"]?.jsonPrimitive?.content.orEmpty()
        val words = result["result"]?.jsonArray.orEmpty()
        val confidence = words.mapNotNull {
            it.jsonObject["conf"]?.jsonPrimitive?.doubleOrNull
        }.average().takeUnless { it.isNaN() } ?: 0.0
        val command = LocalVoiceCommandParser.parse(text, confidence) ?: return
        val now = SystemClock.elapsedRealtime()
        if (now - lastCommandAt < COMMAND_COOLDOWN_MS) return
        lastCommandAt = now
        onCommand(command)
    }

    override fun close() {
        processingJob?.cancel()
        frames.close()
        englishRecognizer?.close()
        portugueseRecognizer?.close()
        englishModel?.close()
        portugueseModel?.close()
        englishRecognizer = null
        portugueseRecognizer = null
        englishModel = null
        portugueseModel = null
    }

    private fun resampleTo16KhzMono(frame: RtcAudioFrame): ByteArray {
        val input = ByteBuffer.wrap(frame.pcm16).order(ByteOrder.LITTLE_ENDIAN)
        val inputFrames = frame.pcm16.size / 2 / frame.channelCount.coerceAtLeast(1)
        val samples = ShortArray(inputFrames)
        repeat(inputFrames) { frameIndex ->
            var sum = 0
            repeat(frame.channelCount.coerceAtLeast(1)) {
                sum += input.short.toInt()
            }
            samples[frameIndex] = (sum / frame.channelCount.coerceAtLeast(1)).toShort()
        }
        if (frame.sampleRate == TARGET_SAMPLE_RATE) {
            return ByteBuffer.allocate(samples.size * 2)
                .order(ByteOrder.LITTLE_ENDIAN)
                .apply { samples.forEach(::putShort) }
                .array()
        }
        val outputCount = (samples.size.toLong() * TARGET_SAMPLE_RATE / frame.sampleRate)
            .toInt()
            .coerceAtLeast(1)
        return ByteBuffer.allocate(outputCount * 2)
            .order(ByteOrder.LITTLE_ENDIAN)
            .apply {
                repeat(outputCount) { outputIndex ->
                    val sourceIndex = (
                        outputIndex.toLong() * frame.sampleRate / TARGET_SAMPLE_RATE
                    ).toInt().coerceIn(samples.indices)
                    putShort(samples[sourceIndex])
                }
            }
            .array()
    }

    private fun installModels(context: Context): File {
        val root = File(context.filesDir, "voice-models")
        val marker = File(root, ".phase1-models")
        if (marker.readTextOrNull() == MODEL_MARKER) return root
        root.deleteRecursively()
        copyAssetTree(context, "voice-models", root)
        marker.writeText(MODEL_MARKER)
        return root
    }

    private fun copyAssetTree(context: Context, assetPath: String, destination: File) {
        val children = context.assets.list(assetPath).orEmpty()
        if (children.isEmpty()) {
            destination.parentFile?.mkdirs()
            context.assets.open(assetPath).use { input ->
                destination.outputStream().use(input::copyTo)
            }
            return
        }
        destination.mkdirs()
        children.sorted().forEach { child ->
            copyAssetTree(context, "$assetPath/$child", File(destination, child))
        }
    }

    private fun File.readTextOrNull(): String? = runCatching { readText() }.getOrNull()

    private companion object {
        const val TARGET_SAMPLE_RATE = 16_000
        const val COMMAND_COOLDOWN_MS = 1_500L
        const val ENGLISH_MODEL = "vosk-model-small-en-us-0.15"
        const val PORTUGUESE_MODEL = "vosk-model-small-pt-0.3"
        const val MODEL_MARKER =
            "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498:" +
                "6e1ce909032e1afa7a88e68a3d628ecafff302bdf195befab308826c395e93b7"
    }
}
