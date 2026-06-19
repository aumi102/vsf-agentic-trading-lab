from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.db.schema import create_schema
from trading_agent.ingestion.adjusted_price_evidence_pipeline import run_adjusted_price_evidence_pipeline
from trading_agent.ingestion.adjusted_readiness import get_adjusted_ohlc_readiness


DEFAULT_SYMBOLS = ["FPT", "VNM", "VCB"]
TRADE_DATE = "2026-01-02"
SYNTHETIC_PRICES = {
    "FPT": {"close": 100.0, "adjusted_close": 80.0},
    "VNM": {"close": 200.0, "adjusted_close": 180.0},
    "VCB": {"close": 50.0, "adjusted_close": 45.0},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local adjusted-price evidence smoke.")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional explicit directory for smoke artifacts. Defaults to a temporary directory.",
    )
    args = parser.parse_args()

    symbols = _parse_symbols(args.symbols)
    if args.output_dir:
        work_dir = Path(args.output_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        result = run_smoke(work_dir=work_dir, symbols=symbols, artifacts_persisted=True)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if result["status"] == "ok" else 1

    with tempfile.TemporaryDirectory(prefix="vsf_adjusted_price_smoke_", ignore_cleanup_errors=True) as temp_dir:
        result = run_smoke(work_dir=Path(temp_dir), symbols=symbols, artifacts_persisted=False)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if result["status"] == "ok" else 1


def run_smoke(*, work_dir: Path, symbols: list[str], artifacts_persisted: bool) -> dict[str, Any]:
    requested = _validate_symbols(symbols)
    if not requested:
        return {
            "status": "invalid_request",
            "symbols": requested,
            "reasons": ["explicit_symbols_required"],
            "artifacts_persisted": artifacts_persisted,
        }
    if len(requested) > 3:
        return {
            "status": "invalid_request",
            "symbols": requested,
            "reasons": ["too_many_symbols:max=3"],
            "artifacts_persisted": artifacts_persisted,
        }

    missing = sorted(set(requested) - set(SYNTHETIC_PRICES))
    if missing:
        return {
            "status": "invalid_request",
            "symbols": requested,
            "reasons": [f"unsupported_synthetic_symbols:{','.join(missing)}"],
            "artifacts_persisted": artifacts_persisted,
        }

    work_dir.mkdir(parents=True, exist_ok=True)
    payload_path = work_dir / "adjusted_price_payload.json"
    dry_factor_path = work_dir / "factors_dry_run.json"
    execute_factor_path = work_dir / "factors_execute.json"
    db_path = work_dir / "adjusted_price_smoke.sqlite"

    _write_payload(payload_path, requested)
    _write_daily_price_db(db_path, requested)

    dry_run = run_adjusted_price_evidence_pipeline(
        payload_path=payload_path,
        source_id="fixture:adjusted_price_smoke",
        raw_path=str(payload_path),
        symbols=requested,
        factor_output_path=dry_factor_path,
        dry_run=True,
        execute=False,
    )
    execute = run_adjusted_price_evidence_pipeline(
        payload_path=payload_path,
        source_id="fixture:adjusted_price_smoke",
        raw_path=str(payload_path),
        symbols=requested,
        factor_output_path=execute_factor_path,
        db_path=db_path,
        dry_run=False,
        execute=True,
    )
    readiness = get_adjusted_ohlc_readiness(db_path, symbols=requested)
    status = (
        "ok"
        if dry_run.get("status") == "ok"
        and execute.get("status") == "ok"
        and readiness.get("backtest_gate") == "pass"
        else "not_ready"
    )
    return {
        "status": status,
        "symbols": requested,
        "payload_path": str(payload_path) if artifacts_persisted else None,
        "db_path": str(db_path) if artifacts_persisted else None,
        "factor_output_paths": [str(dry_factor_path), str(execute_factor_path)] if artifacts_persisted else [],
        "artifacts_persisted": artifacts_persisted,
        "dry_run": dry_run,
        "execute": execute,
        "readiness": readiness,
        "caveats": [
            "Synthetic local payload only; no network request is made.",
            "Temporary DB mutation is isolated to the smoke artifact directory.",
            "No Backtrader/VN100 run is performed.",
        ],
    }


def _write_payload(path: Path, symbols: list[str]) -> None:
    rows = []
    for symbol in symbols:
        prices = SYNTHETIC_PRICES[symbol]
        rows.append(
            {
                "symbol": symbol,
                "trade_date": TRADE_DATE,
                "close": prices["close"],
                "adjusted_close": prices["adjusted_close"],
            }
        )
    path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")


def _write_daily_price_db(path: Path, symbols: list[str]) -> None:
    with sqlite3.connect(path) as con:
        create_schema(con)
        for symbol in symbols:
            close = SYNTHETIC_PRICES[symbol]["close"]
            con.execute(
                """
                INSERT INTO daily_prices (
                    security_id, symbol, trade_date, open, high, low, close,
                    volume, value, price_basis, adjustment_status, source_id, raw_path, quality_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"fixture:smoke:{symbol}:{TRADE_DATE}",
                    symbol,
                    TRADE_DATE,
                    close * 0.95,
                    close * 1.05,
                    close * 0.9,
                    close,
                    1000.0,
                    close * 1000.0,
                    "source_reported",
                    "unknown",
                    "fixture:daily_prices_smoke",
                    f"synthetic://adjusted-price-smoke/{symbol.lower()}",
                    "ok",
                ),
            )
        con.commit()


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _validate_symbols(symbols: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for symbol in symbols:
        clean = str(symbol or "").strip().upper()
        if clean and clean not in seen:
            normalized.append(clean)
            seen.add(clean)
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
