package furhatos.app.arthurcompanion.tools

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper

data class ToolResult(
    val ok: Boolean,
    val result: JsonNode? = null,
    val error: String? = null,
) {
    fun toJsonString(): String {
        val mapper = jacksonObjectMapper()
        val node = mapper.createObjectNode().apply {
            put("ok", ok)
            if (result != null) set<JsonNode>("result", result)
            if (error != null) put("error", error)
        }
        return mapper.writeValueAsString(node)
    }

    companion object {
        fun ok(node: JsonNode): ToolResult = ToolResult(ok = true, result = node)
        fun error(msg: String): ToolResult = ToolResult(ok = false, error = msg)
    }
}
