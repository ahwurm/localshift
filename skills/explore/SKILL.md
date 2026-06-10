---
description: Explore a headless AI workload (cron .sh step, Claude Code skill, or prompt file) and produce WORKLOAD.md — its goal, dataflow, tools, and context footprint. Stage 1 of the LocalShift migration pipeline. Use when the user designates a workload to migrate off frontier.
argument-hint: <path-to-.sh | skill-dir | prompt.md> [step-name]
---

# /localshift:explore

Stage 1 of the LocalShift pipeline. Input: `$ARGUMENTS` — a path to a cron shell script (optionally a named step within it), a Claude Code skill directory, or a bare prompt file. Output: `workloads/<name>/WORKLOAD.md` in the LocalShift repo (root = `$CLAUDE_PLUGIN_ROOT` if set, else `~/localshift`).

## Procedure

1. **Read the source read-only.** Never edit the workload itself. If the path doesn't exist or the step name doesn't match, fail explicitly — do not guess.
2. **Derive the workload name**: kebab-case from the step/skill (e.g. `reasoning-qa`, `chart-analyst`). One workload = one LLM invocation shape. A multi-step script becomes multiple workloads; explore the designated step, list the others as candidates.
3. **Trace the workflow** (GSD-explore style — follow every reference):
   - Trigger & cadence (crontab line, schedule, guards like trading-day checks)
   - The exact LLM invocation: command, model (explicit or default), flags, allowed tools, how the prompt is assembled (envsubst vars, file concatenation)
   - Inputs: files/dirs/state read at runtime; which are produced by upstream steps
   - Artifacts written: paths, formats, naming patterns
   - Downstream consumers: who reads the artifacts (later steps, delivery, humans)
   - Failure semantics: `set -e`? logged where? what breaks downstream if this step fails or degrades
4. **Estimate the context footprint** (mark all numbers as estimates): prompt file tokens (~chars/4), typical runtime input tokens (measure a real input if available), expected output size. Note anything that scales (per-ticker fan-out, growing files).
5. **Write `workloads/<name>/WORKLOAD.md`**:

```markdown
# Workload: <name>
- **Source:** <file:line or skill path> (step N of <script>)
- **Goal:** <one sentence — the quality outcome this step exists to produce>
- **Trigger & cadence:** <schedule, guards>

## Dataflow
inputs → step → artifacts → consumers (be concrete: paths, formats)

## LLM call shape
model, tools allowed, flags, prompt assembly, parallelism/fan-out

## Context footprint (estimates)
prompt ~N tok · runtime inputs ~N tok · output ~N tok · scaling notes

## Constraints & risks
<web/edit tool needs, ordering dependencies, latency budget, anything that complicates local replication>

## Open questions
<unknowns — never invent answers>
```

6. **Report** a 5-line summary and suggest the next stage: `/localshift:design-eval <name>`.

## Rules

- Read-only on the source workload. All writes go under `workloads/<name>/`.
- No invented data: unknowns go in Open questions, estimates are labeled.
- If the source already has a WORKLOAD.md, update it in place (note what changed).
