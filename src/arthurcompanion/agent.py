import datetime
import json
from zoneinfo import ZoneInfo
from .state import StateStore
from .tools import ToolDispatcher
from .llm import LLMClient, parse_tool_call

class AgentController:
    def __init__(self, config: dict, store: StateStore, furhat=None):
        self.config = config
        self.store = store
        self.furhat = furhat
        self.tools = ToolDispatcher(config, store)
        self.llm = LLMClient(
            config["llm"]["baseUrl"],
            config["llm"]["model"],
            config["llm"].get("apiKey", "")
        )
        self.timezone = ZoneInfo(config["timezone"])
        self.idle_spacing_seconds = 120  # 2 minutes between idle chat
        try:
            with open("prompts_system.txt", "r", encoding="utf-8") as f:
                self.prompt_template = f.read()
        except FileNotFoundError:
            self.prompt_template = "You are Arthur. Output JSON only."

    def play_gesture(self, name: str):
        if not self.furhat:
            return
        expressive = self.config.get("expressiveMode", True)
        if expressive:
            try:
                self.furhat.gesture(name=name)
            except Exception as e:
                print(f"[DEBUG] Failed to play gesture {name}: {e}")
        else:
            print(f"[DEBUG] expressiveMode=False. Suppressed gesture: {name}")

    def get_now(self) -> datetime.datetime:
        mock_str = self.config.get("mockTime", "")
        if mock_str:
            try:
                if "T" in mock_str:
                    return datetime.datetime.fromisoformat(mock_str).astimezone(self.timezone)
                else:
                    t = datetime.time.fromisoformat(mock_str)
                    d = datetime.datetime.now(self.timezone).date()
                    return datetime.datetime.combine(d, t, tzinfo=self.timezone)
            except Exception as e:
                print(f"[WARNING] Failed to parse mockTime '{mock_str}': {e}")
        return datetime.datetime.now(self.timezone)

    def mark_bot_spoke(self):
        def m(st):
            st["conversation"]["lastBotSpokeAt"] = self.get_now().isoformat()
            return st
        self.store.update(m)

    def mark_user_seen(self):
        def m(st):
            st["conversation"]["lastUserSeenAt"] = self.get_now().isoformat()
            return st
        self.store.update(m)

    # ── 3-variable skill router ──────────────────────────────────────
    def _select_skill(self, now, st, due):
        """Check time, happiness, and due tasks → return (skill_name, directive)."""
        happiness = st["happiness"]["score"]
        pending = [i for i in st.get("agenda", []) if i.get("status") == "pending"]

        # Priority 1: Medication due
        med_due = [d for d in due if d.key.startswith("meds_")]
        if med_due:
            return ("medication", f"URGENT: {med_due[0].label} is due RIGHT NOW. Remind Arthur firmly and kindly to take his scheduled medication.")

        # Priority 2: Meal / routine due
        routine_due = [d for d in due if d.key in ("breakfast", "lunch", "dinner", "hygiene", "safety_checks", "hydration")]
        if routine_due:
            return ("routine", f"{routine_due[0].label} is due RIGHT NOW. Guide Arthur to do it.")

        # Priority 3: Low happiness → comfort skill
        if happiness < self.config["happiness"]["goodMoodThreshold"]:
            return ("comfort", f"Arthur's happiness is {happiness:.2f} (below {self.config['happiness']['goodMoodThreshold']}). Be extra warm, suggest ONE calming activity.")

        # Priority 4: Pending agenda tasks
        if pending:
            top = pending[0]["text"]
            return ("task", f"Arthur has a pending task: '{top}'. Help him work on it or ask if he wants to do it now.")

        # Priority 5: Memory exercise due
        mem_due = [d for d in due if d.key.startswith("memory_")]
        if mem_due:
            return ("memory", f"{mem_due[0].label} is due. Start the memory exercise.")

        # Priority 6: Nothing pressing → idle small talk
        return ("idle", "Nothing urgent is due. Make friendly small talk, suggest a simple activity, or ask Arthur how he is feeling. Keep it natural and warm.")

    def _select_proactive_skill(self, now, st, due):
        """Select the highest-priority skill/routine that is not on cooldown.
        Returns (skill_name, key, directive) or (None, None, None).
        """
        happiness = st["happiness"]["score"]
        pending = [i for i in st.get("agenda", []) if i.get("status") == "pending"]

        # Helper to check if a key is on cooldown
        def on_cooldown(key, cooldown_seconds):
            last_prompt_str = st["routines"].get(key, {}).get("lastPromptedAt")
            if last_prompt_str:
                last_prompt = datetime.datetime.fromisoformat(last_prompt_str)
                return (now - last_prompt).total_seconds() < cooldown_seconds
            return False

        # Priority 1: Medication due
        med_due = [d for d in due if d.key.startswith("meds_")]
        for med in med_due:
            if not on_cooldown(med.key, self.config["proactive"]["minPromptSpacingSeconds"]):
                return (
                    "medication",
                    med.key,
                    f"URGENT: {med.label} is due RIGHT NOW. Remind Arthur firmly and kindly to take his scheduled medication."
                )

        # Priority 2: Meal / routine due
        routine_due = [d for d in due if d.key in ("breakfast", "lunch", "dinner", "hygiene", "safety_checks", "hydration")]
        for r in routine_due:
            if not on_cooldown(r.key, self.config["proactive"]["minPromptSpacingSeconds"]):
                return (
                    "routine",
                    r.key,
                    f"{r.label} is due RIGHT NOW. Guide Arthur to do it."
                )

        # Priority 3: Low happiness → comfort skill (triggered under Option B threshold of 0.50)
        if happiness < 0.50:
            if not on_cooldown("skill_comfort", 300):  # 5 min cooldown
                return (
                    "comfort",
                    "skill_comfort",
                    f"Arthur's happiness is {happiness:.2f} (below 0.50). Be extra warm, suggest ONE calming activity."
                )

        # Priority 4: Pending agenda tasks
        if pending:
            if not on_cooldown("skill_task", 300):  # 5 min cooldown
                top = pending[0]["text"]
                return (
                    "task",
                    "skill_task",
                    f"Arthur has a pending task: '{top}'. Help him work on it or ask if he wants to do it now."
                )

        # Priority 5: Memory exercise due
        mem_due = [d for d in due if d.key.startswith("memory_")]
        for m in mem_due:
            if not on_cooldown(m.key, self.config["proactive"]["minPromptSpacingSeconds"]):
                return (
                    "memory",
                    m.key,
                    f"{m.label} is due. Start the memory exercise."
                )

        # Priority 6: Nothing pressing → idle small talk
        if not on_cooldown("skill_idle", 120):  # 2 min cooldown
            return (
                "idle",
                "skill_idle",
                "Nothing urgent is due. Make friendly small talk, suggest a simple activity, or ask Arthur how he is feeling. Keep it natural and warm."
            )

        return None, None, None

    # ── Auto-gather context (no LLM tool calls needed) ───────────────
    def _gather_context(self, now, st):
        """Automatically call tools and build context string for the LLM."""
        due = self.tools.routines_due(now)
        due_str = ", ".join(d.label for d in due) if due else "none"

        happiness = st["happiness"]["score"]

        pending = [i["text"] for i in st.get("agenda", []) if i.get("status") == "pending"]
        pending_str = ", ".join(pending) if pending else "none"

        return due, (
            f"Context (auto-checked by system, NOT by you):\n"
            f"- Timezone: {self.timezone}\n"
            f"- Local time now: {now.strftime('%H:%M:%S')}\n"
            f"- Happiness: {happiness:.2f} (good>={self.config['happiness']['goodMoodThreshold']})\n"
            f"- Routines due NOW: {due_str}\n"
            f"- Pending tasks: {pending_str}\n"
        )

    # ── System prompt with all 3 variables ───────────────────────────
    def _render_system_prompt(self, context_str, skill_directive=None) -> str:
        prompt = f"{self.prompt_template.strip()}\n\n{context_str}"

        if skill_directive:
            prompt += f"\n>>> PRIORITY ACTION: {skill_directive}\n"

        return prompt

    # ── Handle user speech ───────────────────────────────────────────
    def handle_user_text(self, text: str) -> str:
        from .config import load_config
        try:
            self.config = load_config()
            self.tools.config = self.config
        except Exception:
            pass

        st = self.store.load()
        now = self.get_now()
        due, context_str = self._gather_context(now, st)
        
        # ── Scripted Routine & Exercise Interceptions ──────────────────────
        active_script = st.get("conversation", {}).get("activeScript", "")
        mem_state = st.get("memory", {}).get("memoryState", "idle")
        words = st.get("memory", {}).get("words", [])
        norm_text = text.lower()
        
        # 1. Active Script Interceptions (Ongoing Routines)
        if active_script:
            confirmed = False
            denied = False
            
            # Simple keyword-based checking for affirmation / denial
            if any(w in norm_text for w in ["yes", "yeah", "yep", "ok", "okay", "sure", "done", "took", "fed", "ate", "finished", "completed"]):
                confirmed = True
            elif any(w in norm_text for w in ["no", "nope", "not now", "later", "dont", "don't", "cant", "can't"]):
                denied = True
                
            # Medication scripts
            if active_script.startswith("meds_"):
                if confirmed:
                    self.tools.execute("routines_mark_done", {"key": active_script})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Smile")
                    name_map = {
                        "meds_morning": "Morning medication",
                        "meds_lunch": "Lunch medication",
                        "meds_evening": "Evening medication",
                        "meds_bed": "Bedtime medication"
                    }
                    lbl = name_map.get(active_script, "Medication")
                    return f"Good. {lbl} is checked off."
                elif denied:
                    name_map = {
                        "meds_morning": "Morning medication",
                        "meds_lunch": "Lunch medication",
                        "meds_evening": "Evening medication",
                        "meds_bed": "Bedtime medication"
                    }
                    lbl = name_map.get(active_script, "Medication")
                    self.tools.execute("agenda_add", {"text": lbl})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Thoughtful")
                    return f"No problem, Arthur. I will add {lbl} to your agenda so we don't forget it, and we can check back later."
            
            # Cat food script
            elif active_script == "feed_luna":
                if confirmed:
                    self.tools.execute("routines_mark_done", {"key": "feed_luna"})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("BigSmile")
                    return "Well done! Luna is fed and happy now."
                elif denied:
                    self.tools.execute("agenda_add", {"text": "Feed Luna"})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Thoughtful")
                    return "No problem. I will add Feed Luna to your agenda for later. Let's move on."
                    
            # Meal scripts
            elif active_script in ("breakfast", "lunch", "dinner"):
                if confirmed:
                    self.tools.execute("routines_mark_done", {"key": active_script})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Smile")
                    return f"Great! I have marked your {active_script} as completed."
                elif denied:
                    lbl = active_script.capitalize()
                    self.tools.execute("agenda_add", {"text": lbl})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Thoughtful")
                    return f"No problem. I will add {lbl} to your agenda for later. Let's move on."

            # Safety checks script
            elif active_script == "safety_checks":
                if confirmed:
                    self.tools.execute("routines_mark_done", {"key": "safety_checks"})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Smile")
                    return "Excellent! The safety checks are completed and everything is secure."
                elif denied:
                    self.tools.execute("agenda_add", {"text": "Safety checks"})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Thoughtful")
                    return "No problem. I will add Safety checks to your agenda for later."

            # Hygiene script
            elif active_script == "hygiene":
                if confirmed:
                    self.tools.execute("routines_mark_done", {"key": "hygiene"})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Smile")
                    return "Great! Hygiene routine is checked off."
                elif denied:
                    self.tools.execute("agenda_add", {"text": "Hygiene"})
                    def clear_script(s):
                        s["conversation"]["activeScript"] = ""
                        return s
                    self.store.update(clear_script)
                    self.play_gesture("Thoughtful")
                    return "No problem. I will add Hygiene to your agenda for later."

        # 2. Memory Exercise Dialog States
        if mem_state == "giving":
            matched = [w for w in words if w.lower() in norm_text]
            def clear_giving(s):
                s["memory"]["memoryState"] = "idle"
                return s
            self.store.update(clear_giving)
            if len(matched) == 3:
                self.play_gesture("BigSmile")
                return f"Excellent, Arthur! You repeated all three words: {', '.join(words)}. Please keep them in mind, I will ask you to recall them later today."
            elif len(matched) > 0:
                self.play_gesture("Smile")
                return f"Very close, Arthur! You repeated {', '.join(matched)}. Just to be sure, the three words are: {', '.join(words)}. Try to keep them in mind, and I will test you on them later."
            else:
                self.play_gesture("Thoughtful")
                return f"No worries, Arthur. Let me say them again. The three words are: {', '.join(words)}. Please keep these in mind, and we will try to recall them later today."

        elif mem_state == "recalling":
            matched = [w for w in words if w.lower() in norm_text]
            self.tools.execute("memory_mark_recall", {})
            def clear_recalling(s):
                s["memory"]["memoryState"] = "idle"
                return s
            self.store.update(clear_recalling)
            if len(matched) == 3:
                self.play_gesture("BigSmile")
                return f"Wonderful job, Arthur! You recalled all three words perfectly: {', '.join(words)}. Your memory is doing excellent today!"
            elif len(matched) > 0:
                self.play_gesture("Smile")
                return f"Good try, Arthur! You recalled {len(matched)} of the words: {', '.join(matched)}. The three words were: {', '.join(words)}. We will keep practicing!"
            else:
                self.play_gesture("Thoughtful")
                return f"That is completely fine, Arthur. The three words were: {', '.join(words)}. Don't worry, we can practice again next time!"

        # 3. Explicit User-Triggered Interceptions
        # Memory Exercise
        if any(phrase in norm_text for phrase in ["start exercise", "memory game", "word game", "give me words", "start the exercise"]):
            res = self.tools.execute("memory_give_words", {})
            new_words = res["data"]
            def set_giving(s):
                s["memory"]["memoryState"] = "giving"
                return s
            self.store.update(set_giving)
            self.play_gesture("BigSmile")
            return f"Let's do our memory game! I will tell you three words. Please repeat them back to me: {', '.join(new_words)}. What are the three words?"

        elif any(phrase in norm_text for phrase in ["recall words", "test my memory", "test memory", "what were the words", "do the recall"]):
            if not words:
                return "We haven't done the memory game yet today. Would you like to start it now and get three words?"
            def set_recalling(s):
                s["memory"]["memoryState"] = "recalling"
                return s
            self.store.update(set_recalling)
            self.play_gesture("Smile")
            return "It is time to check your memory! Do you remember the three words I told you earlier today?"

        # Medication
        elif any(phrase in norm_text for phrase in ["take my medication", "take my medicine", "take medication", "take medicine", "give me my medicine"]):
            hour = now.hour
            if 5 <= hour < 12:
                med_key = "meds_morning"
                lbl = "Morning medication"
            elif 12 <= hour < 18:
                med_key = "meds_lunch"
                lbl = "Lunch medication"
            elif 18 <= hour < 21:
                med_key = "meds_evening"
                lbl = "Evening medication"
            else:
                med_key = "meds_bed"
                lbl = "Bedtime medication"
                
            def set_script(s):
                s["conversation"]["activeScript"] = med_key
                return s
            self.store.update(set_script)
            self.play_gesture("Thoughtful")
            return f"Let's begin with our daily routine. Your medication is in the kitchen inside the white pillbox on the counter. Have you taken your {lbl.lower()} yet?"

        # Feed Luna
        elif any(phrase in norm_text for phrase in ["feed luna", "feed the cat", "give luna food"]):
            def set_script(s):
                s["conversation"]["activeScript"] = "feed_luna"
                return s
            self.store.update(set_script)
            self.play_gesture("Smile")
            return "Next, Luna is probably hungry. The cat food is on the kitchen counter. Have you fed Luna yet?"

        # Agenda Checks
        elif any(phrase in norm_text for phrase in ["what's on my agenda", "what is on my agenda", "show me my agenda", "check my agenda", "check the agenda", "my agenda"]):
            res = self.tools.execute("agenda_list", {"status": "pending"})
            pending_items = res.get("data", [])
            if not pending_items:
                return "You have no pending items on your agenda today! Everything is all caught up."
            items_str = ", ".join(i["text"] for i in pending_items)
            return f"You have {len(pending_items)} pending items on your agenda: {items_str}. Let me know if you completed any of these."
        
        # We don't pass a strict PRIORITY ACTION directive on user speech,
        # so the LLM responds naturally to the user.
        history = [
            {"role": "system", "content": self._render_system_prompt(context_str)},
            {"role": "user", "content": text}
        ]

        # Log active skill state for debugging
        skill_name, _ = self._select_skill(now, st, due)

        def debug_ctx() -> str:
            s = self.store.load()
            n = self.get_now()
            h = s.get("happiness", {}).get("score")
            cl = [i.get("text", "") for i in s.get("agenda", []) if i.get("status") == "pending"]
            d = [item.key for item in self.tools.routines_due(n)]
            return f"time={n.strftime('%H:%M:%S')} happiness={h} checklist={cl} due={d} skill={skill_name}"

        tool_calls = 0
        while True:
            model_out = self.llm.chat(history)
            parsed = parse_tool_call(model_out)
            print(f"[DEBUG] {debug_ctx()} model_out={model_out}")

            if parsed is None:
                # Stateless retry
                try:
                    retry_out = self.llm.chat(history)
                    parsed = parse_tool_call(retry_out)
                    print(f"[DEBUG] {debug_ctx()} retry_out={retry_out}")
                except Exception:
                    pass
                if parsed is None:
                    print(f"[DEBUG] {debug_ctx()} parsed=None after retry")
                    return "I did not understand."

            if parsed["type"] == "final":
                print(f"[DEBUG] {debug_ctx()} parsed_type=final text={parsed.get('text', '')}")
                return parsed.get("text", "")

            elif parsed["type"] == "tool_call":
                tool_calls += 1
                if tool_calls > 3:
                    return "Let us pause for a moment."

                name = parsed.get("name", "")
                args = parsed.get("args", {})
                print(f"[DEBUG] {debug_ctx()} parsed_type=tool_call name={name} args={args}")
                res = self.tools.execute(name, args)
                print(f"[DEBUG] {debug_ctx()} tool_result name={name} result={res}")

                history.append({"role": "assistant", "content": model_out})
                history.append({"role": "user", "content": f"[Tool result for {name}]: {json.dumps(res)}"})

    # ── Proactive prompt (silence-triggered) ─────────────────────────
    def maybe_proactive_prompt(self) -> str | None:
        from .config import load_config
        try:
            self.config = load_config()
            self.tools.config = self.config
        except Exception:
            pass

        st = self.store.load()
        now = self.get_now()

        # Gather the 3 variables
        due, context_str = self._gather_context(now, st)
        skill_name, key, directive = self._select_proactive_skill(now, st, due)

        if not skill_name:
            return None

        # Determine spacing based on skill urgency
        if skill_name in ("medication", "routine", "memory"):
            spacing = self.config["proactive"]["minPromptSpacingSeconds"]  # 30s
        else:
            spacing = max(60, self.config["proactive"]["minPromptSpacingSeconds"])  # At least 60s for non-urgent

        # Guard: don't speak too soon after the last bot message
        last_bot_str = st["conversation"]["lastBotSpokeAt"]
        if last_bot_str:
            last_bot = datetime.datetime.fromisoformat(last_bot_str)
            if (now - last_bot).total_seconds() < spacing:
                return None

        # Mark the chosen skill/routine as prompted
        self.tools.mark_prompted(key, now)

        # Intercept proactive routines for scripted dialogue
        if key.startswith("meds_"):
            def set_script(s):
                s["conversation"]["activeScript"] = key
                return s
            self.store.update(set_script)
            self.play_gesture("Thoughtful")
            name_map = {
                "meds_morning": "morning medication",
                "meds_lunch": "lunch medication",
                "meds_evening": "evening medication",
                "meds_bed": "bedtime medication"
            }
            lbl = name_map.get(key, "medication")
            return f"Arthur, your medication is in the kitchen inside the white pillbox on the counter. Have you taken your {lbl} yet? Let me know when you are done."
            
        elif key == "feed_luna":
            def set_script(s):
                s["conversation"]["activeScript"] = "feed_luna"
                return s
            self.store.update(set_script)
            self.play_gesture("Smile")
            return "Arthur, Luna is probably hungry. The cat food is on the kitchen counter. Please go to the kitchen, take the cat food from the counter, and fill her bowl. Let me know when it is done."
            
        elif key in ("breakfast", "lunch", "dinner"):
            def set_script(s):
                s["conversation"]["activeScript"] = key
                return s
            self.store.update(set_script)
            self.play_gesture("Smile")
            return f"Arthur, it is time for your {key}. Please go to the kitchen, take the food out of the fridge, put it in the microwave, and heat it up. Let me know when you are done."
            
        elif key == "safety_checks":
            def set_script(s):
                s["conversation"]["activeScript"] = "safety_checks"
                return s
            self.store.update(set_script)
            self.play_gesture("Thoughtful")
            return "Arthur, let's do our safety checks. Please make sure the doors are locked, the stove is off, and Luna is safe inside. Have you locked the front doors yet?"
            
        elif key == "hygiene":
            def set_script(s):
                s["conversation"]["activeScript"] = "hygiene"
                return s
            self.store.update(set_script)
            self.play_gesture("Smile")
            return "Arthur, it is time to get ready for bed. Shall we do our hygiene routine now?"

        elif key == "memory_give":
            res = self.tools.execute("memory_give_words", {})
            new_words = res["data"]
            def set_giving(s):
                s["memory"]["memoryState"] = "giving"
                return s
            self.store.update(set_giving)
            self.play_gesture("BigSmile")
            return f"Let's do our memory game! I will tell you three words. Please repeat them back to me: {', '.join(new_words)}. What are the three words?"
            
        elif key == "memory_recall":
            words = st.get("memory", {}).get("words", [])
            if words:
                def set_recalling(s):
                    s["memory"]["memoryState"] = "recalling"
                    return s
                self.store.update(set_recalling)
                self.play_gesture("Smile")
                return "It is time to check your memory! Do you remember the three words I told you earlier today?"

        # Use LLM with full context to generate a natural prompt
        try:
            reply = self._run_proactive_llm(context_str, directive)
            if reply:
                return reply
        except Exception as e:
            print(f"[DEBUG] proactive LLM error: {e}")

        return None

    def _run_proactive_llm(self, context_str, directive) -> str | None:
        """Send a proactive prompt through the LLM with full context."""
        history = [
            {"role": "system", "content": self._render_system_prompt(context_str, directive)},
            {"role": "user", "content": "[System: Arthur has not spoken. Based on the context above, speak to Arthur about the most important thing right now. Do NOT mention system internals.]"}
        ]

        model_out = self.llm.chat(history)
        parsed = parse_tool_call(model_out)

        if parsed and parsed["type"] == "final":
            return parsed.get("text", "")

        # If LLM tried a tool call, execute it and get the final text
        if parsed and parsed["type"] == "tool_call":
            name = parsed.get("name", "")
            args = parsed.get("args", {})
            res = self.tools.execute(name, args)
            history.append({"role": "assistant", "content": model_out})
            history.append({"role": "user", "content": f"[Tool result for {name}]: {json.dumps(res)}"})

            model_out2 = self.llm.chat(history)
            parsed2 = parse_tool_call(model_out2)
            if parsed2 and parsed2["type"] == "final":
                return parsed2.get("text", "")

        return None
