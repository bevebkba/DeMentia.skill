# Session Notes (2026-05-25)

This file captures key decisions and fixes from the initial OpenCode build session.

## Target

- Furhat Skill SDK (Kotlin/Gradle), laptop-only (Virtual Furhat).
- LLM backend: Ollama at `http://100.71.253.9:11434`, model `gemma4:e2b`.
- Timezone: `Europe/Amsterdam`.

## Safety

- No medical advice/diagnosis/dosing.
- Medication prompts must be generic ("scheduled medication") and only when routine tool says due.

## Routine Config (Defaults)

- Proactive: silence `5m`, tick `10s`, min spacing `60s`.
- Hydration: every `120m`, active `08:00-20:00`.
- Medication windows:
  - 07:00-09:00
  - 12:00-13:30
  - 18:00-21:00
  - 21:00-23:00
- Evening calm: after 19:00 suppress non-calm prompts (memory recall allowed).

## Happiness + Memory

- Happiness range: `0..1`.
- Initial happiness: `0.60`.
- Good mood threshold: `>= 0.70`.
- Sentiment update: LLM labels `positive|negative|neutral`; tool applies `+0.05/-0.05/0` and clamps.
- Memory exercise: give 3 words before 12:00 once/day; prompt recall max 2/day; recall allowed after 19:00.

## LLM Contract

Model must output JSON only:

- `{"type":"tool_call","name":"...","args":{...}}`
- `{"type":"final","text":"..."}`

Invalid JSON: one repair attempt then fallback.

## Key Fixes Made During Session

- Java runtime compatibility:
  - Furhat skill runtime uses Java 8 (classfile major 52).
  - Build configured to target Java 8 via Gradle toolchains.
  - Gradle itself may need JDK 21 to run in this environment.

- Config loading:
  - `config.json` is bundled into the `.skill` and loaded from classpath if not present in working directory.

- Flow responsiveness:
  - Ollama HTTP calls moved off the main flow thread using `call { ... }` to avoid "Flow unresponsive" warnings.

- Listening loop:
  - Added `onReentry { furhat.listen() }` so skill keeps listening after each turn/no-response.

- SDK alignment:
  - Skill dependency aligned to installed Virtual Furhat SDK: `furhat-commons:2.9.2`.

## Build/Run Commands

- Build/tests (use JDK 21 for Gradle runtime if needed):
  - `JAVA_HOME=/tmp/opencode/jdk21 PATH=$JAVA_HOME/bin:$PATH ./gradlew test shadowJar`
- Output artifact:
  - `build/libs/ArthurCompanion-0.1.0-all.skill`

## Repo

- Published to: `https://github.com/bevebkba/DeMentia.skill`
