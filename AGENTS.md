# AGENTS.md

- Read `SESSION.md` first. Treat it as source of truth for schedule defaults, safety rules, LLM contract, and already-fixed runtime issues.

- Repo is single-module Furhat Remote API Python app for laptop/Virtual Furhat, not robot deploy.
- Entry point: `main.py`.
- Run locally with Virtual Furhat running: `python main.py` in the `furhat` conda environment.

- Legacy Kotlin code is preserved in `legacy/`.

- `config.json` is runtime config.
- Persistent app state is `data/state.json`; updated via standard Python IO.

- LLM settings in `config.json` under `"llm"` key: base URL, model, optional apiKey.
- LLM output must stay JSON-only: `{"type":"tool_call","name":"...","args":{}}` or `{"type":"final","text":"..."}`. Parser allows exactly one repair retry, then fallback.

- Safety invariant: no medical advice/diagnosis/dosing. Medication prompts must remain generic `scheduled medication` and only come from due-window tool logic.
- Routine/schedule behavior is implemented in `src/main/kotlin/furhatos/app/arthurcompanion/tools/ToolDispatcher.kt`; preserve calm-evening filtering, happiness clamp/update rules, and memory exercise limits from `SESSION.md`.

- Python loop uses short-polling `furhat.listen(timeout=5000)`.
- Voice-only start: `furhat.attend(userid="NOBODY")` and `Hello Arthur.`; no FaceEngine dependency. User tracking updates only on verbal response.

- Tests are sparse. Existing coverage is `src/test/kotlin/furhatos/app/arthurcompanion/ToolDispatcherTest.kt`; when changing routine timing or state-reset logic, add focused tests there or alongside it.
