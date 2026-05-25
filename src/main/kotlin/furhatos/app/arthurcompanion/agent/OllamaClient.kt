package furhatos.app.arthurcompanion.agent

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

class OllamaClient(
    private val baseUrl: String,
    private val model: String,
) {
    private val mapper = jacksonObjectMapper()

    fun chat(messages: List<ChatMessage>): String {
        val body = mapper.createObjectNode().apply {
            put("model", model)
            put("stream", false)
            set<JsonNode>(
                "messages",
                mapper.valueToTree(messages.map { m ->
                    mapper.createObjectNode().apply {
                        put("role", m.role)
                        put("content", m.content)
                        if (m.name != null) put("name", m.name)
                    }
                })
            )
        }

        val url = URL(baseUrl.trimEnd('/') + "/api/chat")
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 10_000
            readTimeout = 60_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
        }

        val payload = mapper.writeValueAsBytes(body)
        conn.outputStream.use { it.write(payload) }

        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val respBody = BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
        if (code !in 200..299) {
            throw RuntimeException("Ollama HTTP $code: $respBody")
        }

        val json = mapper.readTree(respBody)
        return json.path("message").path("content").asText("")
    }
}
