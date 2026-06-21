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
    result = _audit_strict(tmp_path, db_path=db_path, symbols=["FPT", "VNM", "VCB"])

    assert result["status"] == "ok"
    assert result["rows_total"] == 3
    assert result["adjusted_rows"] == 3
    assert result["backtest_gate"] == "pass"
    assert result["backtest_planning_gate"] == "pass"
    assert result["evidence_mode"] == "strict"


def test_unadjusted_row_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, unadjusted_symbol="FPT")

    result = _audit_strict(tmp_path, db_path=db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert any(reason.startswith("adjusted_ohlc_missing:") for reason in result["reasons"])


def test_missing_adjusted_close_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, null_column="adjusted_close")

    result = _audit_strict(tmp_path, db_path=db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert any(reason.startswith("adjusted_ohlc_missing:") for reason in result["reasons"])


def test_adjusted_ohlc_inconsistency_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, inconsistent=True)

    result = _audit_strict(tmp_path, db_path=db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert any(reason.startswith("adjusted_ohlc_inconsistent:") for reason in result["reasons"])


def test_missing_provenance_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, missing_provenance=True)

    result = _audit_strict(tmp_path, db_path=db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert any(reason.startswith("adjustment_provenance_missing:") for reason in result["reasons"])


def test_factor_mismatch_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    factors = _write_factors(tmp_path, factor=0.7)

    result = audit_adjusted_ohlc_execution(
        db_path=db_path,
        symbols=["FPT"],
        factor_records_path=factors,
        validation_report_path=_write_validation(tmp_path),
        readiness_report_path=_write_readiness(tmp_path),
    )

    assert result["status"] == "not_ready"
    assert any(reason.startswith("factor_mismatch:") for reason in result["reasons"])


def test_missing_factor_record_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    factors = _write_factors(tmp_path, symbols=["VNM"])

    result = audit_adjusted_ohlc_execution(
        db_path=db_path,
        symbols=["FPT"],
        factor_records_path=factors,
        validation_report_path=_write_validation(tmp_path),
        readiness_report_path=_write_readiness(tmp_path),
    )

    assert result["status"] == "not_ready"
    assert any(reason.startswith("factor_record_missing:") for reason in result["reasons"])


def test_validation_report_not_ok_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    validation = _write_validation(tmp_path, status="not_ready", db_mutation_made=True)

    result = audit_adjusted_ohlc_execution(
        db_path=db_path,
        symbols=["FPT"],
        factor_records_path=_write_factors(tmp_path),
        validation_report_path=validation,
        readiness_report_path=_write_readiness(tmp_path),
    )

    assert result["status"] == "not_ready"
    assert "validation_status_not_ok:not_ready" in result["reasons"]


def test_readiness_report_not_ok_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    readiness = _write_readiness(tmp_path, status="not_ready", backtest_gate="blocked")

    result = audit_adjusted_ohlc_execution(
        db_path=db_path,
        symbols=["FPT"],
        factor_records_path=_write_factors(tmp_path),
        validation_report_path=_write_validation(tmp_path),
        readiness_report_path=readiness,
    )

    assert result["status"] == "not_ready"
    assert "readiness_status_not_ok:not_ready" in result["reasons"]


def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--factor-records",
        str(_write_factors(tmp_path)),
        "--validation-report",
        str(_write_validation(tmp_path)),
        "--readiness-report",
        str(_write_readiness(tmp_path)),
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

    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--factor-records",
        str(_write_factors(tmp_path)),
        "--validation-report",
        str(_write_validation(tmp_path)),
        "--readiness-report",
        str(_write_readiness(tmp_path)),
        "--output-json",
        str(output),
    )

    assert completed.returncode == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ok"


def test_markdown_output_written(tmp_path: Path) -> None:
    output = tmp_path / "audit.md"

    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--factor-records",
        str(_write_factors(tmp_path)),
        "--validation-report",
        str(_write_validation(tmp_path)),
        "--readiness-report",
        str(_write_readiness(tmp_path)),
        "--output-md",
        str(output),
    )

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

    result = _audit_strict(tmp_path, db_path=db_path, symbols=["FPT", "VNM", "VCB"])

    assert result["status"] == "ok"
    assert _raw_rows(db_path) == before


def test_raw_ohlc_baseline_matching_returns_ok(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    baseline = _write_raw_baseline(tmp_path)

    result = _audit_strict(tmp_path, db_path=db_path, symbols=["FPT"], raw_baseline_path=baseline)

    assert result["status"] == "ok"
    assert result["raw_ohlc_baseline_status"] == "ok"


def test_missing_factor_records_path_in_strict_mode_returns_not_ready(tmp_path: Path) -> None:
    result = audit_adjusted_ohlc_execution(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        validation_report_path=_write_validation(tmp_path),
        readiness_report_path=_write_readiness(tmp_path),
    )

    assert result["status"] == "not_ready"
    assert result["backtest_planning_gate"] == "blocked"
    assert "factor_records_required" in result["reasons"]


def test_missing_validation_report_path_in_strict_mode_returns_not_ready(tmp_path: Path) -> None:
    result = audit_adjusted_ohlc_execution(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        factor_records_path=_write_factors(tmp_path),
        readiness_report_path=_write_readiness(tmp_path),
    )

    assert result["status"] == "not_ready"
    assert "validation_report_required" in result["reasons"]


def test_missing_readiness_report_path_in_strict_mode_returns_not_ready(tmp_path: Path) -> None:
    result = audit_adjusted_ohlc_execution(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        factor_records_path=_write_factors(tmp_path),
        validation_report_path=_write_validation(tmp_path),
    )

    assert result["status"] == "not_ready"
    assert "readiness_report_required" in result["reasons"]


def test_allow_incomplete_evidence_permits_row_level_audit_but_blocks_planning(tmp_path: Path) -> None:
    result = audit_adjusted_ohlc_execution(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        allow_incomplete_evidence=True,
    )

    assert result["status"] == "ok"
    assert result["evidence_mode"] == "incomplete"
    assert result["backtest_planning_gate"] == "blocked"
    assert "Incomplete evidence mode; not sufficient for backtest planning." in result["caveats"]


def test_incomplete_mode_markdown_says_not_sufficient_for_backtest_planning(tmp_path: Path) -> None:
    output = tmp_path / "audit.md"

    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--allow-incomplete-evidence",
        "--output-md",
        str(output),
    )

    assert completed.returncode == 0
    assert "not sufficient for backtest planning" in output.read_text(encoding="utf-8")


def test_missing_raw_baseline_does_not_fail_but_reports_not_provided(tmp_path: Path) -> None:
    result = _audit_strict(tmp_path, db_path=_make_db(tmp_path), symbols=["FPT"])

    assert result["status"] == "ok"
    assert result["raw_ohlc_baseline_status"] == "not_provided"


def test_raw_baseline_mismatch_returns_not_ready(tmp_path: Path) -> None:
    baseline = _write_raw_baseline(tmp_path, open_value=99.0)

    result = _audit_strict(tmp_path, db_path=_make_db(tmp_path), symbols=["FPT"], raw_baseline_path=baseline)

    assert result["status"] == "not_ready"
    assert any(reason.startswith("raw_ohlc_baseline_mismatch:FPT:2026-01-02:open") for reason in result["reasons"])


def test_raw_baseline_missing_db_row_returns_not_ready(tmp_path: Path) -> None:
    baseline = _write_raw_baseline(tmp_path, symbol="MSN")

    result = _audit_strict(tmp_path, db_path=_make_db(tmp_path), symbols=["FPT"], raw_baseline_path=baseline)

    assert result["status"] == "not_ready"
    assert "raw_ohlc_baseline_row_missing:MSN:2026-01-02" in result["reasons"]


def test_invalid_baseline_json_exits_one_cleanly_through_cli(tmp_path: Path) -> None:
    baseline = tmp_path / "bad_baseline.json"
    baseline.write_text("{bad-json", encoding="utf-8")

    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--factor-records",
        str(_write_factors(tmp_path)),
        "--validation-report",
        str(_write_validation(tmp_path)),
        "--readiness-report",
        str(_write_readiness(tmp_path)),
        "--raw-baseline",
        str(baseline),
    )

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "raw_ohlc_baseline_invalid" in completed.stdout


def test_baseline_cli_success_exits_zero_when_matching(tmp_path: Path) -> None:
    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--factor-records",
        str(_write_factors(tmp_path)),
        "--validation-report",
        str(_write_validation(tmp_path)),
        "--readiness-report",
        str(_write_readiness(tmp_path)),
        "--raw-baseline",
        str(_write_raw_baseline(tmp_path)),
    )

    assert completed.returncode == 0
    assert '"raw_ohlc_baseline_status": "ok"' in completed.stdout


def test_markdown_includes_raw_baseline_status_and_planning_gate(tmp_path: Path) -> None:
    output = tmp_path / "audit.md"

    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--factor-records",
        str(_write_factors(tmp_path)),
        "--validation-report",
        str(_write_validation(tmp_path)),
        "--readiness-report",
        str(_write_readiness(tmp_path)),
        "--output-md",
        str(output),
    )

    assert completed.returncode == 0
    text = output.read_text(encoding="utf-8")
    assert "Raw OHLC baseline status:" in text
    assert "Backtest planning gate:" in text


def test_cli_without_evidence_exits_one_in_strict_mode(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--db-path", str(_make_db(tmp_path)))

    assert completed.returncode == 1
    assert "factor_records_required" in completed.stdout
    assert "validation_report_required" in completed.stdout
    assert "readiness_report_required" in completed.stdout


def test_cli_allow_incomplete_evidence_exits_zero_for_row_level_audit_with_blocked_gate(tmp_path: Path) -> None:
    completed = _run_cli(
        tmp_path,
        "--db-path",
        str(_make_db(tmp_path)),
        "--allow-incomplete-evidence",
    )

    assert completed.returncode == 0
    assert '"backtest_planning_gate": "blocked"' in completed.stdout


def _run_cli(tmp_path: Path, *overrides: str) -> subprocess.CompletedProcess[str]:
    override_map = {}
    index = 0
    while index < len(overrides):
        flag = overrides[index]
        if flag == "--allow-incomplete-evidence":
            index += 1
            continue
        override_map[flag] = overrides[index + 1]
        index += 2
    db_path = override_map["--db-path"] if "--db-path" in override_map else str(_make_db(tmp_path))
    args = [
        sys.executable,
        str(SCRIPT),
        "--db-path",
        db_path,
        "--symbols",
        "FPT,VNM,VCB",
    ]
    index = 0
    while index < len(overrides):
        flag = overrides[index]
        if flag == "--allow-incomplete-evidence":
            args.append(flag)
            index += 1
            continue
        value = overrides[index + 1]
        if flag in args:
            args[args.index(flag) + 1] = value
        else:
            args.extend([flag, value])
        index += 2
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)


def _audit_strict(
    tmp_path: Path,
    *,
    db_path: Path,
    symbols: list[str],
    raw_baseline_path: Path | None = None,
) -> dict[str, object]:
    return audit_adjusted_ohlc_execution(
        db_path=db_path,
        symbols=symbols,
        factor_records_path=_write_factors(tmp_path),
        validation_report_path=_write_validation(tmp_path),
        readiness_report_path=_write_readiness(tmp_path),
        raw_baseline_path=raw_baseline_path,
    )


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


def _write_raw_baseline(tmp_path: Path, *, symbol: str = "FPT", open_value: float = 95.0) -> Path:
    path = tmp_path / "raw_baseline.json"
    path.write_text(
        json.dumps(
            [
                {
                    "symbol": symbol,
                    "trade_date": "2026-01-02",
                    "open": open_value,
                    "high": 105.0,
                    "low": 90.0,
                    "close": 100.0,
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _raw_rows(db_path: Path) -> dict[str, tuple[float, float, float, float]]:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT symbol, open, high, low, close FROM daily_prices ORDER BY symbol").fetchall()
    return {str(row["symbol"]): (row["open"], row["high"], row["low"], row["close"]) for row in rows}
