from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from trading_agent.db.schema import create_schema
from trading_agent.ingestion.adjusted_ohlc_execution_audit import audit_adjusted_ohlc_execution


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/audit_adjusted_ohlc_execution.py")


def test_missing_db_returns_invalid_request(tmp_path: Path) -> None:
    result = audit_adjusted_ohlc_execution(db_path=tmp_path / "missing.sqlite", symbols=["FPT"])

    assert result["status"] == "invalid_request"
    assert any(reason.startswith("db_missing:") for reason in result["reasons"])


def test_explicit_symbols_required(tmp_path: Path) -> None:
    result = audit_adjusted_ohlc_execution(db_path=_make_db(tmp_path), symbols=[])

    assert result["status"] == "invalid_request"
    assert "explicit_symbols_required" in result["reasons"]


def test_demo_db_refused_by_default() -> None:
    result = audit_adjusted_ohlc_execution(db_path=Path("data/demo/mvp_trading_agent.sqlite"), symbols=["FPT"])

    assert result["status"] == "invalid_request"
    assert "demo_db_blocked" in result["reasons"]


def test_successful_adjusted_db_audit_returns_ok(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    factors = _write_factors(tmp_path)
    validation = _write_validation(tmp_path)
    readiness = _write_readiness(tmp_path)

    result = audit_adjusted_ohlc_execution(
        db_path=db_path,
        symbols=["FPT", "VNM", "VCB"],
        factor_records_path=factors,
        validation_report_path=validation,
        readiness_report_path=readiness,
    )

    assert result["status"] == "ok"
    assert result["rows_total"] == 3
    assert result["adjusted_rows"] == 3
    assert result["backtest_gate"] == "pass"


def test_unadjusted_row_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, unadjusted_symbol="FPT")

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert any(reason.startswith("adjusted_ohlc_missing:") for reason in result["reasons"])


def test_missing_adjusted_close_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, null_column="adjusted_close")

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert any(reason.startswith("adjusted_ohlc_missing:") for reason in result["reasons"])


def test_adjusted_ohlc_inconsistency_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, inconsistent=True)

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert any(reason.startswith("adjusted_ohlc_inconsistent:") for reason in result["reasons"])


def test_missing_provenance_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, missing_provenance=True)

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert any(reason.startswith("adjustment_provenance_missing:") for reason in result["reasons"])


def test_factor_mismatch_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    factors = _write_factors(tmp_path, factor=0.7)

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"], factor_records_path=factors)

    assert result["status"] == "not_ready"
    assert any(reason.startswith("factor_mismatch:") for reason in result["reasons"])


def test_missing_factor_record_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    factors = _write_factors(tmp_path, symbols=["VNM"])

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"], factor_records_path=factors)

    assert result["status"] == "not_ready"
    assert any(reason.startswith("factor_record_missing:") for reason in result["reasons"])


def test_validation_report_not_ok_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    validation = _write_validation(tmp_path, status="not_ready", db_mutation_made=True)

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"], validation_report_path=validation)

    assert result["status"] == "not_ready"
    assert "validation_status_not_ok:not_ready" in result["reasons"]


def test_readiness_report_not_ok_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    readiness = _write_readiness(tmp_path, status="not_ready", backtest_gate="blocked")

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"], readiness_report_path=readiness)

    assert result["status"] == "not_ready"
    assert "readiness_status_not_ok:not_ready" in result["reasons"]


def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--factor-records",
        str(_write_factors(tmp_path)),
    )

    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


def test_cli_failure_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--db-path", str(tmp_path / "missing.sqlite"))

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert '"status": "invalid_request"' in completed.stdout


def test_json_output_written(tmp_path: Path) -> None:
    output = tmp_path / "audit.json"

    completed = _run_cli(tmp_path, "--db-path", str(_make_db(tmp_path)), "--output-json", str(output))

    assert completed.returncode == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ok"


def test_markdown_output_written(tmp_path: Path) -> None:
    output = tmp_path / "audit.md"

    completed = _run_cli(tmp_path, "--db-path", str(_make_db(tmp_path)), "--output-md", str(output))

    assert completed.returncode == 0
    text = output.read_text(encoding="utf-8")
    assert "Adjusted OHLC Execution Audit" in text
    assert "Backtrader/VN100 remains blocked" in text


def test_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/adjusted_ohlc_execution_audit.py").read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert all(name not in source + script for name in ["requests", "httpx", "urllib"])


def test_no_backtrader_docker_questdb_behavior() -> None:
    text = (
        Path("src/trading_agent/ingestion/adjusted_ohlc_execution_audit.py").read_text(encoding="utf-8")
        + SCRIPT.read_text(encoding="utf-8")
    ).lower()

    assert "import backtrader" not in text
    assert "import docker" not in text
    assert "questdb" not in text


def test_no_db_mutation(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    before = _raw_rows(db_path)

    result = audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT", "VNM", "VCB"])

    assert result["status"] == "ok"
    assert _raw_rows(db_path) == before


def test_raw_ohlc_unchanged_in_fixture_baseline(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    baseline = {"FPT": (95.0, 105.0, 90.0, 100.0)}

    audit_adjusted_ohlc_execution(db_path=db_path, symbols=["FPT"], factor_records_path=_write_factors(tmp_path))

    assert _raw_rows(db_path)["FPT"] == baseline["FPT"]


def _run_cli(tmp_path: Path, *overrides: str) -> subprocess.CompletedProcess[str]:
    override_map = {overrides[index]: overrides[index + 1] for index in range(0, len(overrides), 2)}
    db_path = override_map["--db-path"] if "--db-path" in override_map else str(_make_db(tmp_path))
    args = [
        sys.executable,
        str(SCRIPT),
        "--db-path",
        db_path,
        "--symbols",
        "FPT,VNM,VCB",
    ]
    for index in range(0, len(overrides), 2):
        flag = overrides[index]
        value = overrides[index + 1]
        if flag in args:
            args[args.index(flag) + 1] = value
        else:
            args.extend([flag, value])
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)


def _make_db(
    tmp_path: Path,
    *,
    unadjusted_symbol: str | None = None,
    null_column: str | None = None,
    inconsistent: bool = False,
    missing_provenance: bool = False,
) -> Path:
    db_path = tmp_path / "adjusted_audit.sqlite"
    if db_path.exists():
        db_path.unlink()
    raw_close = {"FPT": 100.0, "VNM": 200.0, "VCB": 50.0}
    factor = 0.8
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        for symbol, close in raw_close.items():
            raw = {
                "open": close * 0.95,
                "high": close * 1.05,
                "low": close * 0.9,
                "close": close,
            }
            adjusted = {key: value * factor for key, value in raw.items()}
            row = {
                "security_id": f"fixture:audit:{symbol}",
                "symbol": symbol,
                "trade_date": "2026-01-02",
                **raw,
                "adjustment_factor": factor,
                "adjusted_open": adjusted["open"],
                "adjusted_high": adjusted["high"],
                "adjusted_low": adjusted["low"],
                "adjusted_close": adjusted["close"],
                "adjustment_source_id": "fixture:reviewed_evidence_package",
                "adjustment_raw_path": "payload.json",
                "adjustment_method": "adjusted_close_ratio",
                "volume": 1000.0,
                "value": close * 1000.0,
                "price_basis": "source_reported",
                "adjustment_status": "adjusted",
                "source_id": "fixture:daily_prices_audit",
                "raw_path": f"synthetic://adjusted-audit/{symbol.lower()}",
                "quality_status": "ok",
            }
            if unadjusted_symbol == symbol:
                for column in [
                    "adjustment_factor",
                    "adjusted_open",
                    "adjusted_high",
                    "adjusted_low",
                    "adjusted_close",
                    "adjustment_source_id",
                    "adjustment_raw_path",
                    "adjustment_method",
                ]:
                    row[column] = None
            if null_column and symbol == "FPT":
                row[null_column] = None
            if inconsistent and symbol == "FPT":
                row["adjusted_high"] = row["adjusted_low"] - 1.0
            if missing_provenance and symbol == "FPT":
                row["adjustment_raw_path"] = None
            _insert_daily_price(con, row)
        con.commit()
    return db_path


def _insert_daily_price(con: sqlite3.Connection, row: dict[str, object]) -> None:
    columns = list(row.keys())
    placeholders = ", ".join(["?"] * len(columns))
    con.execute(
        f"INSERT INTO daily_prices ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def _write_factors(tmp_path: Path, *, factor: float = 0.8, symbols: list[str] | None = None) -> Path:
    selected = symbols or ["FPT", "VNM", "VCB"]
    records = [
        {
            "symbol": symbol,
            "trade_date": "2026-01-02",
            "factor": factor,
            "source_id": "fixture:reviewed_evidence_package",
            "raw_path": "payload.json",
            "method": "adjusted_close_ratio",
            "status": "ok",
            "reasons": [],
        }
        for symbol in selected
    ]
    path = tmp_path / "factors.json"
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return path


def _write_validation(tmp_path: Path, *, status: str = "ok", db_mutation_made: bool = True) -> Path:
    path = tmp_path / "validation.json"
    path.write_text(
        json.dumps({"status": status, "db_mutation_made": db_mutation_made, "reasons": []}, indent=2),
        encoding="utf-8",
    )
    return path


def _write_readiness(tmp_path: Path, *, status: str = "ok", backtest_gate: str = "pass") -> Path:
    path = tmp_path / "readiness.json"
    path.write_text(
        json.dumps({"status": status, "backtest_gate": backtest_gate, "reasons": []}, indent=2),
        encoding="utf-8",
    )
    return path


def _raw_rows(db_path: Path) -> dict[str, tuple[float, float, float, float]]:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT symbol, open, high, low, close FROM daily_prices ORDER BY symbol").fetchall()
    return {str(row["symbol"]): (row["open"], row["high"], row["low"], row["close"]) for row in rows}
