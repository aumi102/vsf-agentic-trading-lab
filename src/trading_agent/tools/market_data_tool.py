from __future__ import annotations

from pathlib import Path

from trading_agent.tools._store import DEFAULT_DB_PATH, connect_readonly, row_to_dict


def get_latest_market_data(symbol: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, object]:
    normalized = symbol.strip().upper()
    try:
        with connect_readonly(db_path) as con:
            row = con.execute(
                """
                SELECT symbol, trade_date, open, high, low, close, volume, value,
                       source_id, raw_path, quality_status, price_basis, adjustment_status
                FROM daily_prices
                WHERE symbol = ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
    except FileNotFoundError as exc:
        return {"status": "error", "symbol": normalized, "caveats": [str(exc)]}
    data = row_to_dict(row)
    if data is None:
        return {"status": "not_found", "symbol": normalized, "caveats": ["Symbol not found in MVP store."]}
    caveats = []
    if data.get("adjustment_status") == "unknown":
        caveats.append("Adjustment/corporate-action basis is unknown.")
    return {
        "status": "ok",
        "symbol": normalized,
        "latest_date": data["trade_date"],
        "ohlcv": {
            "open": data["open"],
            "high": data["high"],
            "low": data["low"],
            "close": data["close"],
            "volume": data["volume"],
            "value": data["value"],
        },
        "source_id": data["source_id"],
        "raw_path": data["raw_path"],
        "quality_status": data["quality_status"],
        "price_basis": data["price_basis"],
        "adjustment_status": data["adjustment_status"],
        "caveats": caveats,
    }
