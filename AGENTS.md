# AGENTS.md

- Project is Furhat Skill SDK (Kotlin/Gradle), runs on laptop (no robot deploy).
- Entry point: `src/main/kotlin/furhatos/app/arthurcompanion/main.kt` (`ArthurCompanionSkill`).

- Build skill file: `./gradlew shadowJar` (outputs `build/libs/*.skill`).
- Run locally: Furhat SDK/Virtual Furhat must be running; easiest is run `main()` from IntelliJ.
- Tests: `./gradlew test`.

- Skill runtime uses Java 8 (class file version 52). Build targets Java 8 via Gradle toolchains.

- If `./gradlew` fails on system Java ("Unsupported class file major version 70"), run Gradle with JDK 21 via `JAVA_HOME=... PATH=$JAVA_HOME/bin:$PATH ./gradlew ...`.

- Runtime config lives in `config.json` (timezone `Europe/Amsterdam`, routine windows, Ollama endpoint/model).
- Persistent state lives in `data/state.json` (agenda, happiness, routines, memory, last seen/spoke).

- Ollama endpoint default: `http://100.71.253.9:11434` (`config.json` -> `ollama.baseUrl`).

- LLM contract: model must output JSON only:
  - `{"type":"tool_call","name":"...","args":{...}}` or `{"type":"final","text":"..."}`.
  - Invalid JSON triggers one repair attempt then fallback response.

- Safety hard rule: no medical advice/diagnosis/dosing; medication prompts are generic ("scheduled medication") and only when tool layer marks a window due.
