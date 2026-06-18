from __future__ import annotations

from pathlib import Path

from trading_agent.db.paths import DEFAULT_DB_PATH
from trading_agent.ingestion.adjusted_readiness import get_adjusted_ohlc_readiness


def check_adjusted_ohlc_readiness(
    symbols: list[str] | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    return get_adjusted_ohlc_readiness(
        db_path=db_path,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )
