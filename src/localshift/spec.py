"""task.yaml loader, validator, and env rendering — the single source-of-truth parser.

Implements the task.yaml schema from skills/build/SKILL.md section 1. Both engines
(Plan 03) and the CLI (Plan 04) consume load_task(). Hand-rolled validation (no
pydantic) so error messages are field-level and actionable. pyyaml is the only
non-stdlib dependency.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

# Friendly builtin tool names accepted in task.yaml `tools:`. spec.py does NOT map
# these to localharness register_builtin_tools names (bash->bash_exec, lowercasing) —
# that is engine_local's job (Plan 03). Validation is case-insensitive.
KNOWN_TOOLS = {"read", "write", "bash", "glob", "grep"}

# ${VAR} or $VAR (word chars). Used by render_env for envsubst-style substitution.
_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

REQUIRED_FIELDS = (
    "name", "source", "prompt_file", "env_vars",
    "workdir", "tools", "budget", "artifacts", "models",
)


class SpecError(Exception):
    """Unrecoverable task.yaml problem: parse error, missing render var, or aggregate
    validation failure."""


@dataclass
class TaskSpec:
    name: str
    source: str
    prompt_file: str
    env_vars: list[str]
    workdir: str
    tools: list[str]
    max_actions: int
    max_duration_minutes: float
    artifacts: list[str]
    model_local: str
    model_frontier: str


def validate_task(data: dict) -> list[str]:
    """Pure function (no I/O). Return human-readable error strings; empty list = valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["task spec must be a mapping (got: %r)" % type(data).__name__]

    for key in REQUIRED_FIELDS:
        if key not in data:
            errors.append(f"missing required field: {key}")

    pf = data.get("prompt_file")
    if "prompt_file" in data and (not isinstance(pf, str) or not pf.strip()):
        errors.append("prompt_file must be a non-empty string")

    tools = data.get("tools")
    if "tools" in data:
        if not isinstance(tools, list):
            errors.append("tools must be a list of builtin tool names")
        else:
            for i, t in enumerate(tools):
                if not isinstance(t, str) or t.lower() not in KNOWN_TOOLS:
                    errors.append(
                        f"tools[{i}]={t!r} is not a known builtin tool "
                        f"(allowed: read,write,bash,glob,grep)"
                    )

    budget = data.get("budget")
    if "budget" in data:
        if not isinstance(budget, dict):
            errors.append("budget must be a mapping with max_actions and max_duration_minutes")
        else:
            ma = budget.get("max_actions")
            if not isinstance(ma, int) or isinstance(ma, bool) or ma < 1:
                errors.append(f"budget.max_actions must be an int >= 1 (got: {ma!r})")
            md = budget.get("max_duration_minutes")
            if isinstance(md, bool) or not isinstance(md, (int, float)) or md <= 0:
                errors.append(f"budget.max_duration_minutes must be a number > 0 (got: {md!r})")

    artifacts = data.get("artifacts")
    if "artifacts" in data:
        if not isinstance(artifacts, list) or not artifacts:
            errors.append("artifacts must be a non-empty list of strings")
        elif not all(isinstance(a, str) for a in artifacts):
            errors.append("artifacts must be a non-empty list of strings")

    models = data.get("models")
    if "models" in data:
        if not isinstance(models, dict):
            errors.append("models must be a mapping with local and frontier")
        else:
            if not isinstance(models.get("local"), str):
                errors.append("models.local must be a string (the default_model name)")
            if not isinstance(models.get("frontier"), str):
                errors.append("models.frontier must be a string")

    return errors


def load_task(path: str | Path) -> TaskSpec:
    """Parse task.yaml at path, validate, and build a TaskSpec. Raises SpecError on
    YAML errors or aggregate validation failure (messages joined by newline)."""
    p = Path(path)
    try:
        with open(p) as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as e:
        raise SpecError(f"failed to parse YAML {p}: {e}") from e
    except OSError as e:
        raise SpecError(f"cannot read task spec {p}: {e}") from e

    errors = validate_task(data)
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise SpecError(f"invalid task spec {p}:\n{joined}")

    budget = data["budget"]
    models = data["models"]
    return TaskSpec(
        name=data["name"],
        source=data["source"],
        prompt_file=data["prompt_file"],
        env_vars=list(data["env_vars"]),
        workdir=data["workdir"],
        tools=list(data["tools"]),
        max_actions=budget["max_actions"],
        max_duration_minutes=float(budget["max_duration_minutes"]),
        artifacts=list(data["artifacts"]),
        model_local=models["local"],
        model_frontier=models["frontier"],
    )


def render_env(text: str, env: Mapping[str, str]) -> str:
    """Substitute ${VAR} / $VAR tokens from env (in-process, deterministic). Raise
    SpecError naming any referenced var absent from env."""
    def _sub(m: re.Match[str]) -> str:
        var = m.group(1) or m.group(2)
        if var not in env:
            raise SpecError(f"undefined variable in template: {var}")
        return str(env[var])

    return _VAR_RE.sub(_sub, text)


def resolve_artifacts(spec: TaskSpec, env: Mapping[str, str]) -> list[Path]:
    """Render each declared artifact path with env; relative paths join under
    spec.workdir. Engines use this to assert artifacts exist post-run."""
    out: list[Path] = []
    for a in spec.artifacts:
        rendered = render_env(a, env)
        p = Path(rendered)
        if not p.is_absolute():
            p = Path(spec.workdir) / p
        out.append(p)
    return out
