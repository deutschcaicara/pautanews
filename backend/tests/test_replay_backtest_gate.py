from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "replay_backtest_gate.py"
_SPEC = importlib.util.spec_from_file_location("replay_backtest_gate", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


def test_resolve_legacy_bench_prefers_env_script(monkeypatch) -> None:
    monkeypatch.setenv("LEGACY_BENCHMARK_SCRIPT", "/tmp/custom_bench.py")
    assert gate.resolve_legacy_bench() == Path("/tmp/custom_bench.py")


def test_default_output_is_under_repo_artifacts() -> None:
    expected = gate.ROOT / "artifacts" / "benchmark" / "story_matching_report.json"
    assert gate.DEFAULT_OUTPUT == expected
