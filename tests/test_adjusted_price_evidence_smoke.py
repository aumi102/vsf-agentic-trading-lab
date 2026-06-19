from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/smoke_adjusted_price_evidence_pipeline.py")


def test_smoke_script_has_no_network_imports() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert all(name not in text for name in ["requests", "httpx", "urllib"])


def test_smoke_script_has_no_backtrader_docker_questdb_imports_or_behavior() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()

    assert "import backtrader" not in text
    assert "import docker" not in text
    assert "questdb" not in text


def test_smoke_script_never_references_demo_db() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "data/demo" not in text
    assert "mvp_trading_agent.sqlite" not in text


def test_smoke_exits_zero_with_synthetic_fixture() -> None:
    completed = _run_smoke()

    assert completed.returncode == 0
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["symbols"] == ["FPT", "VNM", "VCB"]
    assert payload["artifacts_persisted"] is False
    assert payload["dry_run"]["status"] == "ok"
    assert payload["execute"]["status"] == "ok"
    assert payload["execute"]["db_mutation_made"] is True
    assert payload["readiness"]["status"] == "ok"
    assert payload["readiness"]["backtest_gate"] == "pass"


def test_smoke_output_dir_persists_requested_artifacts(tmp_path: Path) -> None:
    completed = _run_smoke("--output-dir", str(tmp_path))

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["artifacts_persisted"] is True
    assert (tmp_path / "adjusted_price_payload.json").exists()
    assert (tmp_path / "factors_dry_run.json").exists()
    assert (tmp_path / "factors_execute.json").exists()
    assert (tmp_path / "adjusted_price_smoke.sqlite").exists()
    assert payload["payload_path"] == str(tmp_path / "adjusted_price_payload.json")
    assert payload["db_path"] == str(tmp_path / "adjusted_price_smoke.sqlite")


def test_smoke_rejects_too_many_symbols_cleanly() -> None:
    completed = _run_smoke("--symbols", "FPT,VNM,VCB,HPG")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "invalid_request"
    assert payload["dry_run"] is None
    assert payload["execute"] is None
    assert payload["readiness"] is None
    assert payload["artifacts_persisted"] is False
    assert "too_many_symbols:max=3" in payload["reasons"]


def test_smoke_rejects_unsupported_symbol_cleanly() -> None:
    completed = _run_smoke("--symbols", "FPT,MSN")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "invalid_request"
    assert payload["symbols"] == ["FPT", "MSN"]
    assert payload["factor_output_paths"] == []
    assert "unsupported_synthetic_symbols:MSN" in payload["reasons"]


def _run_smoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
