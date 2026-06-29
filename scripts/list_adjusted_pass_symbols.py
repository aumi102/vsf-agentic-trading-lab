"""List approved/prototype adjusted symbols from adjusted_daily_prices.

Read-only. Queries QuestDB for symbols with source_backed_corporate_action rows.
Separates approved vs prototype (vnstock) sources.

Usage:
  python scripts/list_adjusted_pass_symbols.py --limit 100 --json
  python scripts/list_adjusted_pass_symbols.py --limit 100 --source-policy prototype_allowed --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for p in (str(ROOT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_agent.storage import questdb_client as qdb

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL


def _vnstock(source: str | None) -> bool:
    if not source:
        return False
    return "vnstock" in str(source).lower()


def list_adjusted_symbols(
    client, base_url: str,
    limit: int | None = None,
    source_policy: str = "approved_only",
) -> dict:
    """List symbols from adjusted_daily_prices, separated by source approval.

    source_policy:
      approved_only     -- vnstock rows NOT counted as approved pass
      prototype_allowed -- vnstock rows counted as prototype pass
    """
    _, tables = qdb.exec_rows(client, base_url, "SHOW TABLES")
    table_names = {str(r[0]) for r in tables if r}
    adj_exists = "adjusted_daily_prices" in table_names

    if not adj_exists:
        return {
            "status": "TABLE_MISSING",
            "approved_symbols": [],
            "prototype_symbols": [],
            "blocked_unapproved_symbols": [],
            "approved_count": 0,
            "prototype_count": 0,
            "blocked_unapproved_count": 0,
            "source_policy": source_policy,
        }

    limit_sql = f"LIMIT {limit}" if limit else ""
    # Get symbol + source for each symbol with source-backed rows
    sql = (
        f"SELECT symbol, adjustment_source, COUNT(*) as row_count, "
        f"MIN(trade_date) as first_date, MAX(trade_date) as last_date "
        f"FROM adjusted_daily_prices "
        f"WHERE adjustment_status = 'source_backed_corporate_action' "
        f"GROUP BY symbol, adjustment_source "
        f"ORDER BY symbol {limit_sql}"
    )
    _, rows = qdb.exec_rows(client, base_url, sql)

    approved_symbols = []
    prototype_symbols = []
    blocked_unapproved = []

    for r in rows:
        if not r or not r[0]:
            continue
        sym = str(r[0])
        adj_source = str(r[1]) if r[1] else None
        is_vnstock = _vnstock(adj_source)

        record = {
            "symbol": sym,
            "row_count": int(r[2]) if r[2] else 0,
            "first_date": str(r[3])[:10] if r[3] else None,
            "last_date": str(r[4])[:10] if r[4] else None,
            "adjustment_source": adj_source,
            "source_approval_status": (
                "PROTOTYPE_ONLY" if is_vnstock else "APPROVED"
            ),
        }

        if source_policy == "approved_only":
            if is_vnstock:
                blocked_unapproved.append(record)
            else:
                approved_symbols.append(record)
        else:  # prototype_allowed
            if is_vnstock:
                prototype_symbols.append(record)
            else:
                approved_symbols.append(record)

    # Count missing symbols (in daily_prices but in neither approved/prototype NOR blocked_unapproved).
    # blocked_unapproved symbols are KNOWN to have an vnstock source -- they are not missing,
    # they are explicitly blocked. Exclude them so buckets are disjoint.
    _, dp_rows = qdb.exec_rows(
        client, base_url,
        "SELECT DISTINCT symbol FROM daily_prices ORDER BY symbol"
    )
    all_symbols = {str(r[0]) for r in dp_rows if r}
    pass_set = {s["symbol"] for s in approved_symbols + prototype_symbols}
    blocked_set = {s["symbol"] for s in blocked_unapproved}
    missing = sorted(all_symbols - pass_set - blocked_set)

    return {
        "status": "OK",
        "approved_symbols": approved_symbols,
        "prototype_symbols": prototype_symbols,
        "blocked_unapproved_symbols": blocked_unapproved,
        "approved_count": len(approved_symbols),
        "prototype_count": len(prototype_symbols),
        "blocked_unapproved_count": len(blocked_unapproved),
        "missing_adjusted_source_count": len(missing),
        "missing_adjusted_source_symbols": missing,
        "source_policy": source_policy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List approved/prototype adjusted symbols from adjusted_daily_prices."
    )
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--limit", type=int, default=None, help="Max symbols to return")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--source-policy",
        choices=["approved_only", "prototype_allowed"],
        default="approved_only",
        help="approved_only: vnstock rows NOT counted as approved (default). "
             "prototype_allowed: vnstock rows counted as prototype.",
    )
    args = parser.parse_args()

    base_url = args.questdb_url.rstrip("/")
    with qdb.open_client(timeout_seconds=60.0) as client:
        result = list_adjusted_symbols(
            client, base_url, args.limit, source_policy=args.source_policy
        )

    if args.json:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        policy = result["source_policy"]
        print("=" * 62)
        print(f"  Adjusted symbol listing  |  source_policy={policy}")
        print("=" * 62)
        print(f"  Approved count : {result['approved_count']}")
        print(f"  Prototype count: {result['prototype_count']}")
        print(f"  Blocked (unapproved): {result['blocked_unapproved_count']}")
        print(f"  Missing source    : {result['missing_adjusted_source_count']}")
        if result["approved_symbols"]:
            print()
            print("  APPROVED symbols:")
            for s in result["approved_symbols"]:
                print(f"    {s['symbol']:<8} rows={s['row_count']:>5}  "
                      f"{s['first_date']} -> {s['last_date']}  source={s['adjustment_source']}")
        if result["prototype_symbols"]:
            print()
            print("  PROTOTYPE symbols (vnstock - not approved):")
            for s in result["prototype_symbols"]:
                print(f"    {s['symbol']:<8} rows={s['row_count']:>5}  "
                      f"{s['first_date']} -> {s['last_date']}  [PROTOTYPE]")
        if result["blocked_unapproved_symbols"]:
            print()
            print("  BLOCKED (vnstock, not approved under source_policy=approved_only):")
            for s in result["blocked_unapproved_symbols"]:
                print(f"    {s['symbol']:<8} rows={s['row_count']:>5}  [BLOCKED_UNAPPROVED]")
        if result["missing_adjusted_source_symbols"]:
            print()
            print(f"  Missing adjusted source ({len(result['missing_adjusted_source_symbols'])}): "
                  f"{', '.join(result['missing_adjusted_source_symbols'][:20])}"
                  f"{'...' if len(result['missing_adjusted_source_symbols']) > 20 else ''}")
        print("=" * 62)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
