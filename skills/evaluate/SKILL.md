---
description: The 1v1 — run deterministic checks on all captured runs, judge local vs frontier blind per the workload's protocol, aggregate into EVAL-REPORT.md with a migrate/conditional/keep-frontier verdict. Stage 5 (final) of the LocalShift pipeline.
argument-hint: <workload-name>
---

# /localshift:evaluate

Stage 5 — the verdict. Input: workload with built apparatus and runs captured (repo root = `$CLAUDE_PLUGIN_ROOT` if set, else `~/localshift`). Output: `workloads/<name>/EVAL-REPORT.md` — the final eval artifact.

## Procedure

1. **Enumerate eligible runs**: dates under `runs/` with BOTH a frontier baseline and ≥1 clean local run on the SAME inputs. Check against EVAL.md's N-runs requirement; if short, stop and report exactly what's missing (dates, counts) — no verdict on insufficient data.
2. **Cohorts**: group local runs by `model_id` from the ledger. Never mix weights in one cohort (a quantization swap mid-window starts a fresh cohort); the verdict cohort is the one meeting N.
3. **Deterministic checks**: run every `checks.yaml` check against every eligible run's artifacts (`bin/localshift check`, or apply by hand with bash/grep until the runner lands). Tabulate pass rates per check, local AND frontier (frontier failures calibrate whether a check is too strict).
4. **Blind 1v1 judging** per `judge.md`:
   - For each eligible date: present identical inputs + artifact A + artifact B per the recorded `blind-map.json` — do NOT read the map until all scores for that date are written down.
   - Score each judge dimension pass/borderline/fail with one line of evidence.
   - After scoring all dates, unblind and attribute.
5. **Aggregate `EVAL-REPORT.md`**:

```markdown
# Eval report: <name>   (<date range>, cohort model_id=<id>, N=<n>)
## Deterministic checks
| check | hard | local pass | frontier pass |
## 1v1 judge (blind)
| dimension | bar | local | frontier (anchor) | met? |
## Feasibility notes
<latency, memory, fan-out observations from traces>
## VERDICT: migrate | conditional | keep-frontier
<one paragraph of reasoning anchored to the bars>
<if migrate: the exact cutover flag block to paste into the source .sh>
<if conditional: the ordered fix list>
<if keep-frontier: the specific blocking dimension(s)/constraint(s)>
```

   Verdict logic: **migrate** = zero hard-check failures in the cohort AND every judge dimension meets its bar. **conditional** = specific fixable gaps. **keep-frontier** = a dimension or feasibility constraint local can't meet now — state it plainly; this is a first-class product outcome.

## Honesty rules

- Only computed numbers; no extrapolation across cohorts or undated claims.
- Judge scores come from artifacts you actually read this session, blind-first.
- Cutover itself is manual + user-approved: emit the flag block, never edit the source `.sh` from this skill.
