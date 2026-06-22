"""Benchmark common QuestDB query patterns on `daily_prices`.

  python scripts/benchmark_questdb_daily_prices.py
  python scripts/benchmark_questdb_daily_prices.py --symbol FPT --repeat 3

Prints elapsed milliseconds (best of N repeats) for each query so we can show,
with evidence, whether QuestDB is actually slow. Read-only.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from trading_agent.storage import questdb_client as qdb  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark QuestDB daily_prices queries.")
    p.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    p.add_argument("--table", default="daily_prices")
    p.add_argument("--symbol", default="FPT")
    p.add_argument("--repeat", type=int, default=3, help="Repeat each query N times; report best (warm) ms.")
    args = p.parse_args()
    base = args.questdb_url.rstrip("/")
    t = args.table
    sym = args.symbol.strip().upper()

    queries = [
        ("count_all", f"SELECT count() FROM {t}"),
        ("count_distinct_symbol", f"SELECT count_distinct(symbol) FROM {t}"),
        ("latest_one_symbol",
         f"SELECT * FROM {t} WHERE symbol='{sym}' ORDER BY trade_date DESC LIMIT 5"),
        ("range_one_symbol",
         f"SELECT trade_date, adjusted_close, volume FROM {t} WHERE symbol='{sym}' "
         f"AND trade_date BETWEEN '2020-01-01T00:00:00.000000Z' AND '2025-12-31T00:00:00.000000Z'"),
        ("aggregate_symbols",
         f"SELECT symbol, count() FROM {t} ORDER BY symbol LIMIT 50"),
    ]

    with qdb.open_client(timeout_seconds=120) as client:
        if qdb.exec_scalar(client, base, "SELECT 1", None) != 1:
            print("ERROR: QuestDB did not answer SELECT 1.", file=sys.stderr)
            return 1
        total = int(qdb.exec_scalar(client, base, f"SELECT count() FROM {t}", 0))
        print(f"QuestDB benchmark on {base}  table={t}  rows={total:,}  symbol={sym}  repeat={args.repeat}")
        print(f"{'query':<24} {'best_ms':>10} {'rows':>8}")
        print("-" * 46)
        for name, sql in queries:
            best_ms = float("inf")
            rowcount = 0
            for _ in range(max(1, args.repeat)):
                t0 = time.perf_counter()
                _, dataset = qdb.exec_rows(client, base, sql)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                best_ms = min(best_ms, elapsed_ms)
                rowcount = len(dataset)
            print(f"{name:<24} {best_ms:>10.1f} {rowcount:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
