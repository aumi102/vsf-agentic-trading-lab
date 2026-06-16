from __future__ import annotations

from pathlib import Path

from trading_agent.tools._store import DEFAULT_DB_PATH, connect_readonly, row_to_dict


def evaluate_active_signals(symbol: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, object]:
    normalized = symbol.strip().upper()
    try:
        with connect_readonly(db_path) as con:
            row = con.execute(
                """
                SELECT symbol, as_of_date, strategy_id, action, score, reason_code,
                       reason_text, signal_version, quality_status
                FROM signals
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
        return {"status": "not_found", "symbol": normalized, "caveats": ["Signal not found in MVP store."]}
    caveats = []
    if data["quality_status"] == "warn":
        caveats.append("Signal quality is warning-level; inspect lookback and data caveats.")
    return {
        "status": "ok",
        "symbol": normalized,
        "as_of_date": data["as_of_date"],
        "strategy_id": data["strategy_id"],
        "action": data["action"],
        "score": data["score"],
        "reason_codes": [data["reason_code"]],
        "reason_text": data["reason_text"],
        "signal_version": data["signal_version"],
        "quality_status": data["quality_status"],
        "caveats": caveats,
    }
