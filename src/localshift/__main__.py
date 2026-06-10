"""LocalShift runner CLI — the claude-free execution path for migrated workloads."""
import sys


def main() -> int:
    sys.stderr.write(
        "localshift runner not built yet (run/check/validate/savings land 2026-06-10).\n"
        "The pipeline skills (/localshift:explore ... :evaluate) are usable now via Claude Code.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
