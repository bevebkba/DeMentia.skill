package furhatos.app.arthurcompanion.tools

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import furhatos.app.arthurcompanion.agent.AppConfig
import furhatos.app.arthurcompanion.agent.TimeWindow
import furhatos.app.arthurcompanion.state.AgendaItem
import furhatos.app.arthurcompanion.state.AgendaStatus
import furhatos.app.arthurcompanion.state.JsonStore
import furhatos.app.arthurcompanion.state.RoutineStatus
import furhatos.app.arthurcompanion.state.State
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.UUID

class ToolDispatcher(
    private val config: AppConfig,
    private val store: JsonStore,
) {
    private val mapper = jacksonObjectMapper()

    fun execute(name: String, args: JsonNode): ToolResult {
        return when (name) {
            "time_now" -> ToolResult.ok(
                mapper.createObjectNode().apply {
                    val zone = ZoneId.of(config.timezone)
                    val now = ZonedDateTime.now(zone)
                    put("iso", now.toInstant().toString())
                    put("localTime", now.toLocalTime().toString())
                    put("zoneId", config.timezone)
                }
            )
            "agenda_add" -> {
                val text = args.path("text").asText("").trim()
                if (text.isBlank()) return ToolResult.error("missing text")
                val now = Instant.now()
                val item = AgendaItem(
                    id = UUID.randomUUID().toString(),
                    text = text,
                    status = AgendaStatus.pending,
                    createdAt = now,
                )
                store.update { it.copy(agenda = it.agenda + item) }
                ToolResult.ok(mapper.valueToTree(item))
            }
            "agenda_list" -> {
                val status = args.path("status").asText("").trim()
                val state = store.load()
                val items = when (status) {
                    "pending" -> state.agenda.filter { it.status == AgendaStatus.pending }
                    "done" -> state.agenda.filter { it.status == AgendaStatus.done }
                    "" -> state.agenda
                    else -> state.agenda
                }
                ToolResult.ok(mapper.valueToTree(items))
            }
            "agenda_complete" -> {
                val idOrText = args.path("idOrText").asText("").trim()
                if (idOrText.isBlank()) return ToolResult.error("missing idOrText")
                val now = Instant.now()
                var matched: AgendaItem? = null
                store.update { st ->
                    val next = st.agenda.map { item ->
                        if (item.status == AgendaStatus.pending && (item.id == idOrText || item.text.equals(idOrText, true))) {
                            val done = item.copy(status = AgendaStatus.done, doneAt = now)
                            matched = done
                            done
                        } else item
                    }
                    st.copy(agenda = next)
                }
                val out = mapper.createObjectNode().apply {
                    put("matched", matched != null)
                    set<JsonNode>("item", if (matched == null) mapper.nullNode() else mapper.valueToTree(matched))
                }
                ToolResult.ok(out)
            }
            "happiness_apply_label" -> {
                val label = args.path("label").asText("").trim().lowercase()
                val delta = when (label) {
                    "positive" -> config.happiness.deltaPositive
                    "negative" -> config.happiness.deltaNegative
                    "neutral" -> 0.0
                    else -> 0.0
                }
                val now = Instant.now()
                val next = store.update { st ->
                    val score = clamp01(st.happiness.score + delta)
                    st.copy(happiness = st.happiness.copy(score = score, updatedAt = now))
                }
                ToolResult.ok(mapper.createObjectNode().put("score", next.happiness.score))
            }
            "happiness_get" -> {
                val st = store.load()
                ToolResult.ok(mapper.createObjectNode().put("score", st.happiness.score))
            }
            "routines_due" -> {
                val now = Instant.parse(args.path("nowIso").asText(Instant.now().toString()))
                val due = computeDue(now, store.load())
                ToolResult.ok(mapper.valueToTree(due))
            }
            "routines_mark_done" -> {
                val key = args.path("key").asText("").trim()
                if (key.isBlank()) return ToolResult.error("missing key")
                val now = Instant.now()
                val next = store.update { st ->
                    st.copy(routines = st.routines + (key to (st.routines[key] ?: RoutineStatus()).copy(lastDoneAt = now)))
                }
                ToolResult.ok(mapper.valueToTree(next.routines[key]))
            }
            "memory_give_words" -> {
                val now = Instant.now()
                val zone = ZoneId.of(config.timezone)
                val localDate = LocalDate.now(zone).toString()
                val words = pickWordsOfDay()
                store.update { st ->
                    st.copy(
                        memory = st.memory.copy(
                            localDate = localDate,
                            words = words,
                            givenAt = now,
                            recallCount = 0,
                            lastRecallAt = null,
                        )
                    )
                }
                ToolResult.ok(mapper.valueToTree(words))
            }
            "memory_mark_recall" -> {
                val now = Instant.now()
                val next = store.update { st ->
                    st.copy(memory = st.memory.copy(recallCount = st.memory.recallCount + 1, lastRecallAt = now))
                }
                ToolResult.ok(mapper.createObjectNode().put("recallCount", next.memory.recallCount))
            }
            else -> ToolResult.error("unknown tool: $name")
        }
    }

    data class DueItem(val key: String, val label: String, val suggestedPrompt: String)

    fun routinesDue(now: Instant): List<DueItem> {
        return computeDue(now, store.load())
    }

    fun markPrompted(key: String, now: Instant = Instant.now()) {
        store.update { st ->
            st.copy(routines = st.routines + (key to (st.routines[key] ?: RoutineStatus()).copy(lastPromptedAt = now)))
        }
    }

    private fun computeDue(now: Instant, st: State): List<DueItem> {
        val zone = ZoneId.of(config.timezone)
        val zdt = now.atZone(zone)
        val localDate = zdt.toLocalDate().toString()

        // Daily reset (memory + per-day routines) when date changes.
        if (st.memory.localDate != null && st.memory.localDate != localDate) {
            store.update { cur ->
                cur.copy(
                    routines = emptyMap(),
                    memory = cur.memory.copy(localDate = localDate, words = null, givenAt = null, recallCount = 0, lastRecallAt = null)
                )
            }
        }

        val due = mutableListOf<DueItem>()

        // Hydration.
        if (withinWindow(zdt.toLocalTime(), config.hydration.activeWindow)) {
            val key = "hydration"
            val lastDone = st.routines[key]?.lastDoneAt
            val lastDoneLocal = lastDone?.atZone(zone)
            val minutesSince = if (lastDoneLocal == null) Long.MAX_VALUE else java.time.Duration.between(lastDoneLocal, zdt).toMinutes()
            if (minutesSince >= config.hydration.intervalMinutes) {
                due.add(DueItem(key, "Hydration", "Would you like a glass of water now?"))
            }
        }

        // Schedule anchors.
        addWindowRoutine(due, st, zdt, zone, key = "breakfast", windowKey = "breakfast", label = "Breakfast", prompt = "Is it time for breakfast now?")
        addWindowRoutine(due, st, zdt, zone, key = "lunch", windowKey = "lunch", label = "Lunch", prompt = "Is it time for lunch now?")
        addWindowRoutine(due, st, zdt, zone, key = "dinner", windowKey = "dinner", label = "Dinner", prompt = "Is it time for dinner now?")
        addWindowRoutine(due, st, zdt, zone, key = "hygiene", windowKey = "hygiene", label = "Hygiene", prompt = "Shall we do hygiene and get ready for bed?")
        addWindowRoutine(due, st, zdt, zone, key = "safety_checks", windowKey = "safetyChecks", label = "Safety checks", prompt = "Shall we do safety checks now: doors, stove, and Luna?")

        // Medication windows: generic prompt only.
        listOf(
            Triple("meds_morning", "Morning medication", config.medicationWindows.morning),
            Triple("meds_lunch", "Lunch medication", config.medicationWindows.lunch),
            Triple("meds_evening", "Evening medication", config.medicationWindows.evening),
            Triple("meds_bed", "Bedtime medication", config.medicationWindows.bed),
        ).forEach { (key, label, window) ->
            if (withinWindow(zdt.toLocalTime(), window)) {
                // Consider it due if not marked done since this window started.
                val start = windowStartToday(zdt.toLocalDate(), window.start, zone)
                val lastDone = st.routines[key]?.lastDoneAt
                if (lastDone == null || lastDone.isBefore(start.toInstant())) {
                    due.add(DueItem(key, label, "Is it time for your scheduled medication now?"))
                }
            }
        }

        // Memory words: give once before noon.
        val noon = LocalTime.parse(config.memoryExercise.giveWordsBefore)
        if (zdt.toLocalTime().isBefore(noon) && st.memory.words == null) {
            due.add(DueItem("memory_give", "Memory words", "Let us do a quick memory exercise. Are you ready for three words?"))
        }

        // Memory recall: max twice/day; allowed after 19:00.
        if (st.memory.words != null && st.memory.recallCount < config.memoryExercise.maxRecallsPerDay) {
            due.add(DueItem("memory_recall", "Recall words", "Do you remember the three words I told you earlier?"))
        }

        // Evening calm: after 19:00, keep only calm items + memory recall.
        val calmCutoff = LocalTime.parse("19:00")
        if (!zdt.toLocalTime().isBefore(calmCutoff)) {
            val allow = setOf(
                "hydration",
                "meds_evening",
                "meds_bed",
                "memory_recall",
                "safety_checks",
                "hygiene",
            )
            return due.filter { allow.contains(it.key) }
        }

        return due
    }

    private fun addWindowRoutine(
        due: MutableList<DueItem>,
        st: State,
        zdt: ZonedDateTime,
        zone: ZoneId,
        key: String,
        windowKey: String,
        label: String,
        prompt: String,
    ) {
        val window = config.dailyScheduleWindows[windowKey] ?: return
        if (!withinWindow(zdt.toLocalTime(), window)) return
        val start = windowStartToday(zdt.toLocalDate(), window.start, zone)
        val lastDone = st.routines[key]?.lastDoneAt
        if (lastDone == null || lastDone.isBefore(start.toInstant())) {
            due.add(DueItem(key, label, prompt))
        }
    }

    private fun withinWindow(now: LocalTime, window: TimeWindow): Boolean {
        val start = LocalTime.parse(window.start)
        val end = LocalTime.parse(window.end)
        return if (end.isAfter(start) || end == start) {
            !now.isBefore(start) && now.isBefore(end)
        } else {
            // Cross-midnight window.
            !now.isBefore(start) || now.isBefore(end)
        }
    }

    private fun windowStartToday(date: LocalDate, start: String, zone: ZoneId): ZonedDateTime {
        return ZonedDateTime.of(date, LocalTime.parse(start), zone)
    }

    private fun clamp01(v: Double): Double = when {
        v < 0.0 -> 0.0
        v > 1.0 -> 1.0
        else -> v
    }

    private fun pickWordsOfDay(): List<String> {
        // Keep deterministic list. Can be upgraded later.
        val pool = listOf(
            "apple",
            "river",
            "chair",
            "window",
            "garden",
            "book",
            "music",
            "coffee",
        )
        return pool.shuffled().take(3)
    }
}
