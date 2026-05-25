package furhatos.app.arthurcompanion.agent

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

class SystemPrompt private constructor(private val template: String) {
    fun render(ctx: AgentContext): String {
        // Keep prompt small; include only dynamic facts that change behavior.
        return buildString {
            append(template.trim())
            append("\n\n")
            append("Context (tool-grounded):\n")
            append("- Timezone: ").append(ctx.timezone).append("\n")
            append("- Local time now: ").append(ctx.localNow).append("\n")
            append("- Happiness: ").append(ctx.happinessScore).append(" (good>=").append(ctx.goodMoodThreshold).append(")\n")
        }
    }

    companion object {
        fun loadResource(resourcePath: String): SystemPrompt {
            val stream = SystemPrompt::class.java.classLoader.getResourceAsStream(resourcePath)
                ?: throw IllegalStateException("Missing resource: $resourcePath")
            val text = stream.readBytes().toString(StandardCharsets.UTF_8)
            return SystemPrompt(text)
        }

        fun load(path: Path): SystemPrompt {
            val bytes = Files.readAllBytes(path)
            return SystemPrompt(String(bytes, StandardCharsets.UTF_8))
        }
    }
}
