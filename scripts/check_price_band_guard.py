"""Check slippage assumptions against exchange price-band metadata."""
from __future__ import annotations

import argparse
import sys
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

from trading_agent.backtest.slippage_guard import evaluate_price_band_guard  # noqa: E402
from trading_agent.storage import questdb_client as qdb  # noqa: E402


def _sql_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _parse_symbols(value: str) -> list[str]:
    symbols = [part.strip().upper() for part in value.split(",") if part.strip()]
    if not symbols:
        raise argparse.ArgumentTypeError("at least one symbol is required")
    return symbols


def _load_exchanges(url: str, symbols: list[str]) -> dict[str, str | None]:
    base = url.rstrip("/")
    quoted = ",".join(_sql_quote(symbol) for symbol in symbols)
    sql = f"SELECT symbol, exchange FROM securities WHERE symbol IN ({quoted})"
    exchanges: dict[str, str | None] = {symbol: None for symbol in symbols}
    with qdb.open_client(timeout_seconds=60.0) as client:
        columns, rows = qdb.exec_rows(client, base, sql)
    for row in rows:
        record: dict[str, Any] = dict(zip(columns, row))
        symbol = str(record.get("symbol") or "").upper()
        if symbol:
            exchanges[symbol] = record.get("exchange")
    return exchanges


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate slippage bps against exchange price bands.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--symbols", type=_parse_symbols, required=True)
    parser.add_argument("--slippage-bps", type=float, required=True)
    args = parser.parse_args()

    exchanges = _load_exchanges(args.questdb_url, args.symbols)
    failures = 0
    for symbol in args.symbols:
        exchange = exchanges.get(symbol)
        result = evaluate_price_band_guard(exchange, args.slippage_bps)
        ok = result.status == "price_band_guard_pass"
        if not ok:
            failures += 1
        print(
            f"{symbol}: status={result.status} exchange={result.exchange} "
            f"slippage_bps={result.slippage_bps} price_band_bps={result.price_band_bps} "
            f"caveats={';'.join(result.caveats)}"
        )
    print(f"overall_status={'PASS' if failures == 0 else 'FAIL'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
