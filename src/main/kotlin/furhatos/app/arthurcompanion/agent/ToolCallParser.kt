package furhatos.app.arthurcompanion.agent

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper

sealed class ParsedModelOutput {
    data class ToolCall(val name: String, val args: JsonNode) : ParsedModelOutput()
    data class Final(val text: String) : ParsedModelOutput()
    data object Invalid : ParsedModelOutput()
}

object ToolCallParser {
    private val mapper = jacksonObjectMapper()

    fun parse(modelText: String): ParsedModelOutput {
        val node = try {
            mapper.readTree(modelText)
        } catch (_: JsonProcessingException) {
            return ParsedModelOutput.Invalid
        }
        val type = node.path("type").asText(null) ?: return ParsedModelOutput.Invalid
        return when (type) {
            "final" -> {
                val text = node.path("text").asText("")
                ParsedModelOutput.Final(text)
            }
            "tool_call" -> {
                val name = node.path("name").asText(null) ?: return ParsedModelOutput.Invalid
                val rawArgs = node.path("args")
                val args = if (rawArgs.isMissingNode || rawArgs.isNull) mapper.createObjectNode() else rawArgs
                ParsedModelOutput.ToolCall(name, args)
            }
            else -> ParsedModelOutput.Invalid
        }
    }
}
