import json
import os
from pathlib import Path
from typing import Any, Dict

def load_config() -> Dict[str, Any]:
    config_path = Path("config.json")
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError("config.json not found in current directory")
