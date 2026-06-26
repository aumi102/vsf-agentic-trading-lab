"""Read-only Vietcap FA coverage summary across QuestDB.

Reports:
- securities count
- symbols with balance sheet / income statement / cash flow / notes
- symbols with all 4 statement families
- latest complete + latest in-progress FA run id
- latest run processed/success/failure counts when available
- top missing symbols
- FPT/VHM/VCB/CTG/HPG/VNM status
- row counts by statement family
- status: PASS / WARN / FAIL

Usage:
  python scripts/questdb_fa_coverage.py
  python scripts/questdb_fa_coverage.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(SRC), str(ROOT / "scripts"), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from trading_agent.storage import questdb_client as qdb  # noqa: E402

IMPORTANT_SYMBOLS = ("FPT", "VHM", "VCB", "CTG", "HPG", "VNM")
FACT_TABLES = ("fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes")


def _table_exists(client, base_url: str, table: str) -> bool:
    _, rows = qdb.exec_rows(client, base_url, "SHOW TABLES")
    return table in {str(row[0]) for row in rows if row}


def _count(client, base_url: str, sql: str) -> int:
    try:
        return int(qdb.exec_scalar(client, base_url, sql, 0))
    except Exception:
        return 0


def _scalar(client, base_url: str, sql: str, default=None):
    try:
        v = qdb.exec_scalar(client, base_url, sql, default)
        return v if v not in (None, "") else default
    except Exception:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Vietcap FA coverage summary.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    parser.add_argument("--top-missing", type=int, default=20)
    args = parser.parse_args()
    base_url = args.questdb_url.rstrip("/")

    summary: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "questdb_url": base_url,
    }

    with qdb.open_client(timeout_seconds=60.0) as client:
        # Base: total securities.
        summary["securities_count"] = _count(client, base_url, "SELECT count_distinct(symbol) FROM securities")

        # Per-table row counts and covered-symbol counts.
        per_table: dict = {}
        table_present: dict = {}
        for t in FACT_TABLES:
            present = _table_exists(client, base_url, t)
            table_present[t] = present
            if not present:
                per_table[t] = {"present": False, "row_count": 0, "symbol_count": 0}
                continue
            rows = _count(client, base_url, f"SELECT count() FROM {t}")
            syms = _count(client, base_url, f"SELECT count_distinct(symbol) FROM {t}")
            per_table[t] = {"present": True, "row_count": rows, "symbol_count": syms}
        summary["per_table"] = per_table
        summary["tables_present"] = table_present

        # All-4 coverage: intersect symbols across the four statement families.
        all_four = None
        for t in FACT_TABLES:
            if not table_present.get(t):
                all_four = set()
                continue
            _, rows = qdb.exec_rows(client, base_url, f"SELECT DISTINCT symbol FROM {t}")
            syms = {str(r[0]).upper() for r in rows if r and r[0]}
            all_four = syms if all_four is None else (all_four & syms)
        summary["all_four_symbol_count"] = len(all_four or set())

        # Latest complete + latest in-progress run ids (full-universe scope).
        latest_complete = None
        latest_in_progress = None
        if _table_exists(client, base_url, "fa_ingest_runs"):
            v = _scalar(client, base_url,
                        "SELECT run_id FROM fa_ingest_runs WHERE scope = 'full_universe' AND status = 'complete' "
                        "ORDER BY created_at DESC LIMIT 1", "")
            latest_complete = str(v) if v else None
            v = _scalar(client, base_url,
                        "SELECT run_id FROM fa_ingest_runs WHERE scope = 'full_universe' AND status = 'in_progress' "
                        "ORDER BY created_at DESC LIMIT 1", "")
            latest_in_progress = str(v) if v else None
        summary["latest_complete_run_id"] = latest_complete
        summary["latest_in_progress_run_id"] = latest_in_progress

        # Latest run row (any scope) for processed/success/failure counts.
        latest_run_summary: dict = {}
        if _table_exists(client, base_url, "fa_ingest_runs"):
            v = _scalar(client, base_url, "SELECT run_id FROM fa_ingest_runs ORDER BY created_at DESC LIMIT 1", "")
            latest_run_id = str(v) if v else None
            if latest_run_id:
                cols, rows = qdb.exec_rows(
                    client, base_url,
                    f"SELECT symbols_processed, failure_count, fa_balance_sheet_rows, fa_income_statement_rows, "
                    f"fa_cash_flow_rows, fa_notes_rows, raw_payload_rows FROM fa_ingest_runs "
                    f"WHERE run_id = '{latest_run_id}' ORDER BY created_at DESC LIMIT 1",
                )
                if rows:
                    r = rows[0]
                    latest_run_summary = {
                        "run_id": latest_run_id,
                        "symbols_processed": r[0] if len(r) > 0 else None,
                        "failure_count": r[1] if len(r) > 1 else None,
                        "fa_balance_sheet_rows": r[2] if len(r) > 2 else None,
                        "fa_income_statement_rows": r[3] if len(r) > 3 else None,
                        "fa_cash_flow_rows": r[4] if len(r) > 4 else None,
                        "fa_notes_rows": r[5] if len(r) > 5 else None,
                        "raw_payload_rows": r[6] if len(r) > 6 else None,
                    }
        summary["latest_run"] = latest_run_summary

        # Important symbols: status = covered if present in fa_balance_sheet.
        important: dict = {}
        if table_present.get("fa_balance_sheet"):
            _, rows = qdb.exec_rows(
                client, base_url,
                "SELECT symbol, cast(count() as long) FROM fa_balance_sheet WHERE symbol IN ("
                + ",".join(f"'{s}'" for s in IMPORTANT_SYMBOLS)
                + ") GROUP BY symbol",
            )
            counts = {str(r[0]).upper(): int(r[1]) for r in rows if r and r[0]}
        else:
            counts = {}
        for s in IMPORTANT_SYMBOLS:
            important[s] = {
                "covered_in_fa_balance_sheet": s in counts,
                "row_count": counts.get(s, 0),
            }
        summary["important_symbols"] = important

        # Top missing: difference between securities and all_four coverage.
        missing: list[str] = []
        if _table_exists(client, base_url, "securities"):
            _, rows = qdb.exec_rows(client, base_url, "SELECT DISTINCT symbol FROM securities ORDER BY symbol")
            all_secs = [str(r[0]).upper() for r in rows if r and r[0]]
            missing = [s for s in all_secs if s not in (all_four or set())][: args.top_missing]
        summary["top_missing_symbols"] = missing
        summary["missing_count"] = len(missing) if missing else max(
            0, (summary["securities_count"] or 0) - (summary["all_four_symbol_count"] or 0)
        )

    # Status: FAIL if any FA table missing, WARN if important symbols missing, PASS otherwise.
    if not all(table_present.get(t) for t in FACT_TABLES):
        status = "FAIL"
        next_action = "Create the missing FA tables (use scripts/ingest_vietcap_financial_reports_to_questdb.py --ensure-tables) and re-run."
    elif not all(important[s]["covered_in_fa_balance_sheet"] for s in ("FPT", "VCB")):
        # FPT and VCB are the historical smoke baseline; if either is missing, FA is regressed.
        status = "WARN"
        next_action = "Re-run the full-universe ingester with --only-missing --resume to recover the baseline (FPT/VCB) coverage."
    elif not all(important[s]["covered_in_fa_balance_sheet"] for s in IMPORTANT_SYMBOLS):
        status = "WARN"
        missing_important = [s for s in IMPORTANT_SYMBOLS if not important[s]["covered_in_fa_balance_sheet"]]
        next_action = f"Important symbols not yet covered in FA: {', '.join(missing_important)}. Run scripts/batch_ingest_vietcap_fa_full_universe.py --only-missing --resume to extend coverage."
    elif summary["missing_count"] > (summary["securities_count"] or 0) * 0.5:
        status = "WARN"
        next_action = "Less than half of the tradable universe is covered. Continue the full-universe ingester with --only-missing --resume."
    else:
        status = "PASS"
        next_action = "FA coverage is at a usable level. Re-run periodically to capture new periods."

    summary["status"] = status
    summary["next_action"] = next_action

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        _print_human(summary)
    return summary


def _print_human(s: dict) -> None:
    print("=" * 70)
    print("QuestDB FA coverage summary")
    print("=" * 70)
    print(f"  generated_at          : {s['generated_at']}")
    print(f"  questdb_url           : {s['questdb_url']}")
    print(f"  securities_count      : {s['securities_count']}")
    print(f"  all_four_symbol_count : {s['all_four_symbol_count']}")
    print(f"  missing_count         : {s['missing_count']}")
    print("  per_table:")
    for t, info in s["per_table"].items():
        print(f"    - {t:30s} present={info['present']!s:5s} rows={info['row_count']:>10d} symbols={info['symbol_count']:>5d}")
    print(f"  latest_complete_run_id   : {s['latest_complete_run_id']}")
    print(f"  latest_in_progress_run_id: {s['latest_in_progress_run_id']}")
    lr = s.get("latest_run") or {}
    if lr:
        print(f"  latest_run            : id={lr.get('run_id')} processed={lr.get('symbols_processed')} "
              f"failures={lr.get('failure_count')}")
    print("  important_symbols:")
    for sym, info in s["important_symbols"].items():
        flag = "OK" if info["covered_in_fa_balance_sheet"] else "MISS"
        print(f"    [{flag}] {sym:5s} bs_rows={info['row_count']:>8d}")
    miss = s.get("top_missing_symbols") or []
    if miss:
        preview = ",".join(miss[:20]) + ("..." if len(miss) > 20 else "")
        print(f"  top_missing_preview   : {preview}")
    print(f"  status                : {s['status']}")
    print(f"  next_action           : {s['next_action']}")


if __name__ == "__main__":
    summary = main()
    if isinstance(summary, int):
        raise SystemExit(summary)
    raise SystemExit(0)
