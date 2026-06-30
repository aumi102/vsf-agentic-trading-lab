"""Read-only adjusted OHLCV readiness check against QuestDB daily_prices.

BLOCKED_ADJUSTED_FACTOR_FABRICATED -- adjustment_factor = 1.0 for ALL rows AND
                                     adjustment_status = 'adjusted_price_missing_warn'
PASS                             -- at least one row has adjustment_factor != 1.0 AND
                                     adjustment_status != 'adjusted_price_missing_warn'
BLOCKED_TABLE_MISSING           -- daily_prices table not found
BLOCKED_MISSING_COLUMNS         -- required columns absent
BLOCKED_NO_ROWS                -- no rows match filters
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for p in (str(ROOT / "src"), str(SCRIPT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL


def _sym_filter(symbols: list[str] | None, col: str = "symbol") -> str:
    if not symbols:
        return ""
    syms = ",".join(f"'{s.strip().upper()}'" for s in symbols if s.strip())
    return f" AND {col} IN ({syms})"


def _date_filter(start_date: str | None, end_date: str | None) -> str:
    f = ""
    if start_date:
        f += f" AND trade_date >= '{start_date}'"
    if end_date:
        f += f" AND trade_date <= '{end_date}'"
    return f


def _blocked_reason(symbol: str) -> str:
    return (
        f"No source-backed adjusted OHLC for {symbol}. "
        "daily_prices has adjustment_factor=1.0 and adjustment_status='adjusted_price_missing_warn' -- "
        "adjusted OHLC is fabricated (adj == raw). "
        "Corporate action source (vnstock company_events) not found for this symbol. "
        "Trading computation is BLOCKED for this symbol."
    )


def _vnstock_source(source: str | None) -> bool:
    if not source:
        return False
    return "vnstock" in str(source).lower()


def _per_symbol_status(
    client, base_url: str,
    symbols: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    source_policy: str = "approved_only",
) -> list[dict]:
    """Return per-symbol readiness: checks adjusted_daily_prices first, then daily_prices.

    source_policy:
      approved_only     -- vnstock-derived rows do NOT count as PASS
      prototype_allowed -- vnstock-derived rows count as PASS_PROTOTYPE with caveat
    """
    date_f = _date_filter(start_date, end_date)

    _, tables = qdb.exec_rows(client, base_url, "SHOW TABLES")
    table_names = {str(r[0]) for r in tables if r}
    adj_table_exists = "adjusted_daily_prices" in table_names

    result: list[dict] = []

    # Symbols requested — use requested list, not just what tables have
    if symbols:
        requested = symbols
    elif adj_table_exists:
        sql = f"SELECT DISTINCT symbol FROM adjusted_daily_prices ORDER BY symbol"
        _, rows = qdb.exec_rows(client, base_url, sql)
        requested = [str(r[0]) for r in rows if r]
    else:
        sql = f"SELECT DISTINCT symbol FROM daily_prices ORDER BY symbol"
        _, rows = qdb.exec_rows(client, base_url, sql)
        requested = [str(r[0]) for r in rows if r]

    for sym in requested:
        sym_f = f" AND symbol = '{sym}'"
        where = f"WHERE 1=1{sym_f}{date_f}"

        # Check adjusted_daily_prices for source-backed rows
        adj_status: str | None = None
        adj_total = 0
        adj_real = 0
        adj_invalid = 0
        adj_source: str | None = None
        is_vnstock = False
        if adj_table_exists:
            # Get source for this symbol
            src_sql = f"SELECT adjustment_source FROM adjusted_daily_prices {where} LIMIT 1"
            src_rows = qdb.exec_rows(client, base_url, src_sql)
            if src_rows[1]:
                adj_source = str(src_rows[1][0][0])
                is_vnstock = _vnstock_source(adj_source)

            cnt_sql = (
                f"SELECT COUNT(*) FROM adjusted_daily_prices {where} "
                f"AND adjustment_status = 'source_backed_corporate_action'"
            )
            adj_real = int(qdb.exec_scalar(client, base_url, cnt_sql) or 0)
            if adj_real > 0:
                total_sql = (
                    f"SELECT COUNT(*) FROM adjusted_daily_prices {where} "
                    f"AND adjustment_status = 'source_backed_corporate_action'"
                )
                adj_total = int(qdb.exec_scalar(client, base_url, total_sql) or 0)
                inv_sql = (
                    f"SELECT COUNT(*) FROM adjusted_daily_prices {where} "
                    f"AND adjustment_status = 'source_backed_corporate_action' "
                    f"AND (high < low OR high < 0 OR low < 0 OR close < 0)"
                )
                adj_invalid = int(qdb.exec_scalar(client, base_url, inv_sql) or 0)
                adj_status = "source_backed"

        if adj_status == "source_backed" and adj_real > 0 and adj_invalid == 0:
            # vnstock policy gate
            if is_vnstock and source_policy == "approved_only":
                result.append({
                    "symbol": sym,
                    "status": "BLOCKED_UNAPPROVED_SOURCE",
                    "backtest_gate": "blocked",
                    "source": "adjusted_daily_prices",
                    "row_count": adj_real,
                    "adjustment_source": adj_source,
                    "source_policy": source_policy,
                    "source_approval_status": "BLOCKED_UNAPPROVED_SOURCE",
                    "blocked_reason": (
                        f"vnstock-derived rows detected (adjustment_source='{adj_source}'). "
                        "vnstock is NOT an approved corporate action source. "
                        "Use --source-policy prototype_allowed or provide an approved source."
                    ),
                    "caveats": [
                        "vnstock is unapproved/prototype-only source. "
                        "Do NOT use these rows for official backtesting or trading decisions.",
                    ],
                })
                continue

            caveats = []
            if is_vnstock and source_policy == "prototype_allowed":
                caveats.append(
                    "vnstock is unapproved/prototype-only source. "
                    "Rows are marked PASS_PROTOTYPE -- not for production use."
                )
            result.append({
                "symbol": sym,
                "status": "PASS_PROTOTYPE" if is_vnstock else "PASS",
                "backtest_gate": "pass",
                "source": "adjusted_daily_prices",
                "row_count": adj_real,
                "adjustment_source": adj_source,
                "source_policy": source_policy,
                "source_approval_status": "APPROVED" if not is_vnstock else "PROTOTYPE_ONLY",
                "blocked_reason": None,
                "caveats": caveats,
            })
            continue

        # Fall back to daily_prices for this symbol
        total_sql = f"SELECT COUNT(*) FROM daily_prices {where}"
        total = int(qdb.exec_scalar(client, base_url, total_sql) or 0)
        warn_sql = (
            f"SELECT COUNT(*) FROM daily_prices {where} "
            f"AND adjustment_status = 'adjusted_price_missing_warn'"
        )
        warn = int(qdb.exec_scalar(client, base_url, warn_sql) or 0)
        real_sql = (
            f"SELECT COUNT(*) FROM daily_prices {where} "
            f"AND adjustment_factor IS NOT NULL AND adjustment_factor != 1.0"
        )
        real = int(qdb.exec_scalar(client, base_url, real_sql) or 0)

        if total == 0:
            result.append({
                "symbol": sym,
                "status": "BLOCKED",
                "backtest_gate": "blocked",
                "source": None,
                "row_count": 0,
                "adjustment_source": None,
                "source_policy": source_policy,
                "source_approval_status": "NO_SOURCE",
                "blocked_reason": f"No daily_prices rows for {sym}.",
                "caveats": [],
            })
        elif real > 0:
            result.append({
                "symbol": sym,
                "status": "PASS",
                "backtest_gate": "pass",
                "source": "daily_prices",
                "row_count": total,
                "adjustment_source": None,
                "source_policy": source_policy,
                "source_approval_status": "APPROVED",
                "blocked_reason": None,
                "caveats": [f"{real} rows have real adjustment factors."],
            })
        else:
            blocked_reason = _blocked_reason(sym)
            result.append({
                "symbol": sym,
                "status": "BLOCKED_ADJUSTED_SOURCE_MISSING",
                "backtest_gate": "blocked",
                "source": "daily_prices",
                "row_count": total,
                "adjustment_source": None,
                "source_policy": source_policy,
                "source_approval_status": "BLOCKED_APPROVED_ADJUSTED_SOURCE_MISSING",
                "blocked_reason": blocked_reason,
                "caveats": [
                    f"All {total} rows have adjustment_factor=1.0 and "
                    "adjustment_status='adjusted_price_missing_warn'.",
                ],
            })

    return result


def check_adjusted_readiness(
    client, base_url: str,
    symbols: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    source_policy: str = "approved_only",
) -> dict:
    sym_f = _sym_filter(symbols)
    date_f = _date_filter(start_date, end_date)
    where = f"WHERE 1=1{sym_f}{date_f}"

    # Table check
    _, tables = qdb.exec_rows(client, base_url, "SHOW TABLES")
    table_names = {str(r[0]) for r in tables if r}
    if "daily_prices" not in table_names:
        return _result(
            status="BLOCKED_TABLE_MISSING", backtest_gate="blocked",
            caveats=["daily_prices table not found in QuestDB."],
            by_symbol=[], symbols=[], coverage={},
        )

    # Column check -- LIMIT 0 returns column names as first element of each row
    cols, _ = qdb.exec_rows(client, base_url, "SELECT * FROM daily_prices LIMIT 0")
    col_names = {str(c) for c in cols} if cols else set()
    required = {"adjustment_factor", "adjusted_open", "adjusted_high", "adjusted_low",
                "adjusted_close", "adjustment_status", "close", "open", "high", "low", "symbol"}
    missing = required - col_names
    if missing:
        return _result(
            status="BLOCKED_MISSING_COLUMNS", backtest_gate="blocked",
            caveats=[f"Missing columns: {', '.join(sorted(missing))}."],
            by_symbol=[], symbols=[], coverage={},
        )

    # Per-symbol status — authoritative
    by_symbol = _per_symbol_status(client, base_url, symbols, start_date, end_date, source_policy)
    requested_syms = symbols or [s["symbol"] for s in by_symbol]

    # Global aggregate counts (daily_prices — raw coverage)
    total_sql = f"SELECT COUNT(*) FROM daily_prices {where}"
    total = int(qdb.exec_scalar(client, base_url, total_sql) or 0)
    warn_sql = (
        f"SELECT COUNT(*) FROM daily_prices {where} "
        f"AND adjustment_status = 'adjusted_price_missing_warn'"
    )
    warn_count = int(qdb.exec_scalar(client, base_url, warn_sql) or 0)
    real_sql = (
        f"SELECT COUNT(*) FROM daily_prices {where} "
        f"AND adjustment_factor IS NOT NULL AND adjustment_factor != 1.0"
    )
    real_count = int(qdb.exec_scalar(client, base_url, real_sql) or 0)

    # adjusted_daily_prices counts (source-backed)
    adj_table_exists = "adjusted_daily_prices" in table_names
    adj_real_count = 0
    adj_invalid_count = 0
    if adj_table_exists:
        adj_real_sql = (
            f"SELECT COUNT(*) FROM adjusted_daily_prices {where} "
            f"AND adjustment_status = 'source_backed_corporate_action'"
        )
        adj_real_count = int(qdb.exec_scalar(client, base_url, adj_real_sql) or 0)
        adj_invalid_sql = (
            f"SELECT COUNT(*) FROM adjusted_daily_prices {where} "
            f"AND adjustment_status = 'source_backed_corporate_action' "
            f"AND (high < low OR high < 0 OR low < 0 OR close < 0)"
        )
        adj_invalid_count = int(qdb.exec_scalar(client, base_url, adj_invalid_sql) or 0)

    # Overall status from per-symbol
    official_pass = [s for s in by_symbol if s["status"] == "PASS"]
    prototype_pass = [s for s in by_symbol if s["status"] == "PASS_PROTOTYPE"]
    blocked_unapproved = [s for s in by_symbol if s["status"] == "BLOCKED_UNAPPROVED_SOURCE"]
    blocked_missing = [s for s in by_symbol if s["status"] in (
        "BLOCKED", "BLOCKED_ADJUSTED_SOURCE_MISSING", "BLOCKED_TABLE_MISSING",
        "BLOCKED_MISSING_COLUMNS", "BLOCKED_NO_ROWS",
    )]
    all_blocked = blocked_unapproved + blocked_missing

    if not all_blocked:
        if prototype_pass and not official_pass:
            status = "PASS_PROTOTYPE"
            backtest_gate = "partial"
        elif official_pass and prototype_pass:
            status = "PARTIAL"
            backtest_gate = "partial"
        elif official_pass:
            status = "PASS"
            backtest_gate = "pass" if adj_invalid_count == 0 else "blocked"
        else:
            status = "BLOCKED_NO_APPROVED_SOURCE"
            backtest_gate = "blocked"
    elif not official_pass and not prototype_pass:
        if blocked_unapproved and not blocked_missing:
            status = "BLOCKED_UNAPPROVED_SOURCE"
            backtest_gate = "blocked"
        else:
            status = "BLOCKED_ADJUSTED_SOURCE_MISSING"
            backtest_gate = "blocked"
    else:
        status = "PARTIAL"
        backtest_gate = "partial"

    # Caveats
    caveats = []
    if total == 0:
        status = "BLOCKED_NO_ROWS"
        backtest_gate = "blocked"
        caveats.append("No daily_prices rows for the selected filters.")
    elif status == "PASS":
        caveats.append(
            f"{adj_real_count} source-backed adjusted rows found in adjusted_daily_prices "
            f"(adjustment_status='source_backed_corporate_action'). "
            f"{adj_invalid_count} rows have invalid OHLC."
        )
    elif status == "PASS_PROTOTYPE":
        caveats.append(
            f"{len(prototype_pass)} of {len(by_symbol)} symbols have prototype-only "
            f"adjusted OHLC (vnstock-derived). "
            f"source_policy={source_policy}. "
            "These rows are NOT approved for official trading/backtesting."
        )
    elif status == "BLOCKED_UNAPPROVED_SOURCE":
        caveats.append(
            f"All {len(blocked_unapproved)} symbols use vnstock as adjustment source. "
            f"vnstock is NOT approved under source_policy={source_policy}. "
            "Provide an approved corporate action source or use prototype_allowed."
        )
    elif status == "PARTIAL":
        caveats.append(
            f"{len(official_pass)} of {len(by_symbol)} symbols have APPROVED adjusted OHLC. "
            f"{len(prototype_pass)} symbols are prototype-only. "
            f"{len(all_blocked)} symbols blocked. "
            f"source_policy={source_policy}. "
            "Trading computation is PARTIAL -- only approved symbols will be processed."
        )
    elif status == "BLOCKED_ADJUSTED_SOURCE_MISSING":
        caveats.append(
            f"All {total} rows have adjustment_factor=1.0 and "
            "adjustment_status='adjusted_price_missing_warn'. "
            "Adjusted OHLCV is fabricated (adj == raw). "
            f"source_policy={source_policy}. "
            "Backtest is BLOCKED -- do not use raw OHLCV as adjusted."
        )
    elif status == "BLOCKED_NO_APPROVED_SOURCE":
        caveats.append(
            f"No approved adjusted OHLC source available for any requested symbol. "
            f"source_policy={source_policy}."
        )

    caveats.append(
        f"Adjusted OHLCV readiness only -- not production monitoring and not financial advice. "
        f"source_policy={source_policy}."
    )

    return _result(
        status=status, backtest_gate=backtest_gate,
        caveats=caveats, by_symbol=by_symbol,
        symbols=requested_syms,
        coverage={
            "total_rows": total,
            "warn_rows": warn_count,
            "real_factor_rows": real_count,
            "invalid_ohlc_rows": 0,
            "adjusted_daily_prices_rows": adj_real_count,
            "adjusted_daily_prices_invalid": adj_invalid_count,
            "adjusted_daily_prices_source": (
                "vnstock:company_events" if adj_real_count > 0 else None
            ),
            "source_policy": source_policy,
        },
    )


def _result(
    status: str, backtest_gate: str,
    caveats: list[str], by_symbol: list[dict],
    symbols: list[str], coverage: dict,
) -> dict:
    return {
        "status": status, "backtest_gate": backtest_gate,
        "caveats": caveats, "by_symbol": by_symbol,
        "symbols": symbols, "coverage": coverage,
    }


def main() -> int:
    import json as _json
    parser = argparse.ArgumentParser(description="QuestDB adjusted OHLCV readiness check.")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--symbols", default=None,
                        help="Comma-separated symbols (default: all)")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-all", action="store_true",
        help="Exit 1 if any requested symbol is blocked (strict PARTIAL gate)"
    )
    parser.add_argument(
        "--source-policy",
        choices=["approved_only", "prototype_allowed"],
        default="approved_only",
        help="approved_only: vnstock rows do NOT count as PASS (default). "
             "prototype_allowed: vnstock rows count as PASS_PROTOTYPE with caveat.",
    )
    args = parser.parse_args()

    syms = None
    if args.symbols:
        syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    base_url = args.questdb_url.rstrip("/")
    try:
        with qdb.open_client(timeout_seconds=60.0) as client:
            result = check_adjusted_readiness(
                client, base_url, syms, args.start_date, args.end_date,
                source_policy=args.source_policy,
            )
    except Exception as exc:
        # Always emit JSON on error so callers can parse the failure reason
        error_result = {
            "status": "ERROR",
            "backtest_gate": "blocked",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "caveats": [f"QuestDB error: {type(exc).__name__}: {exc}"],
            "by_symbol": [],
            "symbols": syms or [],
            "coverage": {},
        }
        print(_json.dumps(error_result, indent=2))
        return 1

    if args.json:
        print(_json.dumps(result, indent=2))

    status = result["status"]
    gate = result["backtest_gate"]

    # Exit codes:
    # 0 = PASS or PARTIAL (with --require-all, PARTIAL returns 1)
    # 1 = BLOCKED or PARTIAL with --require-all
    if gate == "blocked":
        return 1
    if gate == "partial":
        return 0 if not args.require_all else 1
    # gate == "pass"
    if not args.json:
        _print_text(result)
    return 0


def _print_text(result: dict) -> None:
    cov = result.get("coverage", {})
    print("=" * 62)
    print(f"Adjusted OHLCV Readiness  |  status={result['status']}")
    print("=" * 62)
    print(f"  total_rows          : {cov.get('total_rows', 0):>12,}")
    print(f"  warn_rows           : {cov.get('warn_rows', 0):>12,}  (adj = raw, factor=1.0)")
    print(f"  real_factor_rows    : {cov.get('real_factor_rows', 0):>12,}  (factor != 1.0)")
    print(f"  adjusted_daily_prices_rows: {cov.get('adjusted_daily_prices_rows', 0):>10,}")
    print(f"  backtest_gate       : {result['backtest_gate']}")
    if result.get("symbols"):
        print(f"  symbols             : {', '.join(result['symbols'])}")
    print("-" * 62)
    print("  Per-symbol:")
    for s in result.get("by_symbol", []):
        if s["status"] == "PASS":
            ok = "[PASS]"
            src = s.get("source", "unknown")
            print(f"    {ok} {s['symbol']:<6}  rows={s.get('row_count', 0):>6,}  source={src}")
        else:
            ok = "[BLOCK]"
            reason = (s.get("blocked_reason") or "unknown")[:80]
            print(f"    {ok} {s['symbol']:<6}  {reason}")
    print("-" * 62)
    print("  Caveats:")
    for c in result.get("caveats", []):
        print(f"    - {c}")
    print("=" * 62)


if __name__ == "__main__":
    raise SystemExit(main())
