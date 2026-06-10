"""Self-check for localshift.checks — no pytest, no runtime artifacts.

Builds its own tmp dir and proves: all-pass, hard-fail-flips-overall,
soft-fail-does-not, file_glob_count comparisons, and parse failure.
Run: uv run python tests/checks_selfcheck.py  ->  prints "checks OK".
"""
import json
import pathlib
import tempfile
import textwrap

from localshift.checks import run_checks

tmp = pathlib.Path(tempfile.mkdtemp(prefix="checks-selfcheck-"))
good = tmp / "good.txt"
good.write_text("localshift smoke ok", encoding="utf-8")
bad = tmp / "bad.json"
bad.write_text("{not valid json", encoding="utf-8")
many = tmp / "many"
many.mkdir()
for i in range(3):
    (many / f"f{i}.json").write_text("{}", encoding="utf-8")

ENV = {"SMOKE_OUT": str(good)}


def write_yaml(name: str, body: str) -> pathlib.Path:
    p = tmp / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


# 1. all-pass
p = write_yaml("all_pass.yaml", """
    checks:
      - id: present
        type: artifact_exists
        target: ${SMOKE_OUT}
        hard: true
      - id: marker
        type: contains
        target: ${SMOKE_OUT}
        value: "smoke ok"
        hard: true
      - id: no-fab
        type: forbid_regex
        target: ${SMOKE_OUT}
        value: "FABRICATED"
        hard: true
""")
res, overall = run_checks(p, env=ENV)
assert overall is True, f"all-pass: expected overall True, got {overall}"
assert all(r.passed for r in res), f"all-pass: a check failed: {[(r.id, r.detail) for r in res if not r.passed]}"

# 2. hard-fail: forbid_regex matches "ok" -> result False AND overall False
p = write_yaml("hard_fail.yaml", """
    checks:
      - id: forbid-ok
        type: forbid_regex
        target: ${SMOKE_OUT}
        value: "ok"
        hard: true
""")
res, overall = run_checks(p, env=ENV)
assert res[0].passed is False, "hard-fail: forbid_regex matching 'ok' should fail"
assert overall is False, "hard-fail: a hard failure must flip overall to False"

# 3. soft-fail: contains miss, hard:false -> result False but overall True
p = write_yaml("soft_fail.yaml", """
    checks:
      - id: missing-needle
        type: contains
        target: ${SMOKE_OUT}
        value: "absent-needle"
        hard: false
""")
res, overall = run_checks(p, env=ENV)
assert res[0].passed is False, "soft-fail: contains of absent needle should fail"
assert overall is True, "soft-fail: a soft failure must NOT flip overall"

# 4. glob comparisons + parse failure
p = write_yaml("glob_parses.yaml", f"""
    checks:
      - id: glob-ge2
        type: file_glob_count
        target: "{many}/*.json"
        value: ">=2"
        hard: false
      - id: glob-eq1
        type: file_glob_count
        target: "{many}/*.json"
        value: "==1"
        hard: false
      - id: bad-parse
        type: artifact_parses
        target: "{bad}"
        value: json
        hard: false
""")
res, overall = run_checks(p, env=ENV)
by_id = {r.id: r for r in res}
assert by_id["glob-ge2"].passed is True, "glob >=2 should pass with 3 files"
assert by_id["glob-eq1"].passed is False, "glob ==1 should fail with 3 files"
assert by_id["bad-parse"].passed is False, "malformed json should fail to parse"
assert by_id["bad-parse"].detail, "parse failure must carry a non-empty detail"

print("checks OK")
