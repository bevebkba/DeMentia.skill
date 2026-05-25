package furhatos.app.arthurcompanion.agent

import furhatos.app.arthurcompanion.state.State
import java.time.ZoneId
import java.time.ZonedDateTime

data class AgentContext(
    val timezone: String,
    val localNow: String,
    val happinessScore: Double,
    val goodMoodThreshold: Double,
) {
    companion object {
        fun from(state: State, config: AppConfig): AgentContext {
            val zone = ZoneId.of(config.timezone)
            val now = ZonedDateTime.now(zone)
            return AgentContext(
                timezone = config.timezone,
                localNow = now.toString(),
                happinessScore = state.happiness.score,
                goodMoodThreshold = config.happiness.goodMoodThreshold,
            )
        }
    }
}
