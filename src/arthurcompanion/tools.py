import datetime
import uuid
import random
from typing import Dict, Any, List
from zoneinfo import ZoneInfo
from .state import StateStore

class ToolDispatcher:
    def __init__(self, config: Dict[str, Any], store: StateStore):
        self.config = config
        self.store = store
        self.timezone = ZoneInfo(config["timezone"])

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

    def execute(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        now = self.get_now()
        now_iso = now.isoformat()

        if name == "time_now":
            return {
                "status": "ok",
                "data": {
                    "iso": now_iso,
                    "localTime": now.strftime("%H:%M:%S"),
                    "zoneId": str(self.timezone)
                }
            }
        
        elif name == "agenda_add":
            text = args.get("text", "").strip()
            if not text: return {"status": "error", "message": "missing text"}
            item = {
                "id": str(uuid.uuid4()),
                "text": text,
                "status": "pending",
                "createdAt": now_iso
            }
            def add_item(st):
                st["agenda"].append(item)
                return st
            self.store.update(add_item)
            return {"status": "ok", "data": item}

        elif name == "agenda_list":
            status = args.get("status", "").strip()
            st = self.store.load()
            items = st.get("agenda", [])
            if status in ("pending", "done"):
                items = [i for i in items if i.get("status") == status]
            return {"status": "ok", "data": items}

        elif name == "agenda_complete":
            id_or_text = args.get("idOrText", "").strip()
            if not id_or_text: return {"status": "error", "message": "missing idOrText"}
            matched = None
            def complete_item(st):
                nonlocal matched
                for item in st["agenda"]:
                    if item["status"] == "pending" and (item["id"] == id_or_text or item["text"].lower() == id_or_text.lower()):
                        item["status"] = "done"
                        item["doneAt"] = now_iso
                        matched = item
                        break
                return st
            self.store.update(complete_item)
            return {"status": "ok", "data": {"matched": matched is not None, "item": matched}}

        elif name == "happiness_apply_label":
            label = args.get("label", "").strip().lower()
            delta = 0.0
            if label == "positive": delta = self.config["happiness"]["deltaPositive"]
            elif label == "negative": delta = self.config["happiness"]["deltaNegative"]
            
            new_score = 0.0
            def apply_hap(st):
                nonlocal new_score
                cur = st["happiness"]["score"]
                new_score = max(0.0, min(1.0, cur + delta))
                st["happiness"]["score"] = new_score
                st["happiness"]["updatedAt"] = now_iso
                return st
            self.store.update(apply_hap)
            return {"status": "ok", "data": {"score": new_score}}

        elif name == "happiness_get":
            return {"status": "ok", "data": {"score": self.store.load()["happiness"]["score"]}}

        elif name == "routines_due":
            due = self.routines_due(now)
            return {"status": "ok", "data": [d.__dict__ for d in due]}

        elif name == "routines_mark_done":
            key = args.get("key", "").strip()
            if not key: return {"status": "error", "message": "missing key"}
            def mark_done(st):
                if key not in st["routines"]: st["routines"][key] = {}
                st["routines"][key]["lastDoneAt"] = now_iso
                return st
            st = self.store.update(mark_done)
            return {"status": "ok", "data": st["routines"][key]}

        elif name == "memory_give_words":
            words = random.sample(["apple", "river", "chair", "window", "garden", "book", "music", "coffee"], 3)
            def give_words(st):
                st["memory"].update({
                    "localDate": now.date().isoformat(),
                    "words": words,
                    "givenAt": now_iso,
                    "recallCount": 0,
                    "lastRecallAt": None
                })
                return st
            self.store.update(give_words)
            return {"status": "ok", "data": words}

        elif name == "memory_mark_recall":
            rc = 0
            def mark_recall(st):
                nonlocal rc
                st["memory"]["recallCount"] += 1
                st["memory"]["lastRecallAt"] = now_iso
                rc = st["memory"]["recallCount"]
                return st
            self.store.update(mark_recall)
            return {"status": "ok", "data": {"recallCount": rc}}

        return {"status": "error", "message": f"unknown tool: {name}"}

    class DueItem:
        def __init__(self, key: str, label: str, prompt: str):
            self.key = key
            self.label = label
            self.suggestedPrompt = prompt

    def mark_prompted(self, key: str, dt_now: datetime.datetime = None):
        if not dt_now: dt_now = self.get_now()
        def mp(st):
            if key not in st["routines"]: st["routines"][key] = {}
            st["routines"][key]["lastPromptedAt"] = dt_now.isoformat()
            return st
        self.store.update(mp)

    def routines_due(self, now: datetime.datetime) -> List['ToolDispatcher.DueItem']:
        st = self.store.load()
        local_date_str = now.date().isoformat()
        now_time = now.time()

        if st["memory"]["localDate"] and st["memory"]["localDate"] != local_date_str:
            def reset_daily(s):
                s["routines"] = {}
                s["memory"].update({
                    "localDate": local_date_str,
                    "words": None, "givenAt": None, "recallCount": 0, "lastRecallAt": None,
                    "memoryState": "idle"
                })
                return s
            st = self.store.update(reset_daily)

        due = []

        # Hydration
        hc = self.config["hydration"]
        if self._in_window(now_time, hc["activeWindow"]["start"], hc["activeWindow"]["end"]):
            last_done_str = st["routines"].get("hydration", {}).get("lastDoneAt")
            if not last_done_str:
                due.append(self.DueItem("hydration", "Hydration", "Would you like a glass of water now?"))
            else:
                last_done = datetime.datetime.fromisoformat(last_done_str)
                if (now - last_done).total_seconds() / 60 >= hc["intervalMinutes"]:
                    due.append(self.DueItem("hydration", "Hydration", "Would you like a glass of water now?"))

        # Schedule Anchors
        dw = self.config["dailyScheduleWindows"]
        self._add_window(due, st, now, "breakfast", dw.get("breakfast"), "Breakfast", "Is it time for breakfast now?")
        self._add_window(due, st, now, "lunch", dw.get("lunch"), "Lunch", "Is it time for lunch now?")
        self._add_window(due, st, now, "dinner", dw.get("dinner"), "Dinner", "Is it time for dinner now?")
        self._add_window(due, st, now, "feed_luna", dw.get("feedLuna"), "Feed Luna", "Shall we feed Luna now?")
        self._add_window(due, st, now, "hygiene", dw.get("hygiene"), "Hygiene", "Shall we do hygiene and get ready for bed?")
        self._add_window(due, st, now, "safety_checks", dw.get("safetyChecks"), "Safety checks", "Shall we do safety checks now: doors, stove, and Luna?")

        # Meds
        mw = self.config["medicationWindows"]
        for k, lbl, win in [("meds_morning", "Morning medication", mw.get("morning")),
                            ("meds_lunch", "Lunch medication", mw.get("lunch")),
                            ("meds_evening", "Evening medication", mw.get("evening")),
                            ("meds_bed", "Bedtime medication", mw.get("bed"))]:
            if win and self._in_window(now_time, win["start"], win["end"]):
                win_start_dt = datetime.datetime.combine(now.date(), datetime.time.fromisoformat(win["start"]), tzinfo=self.timezone)
                last_done_str = st["routines"].get(k, {}).get("lastDoneAt")
                if not last_done_str or datetime.datetime.fromisoformat(last_done_str) < win_start_dt:
                    due.append(self.DueItem(k, lbl, "Is it time for your scheduled medication now?"))

        # Memory
        mc = self.config["memoryExercise"]
        noon = datetime.time.fromisoformat(mc["giveWordsBefore"])
        if now_time < noon and not st["memory"].get("words"):
            due.append(self.DueItem("memory_give", "Memory words", "Let us do a quick memory exercise. Are you ready for three words?"))
        
        if st["memory"].get("words") and st["memory"]["recallCount"] < mc["maxRecallsPerDay"]:
            allow_time = datetime.time.fromisoformat(mc["allowAfter"])
            if now_time >= allow_time:
                due.append(self.DueItem("memory_recall", "Recall words", "Do you remember the three words I told you earlier?"))

        # Evening Calm
        calm = datetime.time.fromisoformat("19:00")
        if now_time >= calm:
            allowed = {"hydration", "meds_evening", "meds_bed", "memory_recall", "safety_checks", "hygiene", "feed_luna"}
            due = [d for d in due if d.key in allowed]

        return due

    def _add_window(self, due, st, now, key, win, label, prompt):
        if not win: return
        if not self._in_window(now.time(), win["start"], win["end"]): return
        win_start_dt = datetime.datetime.combine(now.date(), datetime.time.fromisoformat(win["start"]), tzinfo=self.timezone)
        last_done_str = st["routines"].get(key, {}).get("lastDoneAt")
        if not last_done_str or datetime.datetime.fromisoformat(last_done_str) < win_start_dt:
            due.append(self.DueItem(key, label, prompt))

    def _in_window(self, t, start_str, end_str) -> bool:
        start = datetime.time.fromisoformat(start_str)
        end = datetime.time.fromisoformat(end_str)
        if end >= start:
            return start <= t < end
        return t >= start or t < end
