"""engine_local (RUN-01) — run a task spec through the pinned localharness AgentLoop
against the live vLLM endpoint.

Sources model_id LIVE from the endpoint (/v1/models) — never from config (an NVFP4
weight swap may change the served model mid-week, so the cohort label must be read
from the endpoint at run time). Builds the tool registry from a REAL base registry
restricted to the task tools — `from_allowed` raises without a base (the empty-registry
trap documented in localharness bench/runner.py). Writes a JSONL EventBus trace and
gates ok on declared-artifact presence: a missing artifact is a FAIL, never a silent
success (the say-not-do gate from skills/replicate).

Returns the uniform RunResult the CLI (Plan 04) maps to a ledger row. engine_frontier
imports RunResult from here — single definition.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

import httpx

from .spec import TaskSpec, render_env, resolve_artifacts

# The live local endpoint. Only the URL is a constant — the model NAME is always read
# from the endpoint response below, never hard-coded (NVFP4 cohort honesty).
BASE_URL = "http://localhost:8000/v1"

# Friendly task.yaml tool names -> localharness register_builtin_tools names. spec.py
# stores the friendly names verbatim (read/write/bash/glob/grep); the rename + lowercase
# is engine_local's job. register_builtin_tools registers exactly: bash_exec/glob/grep/
# read/write.
_BUILTIN_TOOL_MAP = {
    "read": "read",
    "write": "write",
    "glob": "glob",
    "grep": "grep",
    "bash": "bash_exec",
}


@dataclass
class RunResult:
    """Uniform run outcome across both engines; the CLI maps it to a ledger row.

    ok is True only if the run completed AND every declared artifact exists.
    model_id/tokens are None (never fabricated 0) when not captured — the honesty rule.
    """

    ok: bool
    model_id: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    tokens_estimated: bool
    duration_s: float
    artifacts_ok: bool
    trace_path: Optional[str]
    note: Optional[str]


def _resolve_model_id() -> Optional[str]:
    """Read the served model id from the live endpoint. Return None on any failure or
    empty list — the run then cannot proceed honestly (no config fallback model)."""
    try:
        data = httpx.get(BASE_URL + "/models", timeout=10).json()["data"]
        if not data:
            return None
        return data[0]["id"]
    except Exception:
        return None


def _map_tools_builtin(tools: list[str]) -> list[str]:
    """Map friendly task tool names to localharness builtin names. Raise ValueError on
    an unmapped tool (spec.py already validated membership, but fail loud on drift)."""
    mapped: list[str] = []
    for t in tools:
        key = t.lower()
        if key not in _BUILTIN_TOOL_MAP:
            raise ValueError(
                f"tool {t!r} has no localharness builtin mapping "
                f"(known: {', '.join(sorted(_BUILTIN_TOOL_MAP))})"
            )
        mapped.append(_BUILTIN_TOOL_MAP[key])
    return mapped


async def run_local(spec: TaskSpec, env: Mapping[str, str], *, trace_path: str | Path) -> RunResult:
    """Run one task spec via the localharness AgentLoop against the live vLLM endpoint.

    ONE task per call (RAM-tight box — no asyncio.gather fan-out). The AgentLoop's
    run_turn never raises (loop.py converts internal errors to a summary string), so
    the authoritative success signal is declared-artifact presence, not the loop return.
    """
    # 1. model_id LIVE from the endpoint — no fallback. Unreachable -> clean ok=False.
    model_id = _resolve_model_id()
    if model_id is None:
        return RunResult(
            ok=False,
            model_id=None,
            tokens_in=None,
            tokens_out=None,
            tokens_estimated=False,
            duration_s=0.0,
            artifacts_ok=False,
            trace_path=None,
            note="endpoint /v1/models unreachable or empty — cannot source model_id",
        )

    # Imports local to keep module import cheap and isolate localharness signature drift.
    from localharness.agent.context import ContextManager
    from localharness.agent.loop import AgentLoop
    from localharness.agent.permissions import PermissionEvaluator
    from localharness.config.models import AgentConfig, BudgetConfig, PermissionConfig
    from localharness.core.bus import EventBus
    from localharness.core.events import TurnCompleted, TurnFailed
    from localharness.provider.client import LLMClient, LLMConfig
    from localharness.tools.builtin import register_builtin_tools
    from localharness.tools.registry import ToolRegistry

    # 2. LLMConfig — is_local REQUIRES timeout_seconds >= 300.0 or LLMClient raises.
    #    model is the LIVE endpoint id (stored in RunResult.model_id too). The endpoint
    #    advertises supports_function_calling: false, so detect_capabilities() must run
    #    once before the loop to set tool_call_mode (xml/native) from a live probe.
    cfg = LLMConfig(
        base_url=BASE_URL,
        model=model_id,
        api_key="none",
        timeout_seconds=300.0,
        temperature=0.6,
        max_tokens=4096,
        is_local=True,
        extra_headers={},
        stop_sequences=[],
    )
    llm = LLMClient(cfg)
    await llm.detect_capabilities()  # never raises; defaults to xml on probe failure

    # 3. Tool registry from a REAL base restricted to the task tools. base_registry is
    #    MANDATORY — from_allowed() WITHOUT it raises (the empty-registry trap).
    base = ToolRegistry()
    await register_builtin_tools(base)
    allowed = _map_tools_builtin(list(spec.tools))
    tool_registry = ToolRegistry.from_allowed(allowed, base_registry=base)

    # 4. EventBus persisting each event as one JSONL line == the run trace. Subscribe a
    #    tiny token accumulator BEFORE the run (run_turn returns only the summary string;
    #    token counts arrive on TurnCompleted/TurnFailed — verified model_fields).
    trace_p = Path(trace_path)
    trace_p.parent.mkdir(parents=True, exist_ok=True)
    bus = EventBus(persist_path=trace_p)
    acc = {"tin": 0, "tout": 0, "est": False, "seen": False}

    async def _accumulate(ev) -> None:
        acc["tin"] += int(getattr(ev, "input_tokens", 0) or 0)
        acc["tout"] += int(getattr(ev, "output_tokens", 0) or 0)
        acc["est"] = acc["est"] or bool(getattr(ev, "tokens_estimated", False))
        acc["seen"] = True

    bus.subscribe(TurnCompleted, _accumulate)
    bus.subscribe(TurnFailed, _accumulate)

    # 5. AgentLoop construction (verified signature). Agent name validator allows
    #    [a-z0-9-] only — replace underscores from spec.name.
    agent_name = "localshift-" + spec.name.replace("_", "-")
    agent_config = AgentConfig(
        name=agent_name,
        role="LocalShift replica run for " + spec.name,
        permissions=PermissionConfig(
            budget=BudgetConfig(
                max_actions=spec.max_actions,
                max_duration_minutes=spec.max_duration_minutes,
            )
        ),
    )
    ctx = ContextManager(
        max_context_tokens=65000, bus=bus, agent_id=agent_name, session_id=agent_name
    )
    perms = PermissionEvaluator()
    loop = AgentLoop(
        config=agent_config,
        llm=llm,
        bus=bus,
        context_manager=ctx,
        tool_registry=tool_registry,
        permission_evaluator=perms,
    )

    # 6. Prompt = the prompt file with the run env substituted in-process (SMOKE_OUT, ...).
    prompt = render_env(Path(spec.prompt_file).read_text(), env)

    # 7. Run in spec.workdir so relative tool writes land where artifacts expect; restore
    #    cwd in finally no matter what.
    Path(spec.workdir).mkdir(parents=True, exist_ok=True)
    cwd0 = os.getcwd()
    os.chdir(spec.workdir)
    t0 = time.monotonic()
    try:
        await loop.run_turn(task=prompt)
    finally:
        os.chdir(cwd0)
    duration_s = time.monotonic() - t0

    # 8. Artifact presence is the authoritative gate (run_turn never raises). A declared
    #    artifact that is missing or empty = ok False, no silent success.
    artifacts = resolve_artifacts(spec, env)
    artifacts_ok = all(p.exists() and p.stat().st_size > 0 for p in artifacts)
    ok = artifacts_ok

    # 9. Tokens: real endpoint usage if any turn was seen (keep ints even if 0); else
    #    None/None. note explains a failure (which artifacts are missing).
    tokens_in = acc["tin"] if acc["seen"] else None
    tokens_out = acc["tout"] if acc["seen"] else None
    if ok:
        note = None
    else:
        missing = [str(p) for p in artifacts if not (p.exists() and p.stat().st_size > 0)]
        note = "artifacts missing or empty: " + ", ".join(missing)

    return RunResult(
        ok=ok,
        model_id=model_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_estimated=acc["est"],
        duration_s=duration_s,
        artifacts_ok=artifacts_ok,
        trace_path=str(trace_p),
        note=note,
    )
