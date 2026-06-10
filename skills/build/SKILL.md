---
description: Materialize the eval framework for a designed workload — task.yaml (runner spec), checks.yaml (deterministic checks), judge.md (1v1 protocol). Stage 3 of the LocalShift pipeline.
argument-hint: <workload-name>
---

# /localshift:build

Stage 3. Input: workload name with `WORKLOAD.md` + `EVAL.md` present (repo root = `$CLAUDE_PLUGIN_ROOT` if set, else `~/localshift`); fail explicitly if either is missing. Output: three files under `workloads/<name>/` that fully determine replication and evaluation.

## 1. `task.yaml` — the runner spec (consumed by `bin/localshift run`)

```yaml
name: <name>
source: "<script/skill path + step>"
prompt_file: /abs/path/to/original/prompt.md   # or prompt.local.md if an adaptation was needed (see replicate rules)
env_vars: [DATE_STR, PROJECT_DIR, ...]          # rendered with envsubst semantics
workdir: /abs/path                              # cwd for the agent run
tools: [read, write, bash, glob, grep]          # localharness builtin names only — list exactly what the step needs
budget:
  max_actions: <int>                            # tool calls + finalize; derive from WORKLOAD.md dataflow, not guesswork
  max_duration_minutes: <float>
artifacts:
  - "reports/${DATE_STR}/<artifact>"            # everything downstream consumers need
models:
  local: <default_model from ~/.localharness/config.yaml — read it, don't assume>
  frontier: "claude -p (cron default)"
```

## 2. `checks.yaml` — deterministic apparatus (from EVAL.md rows marked deterministic/structural)

```yaml
checks:
  - id: <kebab-id>
    type: artifact_exists | artifact_parses | contains | regex | forbid_regex | file_glob_count
    target: "<artifact path or glob, ${VAR} ok>"
    value: "<pattern/needle/count — omit for exists/parses>"
    hard: true   # hard=true ⇒ any failure blocks a migrate verdict
```

Every EVAL.md deterministic/structural row maps to exactly one check; cite the dimension id in a comment.

## 3. `judge.md` — the 1v1 protocol (from EVAL.md rows marked judge)

- Dimensions to score (only judge-apparatus ones), each with its good-enough bar from EVAL.md
- Blind A/B layout: identical inputs + artifact A + artifact B, **assignment randomized per run and recorded to `runs/<date>/blind-map.json` which the judge must not read until scores are written**
- Scale: pass / borderline / fail per dimension, one line of evidence each
- Aggregation rule (how per-run scores roll up to the bar)

## Validation

- `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` both YAML files.
- Once the runner lands: `bin/localshift validate workloads/<name>/task.yaml`.
- Cross-check: every EVAL.md dimension is covered by exactly one apparatus artifact (no orphan dimensions, no unmapped checks). Report the coverage table.

Suggest next: `/localshift:replicate <name>`.
