import requests
import json
from typing import List, Dict, Any

class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = ""):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.api_key = api_key

    def chat(self, messages: List[Dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": messages
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=(10, 60)
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

def parse_tool_call(text: str) -> Dict[str, Any] | None:
    text = text.strip()
    # Attempt simple parse first
    try:
        data = json.loads(text)
        if data.get("type") in ("tool_call", "final"):
            return data
    except Exception:
        pass

    # Extract JSON inside markdown code blocks if present
    if "```" in text:
        try:
            # Look for ```json ... ``` or ``` ... ```
            parts = text.split("```")
            for part in parts[1::2]: # inspect content inside blocks
                # Strip optional "json" language prefix
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                try:
                    data = json.loads(candidate)
                    if data.get("type") in ("tool_call", "final"):
                        return data
                except Exception:
                    continue
        except Exception:
            pass

    # Attempt to locate first { and last } to extract JSON from prose
    try:
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidate = text[start_idx:end_idx + 1]
            data = json.loads(candidate)
            if data.get("type") in ("tool_call", "final"):
                return data
    except Exception:
        pass

    return None
