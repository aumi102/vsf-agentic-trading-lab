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

FA_FACT_TABLES = ["fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes"]
FA_TABLES = FA_FACT_TABLES + ["fa_raw_payloads", "fa_ingest_runs"]


def _print_run_status(client, base: str, existing: set[str]) -> None:
    if "fa_ingest_runs" not in existing:
        print("fa_ingest_runs: missing")
        return
    total = int(qdb.exec_scalar(client, base, "SELECT count() FROM fa_ingest_runs", 0))
    print(f"fa_ingest_runs: rows={total:,}")
    _, status_rows = qdb.exec_rows(client, base, "SELECT status, count() c FROM fa_ingest_runs ORDER BY c DESC")
    print("  status=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in status_rows))
    _, latest = qdb.exec_rows(
        client,
        base,
        "SELECT created_at, run_id, status, replace_mode, symbols_processed, raw_payload_rows, "
        "fa_balance_sheet_rows, fa_income_statement_rows, fa_cash_flow_rows, fa_notes_rows, failure_count "
        "FROM fa_ingest_runs ORDER BY created_at DESC LIMIT 1",
    )
    if latest:
        row = latest[0]
        print(
            "  latest_run="
            f"created_at={row[0]} run_id={row[1]} status={row[2]} replace_mode={row[3]} "
            f"symbols_processed={int(row[4]) if row[4] is not None else 0} raw_payload_rows={int(row[5]) if row[5] is not None else 0} "
            f"bs={int(row[6]) if row[6] is not None else 0} is={int(row[7]) if row[7] is not None else 0} "
            f"cf={int(row[8]) if row[8] is not None else 0} notes={int(row[9]) if row[9] is not None else 0} "
            f"failure_count={int(row[10]) if row[10] is not None else 0}"
        )
    _, complete = qdb.exec_rows(
        client,
        base,
        "SELECT created_at, run_id, replace_mode, symbols_processed, failure_count "
        "FROM fa_ingest_runs WHERE status = 'complete' ORDER BY created_at DESC LIMIT 1",
    )
    if complete:
        row = complete[0]
        print(
            "  latest_complete_run="
            f"created_at={row[0]} run_id={row[1]} replace_mode={row[2]} "
            f"symbols_processed={int(row[3]) if row[3] is not None else 0} failure_count={int(row[4]) if row[4] is not None else 0}"
        )
    else:
        print("  latest_complete_run=none")


def _print_run_counts(client, base: str, table: str, columns: set[str]) -> None:
    if "run_id" not in columns:
        return
    _, run_counts = qdb.exec_rows(client, base, f"SELECT run_id, count() c FROM {table} ORDER BY c DESC LIMIT 5")
    print("  run_id_rows=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in run_counts))


def main() -> int:
    parser = argparse.ArgumentParser(description="Show QuestDB FA table status.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    args = parser.parse_args()
    base = args.questdb_url.rstrip("/")
    with qdb.open_client() as client:
        _, table_rows = qdb.exec_rows(client, base, "SHOW TABLES")
        existing = {str(row[0]) for row in table_rows if row}
        print("tables_present=" + ",".join(t for t in FA_TABLES if t in existing))
        _print_run_status(client, base, existing)
        for table in FA_TABLES:
            if table == "fa_ingest_runs":
                continue
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
            _print_run_counts(client, base, table, columns)
            if "symbol" in columns:
                _, top = qdb.exec_rows(client, base, f"SELECT symbol, count() c FROM {table} ORDER BY c DESC LIMIT 5")
                print("  top_symbols=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
