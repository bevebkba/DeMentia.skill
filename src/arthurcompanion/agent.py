import datetime
import json
from zoneinfo import ZoneInfo
from .state import StateStore
from .tools import ToolDispatcher
from .llm import OllamaClient, parse_tool_call

class AgentController:
    def __init__(self, config: dict, store: StateStore):
        self.config = config
        self.store = store
        self.tools = ToolDispatcher(config, store)
        self.ollama = OllamaClient(config["ollama"]["baseUrl"], config["ollama"]["model"])
        self.timezone = ZoneInfo(config["timezone"])
        try:
            with open("prompts_system.txt", "r", encoding="utf-8") as f:
                self.prompt_template = f.read()
        except FileNotFoundError:
            self.prompt_template = "You are Arthur. Output JSON only."

    def mark_bot_spoke(self):
        def m(st):
            st["conversation"]["lastBotSpokeAt"] = datetime.datetime.now(self.timezone).isoformat()
            return st
        self.store.update(m)

    def mark_user_seen(self):
        def m(st):
            st["conversation"]["lastUserSeenAt"] = datetime.datetime.now(self.timezone).isoformat()
            return st
        self.store.update(m)

    def _render_system_prompt(self) -> str:
        st = self.store.load()
        now = datetime.datetime.now(self.timezone)
        return (f"{self.prompt_template.strip()}\n\n"
                f"Context (tool-grounded):\n"
                f"- Timezone: {self.timezone}\n"
                f"- Local time now: {now.strftime('%H:%M:%S')}\n"
                f"- Happiness: {st['happiness']['score']} "
                f"(good>={self.config['happiness']['goodMoodThreshold']})\n")

    def handle_user_text(self, text: str) -> str:
        history = [
            {"role": "system", "content": self._render_system_prompt()},
            {"role": "user", "content": text}
        ]
        
        tool_calls = 0
        while True:
            model_out = self.ollama.chat(history)
            parsed = parse_tool_call(model_out)
            
            if parsed is None:
                # Stateless retry: do not append failure, resend exact same history
                try:
                    retry_out = self.ollama.chat(history)
                    parsed = parse_tool_call(retry_out)
                except Exception:
                    pass
                if parsed is None:
                    return "I did not understand."

            if parsed["type"] == "final":
                return parsed.get("text", "")
            
            elif parsed["type"] == "tool_call":
                tool_calls += 1
                if tool_calls > 3:
                    return "Let us pause for a moment."
                
                name = parsed.get("name", "")
                args = parsed.get("args", {})
                res = self.tools.execute(name, args)
                
                history.append({"role": "assistant", "content": model_out})
                history.append({"role": "tool", "content": json.dumps(res), "name": name})

    def maybe_proactive_prompt(self) -> str | None:
        st = self.store.load()
        now = datetime.datetime.now(self.timezone)
        
        last_user_str = st["conversation"]["lastUserSeenAt"]
        if not last_user_str: return None
        last_user = datetime.datetime.fromisoformat(last_user_str)
        if (now - last_user).total_seconds() < self.config["proactive"]["silenceThresholdSeconds"]:
            return None

        last_bot_str = st["conversation"]["lastBotSpokeAt"]
        if last_bot_str:
            last_bot = datetime.datetime.fromisoformat(last_bot_str)
            if (now - last_bot).total_seconds() < self.config["proactive"]["minPromptSpacingSeconds"]:
                return None

        due = self.tools.routines_due(now)
        if not due: return None
        top = due[0]
        
        last_prompt_str = st["routines"].get(top.key, {}).get("lastPromptedAt")
        if last_prompt_str:
            last_prompt = datetime.datetime.fromisoformat(last_prompt_str)
            if (now - last_prompt).total_seconds() < self.config["proactive"]["minPromptSpacingSeconds"]:
                return None

        self.tools.mark_prompted(top.key, now)
        return top.suggestedPrompt
