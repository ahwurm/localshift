"""Plain-python selfcheck for localshift.ledger (no pytest). Exits nonzero on failure."""
import json
import tempfile

from localshift.ledger import append_row, ledger_path

with tempfile.TemporaryDirectory() as root:
    # local row: real model_id + token counts
    local = append_row(
        root, workload="smoke", engine="local", model_id="qwen3.6-27b",
        tokens_in=120, tokens_out=44, tokens_estimated=False,
        duration_s=1.5, exit_status=0, artifacts_ok=True,
    )
    # frontier row: model_id + tokens NOT captured -> null (never fabricated as 0)
    frontier = append_row(
        root, workload="smoke", engine="frontier", model_id=None,
        tokens_in=None, tokens_out=None, tokens_estimated=False,
        duration_s=2.0, exit_status=0, artifacts_ok=True,
        note="frontier token harvest failed: transcript unparsable",
    )

    lines = ledger_path(root).read_text().splitlines()
    assert len(lines) == 2, f"expected 2 ledger lines, got {len(lines)}"

    r0 = json.loads(lines[0])
    assert r0["tokens_in"] == 120 and r0["model_id"] == "qwen3.6-27b", r0

    r1 = json.loads(lines[1])
    assert r1["model_id"] is None and r1["tokens_in"] is None and r1["tokens_out"] is None, r1
    assert r1["note"] == "frontier token harvest failed: transcript unparsable", r1

    try:
        append_row(
            root, workload="x", engine="bogus", model_id=None,
            tokens_in=None, tokens_out=None, tokens_estimated=False,
            duration_s=0.0, exit_status=0, artifacts_ok=False,
        )
        raise AssertionError("expected ValueError for engine='bogus'")
    except ValueError:
        pass

print("ledger OK")
