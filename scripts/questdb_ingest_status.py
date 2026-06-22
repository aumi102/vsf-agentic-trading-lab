"""Lightweight QuestDB ingestion status / health snapshot.

  python scripts/questdb_ingest_status.py
  python scripts/questdb_ingest_status.py --table daily_prices --questdb-url http://localhost:9000

Read-only. Prints table existence, row + distinct-symbol counts, top-20 symbols,
last-20 checkpointed symbols, adjustment_status / quality_status breakdowns,
WAL suspended state, and whether the >3M-row target has been reached.
"""
from __future__ import annotations

import argparse
import sys
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

CHECKPOINT_DIR = ROOT / "data/cache/vietcap/checkpoints"
TARGET_ROWS = 3_000_000


def last_checkpointed(n: int = 20) -> list[str]:
    files = sorted(CHECKPOINT_DIR.glob("run_id=*/completed_symbols.txt"), key=lambda p: p.stat().st_mtime)
    collected: list[str] = []
    for path in files:
        collected.extend(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return collected[-n:]


def main() -> int:
    p = argparse.ArgumentParser(description="QuestDB ingestion status snapshot.")
    p.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    p.add_argument("--table", default="daily_prices")
    args = p.parse_args()
    base = args.questdb_url.rstrip("/")

    with qdb.open_client() as client:
        if qdb.exec_scalar(client, base, "SELECT 1", None) != 1:
            print("ERROR: QuestDB did not answer SELECT 1.", file=sys.stderr)
            return 1
        exists = qdb.table_exists(client, base, args.table)
        print(f"questdb_url        : {base}")
        print(f"table              : {args.table}")
        print(f"table_exists       : {exists}")
        if not exists:
            print("No table yet. Run the ingest first.")
            return 0

        total = int(qdb.exec_scalar(client, base, f"SELECT count() FROM {args.table}", 0))
        distinct = int(qdb.exec_scalar(client, base, f"SELECT count_distinct(symbol) FROM {args.table}", 0))
        _, rng = qdb.exec_rows(client, base, f"SELECT min(trade_date), max(trade_date) FROM {args.table}")
        first_dt = str(rng[0][0])[:10] if rng and rng[0] else None
        last_dt = str(rng[0][1])[:10] if rng and rng[0] else None

        _, wal = qdb.exec_rows(client, base, f"SELECT suspended, writerTxn, sequencerTxn FROM wal_tables() WHERE name='{args.table}'")
        suspended = wal[0][0] if wal and wal[0] else None
        caught_up = (wal and wal[0] and wal[0][1] == wal[0][2])

        print(f"row_count          : {total:,}")
        print(f"distinct_symbols   : {distinct:,}")
        print(f"date_range         : {first_dt} .. {last_dt}")
        print(f"wal_suspended      : {suspended}")
        print(f"wal_caught_up      : {caught_up}")
        print(f"target_rows        : {TARGET_ROWS:,}")
        print(f"target_3M_reached  : {total >= TARGET_ROWS}")
        print(f"universe_target    : ~1597 tradable tickers")

        print("\nadjustment_status breakdown:")
        _, adj = qdb.exec_rows(client, base, f"SELECT adjustment_status, count() FROM {args.table} ORDER BY 2 DESC")
        for row in adj:
            print(f"  {row[0]:<32} {int(row[1]):,}")

        print("\nquality_status breakdown:")
        _, ql = qdb.exec_rows(client, base, f"SELECT quality_status, count() FROM {args.table} ORDER BY 2 DESC")
        for row in ql:
            print(f"  {row[0]:<32} {int(row[1]):,}")

        print("\ntop 20 symbols by row count:")
        _, top = qdb.exec_rows(client, base, f"SELECT symbol, count() c FROM {args.table} ORDER BY c DESC LIMIT 20")
        for row in top:
            print(f"  {row[0]:<8} {int(row[1]):,}")

    recent = last_checkpointed(20)
    print(f"\nlast {len(recent)} checkpointed symbols (most recent first):")
    print("  " + ", ".join(reversed(recent)) if recent else "  (no checkpoint files found)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
