package furhatos.app.arthurcompanion.state

import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.databind.SerializationFeature
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

class JsonStore(private val path: Path) {
    private val mapper = jacksonObjectMapper()
        .registerModule(JavaTimeModule())
        .configure(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS, false)
        .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)

    @Synchronized
    fun load(): State {
        if (!Files.exists(path)) return State()
        return mapper.readValue(path.toFile())
    }

    @Synchronized
    fun save(state: State) {
        Files.createDirectories(path.parent)
        val tmp = path.resolveSibling(path.fileName.toString() + ".tmp")
        mapper.writerWithDefaultPrettyPrinter().writeValue(tmp.toFile(), state)
        Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
    }

    @Synchronized
    fun update(fn: (State) -> State): State {
        val next = fn(load())
        save(next)
        return next
    }
}
