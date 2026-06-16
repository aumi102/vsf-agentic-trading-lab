from __future__ import annotations

from pathlib import Path

from trading_agent.tools._store import DEFAULT_DB_PATH, connect_readonly, row_to_dict


def compute_latest_features(symbol: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, object]:
    normalized = symbol.strip().upper()
    try:
        with connect_readonly(db_path) as con:
            row = con.execute(
                """
                SELECT symbol, as_of_date, return_1d, return_5d, return_20d,
                       ma_20, ma_50, volatility_20d, volume_ratio_20d,
                       feature_version, lookback_coverage, quality_status
                FROM feature_snapshots
                WHERE symbol = ?
                ORDER BY as_of_date DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
    except FileNotFoundError as exc:
        return {"status": "error", "symbol": normalized, "caveats": [str(exc)]}
    data = row_to_dict(row)
    if data is None:
        return {"status": "not_found", "symbol": normalized, "caveats": ["Features not found in MVP store."]}
    caveats = []
    if int(data["lookback_coverage"]) < 50:
        caveats.append("Insufficient lookback for MA50-based signal.")
    return {
        "status": "ok",
        "symbol": normalized,
        "as_of_date": data["as_of_date"],
        "features": {
            "return_1d": data["return_1d"],
            "return_5d": data["return_5d"],
            "return_20d": data["return_20d"],
            "ma_20": data["ma_20"],
            "ma_50": data["ma_50"],
            "volatility_20d": data["volatility_20d"],
            "volume_ratio_20d": data["volume_ratio_20d"],
        },
        "feature_version": data["feature_version"],
        "lookback_coverage": data["lookback_coverage"],
        "quality_status": data["quality_status"],
        "caveats": caveats,
    }
