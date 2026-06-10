"""LocalShift runner CLI (RUN-01..05) — the claude-free cron entrypoint.

Exposes four commands wiring the prior-plan modules with honest exit codes so a
cron `set -euo pipefail` step can depend on them:

  validate <task.yaml>            spec.load_task -> 0 valid / 1 errors (RUN-04)
  run <task.yaml> --engine E      pick engine -> RunResult -> ledger row -> exit (RUN-01/02/05)
  check <workload>                run_checks workloads/<w>/checks.yaml -> 0/1 on hard fail (RUN-03)
  ledger [--workload --tail]      view over runs/ledger.jsonl (RUN-05 convenience)

Exit-code discipline (the cron contract): 0 only on success; nonzero on a missing
input, SpecError, run failure (RunResult.ok False), or any hard-check failure.
Usage errors (bad --engine) exit 2. Every `run` ALWAYS appends exactly one ledger
row — success or failure — with model_id/tokens nulls preserved (never fabricated).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from localshift.spec import load_task, SpecError
from localshift.ledger import append_row, ledger_path
from localshift.checks import run_checks
from localshift.engine_local import run_local
from localshift.engine_frontier import run_frontier

app = typer.Typer(add_completion=False, no_args_is_help=True)


def repo_root() -> Path:
    """src/localshift/cli.py -> repo root (parents[2]). Anchors runs/ and workloads/."""
    return Path(__file__).resolve().parents[2]


def utc_ts() -> str:
    """Compact UTC timestamp for trace filenames (sortable, filesystem-safe)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_env(
    declared_vars: list[str],
    date: Optional[str],
    env_pairs: list[str],
    *,
    workdir: str,
) -> dict[str, str]:
    """Assemble the run env the prompt/artifacts render against.

    1. Pull each DECLARED var that is present in os.environ (so DATE_STR etc. flow
       through exactly like the cron). 2. Overlay --env KEY=VALUE pairs (split on the
       first '='). 3. Inject computed defaults ONLY for declared-but-unset vars:
       DATE_STR <- --date (if given); SMOKE_OUT <- <workdir>/smoke.txt. A declared var
       that stays unset is allowed — render_env fails loudly only if it is referenced.
       NEVER blank-fill undeclared vars (that would mask a real missing-var error).
    """
    import os

    env: dict[str, str] = {}
    for v in declared_vars:
        if v in os.environ:
            env[v] = os.environ[v]

    for pair in env_pairs:
        if "=" not in pair:
            raise typer.BadParameter(f"--env expects KEY=VALUE (got: {pair!r})")
        key, val = pair.split("=", 1)
        env[key] = val

    if "DATE_STR" in declared_vars and "DATE_STR" not in env and date:
        env["DATE_STR"] = date
    if "SMOKE_OUT" in declared_vars and "SMOKE_OUT" not in env:
        env["SMOKE_OUT"] = str(Path(workdir) / "smoke.txt")

    return env


@app.command()
def validate(task_yaml: str) -> None:
    """Validate a task.yaml: print actionable errors and exit nonzero on a bad spec,
    exit 0 on a valid one (RUN-04)."""
    try:
        load_task(task_yaml)
    except SpecError as e:
        typer.echo(f"ERROR {task_yaml}:")
        for line in str(e).splitlines():
            typer.echo(line if line.startswith("  ") else f"  {line}")
        raise typer.Exit(1)
    typer.echo(f"OK {task_yaml}")


@app.command()
def run(
    task_yaml: str,
    engine: str = typer.Option(..., "--engine", help="local | frontier"),
    date: Optional[str] = typer.Option(None, "--date", help="YYYY-MM-DD -> DATE_STR if declared"),
    env: Optional[list[str]] = typer.Option(None, "--env", help="KEY=VALUE (repeatable)"),
    trace: Optional[str] = typer.Option(None, "--trace", help="override trace/log path"),
) -> None:
    """Run a task spec on the chosen engine, append exactly one honest ledger row, and
    exit 0 on success / nonzero on any failure (RUN-01 local, RUN-02 frontier, RUN-05)."""
    if engine not in ("local", "frontier"):
        typer.echo(f"ERROR: --engine must be 'local' or 'frontier' (got: {engine!r})")
        raise typer.Exit(2)

    try:
        spec = load_task(task_yaml)
    except SpecError as e:
        typer.echo(f"ERROR {task_yaml}:")
        for line in str(e).splitlines():
            typer.echo(line if line.startswith("  ") else f"  {line}")
        raise typer.Exit(1)

    env_map = build_env(spec.env_vars, date, env or [], workdir=spec.workdir)

    ext = "jsonl" if engine == "local" else "log"
    trace_path = trace or str(repo_root() / "runs" / spec.name / f"{engine}-{utc_ts()}.{ext}")
    Path(trace_path).parent.mkdir(parents=True, exist_ok=True)

    if engine == "local":
        res = asyncio.run(run_local(spec, env_map, trace_path=trace_path))
    else:
        res = run_frontier(spec, env_map, log_path=trace_path)

    # ALWAYS append exactly one row — success or failure. Nulls pass through honestly.
    append_row(
        repo_root(),
        workload=spec.name,
        engine=engine,
        model_id=res.model_id,
        tokens_in=res.tokens_in,
        tokens_out=res.tokens_out,
        tokens_estimated=res.tokens_estimated,
        duration_s=res.duration_s,
        exit_status=(0 if res.ok else 1),
        artifacts_ok=res.artifacts_ok,
        note=res.note,
    )

    typer.echo(
        f"{'OK' if res.ok else 'FAIL'} {spec.name} [{engine}] "
        f"model={res.model_id} tokens={res.tokens_in}/{res.tokens_out}"
        f"{' (est)' if res.tokens_estimated else ''} "
        f"dur={res.duration_s:.1f}s artifacts_ok={res.artifacts_ok} "
        f"trace={res.trace_path}"
        + (f" note={res.note}" if res.note else "")
    )

    if not res.ok:
        raise typer.Exit(1)


@app.command()
def check(
    workload: str,
    date: Optional[str] = typer.Option(None, "--date", help="YYYY-MM-DD -> DATE_STR if used"),
) -> None:
    """Evaluate workloads/<workload>/checks.yaml and exit nonzero on any hard failure
    (RUN-03). Targets render against SMOKE_OUT/DATE_STR so artifact paths resolve."""
    checks_path = repo_root() / "workloads" / workload / "checks.yaml"
    if not checks_path.exists():
        typer.echo(f"ERROR: no checks.yaml for workload {workload!r} at {checks_path}")
        raise typer.Exit(1)

    env_map = build_env(
        ["SMOKE_OUT", "DATE_STR"], date, [], workdir=str(repo_root() / "runs" / workload)
    )
    results, overall = run_checks(str(checks_path), env=env_map)

    n_pass = sum(1 for r in results if r.passed)
    for r in results:
        typer.echo(
            f"{'PASS' if r.passed else 'FAIL'} "
            f"[{'hard' if r.hard else 'soft'}] {r.id} ({r.type}): {r.detail}"
        )
    typer.echo(f"{n_pass}/{len(results)} passed")

    if not overall:
        raise typer.Exit(1)


@app.command()
def ledger(
    workload: Optional[str] = typer.Option(None, "--workload", help="filter by workload name"),
    tail: int = typer.Option(20, "--tail", help="show the last N rows"),
) -> None:
    """View the last N run-ledger rows (default 20), optionally filtered by workload.
    A missing ledger is not an error — prints 'no runs yet' and exits 0."""
    path = ledger_path(repo_root())
    if not path.exists():
        typer.echo("no runs yet")
        return

    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if workload and row.get("workload") != workload:
            continue
        rows.append(row)

    for row in rows[-tail:]:
        typer.echo(
            f"{row.get('ts')} {row.get('workload')} [{row.get('engine')}] "
            f"model={row.get('model_id')} tokens={row.get('tokens_in')}/{row.get('tokens_out')} "
            f"exit={row.get('exit_status')} artifacts_ok={row.get('artifacts_ok')}"
            + (f" note={row.get('note')}" if row.get("note") else "")
        )


def main() -> None:
    """Console-script + `python -m localshift` entrypoint."""
    app()
