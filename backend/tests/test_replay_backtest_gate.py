from __future__ import annotations

import importlib.util
import json
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


def test_evaluate_report_passes_with_fixture_defaults() -> None:
    fixture = gate._load_json(gate.DEFAULT_FIXTURE_REPORT)
    code, payload = gate.evaluate_report(fixture, report_path=str(gate.DEFAULT_FIXTURE_REPORT), mode="fixture")
    assert code == 0
    assert payload["status"] == "pass"
    assert payload["scenario_replay"]["marasmo"]["noise_rate"] is not None


def test_evaluate_report_fails_when_marasmo_noise_exceeds_threshold(monkeypatch) -> None:
    monkeypatch.setenv("BACKTEST_MAX_MARASMO_NOISE", "0.05")
    fixture = gate._load_json(gate.DEFAULT_FIXTURE_REPORT)
    code, payload = gate.evaluate_report(fixture, report_path="fixture.json", mode="fixture")
    assert code == 3
    assert payload["status"] == "fail"
    assert any("marasmo.noise_rate>" in f for f in payload["failures"])


def test_main_uses_fixture_fallback_when_legacy_missing(monkeypatch, tmp_path, capsys) -> None:
    report_path = tmp_path / "fixture.json"
    report_path.write_text(gate.DEFAULT_FIXTURE_REPORT.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(gate, "LEGACY_BENCH", tmp_path / "missing_bench.py")
    monkeypatch.setenv("BACKTEST_FIXTURE_REPORT", str(report_path))
    monkeypatch.delenv("BACKTEST_REQUIRE_REAL_BENCHMARK", raising=False)
    monkeypatch.setenv("BACKTEST_ALLOW_FIXTURE_FALLBACK", "1")

    code = gate.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert code == 0
    assert payload["mode"] == "fixture"
    assert payload["status"] == "pass"
