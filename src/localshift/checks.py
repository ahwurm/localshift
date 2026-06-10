"""Deterministic check engine (RUN-03).

Loads a checks.yaml, evaluates each rule against produced artifacts, and returns
structured results plus an overall pass/fail. A hard-check failure flips
overall_passed to False; the CLI (Plan 04) turns that into a nonzero exit so the
cron path (set -euo pipefail) aborts rather than shipping a broken local run.

Pure data-in / data-out: paths + rules -> results. No printing here (the CLI
formats the table). Missing targets FAIL explicitly — never silently skip.
"""
from __future__ import annotations

import glob
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_CMP = re.compile(r"^(>=|<=|==|>|<)\s*(-?\d+)$")
_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}
_KNOWN = {
    "artifact_exists",
    "artifact_parses",
    "contains",
    "regex",
    "forbid_regex",
    "file_glob_count",
}


@dataclass
class CheckResult:
    id: str
    type: str
    hard: bool
    passed: bool
    detail: str


class _RenderError(Exception):
    """A target could not be rendered (missing var / no env) — fail the check."""


def load_checks(path) -> list[dict]:
    """Parse checks.yaml; return its ``checks`` list.

    Raise ValueError (naming the path) if the top-level ``checks`` key is
    missing or is not a list.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    checks = (data or {}).get("checks") if isinstance(data, dict) else None
    if not isinstance(checks, list):
        raise ValueError(f"{path}: top-level 'checks' must be a list")
    return checks


def render_target(target: str, env) -> str:
    """Resolve ``${VAR}`` tokens in a target path.

    Uses spec.render_env when it is importable (lazy import so this module loads
    even when spec.py is absent); otherwise substitutes locally. Raises
    _RenderError on a missing referenced var or when a token appears with no env.
    """
    if not isinstance(target, str) or "${" not in target:
        return target
    try:
        from localshift import spec  # lazy: spec.py may not exist yet
    except Exception:
        spec = None
    if spec is not None and hasattr(spec, "render_env"):
        try:
            return spec.render_env(target, env)
        except Exception as exc:  # missing var surfaces as a check failure
            raise _RenderError(str(exc)) from exc

    def _sub(m: re.Match) -> str:
        name = m.group(1)
        if not env or name not in env:
            raise _RenderError(f"unset variable ${{{name}}} in target")
        return str(env[name])

    return _VAR.sub(_sub, target)


def _exists(path: str) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, f"target not found: {path}"
    if p.stat().st_size == 0:
        return False, f"empty file: {path}"
    return True, f"exists ({p.stat().st_size} bytes)"


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _parses(path: str, value) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, f"target not found: {path}"
    fmt = (value or "").strip().lower() if value else ""
    if not fmt:
        suf = p.suffix.lower()
        if suf == ".json":
            fmt = "json"
        elif suf in (".yaml", ".yml"):
            fmt = "yaml"
        else:
            return False, f"cannot infer parser for {path}; set value: json|yaml"
    try:
        if fmt == "json":
            json.loads(_read(path))
        elif fmt == "yaml":
            yaml.safe_load(_read(path))
        else:
            return False, f"unknown parse format '{fmt}' for {path}; use json|yaml"
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        return False, f"parse error: {exc}"
    return True, f"parses as {fmt}"


def _contains(path: str, needle) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, f"target not found: {path}"
    ok = str(needle) in _read(path)
    return ok, f"substring {'found' if ok else 'absent'}: {needle!r}"


def _regex(path: str, pattern) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, f"target not found: {path}"
    ok = re.search(str(pattern), _read(path), re.MULTILINE) is not None
    return ok, f"pattern {'matched' if ok else 'no match'}: {pattern!r}"


def _forbid_regex(path: str, pattern) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, f"target not found: {path}"
    m = re.search(str(pattern), _read(path), re.MULTILINE)
    if m:
        return False, f"forbidden pattern matched {m.group(0)!r}: {pattern!r}"
    return True, f"forbidden pattern absent: {pattern!r}"


def _glob_count(glob_pat: str, value) -> tuple[bool, str]:
    n = len(glob.glob(glob_pat))
    raw = str(value).strip() if value is not None else ""
    m = _CMP.match(raw)
    if m:
        op, want = m.group(1), int(m.group(2))
        ok = _OPS[op](n, want)
    else:
        try:
            want = int(raw)
        except (TypeError, ValueError):
            return False, f"bad file_glob_count value: {value!r} (use int or >=N/<=N/>N/<N/==N)"
        ok = n == want
    return ok, f"matched {n} files (need {value})"


def run_checks(checks_path, env=None) -> tuple[list[CheckResult], bool]:
    """Evaluate every rule in checks.yaml; return (results, overall_passed).

    overall_passed is False iff ANY hard check failed. Soft-check failures are
    reported but do not flip it. Default hard=True: a rule with no ``hard`` flag
    must be able to fail the run (safer default for a migration gate).
    """
    results: list[CheckResult] = []
    for rule in load_checks(checks_path):
        rid = rule.get("id", "<no-id>")
        rtype = rule.get("type", "<no-type>")
        hard = bool(rule.get("hard", True))
        value = rule.get("value")

        if rtype not in _KNOWN:
            results.append(CheckResult(rid, rtype, True, False, f"unknown check type: {rtype}"))
            continue

        try:
            target = render_target(rule.get("target"), env)
        except _RenderError as exc:
            results.append(CheckResult(rid, rtype, hard, False, str(exc)))
            continue

        if rtype == "artifact_exists":
            passed, detail = _exists(target)
        elif rtype == "artifact_parses":
            passed, detail = _parses(target, value)
        elif rtype == "contains":
            passed, detail = _contains(target, value)
        elif rtype == "regex":
            passed, detail = _regex(target, value)
        elif rtype == "forbid_regex":
            passed, detail = _forbid_regex(target, value)
        else:  # file_glob_count
            passed, detail = _glob_count(target, value)

        results.append(CheckResult(rid, rtype, hard, passed, detail))

    overall_passed = not any(r.hard and not r.passed for r in results)
    return results, overall_passed
