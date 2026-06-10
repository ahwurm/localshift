"""Append-only honest run ledger — every run lands exactly one JSONL row.

One row per run, local or frontier, success or failure. Uncaptured model_id and
token counts are written as null (never fabricated as 0) per the KICKOFF honesty
rule. Append mode only; existing rows are never rewritten. Stdlib only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ENGINES = ("local", "frontier")


def ledger_path(repo_root: str | Path) -> Path:
    """Path to the append-only run ledger (runs/ is gitignored)."""
    return Path(repo_root) / "runs" / "ledger.jsonl"


def append_row(
    repo_root: str | Path,
    *,
    workload: str,
    engine: str,
    model_id: Optional[str],
    tokens_in: Optional[int],
    tokens_out: Optional[int],
    tokens_estimated: bool,
    duration_s: float,
    exit_status: int,
    artifacts_ok: bool,
    note: Optional[str] = None,
) -> dict:
    """Append one honest JSONL row and return it. engine must be local|frontier
    (guards against a typo writing a junk cohort). model_id/tokens=None -> JSON null."""
    if engine not in _ENGINES:
        raise ValueError(f"engine must be one of {_ENGINES} (got: {engine!r})")

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "workload": workload,
        "engine": engine,
        "model_id": model_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_estimated": tokens_estimated,
        "duration_s": duration_s,
        "exit_status": exit_status,
        "artifacts_ok": artifacts_ok,
        "note": note,
    }

    path = ledger_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
    return row
