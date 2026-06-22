from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.strategy.strategy_contract import validate_strategy_contract_file


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("src/trading_agent/strategy/strategy_contract.py")
SCRIPT = Path("scripts/validate_strategy_contract.py")


def _contract(**overrides: object) -> dict[str, object]:
    contract: dict[str, object] = {
        "strategy_id": "mentor_baseline_v1",
        "strategy_family": "moving_average",
        "universe": "mentor_approved_small_symbol_research",
        "symbols": ["FPT", "VNM", "VCB"],
        "date_range": {"start": "2022-01-01", "end": "2025-12-31"},
        "price_basis": "adjusted_ohlc",
        "feature_inputs": ["adjusted_close_lag_1", "adjusted_close_ma_20"],
        "entry_rule": "enter intent when prior adjusted close crosses above prior MA20",
        "exit_rule": "exit intent when prior adjusted close crosses below prior MA20",
        "rebalance_rule": "evaluate after each completed daily bar",
        "execution_price": "next_adjusted_open",
        "transaction_cost_bps": 15,
        "slippage_bps": 10,
        "exchange": "HOSE",
        "slippage_band_bps": 700,
        "position_sizing": "equal notional across represented symbols",
        "risk_rule": "one long intent per symbol; no leverage",
        "max_holding_period": "20 trading days",
        "lookahead_policy": "features use information available before execution",
        "data_quality_gates": ["adjusted_ohlc_ready", "provenance_present", "symbols_covered"],
        "expected_outputs": ["signal_intent_report", "assumptions", "caveats"],
        "caveats": ["small-symbol research scope", "survivorship policy not generalized"],
        "mentor_approval_status": "approved",
    }
    contract.update(overrides)
    return contract


def _write(tmp_path: Path, contract: object) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    return path


def _validate(tmp_path: Path, **overrides: object) -> dict[str, object]:
    return validate_strategy_contract_file(_write(tmp_path, _contract(**overrides)))


def test_missing_contract_file_blocks(tmp_path: Path) -> None:
    assert validate_strategy_contract_file(tmp_path / "missing.json")["reasons"] == ["contract_missing"]


def test_invalid_json_blocks(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    path.write_text("{bad", encoding="utf-8")
    assert validate_strategy_contract_file(path)["reasons"] == ["contract_invalid_json"]


def test_contract_not_object_blocks(tmp_path: Path) -> None:
    assert validate_strategy_contract_file(_write(tmp_path, []))["reasons"] == ["contract_must_be_object"]


def test_missing_required_field_blocks(tmp_path: Path) -> None:
    contract = _contract()
    contract.pop("entry_rule")
    assert "required_field_missing:entry_rule" in validate_strategy_contract_file(_write(tmp_path, contract))["reasons"]


def test_raw_price_basis_blocks(tmp_path: Path) -> None:
    assert "price_basis_not_adjusted_ohlc:raw_ohlc" in _validate(tmp_path, price_basis="raw_ohlc")["reasons"]


def test_empty_symbols_blocks(tmp_path: Path) -> None:
    assert "symbols_must_be_nonempty" in _validate(tmp_path, symbols=[])["reasons"]


def test_invalid_date_range_blocks(tmp_path: Path) -> None:
    assert "date_range_invalid" in _validate(tmp_path, date_range={"start": "2025-01-02", "end": "2025-01-01"})["reasons"]


def test_negative_transaction_cost_blocks(tmp_path: Path) -> None:
    assert "transaction_cost_bps_must_be_nonnegative" in _validate(tmp_path, transaction_cost_bps=-1)["reasons"]


def test_negative_slippage_blocks(tmp_path: Path) -> None:
    assert "slippage_bps_must_be_nonnegative" in _validate(tmp_path, slippage_bps=-1)["reasons"]


def test_unknown_exchange_blocks(tmp_path: Path) -> None:
    assert "unknown_exchange:HNX" in _validate(tmp_path, exchange="HNX")["reasons"]


def test_slippage_over_band_blocks(tmp_path: Path) -> None:
    assert "slippage_bps_exceeds_exchange_band:701/700" in _validate(tmp_path, slippage_bps=701)["reasons"]


def test_pending_approval_not_ready(tmp_path: Path) -> None:
    template = ROOT / "docs/strategy/examples/strategy_contract_template.json"
    result = validate_strategy_contract_file(template)
    assert result["status"] == "not_ready"
    assert "mentor_approval_not_approved:pending" in result["reasons"]


def test_rejected_approval_not_ready(tmp_path: Path) -> None:
    result = _validate(tmp_path, mentor_approval_status="rejected")
    assert result["status"] == "not_ready"


def test_approved_valid_contract_ok(tmp_path: Path) -> None:
    result = _validate(tmp_path)
    assert result["status"] == "ok"
    assert result["price_basis"] == "adjusted_ohlc"


def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, _contract())
    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


def test_cli_pending_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, _contract(mentor_approval_status="pending"))
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr


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


def test_missing_universe_blocks(tmp_path: Path) -> None:
    _assert_missing_field_blocks(tmp_path, "universe")


def test_missing_feature_inputs_blocks(tmp_path: Path) -> None:
    _assert_missing_field_blocks(tmp_path, "feature_inputs")


def test_missing_max_holding_period_blocks(tmp_path: Path) -> None:
    _assert_missing_field_blocks(tmp_path, "max_holding_period")


def test_missing_data_quality_gates_blocks(tmp_path: Path) -> None:
    _assert_missing_field_blocks(tmp_path, "data_quality_gates")


def test_missing_expected_outputs_blocks(tmp_path: Path) -> None:
    _assert_missing_field_blocks(tmp_path, "expected_outputs")


def test_missing_caveats_blocks(tmp_path: Path) -> None:
    _assert_missing_field_blocks(tmp_path, "caveats")


def test_approved_pending_entry_rule_blocks(tmp_path: Path) -> None:
    assert "placeholder_value_present:entry_rule" in _validate(tmp_path, entry_rule="PENDING_MENTOR_APPROVAL")["reasons"]


def test_approved_placeholder_exit_rule_blocks(tmp_path: Path) -> None:
    assert "placeholder_value_present:exit_rule" in _validate(tmp_path, exit_rule="mentor placeholder")["reasons"]


def test_approved_tbd_execution_price_blocks(tmp_path: Path) -> None:
    assert "placeholder_value_present:execution_price" in _validate(tmp_path, execution_price="TBD")["reasons"]


def test_docs_schema_includes_every_required_field() -> None:
    schema = (ROOT / "docs/strategy/strategy_contract_schema.md").read_text(encoding="utf-8")
    required = (
        "strategy_id", "strategy_family", "universe", "symbols", "date_range", "price_basis",
        "feature_inputs", "entry_rule", "exit_rule", "rebalance_rule", "execution_price",
        "transaction_cost_bps", "slippage_bps", "exchange", "slippage_band_bps",
        "position_sizing", "risk_rule", "max_holding_period", "lookahead_policy",
        "data_quality_gates", "expected_outputs", "caveats", "mentor_approval_status",
    )
    assert all(f"`{field}`" in schema for field in required)


def _run_cli(tmp_path: Path, contract: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--contract", str(_write(tmp_path, contract))],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _implementation_text() -> str:
    return SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")


def _assert_missing_field_blocks(tmp_path: Path, field: str) -> None:
    contract = _contract()
    contract.pop(field)
    result = validate_strategy_contract_file(_write(tmp_path, contract))
    assert f"required_field_missing:{field}" in result["reasons"]
