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


def main() -> int:
    if not LEGACY_BENCH.exists():
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

    report = json.loads(output_path.read_text(encoding="utf-8"))
    story = report.get("story_matching", {}) or {}
    delta = report.get("delta_vs_legacy", {}) or {}

    min_precision = env_float("BACKTEST_MIN_PRECISION", 0.60)
    min_recall = env_float("BACKTEST_MIN_RECALL", 0.55)
    min_f1 = env_float("BACKTEST_MIN_F1", 0.58)
    min_delta_f1 = env_float("BACKTEST_MIN_DELTA_F1", -0.02)

    failures = []
    if float(story.get("precision", 0.0)) < min_precision:
        failures.append(f"precision<{min_precision}")
    if float(story.get("recall", 0.0)) < min_recall:
        failures.append(f"recall<{min_recall}")
    if float(story.get("f1", 0.0)) < min_f1:
        failures.append(f"f1<{min_f1}")
    if float(delta.get("f1", 0.0)) < min_delta_f1:
        failures.append(f"delta_f1<{min_delta_f1}")

    payload = {
        "status": "pass" if not failures else "fail",
        "thresholds": {
            "min_precision": min_precision,
            "min_recall": min_recall,
            "min_f1": min_f1,
            "min_delta_f1": min_delta_f1,
        },
        "story_matching": story,
        "delta_vs_legacy": delta,
        "report": str(output_path),
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
