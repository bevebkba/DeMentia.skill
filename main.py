import sys
import time
import re
from difflib import SequenceMatcher
from furhat_remote_api import FurhatRemoteAPI
from src.arthurcompanion.config import load_config
from src.arthurcompanion.state import StateStore
from src.arthurcompanion.agent import AgentController


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", text.lower())).strip()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

def main():
    try:
        config = load_config()
    except Exception as e:
        print(f"Failed to load config: {e}")
        sys.exit(1)

    store = StateStore()
    furhat = FurhatRemoteAPI("localhost")
    agent = AgentController(config, store, furhat=furhat)
    
    voice = config.get("voice", "Matthew")
    print(f"Setting voice to {voice}...")
    try:
        furhat.set_voice(name=voice)
    except Exception as e:
        print(f"Failed to set voice: {e}")

    print("Starting ArthurCompanion (Python Remote API)...")
    furhat.attend(userid="NOBODY")
    furhat.say(text="Hello Arthur.")
    agent.mark_bot_spoke()
    deafen_seconds = 4.5
    echo_window_seconds = 14.0
    echo_similarity_threshold = 0.72
    deafen_until = time.monotonic() + deafen_seconds
    last_bot_norms = [_normalize_text("Hello Arthur.")]
    last_bot_until = time.monotonic() + echo_window_seconds

    print("Entering listen loop (Press Ctrl+C to exit).")
    try:
        while True:
            # Short-polling listen
            result = furhat.listen()
            
            if result.message:
                if time.monotonic() < deafen_until:
                    continue
                heard_norm = _normalize_text(result.message)
                if heard_norm and time.monotonic() < last_bot_until:
                    blocked = any(_similarity(heard_norm, prev) >= echo_similarity_threshold for prev in last_bot_norms)
                    if blocked:
                        continue
                print(f"User: {result.message}")
                agent.mark_user_seen()
                try:
                    reply = agent.handle_user_text(result.message)
                    if reply:
                        print(f"Arthur: {reply}")
                        furhat.say(text=reply)
                        agent.mark_bot_spoke()
                        deafen_until = time.monotonic() + deafen_seconds
                        last_bot_norms.append(_normalize_text(reply))
                        last_bot_norms = [t for t in last_bot_norms[-3:] if t]
                        last_bot_until = time.monotonic() + echo_window_seconds
                except Exception as e:
                    print(f"Agent Error: {e}")
                    furhat.say(text="I had trouble reaching my brain.")
                    deafen_until = time.monotonic() + deafen_seconds
                    last_bot_norms.append(_normalize_text("I had trouble reaching my brain."))
                    last_bot_norms = [t for t in last_bot_norms[-3:] if t]
                    last_bot_until = time.monotonic() + echo_window_seconds
            else:
                # Timeout, check proactive
                prompt = agent.maybe_proactive_prompt()
                if prompt:
                    print(f"Proactive: {prompt}")
                    furhat.say(text=prompt)
                    agent.mark_bot_spoke()
                    deafen_until = time.monotonic() + deafen_seconds
                    last_bot_norms.append(_normalize_text(prompt))
                    last_bot_norms = [t for t in last_bot_norms[-3:] if t]
                    last_bot_until = time.monotonic() + echo_window_seconds
            
            # Prevent tight spinning if listen returns immediately
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
