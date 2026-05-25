package furhatos.app.arthurcompanion.flow

import furhatos.app.arthurcompanion.agent.AgentController
import furhatos.flow.kotlin.*

val Idle: State = state {
    val agent = AgentController()

    onTime(repeat = (agent.config.proactive.tickSeconds * 1000).toInt()) {
        val prompt = agent.maybeProactivePrompt()
        if (prompt != null) {
            furhat.say(prompt)
            agent.markBotSpoke()
        }
    }

    onEntry {
        // Do not depend on user presence/FaceEngine; work with voice-only.
        furhat.attendNobody()
        furhat.say("Hello Arthur.")
        agent.markBotSpoke()
        goto(ListenLoop(agent))
    }

    onUserEnter {
        // If user tracking works, attend them.
        furhat.attend(it)
        agent.markUserSeen()
    }
}

private fun ListenLoop(agent: AgentController): State = state {
    onEntry {
        furhat.listen()
    }

    onReentry {
        // Ensure we actually listen again after reentry().
        furhat.listen()
    }

    onResponse {
        agent.markUserSeen()
        val userText = it.text
        // Agent call can block (HTTP to Ollama). Run it in a called state so the flow stays responsive.
        val reply = call {
            try {
                agent.handleUserText(userText)
            } catch (e: Exception) {
                println("Agent error: ${e.message}")
                "I had trouble reaching my brain. Please try again."
            }
        } as String
        if (reply.isNotBlank()) {
            furhat.say(reply)
            agent.markBotSpoke()
        }
        reentry()
    }

    onNoResponse {
        // Keep listening; proactive timer may trigger.
        reentry()
    }
}
