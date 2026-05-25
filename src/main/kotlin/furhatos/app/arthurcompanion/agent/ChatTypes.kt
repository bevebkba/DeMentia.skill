package furhatos.app.arthurcompanion.agent

data class ChatMessage(
    val role: String,
    val content: String,
    // For tool messages; Ollama-compatible servers may ignore.
    val name: String? = null,
)
