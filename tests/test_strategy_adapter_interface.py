from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.strategy.strategy_adapter import run_strategy_adapter_preview


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("src/trading_agent/strategy/strategy_adapter.py")
SCRIPT = Path("scripts/run_strategy_adapter_preview.py")
SYMBOLS = ["FPT", "VNM", "VCB"]


def _contract(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "strategy_id": "mentor_baseline_v1", "strategy_family": "noop",
        "universe": "mentor_approved_small_symbol_research", "symbols": SYMBOLS,
        "date_range": {"start": "2022-01-01", "end": "2025-12-31"},
        "price_basis": "adjusted_ohlc", "feature_inputs": ["adjusted_close_lag_1"],
        "entry_rule": "prior close crosses above prior MA20",
        "exit_rule": "prior close crosses below prior MA20",
        "rebalance_rule": "after each completed daily bar", "execution_price": "next_adjusted_open",
        "transaction_cost_bps": 15, "slippage_bps": 10, "exchange": "HOSE",
        "slippage_band_bps": 700, "position_sizing": "equal notional",
        "risk_rule": "no leverage", "max_holding_period": "20 trading days",
        "lookahead_policy": "features available before execution",
        "data_quality_gates": ["adjusted_ohlc_ready"],
        "expected_outputs": ["signal_intent_report"], "caveats": ["small-symbol research"],
        "mentor_approval_status": "approved",
    }
    payload.update(overrides)
    return payload


def _prepared(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "ok", "backtest_input_status": "ready_for_research_dry_run",
        "price_basis": "adjusted_ohlc", "represented_symbols": SYMBOLS,
        "rows_preview": [{"symbol": symbol, "datetime": "2026-01-02"} for symbol in SYMBOLS],
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(tmp_path: Path, contract: object | None = None, prepared: object | None = None) -> dict[str, object]:
    return run_strategy_adapter_preview(
        contract_path=_write(tmp_path, "contract.json", contract if contract is not None else _contract()),
        prepared_input_path=_write(tmp_path, "prepared.json", prepared if prepared is not None else _prepared()),
    )


def test_contract_missing_blocks(tmp_path: Path) -> None:
    result = run_strategy_adapter_preview(contract_path=tmp_path / "missing.json", prepared_input_path=_write(tmp_path, "p.json", _prepared()))
    assert result["status"] == "blocked"


def test_contract_pending_blocks(tmp_path: Path) -> None:
    assert _run(tmp_path, contract=_contract(mentor_approval_status="pending"))["status"] == "blocked"


def test_contract_invalid_blocks(tmp_path: Path) -> None:
    assert _run(tmp_path, contract=[])["status"] == "blocked"


def test_disabled_family_blocks_with_named_reason(tmp_path: Path) -> None:
    result = _run(tmp_path, contract=_contract(strategy_family="moving_average"))
    assert result["status"] == "blocked"
    assert "strategy_family_not_enabled:moving_average" in result["reasons"]


def test_momentum_family_blocks(tmp_path: Path) -> None:
    result = _run(tmp_path, contract=_contract(strategy_family="momentum"))
    assert "strategy_family_not_enabled:momentum" in result["reasons"]


def test_unknown_family_blocks(tmp_path: Path) -> None:
    result = _run(tmp_path, contract=_contract(strategy_family="does_not_exist"))
    assert "unknown_family:does_not_exist" in result["reasons"]


def test_breakout_family_blocks(tmp_path: Path) -> None:
    result = _run(tmp_path, contract=_contract(strategy_family="breakout"))
    assert "strategy_family_not_enabled:breakout" in result["reasons"]


def test_mean_reversion_family_blocks(tmp_path: Path) -> None:
    result = _run(tmp_path, contract=_contract(strategy_family="mean_reversion"))
    assert "strategy_family_not_enabled:mean_reversion" in result["reasons"]


def test_approved_noop_family_passes(tmp_path: Path) -> None:
    result = _run(tmp_path, contract=_contract(strategy_family="noop"))
    assert result["status"] == "ok"


def test_enablement_gate_doc_has_valid_frontmatter() -> None:
    text = Path("docs/strategy/strategy_family_enablement_gate.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    closing = text.index("\n---", 4)
    front = text[4:closing]
    assert "title: strategy_family_enablement_gate" in front


def test_pending_contract_blocks_before_family_check(tmp_path: Path) -> None:
    # A pending contract must block on contract readiness, not the family gate,
    # even if its family would otherwise be disabled.
    result = _run(tmp_path, contract=_contract(strategy_family="moving_average", mentor_approval_status="pending"))
    assert result["status"] == "blocked"
    assert any(reason.startswith("contract_not_ready:") for reason in result["reasons"])
    assert not any(reason.startswith("strategy_family_not_enabled:") for reason in result["reasons"])


def test_prepared_input_missing_blocks(tmp_path: Path) -> None:
    result = run_strategy_adapter_preview(contract_path=_write(tmp_path, "c.json", _contract()), prepared_input_path=tmp_path / "missing.json")
    assert "prepared_input_missing" in result["reasons"]


def test_prepared_input_not_ok_blocks(tmp_path: Path) -> None:
    assert _run(tmp_path, prepared=_prepared(status="blocked"))["status"] == "blocked"


def test_raw_price_basis_blocks(tmp_path: Path) -> None:
    result = _run(tmp_path, prepared=_prepared(price_basis="raw_ohlc"))
    assert "prepared_input_price_basis_not_adjusted_ohlc:raw_ohlc" in result["reasons"]


def test_missing_contract_symbol_blocks_with_named_reason(tmp_path: Path) -> None:
    reasons = _run(tmp_path, prepared=_prepared(represented_symbols=["FPT"]))["reasons"]
    assert "prepared_input_symbol_missing:VNM" in reasons
    assert "prepared_input_symbol_missing:VCB" in reasons


def test_prepared_input_superset_is_ok_and_ignored(tmp_path: Path) -> None:
    prepared = _prepared(
        represented_symbols=SYMBOLS + ["HPG"],
        rows_preview=[{"symbol": symbol, "datetime": "2026-01-02"} for symbol in SYMBOLS + ["HPG"]],
    )
    result = _run(tmp_path, prepared=prepared)
    assert result["status"] == "ok"


def test_output_rows_only_contain_contract_symbols(tmp_path: Path) -> None:
    prepared = _prepared(
        represented_symbols=SYMBOLS + ["HPG"],
        rows_preview=[{"symbol": symbol, "datetime": "2026-01-02"} for symbol in SYMBOLS + ["HPG"]],
    )
    rows = _run(tmp_path, prepared=prepared)["signal_intent_rows"]
    assert {row["symbol"] for row in rows} == set(SYMBOLS)


def test_rows_missing_blocks(tmp_path: Path) -> None:
    assert "prepared_input_rows_missing" in _run(tmp_path, prepared=_prepared(rows_preview=[]))["reasons"]


def test_valid_inputs_return_ok(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result["status"] == "ok"
    assert result["price_basis"] == "adjusted_ohlc"


def test_output_only_uses_no_signal(tmp_path: Path) -> None:
    rows = _run(tmp_path)["signal_intent_rows"]
    assert {row["signal_intent_action"] for row in rows} == {"NO_SIGNAL"}


def test_output_has_no_recommendation_wording(tmp_path: Path) -> None:
    text = json.dumps(_run(tmp_path)).lower()
    assert all(word not in text for word in ("buy", "sell", "hold"))


def test_output_has_no_trade_or_performance_fields(tmp_path: Path) -> None:
    keys = _all_keys(_run(tmp_path))
    assert not {"trade", "trades", "pnl", "equity", "return", "returns"} & keys


def test_cli_success_exits_zero(tmp_path: Path) -> None:
    assert _run_cli(tmp_path).returncode == 0


def test_cli_failure_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, missing=True)
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr


def test_no_backtrader_import() -> None:
    assert "import backtrader" not in _implementation_text().lower()


def test_no_optimizer_code() -> None:
    assert all(token not in _implementation_text().lower() for token in ("grid_search", "gridsearch", "scipy.optimize", "def optimize"))


def test_no_network_imports() -> None:
    assert all(token not in _implementation_text() for token in ("requests", "httpx", "urllib", "socket"))


def test_no_db_mutation() -> None:
    assert all(token not in _implementation_text().lower() for token in ("sqlite3", "insert into", "update ", "delete from", ".execute("))


def _run_cli(tmp_path: Path, missing: bool = False) -> subprocess.CompletedProcess[str]:
    contract = tmp_path / "missing.json" if missing else _write(tmp_path, "contract.json", _contract())
    prepared = _write(tmp_path, "prepared.json", _prepared())
    return subprocess.run([sys.executable, str(SCRIPT), "--contract", str(contract), "--prepared-input", str(prepared)], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | set().union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _implementation_text() -> str:
    return SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")
