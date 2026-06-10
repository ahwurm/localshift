---
description: Run the local replica of a built workload on captured inputs via the claude-free runner; inspect traces and artifacts; iterate the spec until it runs clean. Stage 4 of the LocalShift pipeline.
argument-hint: <workload-name> [--date YYYY-MM-DD]
---

# /localshift:replicate

Stage 4. Input: workload with `task.yaml` built (repo root = `$CLAUDE_PLUGIN_ROOT` if set, else `~/localshift`). Runs the LOCAL engine on captured inputs and iterates until the replica runs clean. The replica must be reproducible claude-free — your role here is mechanic, not model: diagnose and fix the spec, never hand-produce the artifact.

## Procedure

1. **Pick inputs**: `workloads/<name>/runs/<date>/inputs/` (latest date if `--date` omitted). If none exist, fail explicitly — the input-snapshot hook isn't capturing yet; that's the prerequisite, not something to fake.
2. **Run**: `bin/localshift run workloads/<name>/task.yaml --engine local --date <date>`. Sequential runs only while the box is RAM-tight; respect any fan-out cap in task.yaml (≤3 until the quantized model lands).
3. **Inspect**: exit code; the JSONL trace (iterations, tool calls, tokens, termination reason); artifacts present vs `task.yaml: artifacts`.
4. **Diagnose failures** — common causes, in order: budget too small (raise `max_actions`/duration with a reason, not blindly); prompt assumes a tool the local agent lacks (edit/web — see adaptation rule); model emits the answer but doesn't write the artifact (strengthen the prompt's final-action instruction); context overflow (back to `/localshift:design-eval` mitigations).
5. **Prompt adaptation rule**: NEVER edit the original frontier prompt in its source repo. If the local model needs adapted instructions, copy to `workloads/<name>/prompt.local.md`, point `task.yaml: prompt_file` at it, and record the diff + rationale in WORKLOAD.md. The frontier baseline keeps running on the original.
6. **Repeat** until a clean run: exit 0, all artifacts produced, trace shows real tool use (not hallucinated success).
7. **Verify the ledger row** was appended (`runs/ledger.jsonl`: engine=local, model_id from the vLLM response, real token counts).

## Rules

- Report only numbers actually returned — never parallelize a success claim with a still-running command.
- A run that produces the right text but not the artifact file is a FAIL (say-not-do).
- Don't touch the vLLM server, the source workload, or other repos. All changes land under `workloads/<name>/`.

Suggest next once ≥1 clean run per captured date: `/localshift:evaluate <name>`.
