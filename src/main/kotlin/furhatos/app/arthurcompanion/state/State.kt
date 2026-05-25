package furhatos.app.arthurcompanion.state

import java.time.Instant

data class State(
    val agenda: List<AgendaItem> = emptyList(),
    val happiness: Happiness = Happiness(0.6, null),
    val routines: Map<String, RoutineStatus> = emptyMap(),
    val memory: MemoryState = MemoryState(),
    val conversation: ConversationState = ConversationState(),
)

data class AgendaItem(
    val id: String,
    val text: String,
    val status: AgendaStatus = AgendaStatus.pending,
    val createdAt: Instant,
    val doneAt: Instant? = null,
)

enum class AgendaStatus {
    pending,
    done,
}

data class Happiness(
    val score: Double,
    val updatedAt: Instant?,
)

data class RoutineStatus(
    val lastDoneAt: Instant? = null,
    val lastPromptedAt: Instant? = null,
)

data class MemoryState(
    val localDate: String? = null,
    val words: List<String>? = null,
    val givenAt: Instant? = null,
    val recallCount: Int = 0,
    val lastRecallAt: Instant? = null,
)

data class ConversationState(
    val lastUserSeenAt: Instant? = null,
    val lastBotSpokeAt: Instant? = null,
)
