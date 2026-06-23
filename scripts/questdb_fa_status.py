"""Read-only QuestDB financial-report table status."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.storage import questdb_client as qdb  # noqa: E402

FA_TABLES = ["fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes", "fa_raw_payloads"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Show QuestDB FA table status.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    args = parser.parse_args()
    base = args.questdb_url.rstrip("/")
    with qdb.open_client() as client:
        _, table_rows = qdb.exec_rows(client, base, "SHOW TABLES")
        existing = {str(row[0]) for row in table_rows if row}
        print("tables_present=" + ",".join(t for t in FA_TABLES if t in existing))
        for table in FA_TABLES:
            if table not in existing:
                print(f"{table}: missing")
                continue
            columns = set(qdb.column_names(client, base, table))
            total = int(qdb.exec_scalar(client, base, f"SELECT count() FROM {table}", 0))
            symbols = int(qdb.exec_scalar(client, base, f"SELECT count_distinct(symbol) FROM {table}", 0)) if "symbol" in columns else 0
            date_col = "public_date" if "public_date" in columns else "crawled_at"
            _, dr = qdb.exec_rows(client, base, f"SELECT min({date_col}), max({date_col}) FROM {table}")
            first = str(dr[0][0])[:10] if dr and dr[0] else ""
            last = str(dr[0][1])[:10] if dr and dr[0] else ""
            print(f"{table}: rows={total:,} symbols={symbols:,} {date_col}_range={first}..{last}")
            if "quality_status" in columns:
                _, qs = qdb.exec_rows(client, base, f"SELECT quality_status, count() c FROM {table} ORDER BY c DESC")
                print("  quality_status=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in qs))
            if "symbol" in columns:
                _, top = qdb.exec_rows(client, base, f"SELECT symbol, count() c FROM {table} ORDER BY c DESC LIMIT 5")
                print("  top_symbols=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
