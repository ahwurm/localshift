---
description: Derive the quality eval for an explored workload — measurement dimensions, apparatus (deterministic checks + judge protocol), a good-enough bar (NOT frontier parity), and a feasibility verdict for local hardware. Stage 2 of the LocalShift pipeline.
argument-hint: <workload-name>
---

# /localshift:design-eval

Stage 2. Input: a workload name with an existing `workloads/<name>/WORKLOAD.md` (repo root = `$CLAUDE_PLUGIN_ROOT` if set, else `~/localshift`). Output: `workloads/<name>/EVAL.md`. Fail explicitly if WORKLOAD.md is missing — run `/localshift:explore` first.

The user's standard: **they know local won't be frontier; it has to be good enough and work.** Your job is to define what "good enough" measurably means for THIS workload, and whether local hardware can honestly attempt it.

## Procedure

1. **Goal → quality dimensions.** From WORKLOAD.md's Goal, derive 3–6 dimensions that, if met, mean the step did its job (e.g. for a QA step: catches-real-errors, preserves-structure, no-destructive-rewrites; for chart generation: rule-compliance, data-fidelity, completeness). Each must be observable from artifacts or traces.
2. **Measurement aperture.** For each dimension: which artifact/property/trace exposes it.
3. **Apparatus.** For each dimension, choose the cheapest sufficient instrument, in priority order:
   - `deterministic` — file exists/parses, hard rules, forbidden patterns (preferred; goes to checks.yaml)
   - `structural` — contains:/regex: assertions on artifact content
   - `judge` — needs the 1v1 blind comparison (goes to judge.md); use sparingly, for genuinely qualitative dimensions
4. **Good-enough bar per dimension.** Explicit pass criterion (e.g. "0 hard-rule violations across all runs", "judge ≥ pass on ≥ 5/6 runs"). NOT parity with frontier — frontier output is the reference anchor, not the bar.
5. **Feasibility verdict.** Check against the actual local stack:
   - Context: prompt + typical inputs + output vs the served model's window (probe live: `curl -s http://127.0.0.1:8000/v1/models` — read `max_model_len`; do not assume)
   - Tools: required tools vs localharness builtins available on the pinned version (read/write/glob/grep/bash — NO edit, NO web on current pin)
   - Memory/latency: fan-out pressure, KV-cache headroom, acceptable wall-clock for the cron slot
   - **Try mitigations before declaring infeasible**: prompt slimming, splitting the step, dropping non-essential context, capping fan-out. Record each mitigation tried/proposed.
6. **Write `workloads/<name>/EVAL.md`**:

```markdown
# Eval design: <name>
## Quality dimensions
| dimension | aperture (what's measured) | apparatus (deterministic/structural/judge) | good-enough bar |

## Run requirements
N runs minimum (per-dimension if needed), input variety notes, same-model_id cohort rule.

## Feasibility
verdict: feasible | feasible-with-mitigations | infeasible-now
context math · tool gaps · memory/latency · mitigations (tried/proposed)

## Recommendation
proceed-to-build | keep-frontier (with the specific blocking reason)
```

## Rules

- `keep-frontier` / `infeasible-now` are legitimate, reportable outcomes — say so plainly; that honesty is the product.
- Every bar must be checkable by Stage 5 without new information.
- Probe live endpoints/configs rather than assuming hardware facts; label anything unprobed as assumption.
