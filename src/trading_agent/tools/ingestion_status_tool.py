from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.ingestion.status import get_ingestion_status
from trading_agent.tools._store import DEFAULT_DB_PATH


def inspect_ingestion_status(
    symbols: list[str] | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    return get_ingestion_status(db_path=db_path, symbols=symbols)
