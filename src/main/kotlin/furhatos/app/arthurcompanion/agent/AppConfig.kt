package furhatos.app.arthurcompanion.agent

import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import java.io.InputStream
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

data class AppConfig(
    val timezone: String,
    val proactive: ProactiveConfig,
    val hydration: HydrationConfig,
    val medicationWindows: MedicationWindows,
    val dailyScheduleWindows: Map<String, TimeWindow>,
    val happiness: HappinessConfig,
    val memoryExercise: MemoryExerciseConfig,
    val ollama: OllamaConfig,
) {
    companion object {
        private val mapper = jacksonObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)

        fun load(path: Path): AppConfig = mapper.readValue(path.toFile())

        fun loadDefault(): AppConfig {
            val fsPath = java.nio.file.Paths.get("config.json")
            if (Files.exists(fsPath)) {
                return load(fsPath)
            }
            val stream = AppConfig::class.java.classLoader.getResourceAsStream("config.json")
                ?: throw IllegalStateException("config.json not found on filesystem or classpath")
            return loadFromStream(stream)
        }

        private fun loadFromStream(stream: InputStream): AppConfig {
            stream.use {
                val bytes = it.readBytes()
                return mapper.readValue(String(bytes, StandardCharsets.UTF_8))
            }
        }
    }
}

data class ProactiveConfig(
    val silenceThresholdSeconds: Long,
    val tickSeconds: Long,
    val minPromptSpacingSeconds: Long,
)

data class HydrationConfig(
    val intervalMinutes: Long,
    val activeWindow: TimeWindow,
)

data class MedicationWindows(
    val morning: TimeWindow,
    val lunch: TimeWindow,
    val evening: TimeWindow,
    val bed: TimeWindow,
)

data class TimeWindow(
    val start: String,
    val end: String,
    val onlyIfBefore: String? = null,
)

data class HappinessConfig(
    val initial: Double,
    val goodMoodThreshold: Double,
    val deltaPositive: Double,
    val deltaNegative: Double,
)

data class MemoryExerciseConfig(
    val giveWordsBefore: String,
    val maxRecallsPerDay: Int,
    val allowAfter: String,
)

data class OllamaConfig(
    val baseUrl: String,
    val model: String,
)
