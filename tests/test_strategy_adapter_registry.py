from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.strategy.strategy_adapter_registry import (
    get_strategy_adapter_family,
    list_strategy_adapters,
    validate_family_enabled,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("src/trading_agent/strategy/strategy_adapter_registry.py")
SCRIPT = Path("scripts/list_strategy_adapter_registry.py")
EXPECTED_FAMILIES = {"noop", "moving_average", "momentum", "breakout", "mean_reversion"}


def test_registry_lists_all_expected_families() -> None:
    families = {entry["family"] for entry in list_strategy_adapters()}
    assert families == EXPECTED_FAMILIES


def test_noop_is_implemented_and_enabled() -> None:
    noop = get_strategy_adapter_family("noop")["family"]
    assert noop["implemented"] is True
    assert noop["enabled"] is True
    assert noop["status"] == "interface_preview"
    assert validate_family_enabled("noop")["ok"] is True


def test_non_noop_families_are_disabled() -> None:
    for entry in list_strategy_adapters():
        if entry["family"] == "noop":
            continue
        assert entry["implemented"] is False
        assert entry["enabled"] is False
        assert entry["status"] == "pending_mentor_approval"
        assert entry["requires_mentor_approval"] is True


def test_unknown_family_blocks() -> None:
    found = get_strategy_adapter_family("does_not_exist")
    assert found["ok"] is False
    assert found["reason"] == "unknown_family:does_not_exist"
    assert validate_family_enabled("does_not_exist")["reason"] == "unknown_family:does_not_exist"


def test_disabled_family_blocks() -> None:
    blocked = validate_family_enabled("moving_average")
    assert blocked["ok"] is False
    assert blocked["reason"] == "family_not_enabled:moving_average"


def test_output_has_no_performance_claim() -> None:
    text = json.dumps(list_strategy_adapters()).lower()
    assert all(token not in text for token in ("pnl", "equity", "return", "sharpe", "profit", "win rate"))


def test_no_backtrader_import() -> None:
    assert "import backtrader" not in _implementation_text().lower()


def test_no_optimizer_code() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("grid_search", "gridsearch", "scipy.optimize", "def optimize"))


def test_no_network_imports() -> None:
    assert all(token not in _implementation_text() for token in ("requests", "httpx", "urllib", "socket"))


def test_no_db_mutation() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("sqlite3", "insert into", "update ", "delete from", ".execute("))


def test_cli_success_exits_zero() -> None:
    completed = _run_cli()
    assert completed.returncode == 0


def test_cli_output_json_works(tmp_path: Path) -> None:
    output = tmp_path / "registry.json"
    completed = _run_cli(output)
    assert completed.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert {entry["family"] for entry in payload["families"]} == EXPECTED_FAMILIES
    assert payload["not_financial_advice"] is True


def _run_cli(output: Path | None = None) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(SCRIPT)]
    if output is not None:
        args += ["--output-json", str(output)]
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)


def _implementation_text() -> str:
    return SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")
