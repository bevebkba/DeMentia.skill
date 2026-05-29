import json
from pathlib import Path
from typing import Any, Dict

class StateStore:
    def __init__(self, path: str = "data/state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {
                "agenda": [],
                "happiness": {"score": 0.6, "updatedAt": None},
                "routines": {},
                "memory": {
                    "localDate": None,
                    "words": None,
                    "givenAt": None,
                    "recallCount": 0,
                    "lastRecallAt": None
                },
                "conversation": {"lastUserSeenAt": None, "lastBotSpokeAt": None}
            }
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, state: Dict[str, Any]) -> None:
        # Standard Python IO as agreed (Option A)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def update(self, fn) -> Dict[str, Any]:
        current = self.load()
        next_state = fn(current)
        self.save(next_state)
        return next_state
