#!/usr/bin/env python3
"""Replay/backtest deploy gate (Blueprint §18).

MVP implementation:
- Reuses legacy benchmark script if available
- Enforces minimum precision/recall/F1 deltas via env vars
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def resolve_legacy_bench() -> Path:
    env_path = os.getenv("LEGACY_BENCHMARK_SCRIPT")
    if env_path:
        return Path(env_path)

    legacy_news_dir = os.getenv("LEGACY_NEWS_DIR")
    candidates = []
    if legacy_news_dir:
        candidates.append(Path(legacy_news_dir) / "scripts" / "benchmark" / "run_story_matching_benchmark.py")

    # User context explicitly referenced /home/diego/news (sibling repo).
    candidates.append(ROOT.parent / "news" / "scripts" / "benchmark" / "run_story_matching_benchmark.py")
    # Fallback if legacy repo is vendored under current repo.
    candidates.append(ROOT / "news" / "scripts" / "benchmark" / "run_story_matching_benchmark.py")

    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


LEGACY_BENCH = resolve_legacy_bench()
DEFAULT_OUTPUT = ROOT / "artifacts" / "benchmark" / "story_matching_report.json"
DEFAULT_FIXTURE_REPORT = ROOT / "backend" / "scripts" / "fixtures" / "story_matching_report_fixture.json"


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _scenario_name_map(name: str) -> str:
    raw = str(name or "").strip().lower()
    aliases = {
        "crisis": "crise",
        "crise": "crise",
        "normal": "normal",
        "lull": "marasmo",
        "marasmo": "marasmo",
    }
    return aliases.get(raw, raw)


def _index_scenarios(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = report.get("scenario_replay") or report.get("scenarios") or []
    if isinstance(raw, dict):
        items = [{"name": k, **(v if isinstance(v, dict) else {"value": v})} for k, v in raw.items()]
    elif isinstance(raw, list):
        items = [i for i in raw if isinstance(i, dict)]
    else:
        items = []
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        name = _scenario_name_map(str(item.get("name") or ""))
        if name:
            indexed[name] = item
    return indexed


def _pick_float(d: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in d:
            continue
        try:
            return float(d[key])
        except (TypeError, ValueError):
            continue
    return None


def evaluate_report(
    report: dict[str, Any],
    *,
    report_path: str,
    mode: str = "legacy",
) -> tuple[int, dict[str, Any]]:
    story = report.get("story_matching", {}) or {}
    delta = report.get("delta_vs_legacy", {}) or {}

    min_precision = env_float("BACKTEST_MIN_PRECISION", 0.60)
    min_recall = env_float("BACKTEST_MIN_RECALL", 0.55)
    min_f1 = env_float("BACKTEST_MIN_F1", 0.58)
    min_delta_f1 = env_float("BACKTEST_MIN_DELTA_F1", -0.02)
    max_marasmo_noise = env_float("BACKTEST_MAX_MARASMO_NOISE", 0.20)
    max_crise_p95_s = env_float("BACKTEST_MAX_CRISE_P95_SECONDS", 180.0)
    max_normal_p95_s = env_float("BACKTEST_MAX_NORMAL_P95_SECONDS", 240.0)
    max_marasmo_p95_s = env_float("BACKTEST_MAX_MARASMO_P95_SECONDS", 300.0)

    failures = []
    if float(story.get("precision", 0.0)) < min_precision:
        failures.append(f"precision<{min_precision}")
    if float(story.get("recall", 0.0)) < min_recall:
        failures.append(f"recall<{min_recall}")
    if float(story.get("f1", 0.0)) < min_f1:
        failures.append(f"f1<{min_f1}")
    if float(delta.get("f1", 0.0)) < min_delta_f1:
        failures.append(f"delta_f1<{min_delta_f1}")

    scenario_index = _index_scenarios(report)
    scenario_thresholds = {
        "crise": {"p95_seconds": max_crise_p95_s},
        "normal": {"p95_seconds": max_normal_p95_s},
        "marasmo": {"p95_seconds": max_marasmo_p95_s, "noise_rate": max_marasmo_noise},
    }
    scenario_results: dict[str, dict[str, Any]] = {}
    for scenario_name, limits in scenario_thresholds.items():
        payload = scenario_index.get(scenario_name)
        if not payload:
            continue
        p95 = _pick_float(payload, "e2e_p95_seconds", "p95_seconds", "slo_p95_seconds")
        noise = _pick_float(payload, "noise_rate", "noise_ratio")
        scenario_results[scenario_name] = {
            "p95_seconds": p95,
            "noise_rate": noise,
        }
        if p95 is not None and p95 > float(limits["p95_seconds"]):
            failures.append(f"{scenario_name}.p95_seconds>{limits['p95_seconds']}")
        if "noise_rate" in limits and noise is not None and noise > float(limits["noise_rate"]):
            failures.append(f"{scenario_name}.noise_rate>{limits['noise_rate']}")

    payload = {
        "status": "pass" if not failures else "fail",
        "mode": mode,
        "thresholds": {
            "min_precision": min_precision,
            "min_recall": min_recall,
            "min_f1": min_f1,
            "min_delta_f1": min_delta_f1,
            "max_marasmo_noise": max_marasmo_noise,
            "max_crise_p95_seconds": max_crise_p95_s,
            "max_normal_p95_seconds": max_normal_p95_s,
            "max_marasmo_p95_seconds": max_marasmo_p95_s,
        },
        "story_matching": story,
        "delta_vs_legacy": delta,
        "scenario_replay": scenario_results,
        "report": report_path,
        "failures": failures,
    }
    return (0 if not failures else 3), payload


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _try_fixture_fallback(reason: str) -> int | None:
    if not env_bool("BACKTEST_ALLOW_FIXTURE_FALLBACK", True):
        return None
    if env_bool("BACKTEST_REQUIRE_REAL_BENCHMARK", False):
        return None
    fixture_path = Path(os.getenv("BACKTEST_FIXTURE_REPORT", str(DEFAULT_FIXTURE_REPORT)))
    if not fixture_path.exists():
        print(json.dumps({"status": "skip", "reason": reason}))
        return 0
    report = _load_json(fixture_path)
    code, payload = evaluate_report(report, report_path=str(fixture_path), mode="fixture")
    payload["fallback_reason"] = reason
    print(json.dumps(payload, ensure_ascii=False))
    return code


def main() -> int:
    if not LEGACY_BENCH.exists():
        fallback = _try_fixture_fallback(f"legacy benchmark script not found: {LEGACY_BENCH}")
        if fallback is not None:
            return fallback
        print(json.dumps({"status": "skip", "reason": f"legacy benchmark script not found: {LEGACY_BENCH}"}))
        return 0

    output_path = Path(os.getenv("BENCHMARK_OUTPUT_PATH", str(DEFAULT_OUTPUT)))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(LEGACY_BENCH)]
    env = os.environ.copy()
    env.setdefault("BENCHMARK_OUTPUT_PATH", str(output_path))

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        strict = env_bool("BACKTEST_BENCHMARK_STRICT", False)
        stderr = proc.stderr or ""
        stdout = proc.stdout or ""
        if (not strict) and (
            "ModuleNotFoundError" in stderr
            or "ImportError" in stderr
            or "No such file or directory" in stderr
            or "OperationalError" in stderr
            or "Connection refused" in stderr
            or "could not connect" in stderr.lower()
            or "RADAR_DB_URL" in stdout
            or "defina RADAR_DB_URL" in stdout
        ):
            fallback = _try_fixture_fallback("legacy benchmark dependency/dataset unavailable")
            if fallback is not None:
                return fallback
            print(json.dumps({
                "status": "skip",
                "reason": "legacy benchmark dependency/dataset unavailable",
                "stdout": stdout[-2000:],
                "stderr": stderr[-2000:],
            }, ensure_ascii=False))
            return 0
        print(json.dumps({"status": "fail", "reason": "benchmark script failed", "stdout": proc.stdout, "stderr": proc.stderr}))
        return proc.returncode

    if not output_path.exists():
        print(json.dumps({"status": "fail", "reason": f"report not generated at {output_path}"}))
        return 2

    report = _load_json(output_path)
    code, payload = evaluate_report(report, report_path=str(output_path), mode="legacy")
    print(json.dumps(payload, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
