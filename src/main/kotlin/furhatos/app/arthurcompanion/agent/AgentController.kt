package furhatos.app.arthurcompanion.agent

import furhatos.app.arthurcompanion.state.JsonStore
import furhatos.app.arthurcompanion.state.State
import furhatos.app.arthurcompanion.tools.ToolDispatcher
import furhatos.app.arthurcompanion.tools.ToolResult
import java.nio.file.Paths
import java.time.Instant

class AgentController {
    val config: AppConfig = AppConfig.loadDefault()
    // Persist under current working directory by default.
    private val store = JsonStore(Paths.get(System.getProperty("user.dir")).resolve("data/state.json"))
    private val tools = ToolDispatcher(config, store)
    private val ollama = OllamaClient(config.ollama.baseUrl, config.ollama.model)
    private val prompt = SystemPrompt.loadResource("prompts/system.txt")

    fun markUserSeen(now: Instant = Instant.now()) {
        store.update { it.copy(conversation = it.conversation.copy(lastUserSeenAt = now)) }
    }

    fun markBotSpoke(now: Instant = Instant.now()) {
        store.update { it.copy(conversation = it.conversation.copy(lastBotSpokeAt = now)) }
    }

    fun handleUserText(text: String): String {
        // Minimal conversation: single-turn agent with tool loop.
        val state = store.load()
        val ctx = AgentContext.from(state, config)

        val history = mutableListOf<ChatMessage>()
        history.add(ChatMessage("system", prompt.render(ctx)))
        history.add(ChatMessage("user", text))

        var toolCalls = 0
        while (true) {
            val modelOut = ollama.chat(history)
            val parsed = ToolCallParser.parse(modelOut)
            when (parsed) {
                is ParsedModelOutput.Final -> return parsed.text
                is ParsedModelOutput.ToolCall -> {
                    toolCalls++
                    if (toolCalls > 3) {
                        return "Let us pause for a moment."
                    }
                    val result: ToolResult = tools.execute(parsed.name, parsed.args)
                    history.add(ChatMessage("assistant", modelOut))
                    history.add(ChatMessage("tool", result.toJsonString(), name = parsed.name))
                }
                is ParsedModelOutput.Invalid -> {
                    // Repair prompt: ask for valid JSON only.
                    history.add(ChatMessage("assistant", modelOut))
                    history.add(
                        ChatMessage(
                            "system",
                            "Output invalid. Output JSON only. Either tool_call or final."
                        )
                    )
                    // One retry; if still invalid, bail.
                    val retry = ollama.chat(history)
                    val retryParsed = ToolCallParser.parse(retry)
                    if (retryParsed is ParsedModelOutput.Final) return retryParsed.text
                    return "I did not understand."
                }
            }
        }
    }

    fun maybeProactivePrompt(now: Instant = Instant.now()): String? {
        val state: State = store.load()
        val lastUser = state.conversation.lastUserSeenAt
        val lastBot = state.conversation.lastBotSpokeAt

        if (lastUser == null) return null
        val silentSeconds = now.epochSecond - lastUser.epochSecond
        if (silentSeconds < config.proactive.silenceThresholdSeconds) return null

        if (lastBot != null) {
            val sinceBot = now.epochSecond - lastBot.epochSecond
            if (sinceBot < config.proactive.minPromptSpacingSeconds) return null
        }

        val due = tools.routinesDue(now)
        val top = due.firstOrNull() ?: return null
        // Rate-limit per-item: don't re-prompt same item more often than minPromptSpacingSeconds.
        val lastPrompted = state.routines[top.key]?.lastPromptedAt
        if (lastPrompted != null) {
            val sinceItem = now.epochSecond - lastPrompted.epochSecond
            if (sinceItem < config.proactive.minPromptSpacingSeconds) return null
        }
        tools.markPrompted(top.key, now)
        // Keep proactive prompt simple and tool-grounded.
        return top.suggestedPrompt
    }
}
