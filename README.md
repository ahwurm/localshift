# LocalShift

Point Claude Code at any headless AI workload — a cron job, a skill, a bare prompt — and migrate it to a local LLM with a **derived, per-workload quality eval**.

The bar is not frontier parity. It's *good enough, and works* — proven, not assumed.

## Pipeline

| Stage | Skill | Output |
|---|---|---|
| 1. Explore the workflow | `/localshift:explore` | `WORKLOAD.md` — goal, dataflow, tools, context footprint |
| 2. Design the eval | `/localshift:design-eval` | `EVAL.md` — quality dimensions, measurement apparatus, good-enough bar, feasibility verdict |
| 3. Build the framework | `/localshift:build` | `task.yaml` + `checks.yaml` + `judge.md` |
| 4. Replicate locally | `/localshift:replicate` | Local runs + traces + artifacts via the claude-free runner |
| 5. Evaluate 1v1 | `/localshift:evaluate` | `EVAL-REPORT.md` — blind local-vs-frontier judging → **migrate / conditional / keep-frontier** |

Claude Code does the exploring, eval design, and judging (interactive). The migrated job runs **claude-free** in cron via `bin/localshift` on the [LocalHarness](https://github.com/ahwurm/localharness) runtime — any OpenAI-compatible local endpoint (vLLM, Ollama, llama.cpp).

Honest verdicts are the product: workloads that don't fit local hardware (context window, memory, missing tools) or miss the quality bar get **keep-frontier**, with receipts.

## Install

```text
/plugin marketplace add ahwurm/localshift
/plugin install localshift@localshift
```

Dev: `claude --plugin-dir /path/to/localshift`

## Status

v0.1 in build — launching June 15, 2026 alongside LocalHarness. Part of the Local__ family. MIT.
