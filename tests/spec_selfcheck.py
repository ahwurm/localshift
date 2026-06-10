"""Plain-python selfcheck for localshift.spec (no pytest). Exits nonzero on failure."""
from localshift.spec import validate_task, render_env, SpecError

VALID = {
    "name": "smoke",
    "source": "self-test",
    "prompt_file": "/abs/prompt.md",
    "env_vars": ["X"],
    "workdir": "/abs/wd",
    "tools": ["write"],
    "budget": {"max_actions": 3, "max_duration_minutes": 3.0},
    "artifacts": ["${X}"],
    "models": {"local": "qwen3.6-27b", "frontier": "claude -p"},
}

# missing prompt_file -> error naming it
errs = validate_task({k: v for k, v in VALID.items() if k != "prompt_file"})
assert any("prompt_file" in e for e in errs), errs

# bad tool 'edit' -> error naming edit + tools
errs = validate_task({**VALID, "tools": ["write", "edit"]})
assert any("edit" in e for e in errs), errs
assert any("tool" in e.lower() for e in errs), errs

# bad max_actions type -> error naming max_actions
errs = validate_task({**VALID, "budget": {"max_actions": "three", "max_duration_minutes": 3.0}})
assert any("max_actions" in e for e in errs), errs

# fully valid -> empty list
assert validate_task(VALID) == [], validate_task(VALID)

# render_env substitutes a var; missing var raises SpecError naming it
assert render_env("path=${X}", {"X": "/tmp/a"}) == "path=/tmp/a"
try:
    render_env("path=${MISSING}", {"X": "1"})
    raise AssertionError("expected SpecError for missing var")
except SpecError as e:
    assert "MISSING" in str(e), str(e)

print("spec OK")
