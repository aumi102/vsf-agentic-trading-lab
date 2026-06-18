from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from trading_agent.db.build_mvp_store import (
    DEFAULT_DB_PATH,
    DEFAULT_RAW_BASE_DIR,
    ISSUER_NAMES,
    SOURCE_ID_PREFIX,
    discover_gap_chart_payloads,
)
from trading_agent.db.quality import (
    check_duplicate_daily_price_keys,
    classify_daily_price_row,
    classify_security_row,
)
from trading_agent.db.schema import create_schema, connect
from trading_agent.features.mvp_daily import FEATURE_VERSION, compute_feature_snapshots
from trading_agent.ingestion.parsers.vietcap_iq_gap_chart_parser import parse_vietcap_iq_gap_chart_payload
from trading_agent.ingestion.quality_report import build_ingestion_quality_report
from trading_agent.ingestion.raw_store import build_raw_payload_record, record_raw_payload
from trading_agent.ingestion.run_log import complete_source_run, make_run_id, start_source_run, utc_now_iso
from trading_agent.ingestion.sources.vietcap_iq_gap_chart import fetch_vietcap_iq_gap_chart_live
from trading_agent.signals.mvp_momentum import SIGNAL_VERSION, STRATEGY_ID, generate_signals


DEFAULT_SOURCE = "vietcap_iq_gap_chart"
DEFAULT_MAX_LIVE_SYMBOLS = 3


def run_ohlcv_ingestion(
    symbols: list[str],
    db_path: str | Path = DEFAULT_DB_PATH,
    source: str = DEFAULT_SOURCE,
    mode: str = "cached",
    allow_network: bool = False,
    refresh_features: bool = True,
    refresh_signals: bool = True,
    raw_base_dir: str | Path = DEFAULT_RAW_BASE_DIR,
    count_back: int = 5000,
    live_output_dir: str | Path | None = None,
    timeout_seconds: int = 20,
    max_live_symbols: int = DEFAULT_MAX_LIVE_SYMBOLS,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    run_id = make_run_id(source, mode)
    base_result: dict[str, Any] = {
        "status": "error",
        "run_id": run_id,
        "source": source,
        "mode": mode,
        "symbols_requested": requested,
        "symbols_loaded": [],
        "symbols_failed": requested,
        "raw_payloads": [],
        "canonical_rows": {},
        "feature_rows": 0,
        "signal_rows": 0,
        "quality": {},
        "caveats": [],
    }
    if not requested:
        base_result["caveats"] = ["At least one symbol is required."]
        return base_result
    if mode not in {"cached", "live"}:
        base_result["caveats"] = [f"Unsupported ingestion mode: {mode}."]
        return base_result
    if mode == "live" and not allow_network:
            caveats = [
                "Live ingestion requires explicit --allow-network. No network request was made."
            ]
            return _record_gated_live_attempt(
                db_path=db_path,
                run_id=run_id,
                source=source,
                mode=mode,
                symbols_requested=requested,
                allow_network=allow_network,
                caveats=caveats,
            )
    if mode == "live" and len(requested) > max_live_symbols:
        return _record_gated_live_attempt(
            db_path=db_path,
            run_id=run_id,
            source=source,
            mode=mode,
            symbols_requested=requested,
            allow_network=allow_network,
            caveats=[f"Live ingestion supports at most {max_live_symbols} symbols per run."],
        )

    with connect(db_path) as con:
        create_schema(con)
        if mode == "cached":
            available = discover_gap_chart_payloads(raw_base_dir)
            selected = {symbol: available[symbol] for symbol in requested if symbol in available}
            failed_symbols = [symbol for symbol in requested if symbol not in available]
            caveats = [
                "Cached mode reads saved local payloads only; no network request was made.",
                "Adjustment/corporate-action handling remains source-reported and not production-hardened.",
            ]
            if failed_symbols:
                caveats.append(f"No cached gap-chart payload found for: {', '.join(failed_symbols)}.")
        else:
            caveats = [
                "Live mode is explicitly enabled with --allow-network.",
                "Controlled live adapter is limited to a small explicit symbol list.",
                "Adjustment/corporate-action handling remains source-reported and not production-hardened.",
            ]
            selected = {}
            failed_symbols = []

        start_source_run(
            con,
            run_id=run_id,
            source=source,
            mode=mode,
            symbols_requested=requested,
            allow_network=allow_network,
            caveats=caveats,
        )
        if mode == "live":
            fetch_result = fetch_vietcap_iq_gap_chart_live(
                requested,
                output_base_dir=live_output_dir or raw_base_dir,
                count_back=count_back,
                allow_network=allow_network,
                timeout_seconds=timeout_seconds,
                max_symbols=max_live_symbols,
                run_id=run_id,
            )
            caveats.extend(str(item) for item in fetch_result.get("caveats", []))
            failed_symbols = list(fetch_result.get("symbols_failed", []))
            selected = {
                str(item["symbol"]): (Path(str(item["raw_path"])), Path(str(item["metadata_path"])))
                for item in fetch_result.get("payloads", [])
                if item.get("status") == "success" and item.get("raw_path") and item.get("metadata_path")
            }
        if not selected:
            complete_source_run(
                con,
                run_id=run_id,
                status="error",
                symbols_loaded=[],
                symbols_failed=failed_symbols or requested,
                caveats=caveats,
            )
            base_result["caveats"] = caveats
            base_result["quality"] = build_ingestion_quality_report(con, symbols=requested)
            base_result["symbols_failed"] = failed_symbols or requested
            return base_result

        securities_rows: list[dict[str, object]] = []
        daily_frames: list[pd.DataFrame] = []
        raw_payloads: list[dict[str, object]] = []

        for symbol, (raw_path, metadata_path) in selected.items():
            try:
                raw_record = build_raw_payload_record(
                    run_id=run_id,
                    source=source,
                    symbol=symbol,
                    raw_path=raw_path,
                    metadata_path=metadata_path,
                )
                record_raw_payload(con, raw_record)
                raw_payloads.append(raw_record)
                security_row, prices = _parse_cached_payload(
                    symbol=symbol,
                    raw_path=raw_path,
                    metadata_path=metadata_path,
                    source=source,
                )
                securities_rows.append(security_row)
                daily_frames.append(prices)
            except Exception as exc:  # pragma: no cover - defensive source isolation
                failed_symbols.append(symbol)
                caveats.append(f"{symbol} ingestion failed: {exc}")

        con.commit()
        if not daily_frames:
            complete_source_run(
                con,
                run_id=run_id,
                status="error",
                symbols_loaded=[],
                symbols_failed=sorted(set(failed_symbols)),
                caveats=caveats,
            )
            return {
                **base_result,
                "symbols_failed": sorted(set(failed_symbols)),
                "raw_payloads": raw_payloads,
                "quality": build_ingestion_quality_report(con, symbols=requested),
                "caveats": caveats,
            }

        daily_prices = pd.concat(daily_frames, ignore_index=True).sort_values(["symbol", "trade_date"])
        duplicate_reasons = check_duplicate_daily_price_keys(daily_prices)
        if duplicate_reasons:
            caveats.append(f"Duplicate canonical daily price keys detected: {', '.join(duplicate_reasons)}.")
        _upsert_rows(con, "securities", securities_rows, key_columns=["security_id"])
        _upsert_rows(
            con,
            "daily_prices",
            _records(daily_prices),
            key_columns=["security_id", "trade_date", "source_id"],
        )
        loaded_symbols = sorted({str(symbol) for symbol in daily_prices["symbol"].dropna().unique()})

        feature_rows = 0
        signal_rows = 0
        if refresh_features:
            feature_rows = _refresh_features(con, loaded_symbols)
        if refresh_signals:
            signal_rows = _refresh_signals(con, loaded_symbols)
        _refresh_watermarks(con, source=source, run_id=run_id, symbols=loaded_symbols)

        status = "partial_ok" if failed_symbols else "ok"
        complete_source_run(
            con,
            run_id=run_id,
            status=status,
            symbols_loaded=loaded_symbols,
            symbols_failed=sorted(set(failed_symbols)),
            caveats=caveats,
        )
        quality = build_ingestion_quality_report(con, symbols=requested)
        return {
            "status": status,
            "run_id": run_id,
            "source": source,
            "mode": mode,
            "symbols_requested": requested,
            "symbols_loaded": loaded_symbols,
            "symbols_failed": sorted(set(failed_symbols)),
            "raw_payloads": raw_payloads,
            "canonical_rows": {
                "securities_upserted": len(securities_rows),
                "daily_prices_upserted": int(len(daily_prices)),
                "daily_prices_total_for_loaded_symbols": _count_rows(con, "daily_prices", loaded_symbols),
            },
            "feature_rows": feature_rows,
            "signal_rows": signal_rows,
            "quality": quality,
            "caveats": caveats,
        }


def _record_gated_live_attempt(
    *,
    db_path: str | Path,
    run_id: str,
    source: str,
    mode: str,
    symbols_requested: list[str],
    allow_network: bool,
    caveats: list[str],
) -> dict[str, Any]:
    with connect(db_path) as con:
        create_schema(con)
        start_source_run(
            con,
            run_id=run_id,
            source=source,
            mode=mode,
            symbols_requested=symbols_requested,
            allow_network=allow_network,
            caveats=caveats,
        )
        complete_source_run(
            con,
            run_id=run_id,
            status="error",
            symbols_loaded=[],
            symbols_failed=symbols_requested,
            caveats=caveats,
        )
        quality = build_ingestion_quality_report(con, symbols=symbols_requested)
    return {
        "status": "error",
        "run_id": run_id,
        "source": source,
        "mode": mode,
        "symbols_requested": symbols_requested,
        "symbols_loaded": [],
        "symbols_failed": symbols_requested,
        "raw_payloads": [],
        "canonical_rows": {},
        "feature_rows": 0,
        "signal_rows": 0,
        "quality": quality,
        "caveats": caveats,
    }


def _parse_cached_payload(
    *,
    symbol: str,
    raw_path: Path,
    metadata_path: Path,
    source: str,
) -> tuple[dict[str, object], pd.DataFrame]:
    parsed = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path, symbol_override=symbol)
    bars = parsed.daily_price_bars.copy()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    crawled_at = metadata.get("crawled_at") or utc_now_iso()
    source_id = f"{SOURCE_ID_PREFIX}:{symbol}:{metadata.get('run_id') or metadata_path.parent.parent.name}"
    security_id = f"vietcap_iq:HOSE:{symbol}"
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
    sec_status, _ = classify_security_row(pd.Series(security_row))
    security_row["quality_status"] = sec_status

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
            "adjustment_source_id": None,
            "adjustment_raw_path": None,
            "adjustment_method": None,
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
    return security_row, prices


def _refresh_features(con, symbols: list[str]) -> int:
    _delete_symbol_rows(con, "feature_snapshots", "feature_version", FEATURE_VERSION, symbols)
    prices = _load_usable_prices(con, symbols)
    features = compute_feature_snapshots(prices)
    rows = _records(features)
    if rows:
        _upsert_rows(
            con,
            "feature_snapshots",
            rows,
            key_columns=["security_id", "as_of_date", "feature_version"],
        )
    return len(rows)


def _refresh_signals(con, symbols: list[str]) -> int:
    _delete_symbol_rows(con, "signals", "signal_version", SIGNAL_VERSION, symbols)
    prices = _load_usable_prices(con, symbols)
    features = _load_features(con, symbols)
    signals = generate_signals(features, prices)
    rows = _records(signals)
    if rows:
        _upsert_rows(
            con,
            "signals",
            rows,
            key_columns=["security_id", "as_of_date", "strategy_id", "signal_version"],
        )
    return len(rows)


def _load_usable_prices(con, symbols: list[str]) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(symbols))
    rows = con.execute(
        f"""
        SELECT security_id, symbol, trade_date, open, high, low, close, volume, value,
               price_basis, adjustment_status, source_id, raw_path, quality_status
        FROM daily_prices
        WHERE symbol IN ({placeholders}) AND quality_status != 'fail'
        ORDER BY symbol, trade_date
        """,
        symbols,
    ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _load_features(con, symbols: list[str]) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(symbols))
    rows = con.execute(
        f"""
        SELECT security_id, symbol, as_of_date, return_1d, return_5d, return_20d,
               ma_20, ma_50, volatility_20d, volume_ratio_20d,
               feature_version, lookback_coverage, quality_status
        FROM feature_snapshots
        WHERE symbol IN ({placeholders}) AND feature_version = ?
        ORDER BY symbol, as_of_date
        """,
        [*symbols, FEATURE_VERSION],
    ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _refresh_watermarks(con, *, source: str, run_id: str, symbols: list[str]) -> None:
    for symbol in symbols:
        row = con.execute(
            """
            SELECT MAX(trade_date) AS last_trade_date, COUNT(*) AS row_count
            FROM daily_prices
            WHERE symbol = ? AND quality_status != 'fail'
            """,
            (symbol,),
        ).fetchone()
        con.execute(
            """
            INSERT INTO ingestion_watermarks (
                source, symbol, last_trade_date, last_run_id, updated_at, row_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, symbol) DO UPDATE SET
                last_trade_date = excluded.last_trade_date,
                last_run_id = excluded.last_run_id,
                updated_at = excluded.updated_at,
                row_count = excluded.row_count
            """,
            (
                source,
                symbol,
                row["last_trade_date"],
                run_id,
                utc_now_iso(),
                int(row["row_count"] or 0),
            ),
        )
    con.commit()


def _delete_symbol_rows(con, table: str, version_column: str, version: str, symbols: list[str]) -> None:
    if not symbols:
        return
    placeholders = ", ".join(["?"] * len(symbols))
    con.execute(
        f"DELETE FROM {table} WHERE symbol IN ({placeholders}) AND {version_column} = ?",
        [*symbols, version],
    )


def _upsert_rows(con, table: str, rows: list[dict[str, object]], *, key_columns: list[str]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    update_columns = [column for column in columns if column not in key_columns]
    update_sql = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
    conflict_sql = ", ".join(key_columns)
    values = [tuple(row.get(column) for column in columns) for row in rows]
    con.executemany(
        f"""
        INSERT INTO {table} ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT({conflict_sql}) DO UPDATE SET {update_sql}
        """,
        values,
    )
    con.commit()


def _records(df: pd.DataFrame) -> list[dict[str, object]]:
    if df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def _count_rows(con, table: str, symbols: list[str]) -> int:
    if not symbols:
        return 0
    placeholders = ", ".join(["?"] * len(symbols))
    row = con.execute(
        f"SELECT COUNT(*) AS rows FROM {table} WHERE symbol IN ({placeholders})",
        symbols,
    ).fetchone()
    return int(row["rows"] or 0)


def _normalize_symbols(symbols: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for item in symbols:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    return normalized
