from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from trading_agent.db.quality import (
    check_duplicate_daily_price_keys,
    classify_daily_price_row,
    classify_security_row,
    summarize_quality,
)
from trading_agent.db.schema import create_schema, connect, replace_table
from trading_agent.features.mvp_daily import compute_feature_snapshots
from trading_agent.ingestion.parsers.vietcap_iq_gap_chart_parser import parse_vietcap_iq_gap_chart_payload
from trading_agent.signals.mvp_momentum import generate_signals


DEFAULT_RAW_BASE_DIR = Path("data/raw/controlled_fetch/source=vietcap_iq")
DEFAULT_DB_PATH = Path("data/demo/mvp_trading_agent.sqlite")
SOURCE_ID_PREFIX = "vietcap_iq_gap_chart"
ISSUER_NAMES = {
    "FPT": "FPT Corporation",
    "VNM": "Vietnam Dairy Products JSC",
    "VCB": "Joint Stock Commercial Bank for Foreign Trade of Vietnam",
    "REE": "Refrigeration Electrical Engineering Corporation",
    "SAM": "SAM Holdings Corporation",
}


def discover_gap_chart_payloads(raw_base_dir: str | Path = DEFAULT_RAW_BASE_DIR) -> dict[str, tuple[Path, Path]]:
    base = Path(raw_base_dir)
    found: dict[str, tuple[str, Path, Path]] = {}
    for metadata_path in base.glob("*/vietcap_iq_gap_chart_*_countback_*/metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("access_status") != "verified" or metadata.get("status") != "success":
            continue
        symbol = str(metadata.get("symbol") or "").strip().upper()
        if not symbol:
            dataset = str(metadata.get("dataset") or "")
            parts = dataset.split("_")
            symbol = parts[4].upper() if len(parts) > 4 else ""
        raw_path = Path(metadata.get("raw_path") or metadata_path.parent / "payload.json")
        if not raw_path.exists():
            raw_path = metadata_path.parent / "payload.json"
        if not symbol or not raw_path.exists():
            continue
        key = str(metadata.get("crawled_at") or metadata_path.stat().st_mtime)
        current = found.get(symbol)
        if current is None or key > current[0]:
            found[symbol] = (key, raw_path, metadata_path)
    return {symbol: (raw, metadata) for symbol, (_, raw, metadata) in sorted(found.items())}


def build_mvp_store(
    *,
    symbols: list[str] | None = None,
    raw_base_dir: str | Path = DEFAULT_RAW_BASE_DIR,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    available = discover_gap_chart_payloads(raw_base_dir)
    requested = [symbol.strip().upper() for symbol in symbols or sorted(available) if symbol.strip()]
    selected = {symbol: available[symbol] for symbol in requested if symbol in available}
    missing = [symbol for symbol in requested if symbol not in available]
    if not selected:
        raise FileNotFoundError(f"No local gap-chart payloads found for requested symbols: {requested}")

    securities_rows: list[dict[str, object]] = []
    price_frames: list[pd.DataFrame] = []
    security_quality = []
    price_quality = []

    for symbol, (raw_path, metadata_path) in selected.items():
        parsed = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path, symbol_override=symbol)
        bars = parsed.daily_price_bars.copy()
        security_id = f"vietcap_iq:HOSE:{symbol}"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        crawled_at = metadata.get("crawled_at") or datetime.now(timezone.utc).isoformat()
        source_id = f"{SOURCE_ID_PREFIX}:{symbol}:{metadata.get('run_id') or metadata_path.parent.parent.name}"
        security_row = {
            "security_id": security_id,
            "symbol": symbol,
            "exchange": "HOSE",
            "issuer_name": ISSUER_NAMES.get(symbol, symbol),
            "source_id": source_id,
            "raw_path": str(raw_path),
            "first_seen_at": crawled_at,
            "quality_status": "pass",
        }
        sec_status, sec_reasons = classify_security_row(pd.Series(security_row))
        security_row["quality_status"] = sec_status
        security_quality.append((sec_status, sec_reasons))
        securities_rows.append(security_row)

        prices = pd.DataFrame(
            {
                "security_id": security_id,
                "symbol": bars["symbol"].astype(str).str.upper(),
                "trade_date": bars["trading_date"],
                "open": bars["open_price"],
                "high": bars["high_price"],
                "low": bars["low_price"],
                "close": bars["close_price"],
                "adjustment_factor": None,
                "adjusted_open": None,
                "adjusted_high": None,
                "adjusted_low": None,
                "adjusted_close": None,
                "volume": bars["volume"],
                "value": bars["trading_value"],
                "price_basis": bars["price_basis"],
                "adjustment_status": bars["adjustment_type"],
                "source_id": source_id,
                "raw_path": str(raw_path),
                "quality_status": "pass",
            }
        )
        row_statuses = [classify_daily_price_row(row) for _, row in prices.iterrows()]
        prices["quality_status"] = [status for status, _ in row_statuses]
        price_quality.extend(row_statuses)
        price_frames.append(prices)

    daily_prices = pd.concat(price_frames, ignore_index=True).sort_values(["symbol", "trade_date"])
    duplicate_reasons = check_duplicate_daily_price_keys(daily_prices)
    if duplicate_reasons:
        price_quality.extend([("fail", duplicate_reasons)])

    usable_prices = daily_prices[daily_prices["quality_status"] != "fail"].copy()
    feature_snapshots = compute_feature_snapshots(usable_prices)
    signals = generate_signals(feature_snapshots, usable_prices)

    with connect(db_path) as con:
        create_schema(con)
        replace_table(con, "securities", securities_rows)
        replace_table(con, "daily_prices", _records(daily_prices))
        replace_table(con, "feature_snapshots", _records(feature_snapshots))
        replace_table(con, "signals", _records(signals))

    summary = {
        "status": "ok",
        "storage": "sqlite",
        "db_path": str(db_path),
        "symbols_loaded": sorted(selected),
        "symbols_missing": missing,
        "row_counts": {
            "securities": len(securities_rows),
            "daily_prices": len(daily_prices),
            "feature_snapshots": len(feature_snapshots),
            "signals": len(signals),
        },
        "date_ranges": _date_ranges(daily_prices),
        "quality": {
            "securities": summarize_quality("securities", security_quality).as_dict(),
            "daily_prices": summarize_quality("daily_prices", price_quality).as_dict(),
        },
        "output_paths": {"sqlite": str(db_path)},
    }
    return summary


def _records(df: pd.DataFrame) -> list[dict[str, object]]:
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def _date_ranges(df: pd.DataFrame) -> dict[str, dict[str, object]]:
    ranges = {}
    for symbol, group in df.groupby("symbol"):
        ranges[str(symbol)] = {
            "rows": int(len(group)),
            "start": str(group["trade_date"].min()),
            "end": str(group["trade_date"].max()),
        }
    return ranges
