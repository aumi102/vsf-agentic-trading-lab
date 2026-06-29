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


def _per_symbol_status(
    client, base_url: str,
    symbols: list[str] | None,
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    """Return per-symbol readiness: checks adjusted_daily_prices first, then daily_prices."""
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
        adj_status = None
        adj_total = 0
        adj_real = 0
        adj_invalid = 0
        if adj_table_exists:
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
            result.append({
                "symbol": sym,
                "status": "PASS",
                "backtest_gate": "pass",
                "source": "adjusted_daily_prices",
                "row_count": adj_real,
                "blocked_reason": None,
                "caveats": [],
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
                "blocked_reason": None,
                "caveats": [f"{real} rows have real adjustment factors."],
            })
        else:
            result.append({
                "symbol": sym,
                "status": "BLOCKED",
                "backtest_gate": "blocked",
                "source": "daily_prices",
                "row_count": total,
                "blocked_reason": _blocked_reason(sym),
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
    by_symbol = _per_symbol_status(client, base_url, symbols, start_date, end_date)
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
    pass_count = sum(1 for s in by_symbol if s["status"] == "PASS")
    block_count = sum(1 for s in by_symbol if s["status"] == "BLOCKED")
    if block_count == 0:
        status = "PASS"
        backtest_gate = "pass" if adj_invalid_count == 0 else "blocked"
    elif pass_count == 0:
        status = "BLOCKED_ADJUSTED_FACTOR_FABRICATED"
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
            f"(adjustment_status='source_backed_corporate_action', adjustment_source=vnstock:company_events). "
            f"{adj_invalid_count} rows have invalid OHLC."
        )
    elif status == "PARTIAL":
        caveats.append(
            f"{pass_count} of {len(by_symbol)} symbols have source-backed adjusted OHLC. "
            f"{block_count} symbols blocked (no corporate action source). "
            "Trading computation is PARTIAL -- only PASS symbols will be processed."
        )
    elif status == "BLOCKED_ADJUSTED_FACTOR_FABRICATED":
        caveats.append(
            f"All {total} rows have adjustment_factor=1.0 and "
            "adjustment_status='adjusted_price_missing_warn'. "
            "Vietcap gap-chart source provides no adjustment factors. "
            "Adjusted OHLCV is fabricated (adj == raw). "
            "Backtest is BLOCKED -- do not use raw OHLCV as adjusted."
        )

    caveats.append(
        "Adjusted OHLCV readiness only -- not production monitoring and not financial advice."
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
            "adjusted_daily_prices_source": "vnstock:company_events" if adj_real_count > 0 else None,
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
    args = parser.parse_args()

    syms = None
    if args.symbols:
        syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    base_url = args.questdb_url.rstrip("/")
    with qdb.open_client(timeout_seconds=60.0) as client:
        result = check_adjusted_readiness(client, base_url, syms, args.start_date, args.end_date)

    if args.json:
        import json as _json
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
