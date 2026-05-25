package furhatos.app.arthurcompanion

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import furhatos.app.arthurcompanion.agent.AppConfig
import furhatos.app.arthurcompanion.state.JsonStore
import furhatos.app.arthurcompanion.tools.ToolDispatcher
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.nio.file.Paths

class ToolDispatcherTest {
    @Test
    fun `happiness clamps to 0-1`() {
        val dir = Files.createTempDirectory("arthur")
        val configPath = dir.resolve("config.json")
        val statePath = dir.resolve("data/state.json")
        Files.createDirectories(statePath.parent)

        // Use repo config as baseline.
        val repoConfig = Paths.get("config.json")
        Files.copy(repoConfig, configPath, StandardCopyOption.REPLACE_EXISTING)
        val store = JsonStore(statePath)
        store.save(furhatos.app.arthurcompanion.state.State(happiness = furhatos.app.arthurcompanion.state.Happiness(0.99, null)))

        val config = AppConfig.load(configPath)
        val tools = ToolDispatcher(config, store)
        val mapper = jacksonObjectMapper()

        tools.execute("happiness_apply_label", mapper.readTree("{\"label\":\"positive\"}"))
        assertEquals(1.0, store.load().happiness.score)

        store.update { it.copy(happiness = it.happiness.copy(score = 0.01)) }
        tools.execute("happiness_apply_label", mapper.readTree("{\"label\":\"negative\"}"))
        assertEquals(0.0, store.load().happiness.score)
    }
}
