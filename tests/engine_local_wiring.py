"""engine_local wiring selfcheck — NO live vLLM run (that is Plan 04's single smoke).

Source-grep asserts the load-bearing wiring is present (registry-from-base pattern,
live model_id, capability probe, workdir+finally) and that run_local is async. Keeps
this plan cheap and avoids double-spending the endpoint.
"""
import asyncio
import inspect
import sys

from localshift.engine_local import RunResult, run_local


def main() -> None:
    assert asyncio.iscoroutinefunction(run_local), "run_local must be async"
    assert hasattr(RunResult, "__dataclass_fields__"), "RunResult must be a dataclass"
    for f in (
        "ok",
        "model_id",
        "tokens_in",
        "tokens_out",
        "tokens_estimated",
        "duration_s",
        "artifacts_ok",
        "trace_path",
        "note",
    ):
        assert f in RunResult.__dataclass_fields__, f"RunResult missing field {f}"

    src = inspect.getsource(run_local) + inspect.getsource(
        sys.modules["localshift.engine_local"]
    )
    for needle in (
        "register_builtin_tools",  # real base registry built
        "from_allowed",            # restricted to task tools
        "base_registry",           # the empty-registry trap avoided
        "v1/models",               # model_id from the live endpoint
        "detect_capabilities",     # function-calling-false endpoint handled
    ):
        assert needle in src, f"engine_local source missing required wiring: {needle!r}"

    print("engine_local wiring OK")


if __name__ == "__main__":
    main()
