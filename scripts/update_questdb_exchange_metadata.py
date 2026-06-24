"""Apply audited exchange metadata overrides to QuestDB `securities`.

This script is intentionally narrow: it updates only symbols listed in the
tracked config file and prints before/after evidence. It does not touch OHLCV,
feature, signal, FA, or backtest result tables.
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from trading_agent.backtest.slippage_guard import normalize_exchange  # noqa: E402
from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_CONFIG = ROOT / "configs" / "exchange_metadata_overrides.csv"
SUPPORTED_EXCHANGES = {"HOSE", "HSX", "HNX", "UPCOM", "UPC"}


@dataclass(frozen=True)
class OverrideRow:
    symbol: str
    exchange: str
    source: str
    confidence: str
    notes: str


def _sql_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _read_overrides(path: Path) -> list[OverrideRow]:
    rows: list[OverrideRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"symbol", "exchange", "source", "confidence", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"config missing required columns: {sorted(missing)}")
        for idx, raw in enumerate(reader, start=2):
            symbol = str(raw.get("symbol") or "").strip().upper()
            exchange_raw = str(raw.get("exchange") or "").strip().upper()
            exchange = normalize_exchange(exchange_raw)
            source = str(raw.get("source") or "").strip()
            confidence = str(raw.get("confidence") or "").strip()
            notes = str(raw.get("notes") or "").strip()
            if not symbol:
                raise ValueError(f"row {idx}: symbol is required")
            if exchange_raw not in SUPPORTED_EXCHANGES or exchange == "UNKNOWN":
                raise ValueError(f"row {idx}: unsupported exchange {exchange_raw!r}")
            if not source:
                raise ValueError(f"row {idx}: source is required")
            if not confidence:
                raise ValueError(f"row {idx}: confidence is required")
            rows.append(OverrideRow(symbol=symbol, exchange=exchange, source=source, confidence=confidence, notes=notes))
    duplicates = sorted({row.symbol for row in rows if sum(1 for other in rows if other.symbol == row.symbol) > 1})
    if duplicates:
        raise ValueError(f"duplicate symbols in config: {duplicates}")
    return rows


def _select_symbols(client: Any, base: str, symbols: list[str]) -> list[dict[str, Any]]:
    quoted = ",".join(_sql_quote(symbol) for symbol in symbols)
    sql = (
        "SELECT symbol, exchange, source_family, quality_status, updated_at "
        f"FROM securities WHERE symbol IN ({quoted}) ORDER BY symbol"
    )
    columns, rows = qdb.exec_rows(client, base, sql)
    return [dict(zip(columns, row)) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Update QuestDB securities.exchange from audited overrides.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    overrides = _read_overrides(config_path)
    symbols = [row.symbol for row in overrides]
    base = args.questdb_url.rstrip("/")

    with qdb.open_client(timeout_seconds=60.0) as client:
        before = _select_symbols(client, base, symbols)
        found = {str(row.get("symbol") or "").upper() for row in before}
        missing = [symbol for symbol in symbols if symbol not in found]
        if missing:
            print(f"missing_symbols={','.join(missing)}")
            print("status=failed")
            return 2

        print("before:")
        for row in before:
            print(f"  {row.get('symbol')}: exchange={row.get('exchange')} updated_at={row.get('updated_at')}")

        unsupported = 0
        updated = 0
        for row in overrides:
            if row.exchange not in {"HOSE", "HSX", "HNX", "UPCOM"}:
                unsupported += 1
                continue
            print(
                "override="
                f"symbol={row.symbol} exchange={row.exchange} source={row.source} "
                f"confidence={row.confidence} notes={row.notes}"
            )
            if not args.dry_run:
                qdb.exec_query(
                    client,
                    base,
                    "UPDATE securities "
                    f"SET exchange = {_sql_quote(row.exchange)}, updated_at = now() "
                    f"WHERE symbol = {_sql_quote(row.symbol)}",
                )
            updated += 1

        after = _select_symbols(client, base, symbols)
        print("after:")
        for row in after:
            print(f"  {row.get('symbol')}: exchange={row.get('exchange')} updated_at={row.get('updated_at')}")

    print(f"symbols_requested={len(symbols)}")
    print(f"symbols_found={len(symbols) - len(missing)}")
    print(f"symbols_updated={0 if args.dry_run else updated}")
    print(f"unsupported_exchange_count={unsupported}")
    print(f"missing_symbol_count={len(missing)}")
    print(f"dry_run={str(args.dry_run).lower()}")
    print("status=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
