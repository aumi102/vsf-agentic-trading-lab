from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.db.build_mvp_store import build_mvp_store
from trading_agent.db.quality import check_duplicate_daily_price_keys, classify_daily_price_row
from trading_agent.db.schema import create_schema
from trading_agent.features.mvp_daily import compute_feature_snapshots
from trading_agent.signals.mvp_momentum import evaluate_momentum_signal
from trading_agent.tools.feature_tool import compute_latest_features
from trading_agent.tools.market_data_tool import get_latest_market_data
from trading_agent.tools.report_tool import compose_market_answer
from trading_agent.tools.risk_tool import assess_symbol_risk
from trading_agent.tools.signal_tool import evaluate_active_signals


def test_schema_construction_creates_mvp_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "mvp.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert {"securities", "daily_prices", "feature_snapshots", "signals"} <= tables


def test_duplicate_primary_key_detection() -> None:
    df = pd.DataFrame(
        [
            {"security_id": "vietcap_iq:HOSE:FPT", "trade_date": "2026-01-01", "source_id": "src"},
            {"security_id": "vietcap_iq:HOSE:FPT", "trade_date": "2026-01-01", "source_id": "src"},
        ]
    )
    assert check_duplicate_daily_price_keys(df) == ["duplicate_security_id_trade_date_source_id"]


def test_ohlc_validity_and_missing_lineage_checks() -> None:
    valid = pd.Series(
        {
            "security_id": "vietcap_iq:HOSE:FPT",
            "symbol": "FPT",
            "trade_date": "2026-01-01",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "volume": 1000,
            "source_id": "src",
            "raw_path": "payload.json",
            "adjustment_status": "unknown",
        }
    )
    assert classify_daily_price_row(valid) == ("warn", ["adjustment_status_unknown"])
    invalid = valid.copy()
    invalid["high"] = 9.5
    invalid["raw_path"] = ""
    invalid["source_id"] = ""
    status, reasons = classify_daily_price_row(invalid)
    assert status == "fail"
    assert "ohlc_inconsistent" in reasons
    assert "missing_raw_path" in reasons
    assert "missing_source_id" in reasons


def test_feature_calculation_and_insufficient_lookback() -> None:
    prices = _daily_prices("FPT", closes=[float(10 + i) for i in range(60)])
    features = compute_feature_snapshots(prices)
    latest = features.iloc[-1]
    assert latest["quality_status"] == "pass"
    assert latest["lookback_coverage"] == 60
    assert latest["ma_20"] > latest["ma_50"]
    short = compute_feature_snapshots(prices.head(10)).iloc[-1]
    assert short["quality_status"] == "warn"
    assert pd.isna(short["ma_20"]) or short["ma_20"] is None


def test_buy_hold_sell_signal_rules() -> None:
    buy = evaluate_momentum_signal(100, 90, 80, 0.1, 60)
    sell = evaluate_momentum_signal(70, 80, 90, -0.1, 60)
    hold = evaluate_momentum_signal(85, 90, 80, 0.1, 60)
    low = evaluate_momentum_signal(None, None, None, None, 10)
    assert buy["action"] == "BUY"
    assert sell["action"] == "SELL"
    assert hold["action"] == "HOLD"
    assert low["action"] == "HOLD_WITH_LOW_CONFIDENCE"


def test_build_store_and_tool_output_shapes(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"

    summary = build_mvp_store(symbols=["FPT"], raw_base_dir=raw_base, db_path=db_path)

    assert summary["row_counts"]["securities"] == 1
    assert summary["row_counts"]["daily_prices"] == 60
    market = get_latest_market_data("FPT", db_path)
    features = compute_latest_features("FPT", db_path)
    signal = evaluate_active_signals("FPT", db_path)
    risk = assess_symbol_risk("FPT", db_path)
    assert market["status"] == "ok"
    assert market["latest_date"] == "2026-03-01"
    assert features["status"] == "ok"
    assert signal["action"] == "BUY"
    assert "Corporate-action adjustment status is unknown." in risk["caveats"]


def test_report_tool_does_not_invent_missing_metrics(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[10.0, 10.5])
    db_path = tmp_path / "short.sqlite"
    build_mvp_store(symbols=["FPT"], raw_base_dir=raw_base, db_path=db_path)

    report = compose_market_answer("FPT", db_path=db_path)

    assert report["status"] == "ok"
    answer = str(report["answer_markdown"])
    assert "không có dữ liệu" in answer
    assert "HOLD_WITH_LOW_CONFIDENCE" in answer


def test_demo_cli_smoke(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "cli.sqlite"
    build_mvp_store(symbols=["FPT"], raw_base_dir=raw_base, db_path=db_path)

    completed = subprocess.run(
        [sys.executable, "scripts/demo_agent_tools.py", "--symbol", "FPT", "--db-path", str(db_path)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    assert "## market_data" in completed.stdout
    assert "## final_answer" in completed.stdout
    assert "không phải khuyến nghị đầu tư" in completed.stdout


def _daily_prices(symbol: str, closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "security_id": f"vietcap_iq:HOSE:{symbol}",
            "symbol": symbol,
            "trade_date": [date.date().isoformat() for date in dates],
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": [1000 + i for i in range(len(closes))],
            "value": [10000 + i for i in range(len(closes))],
            "price_basis": "source_reported",
            "adjustment_status": "unknown",
            "source_id": "src",
            "raw_path": "payload.json",
            "quality_status": "warn",
        }
    )


def _write_gap_chart_fixture(tmp_path: Path, symbol: str, *, closes: list[float]) -> Path:
    raw_base = tmp_path / "data" / "raw" / "controlled_fetch" / "source=vietcap_iq"
    dataset_dir = raw_base / "20260616T000000Z" / f"vietcap_iq_gap_chart_{symbol.lower()}_countback_5000"
    dataset_dir.mkdir(parents=True)
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    payload = [
        {
            "symbol": symbol,
            "t": [int(date.timestamp()) for date in dates],
            "o": closes,
            "h": [value + 1 for value in closes],
            "l": [value - 1 for value in closes],
            "c": closes,
            "v": [1000 + i for i in range(len(closes))],
            "accumulatedVolume": [1000 + i for i in range(len(closes))],
            "accumulatedValue": [10000 + i for i in range(len(closes))],
        }
    ]
    raw_path = dataset_dir / "payload.json"
    raw_path.write_text(json.dumps(payload), encoding="utf-8")
    metadata_path = dataset_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source_name": "vietcap_iq",
                "dataset": f"vietcap_iq_gap_chart_{symbol.lower()}_countback_5000",
                "symbol": symbol,
                "run_id": "20260616T000000Z",
                "raw_path": str(raw_path),
                "access_status": "verified",
                "status": "success",
                "content_hash": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "crawled_at": "2026-06-16T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return raw_base
