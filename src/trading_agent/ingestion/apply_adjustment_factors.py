from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from trading_agent.ingestion.adjusted_ohlc import adjust_ohlc
from trading_agent.ingestion.adjustment_factors import AdjustmentFactorRecord, make_adjustment_factor_record


ERROR_STATUSES = {"missing_factor_file", "invalid_factor_json", "missing_store", "invalid_request"}
ADJUSTED_COLUMNS = ("adjustment_factor", "adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close")


def load_adjustment_factor_records(path: str | Path) -> list[AdjustmentFactorRecord]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("Adjustment factor file must contain a JSON list.")
    records: list[AdjustmentFactorRecord] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Adjustment factor record at index {index} must be an object.")
        try:
            records.append(
                make_adjustment_factor_record(
                    symbol=str(item.get("symbol") or ""),
                    trade_date=str(item.get("trade_date") or ""),
                    factor=item.get("factor"),
                    source_id=item.get("source_id"),
                    method=str(item.get("method") or "unknown"),
                    raw_path=item.get("raw_path"),
                    status=str(item.get("status") or ""),
                    reasons=item.get("reasons") or (),
                )
            )
        except ValueError as exc:
            records.append(
                make_adjustment_factor_record(
                    symbol=str(item.get("symbol") or f"INVALID_{index}"),
                    trade_date=str(item.get("trade_date") or "invalid"),
                    factor=None,
                    source_id=item.get("source_id"),
                    method="unknown",
                    raw_path=item.get("raw_path"),
                    status="invalid",
                    reasons=[f"record_validation_error:{exc}"],
                )
            )
    return records


def apply_adjustment_factors_to_rows(
    rows: list[dict[str, Any]],
    factors: list[AdjustmentFactorRecord],
) -> dict[str, Any]:
    factor_map = _usable_factor_map(factors)
    invalid_factor_records = [record for record in factors if not _is_usable_factor(record)]
    results = []
    rows_with_usable_factor = 0
    rows_missing_factor = 0
    rows_invalid = 0
    for row in rows:
        symbol = _normalize_symbol(row.get("symbol"))
        trade_date = str(row.get("trade_date") or "").strip()
        factor = factor_map.get((symbol, trade_date))
        if factor is None:
            rows_missing_factor += 1
            results.append(
                {
                    "security_id": row.get("security_id"),
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "source_id": row.get("source_id"),
                    "status": "missing_factor",
                    "reasons": ["usable_factor_not_found"],
                    **_empty_adjusted_values(),
                }
            )
            continue

        adjusted = adjust_ohlc(
            row.get("open"),
            row.get("high"),
            row.get("low"),
            row.get("close"),
            factor.factor,
        )
        if adjusted["status"] != "ok":
            rows_invalid += 1
            results.append(
                {
                    "security_id": row.get("security_id"),
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "source_id": row.get("source_id"),
                    "status": "invalid",
                    "factor": factor.factor,
                    "reasons": adjusted["reasons"],
                    **_empty_adjusted_values(),
                }
            )
            continue

        rows_with_usable_factor += 1
        results.append(
            {
                "security_id": row.get("security_id"),
                "symbol": symbol,
                "trade_date": trade_date,
                "source_id": row.get("source_id"),
                "status": "ready",
                "factor": factor.factor,
                "factor_source_id": factor.source_id,
                "factor_raw_path": factor.raw_path,
                "reasons": [],
                "adjusted_open": adjusted["adjusted_open"],
                "adjusted_high": adjusted["adjusted_high"],
                "adjusted_low": adjusted["adjusted_low"],
                "adjusted_close": adjusted["adjusted_close"],
            }
        )

    symbols = sorted({_normalize_symbol(row.get("symbol")) for row in rows if _normalize_symbol(row.get("symbol"))})
    return {
        "status": "ok",
        "symbols": symbols,
        "total_rows_considered": len(rows),
        "rows_with_usable_factor": rows_with_usable_factor,
        "rows_missing_factor": rows_missing_factor,
        "rows_invalid": rows_invalid,
        "invalid_factor_records": len(invalid_factor_records),
        "results": results,
        "caveats": [
            "Local verified factor records only.",
            "No factor=1 fallback is used.",
            "Raw OHLC values are not changed.",
        ],
    }


def apply_adjustment_factors_to_db(
    db_path: str | Path,
    factor_path: str | Path,
    symbols: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    path = Path(db_path)
    requested_symbols = _normalize_symbols(symbols or [])
    if not requested_symbols:
        return _error_summary("invalid_request", "At least one explicit symbol is required.", requested_symbols, dry_run)
    if not path.exists():
        return _error_summary("missing_store", f"DB not found: {path}", requested_symbols, dry_run)

    try:
        factors = load_adjustment_factor_records(factor_path)
    except FileNotFoundError:
        return _error_summary("missing_factor_file", f"Factor file not found: {factor_path}", requested_symbols, dry_run)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return _error_summary("invalid_factor_json", f"Invalid factor file: {exc}", requested_symbols, dry_run)

    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        rows = _load_daily_price_rows(con, requested_symbols)
        row_result = apply_adjustment_factors_to_rows([dict(row) for row in rows], factors)
        rows_updated = 0
        if not dry_run:
            rows_updated = _update_adjusted_columns(con, row_result["results"])
            con.commit()
    return {
        **{key: value for key, value in row_result.items() if key != "results"},
        "db_path": str(path),
        "factor_path": str(factor_path),
        "dry_run": bool(dry_run),
        "db_mutation_made": bool(rows_updated),
        "rows_updated": rows_updated,
        "results": row_result["results"],
    }


def _load_daily_price_rows(con: sqlite3.Connection, symbols: list[str]) -> list[sqlite3.Row]:
    where = ""
    params: list[str] = []
    if symbols:
        placeholders = ", ".join(["?"] * len(symbols))
        where = f"WHERE symbol IN ({placeholders})"
        params.extend(symbols)
    return con.execute(
        f"""
        SELECT security_id, symbol, trade_date, open, high, low, close, source_id
        FROM daily_prices
        {where}
        ORDER BY symbol, trade_date, security_id, source_id
        """,
        params,
    ).fetchall()


def _update_adjusted_columns(con: sqlite3.Connection, results: Iterable[dict[str, Any]]) -> int:
    updated = 0
    for item in results:
        if item["status"] != "ready":
            continue
        con.execute(
            """
            UPDATE daily_prices
            SET
                adjustment_factor = ?,
                adjusted_open = ?,
                adjusted_high = ?,
                adjusted_low = ?,
                adjusted_close = ?,
                adjustment_status = ?
            WHERE security_id = ? AND symbol = ? AND trade_date = ? AND source_id = ?
            """,
            (
                item["factor"],
                item["adjusted_open"],
                item["adjusted_high"],
                item["adjusted_low"],
                item["adjusted_close"],
                "adjusted",
                item["security_id"],
                item["symbol"],
                item["trade_date"],
                item["source_id"],
            ),
        )
        updated += con.total_changes - updated
    return updated


def _usable_factor_map(records: list[AdjustmentFactorRecord]) -> dict[tuple[str, str], AdjustmentFactorRecord]:
    usable: dict[tuple[str, str], AdjustmentFactorRecord] = {}
    for record in records:
        if not _is_usable_factor(record):
            continue
        usable[(record.symbol, record.trade_date)] = record
    return usable


def _is_usable_factor(record: AdjustmentFactorRecord) -> bool:
    return (
        record.status == "ok"
        and record.factor is not None
        and record.factor > 0
        and bool(record.source_id)
        and bool(record.raw_path)
        and bool(record.symbol)
        and bool(record.trade_date)
    )


def _error_summary(status: str, reason: str, symbols: list[str], dry_run: bool) -> dict[str, Any]:
    return {
        "status": status,
        "symbols": symbols,
        "total_rows_considered": 0,
        "rows_with_usable_factor": 0,
        "rows_missing_factor": 0,
        "rows_invalid": 0,
        "invalid_factor_records": 0,
        "rows_updated": 0,
        "dry_run": bool(dry_run),
        "db_mutation_made": False,
        "reasons": [reason],
        "caveats": ["No DB mutation was made."],
    }


def _empty_adjusted_values() -> dict[str, None]:
    return {
        "adjusted_open": None,
        "adjusted_high": None,
        "adjusted_low": None,
        "adjusted_close": None,
    }


def _normalize_symbols(values: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for value in values:
        symbol = _normalize_symbol(value)
        if symbol and symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    return normalized


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()
