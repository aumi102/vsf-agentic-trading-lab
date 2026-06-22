"""Read-only status report for the QuestDB market and derived tables."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.storage import questdb_client as qdb  # noqa: E402

KNOWN_TABLES = (
    "daily_prices",
    "securities",
    "feature_snapshots",
    "signals",
    "backtest_runs",
    "backtest_metrics",
)
DATE_COLUMNS = {
    "daily_prices": "trade_date",
    "securities": "last_trade_date",
    "feature_snapshots": "trade_date",
    "signals": "trade_date",
    "backtest_runs": "created_at",
    "backtest_metrics": "created_at",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Show QuestDB table coverage.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    args = parser.parse_args()
    base_url = args.questdb_url.rstrip("/")
    with qdb.open_client() as client:
        _, rows = qdb.exec_rows(client, base_url, "SHOW TABLES")
        existing = [str(row[0]) for row in rows if row]
        print(f"questdb_url : {base_url}")
        print("tables      : " + (", ".join(existing) if existing else "(none)"))
        print("\ncoverage:")
        for table in KNOWN_TABLES:
            if table not in existing:
                print(f"  {table:<20} missing")
                continue
            columns = set(qdb.column_names(client, base_url, table))
            total = int(qdb.exec_scalar(client, base_url, f"SELECT count() FROM {table}", 0))
            symbols = "n/a"
            if "symbol" in columns:
                symbols = f"{int(qdb.exec_scalar(client, base_url, f'SELECT count_distinct(symbol) FROM {table}', 0)):,}"
            latest = "n/a"
            date_column = DATE_COLUMNS.get(table)
            if date_column in columns:
                value = qdb.exec_scalar(client, base_url, f"SELECT max({date_column}) FROM {table}", None)
                latest = str(value)[:10] if value is not None else "null"
            print(f"  {table:<20} rows={total:>10,}  symbols={symbols:>6}  latest={latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
