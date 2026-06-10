"""engine_frontier (RUN-02) — reproduce the cron `claude -p` invocation for baseline
capture, plus best-effort token harvest from the session transcript.

Reproduces the morning/afternoon-report cron shape EXACTLY (morning-report.sh steps
1/2/3a): the envsubst-rendered prompt piped to
    claude -p --dangerously-skip-permissions --allowedTools "<CSV>"
run with cwd=workdir. In-process we render the prompt via spec.render_env (the envsubst
equivalent) and feed it on stdin. ok is gated on returncode 0 AND declared-artifact
presence.

Token harvest is best-effort: Claude writes a session transcript JSONL under
~/.claude/projects/<slug>/. We sum real usage from it. If the transcript is absent or
unparsable we record null tokens + a note — NEVER fabricated zeros (the KICKOFF/STATE
honesty rule). Harvest failure is non-fatal: the run still succeeded if artifacts exist.

RunResult is imported from engine_local — single definition, same contract.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Mapping, Optional

from .engine_local import RunResult
from .spec import TaskSpec, render_env, resolve_artifacts

# Friendly task.yaml tool names -> Claude-CLI --allowedTools names (the cron CSV form).
# Edit is not in our tool set.
_CLI_TOOL_MAP = {
    "read": "Read",
    "write": "Write",
    "bash": "Bash",
    "glob": "Glob",
    "grep": "Grep",
}


def _allowed_tools_csv(tools: list[str]) -> str:
    """Build the --allowedTools CSV from friendly tool names, matching the cron strings
    (e.g. ['read','write','bash'] -> 'Read,Write,Bash'). Raise on an unmapped tool."""
    names: list[str] = []
    for t in tools:
        key = t.lower()
        if key not in _CLI_TOOL_MAP:
            raise ValueError(
                f"tool {t!r} has no Claude-CLI allowedTools mapping "
                f"(known: {', '.join(sorted(_CLI_TOOL_MAP))})"
            )
        names.append(_CLI_TOOL_MAP[key])
    return ",".join(names)


def _project_slug(workdir: str | Path) -> str:
    """Claude derives the transcript project dir from the resolved cwd by replacing '/'
    with '-' (e.g. /home/openclaw-user/financial-models ->
    -home-openclaw-user-financial-models)."""
    return str(Path(workdir).resolve()).replace("/", "-")


def harvest_tokens(
    workdir: str | Path, since_epoch: float
) -> tuple[Optional[int], Optional[int], bool, Optional[str]]:
    """Best-effort token harvest from the just-written session transcript.

    Returns (tokens_in, tokens_out, estimated, note). On any failure (no transcript dir,
    no recent transcript, no usage records, parse error) returns (None, None, False, note)
    — NEVER 0 to mean unknown. tokens_in includes cache_read + cache_creation (real prompt
    cost). estimated is True if some assistant lines lacked usage.
    """
    try:
        proj = Path.home() / ".claude" / "projects" / _project_slug(workdir)
        if not proj.is_dir():
            return (None, None, False, f"no transcript dir for workdir {workdir}")

        # Files written since the run started (allow 1s slack for clock granularity).
        candidates = [
            f for f in proj.glob("*.jsonl") if f.stat().st_mtime >= since_epoch - 1
        ]
        if not candidates:
            return (None, None, False, "no transcript file written since run start")

        transcript = max(candidates, key=lambda f: f.stat().st_mtime)

        tin = 0
        tout = 0
        found = False
        missing_usage = False
        with open(transcript) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = (obj.get("message") or {}).get("usage") or obj.get("usage")
                if usage:
                    tin += int(usage.get("input_tokens", 0) or 0)
                    tin += int(usage.get("cache_read_input_tokens", 0) or 0)
                    tin += int(usage.get("cache_creation_input_tokens", 0) or 0)
                    tout += int(usage.get("output_tokens", 0) or 0)
                    found = True
                elif _is_assistant(obj):
                    missing_usage = True

        if not found:
            return (None, None, False, "transcript had no usage records")
        return (tin, tout, missing_usage, None)
    except Exception as e:  # noqa: BLE001 — harvest failure is data, not a crash
        return (None, None, False, "frontier token harvest failed: " + repr(e))


def _is_assistant(obj: dict) -> bool:
    """True if a transcript line is an assistant message (used to flag estimated when an
    assistant line lacks usage). Tolerates both top-level role and message.role shapes."""
    if obj.get("type") == "assistant" or obj.get("role") == "assistant":
        return True
    msg = obj.get("message")
    return isinstance(msg, dict) and msg.get("role") == "assistant"


def run_frontier(
    spec: TaskSpec, env: Mapping[str, str], *, log_path: str | Path
) -> RunResult:
    """Run the frontier baseline via `claude -p`, reproducing the cron invocation shape.

    The subprocess flags, the allowedTools CSV form, cwd=workdir, and prompt-on-stdin all
    match the cron. ok = (returncode == 0) AND all declared artifacts present. Token
    harvest is best-effort and non-fatal (null + note on failure, never fabricated).
    """
    # 1. Render the prompt in-process (envsubst equivalent) and build the allowedTools CSV.
    prompt = render_env(Path(spec.prompt_file).read_text(), env)
    csv = _allowed_tools_csv(list(spec.tools))

    # 2. Record wall-time BEFORE launching so the harvest finds the just-written transcript.
    Path(spec.workdir).mkdir(parents=True, exist_ok=True)
    since = time.time()
    t0 = time.monotonic()

    # 3. Reproduce the cron `claude -p` call. Prompt on stdin == the `envsubst | claude -p`
    #    pipe. Timeout = the task's max duration.
    proc = None
    timed_out = False
    try:
        proc = subprocess.run(
            [
                "claude",
                "-p",
                "--dangerously-skip-permissions",
                "--allowedTools",
                csv,
            ],
            input=prompt,
            text=True,
            cwd=spec.workdir,
            capture_output=True,
            timeout=spec.max_duration_minutes * 60,
        )
    except subprocess.TimeoutExpired:
        timed_out = True

    duration = time.monotonic() - t0

    # 4. Persist stdout+stderr as the trace (== the cron `>> log 2>&1`).
    log_p = Path(log_path)
    log_p.parent.mkdir(parents=True, exist_ok=True)
    body = (getattr(proc, "stdout", "") or "") + (getattr(proc, "stderr", "") or "")
    log_p.write_text(body)

    # 5. Artifact gate: returncode 0 AND every declared artifact present and non-empty.
    artifacts = resolve_artifacts(spec, env)
    artifacts_ok = all(p.exists() and p.stat().st_size > 0 for p in artifacts)
    returncode = getattr(proc, "returncode", None)
    ok = (returncode == 0) and artifacts_ok

    # 6. Best-effort token harvest. model_id stays None for v0.1 (do NOT guess the served
    #    model from the transcript).
    tin, tout, est, hnote = harvest_tokens(spec.workdir, since)
    model_id = None

    # 7. Compose the note: run failure reason (if any) + harvest note (if tokens null).
    parts: list[str] = []
    if not ok:
        if timed_out:
            parts.append("claude -p timed out")
        else:
            parts.append(f"claude -p failed (rc={returncode})")
    if tin is None and hnote:
        parts.append(hnote)
    note = "; ".join(parts) if parts else None

    return RunResult(
        ok=ok,
        model_id=model_id,
        tokens_in=tin,
        tokens_out=tout,
        tokens_estimated=est,
        duration_s=duration,
        artifacts_ok=artifacts_ok,
        trace_path=str(log_p),
        note=note,
    )
