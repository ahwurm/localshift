"""engine_frontier selfcheck — NO `claude -p` call (the live frontier run is real-cron
work, not this plan). Exercises harvest_tokens against a synthetic transcript and the
allowedTools CSV mapping.

Verifies: (a) harvest sums real usage (input + cache_read + cache_creation; output);
(b) an absent project dir yields (None, None, False, <note>) — NEVER zeros; (c) the
allowedTools CSV matches the cron form.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from localshift.engine_frontier import (
    _allowed_tools_csv,
    _project_slug,
    harvest_tokens,
)


def _write_transcript(home: Path, workdir: str, lines: list[dict]) -> None:
    """Create ~/.claude/projects/<slug>/run.jsonl under the patched home for workdir."""
    proj = home / ".claude" / "projects" / _project_slug(workdir)
    proj.mkdir(parents=True, exist_ok=True)
    f = proj / "run.jsonl"
    f.write_text("\n".join(json.dumps(o) for o in lines) + "\n")


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        workdir = "/home/openclaw-user/financial-models"  # arbitrary; slug derives from it
        since = 0.0  # epoch 0 so the just-written file is "since the run"

        # (a) two assistant lines carrying message.usage — harvest sums real usage.
        lines = [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 30,
                        "cache_read_input_tokens": 10,
                        "cache_creation_input_tokens": 5,
                    },
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input_tokens": 200,
                        "output_tokens": 40,
                        "cache_read_input_tokens": 20,
                        "cache_creation_input_tokens": 0,
                    },
                },
            },
        ]
        with patch.object(Path, "home", return_value=home):
            _write_transcript(home, workdir, lines)
            tin, tout, est, note = harvest_tokens(workdir, since)
        # input(100+200) + cache_read(10+20) + cache_creation(5+0) = 335
        assert tin == 335, f"tokens_in {tin} != 335"
        assert tout == 70, f"tokens_out {tout} != 70"
        assert est is False, f"estimated should be False (every line had usage), got {est}"
        assert note is None, f"note should be None on clean harvest, got {note!r}"

        # (b) project dir does NOT exist -> null + note, NEVER zeros.
        with patch.object(Path, "home", return_value=home):
            r = harvest_tokens("/home/openclaw-user/nonexistent-workdir-xyz", since)
        assert r[0] is None and r[1] is None, f"missing dir must yield (None,None,...), got {r[:2]}"
        assert r[2] is False, f"missing dir estimated must be False, got {r[2]}"
        assert isinstance(r[3], str) and r[3], f"missing dir must carry a non-empty note, got {r[3]!r}"
        assert r[0] != 0 and r[1] != 0, "harvest must NEVER return 0 for unknown tokens"

    # (c) allowedTools CSV matches the cron form.
    assert _allowed_tools_csv(["read", "write", "bash"]) == "Read,Write,Bash", (
        _allowed_tools_csv(["read", "write", "bash"])
    )
    assert _allowed_tools_csv(["Read", "Glob", "Grep"]) == "Read,Glob,Grep", "CSV must be case-insensitive on input"

    print("frontier OK")


if __name__ == "__main__":
    main()
