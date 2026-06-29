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

    # Coverage counts
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

    # Invalid OHLC: only check rows that claim to be adjusted (status != warn).
    # Skip aggregate MAX/MIN in WHERE -- use a simpler flag: adjusted_high < adjusted_low.
    # This catches a class of bad data; full H/L/O/C consistency needs a subquery.
    invalid_sql = (
        f"SELECT COUNT(*) FROM daily_prices {where} "
        f"AND adjustment_status != 'adjusted_price_missing_warn' "
        f"AND (adjusted_high < adjusted_low OR adjusted_high < 0 OR adjusted_low < 0 OR adjusted_close < 0)"
    )
    invalid_count = int(qdb.exec_scalar(client, base_url, invalid_sql) or 0)

    # Per-symbol
    sym_sql = (
        f"SELECT symbol, COUNT(*) AS total, "
        f"SUM(CASE WHEN adjustment_status = 'adjusted_price_missing_warn' THEN 1 ELSE 0 END) AS warn_rows, "
        f"SUM(CASE WHEN adjustment_factor IS NOT NULL AND adjustment_factor != 1.0 THEN 1 ELSE 0 END) AS real_rows "
        f"FROM daily_prices {where} "
        f"GROUP BY symbol ORDER BY symbol"
    )
    _, sym_rows = qdb.exec_rows(client, base_url, sym_sql)
    by_symbol = []
    for row in sym_rows:
        sym = str(row[0])
        tot = int(row[1] or 0)
        warn = int(row[2] or 0)
        real = int(row[3] or 0)
        gate = "pass" if real > 0 and invalid_count == 0 else "blocked"
        by_symbol.append({
            "symbol": sym, "total_rows": tot,
            "warn_rows": warn, "real_factor_rows": real,
            "backtest_gate": gate,
        })

    # Status
    caveats = []
    if total == 0:
        status = "BLOCKED_NO_ROWS"
        backtest_gate = "blocked"
        caveats.append("No daily_prices rows for the selected filters.")
    elif real_count == 0 and warn_count == total:
        status = "BLOCKED_ADJUSTED_FACTOR_FABRICATED"
        backtest_gate = "blocked"
        caveats.append(
            f"All {total} rows have adjustment_factor=1.0 and "
            "adjustment_status='adjusted_price_missing_warn'. "
            "Vietcap gap-chart source provides no adjustment factors. "
            "Adjusted OHLCV is fabricated (adj == raw). "
            "Backtest is BLOCKED -- do not use raw OHLCV as adjusted."
        )
    elif real_count > 0:
        status = "PASS" if invalid_count == 0 else "WARN"
        backtest_gate = "pass" if invalid_count == 0 else "blocked"
        caveats.append(f"{real_count} rows have real adjustment factors (factor != 1.0).")
        if invalid_count:
            caveats.append(f"{invalid_count} rows have inconsistent adjusted OHLC values.")
    else:
        status = "WARN"
        backtest_gate = "blocked"
        caveats.append(
            f"Adjusted status unclear: {warn_count}/{total} rows are warned. "
            "Backtest BLOCKED pending resolution."
        )

    caveats.append(
        "Adjusted OHLCV readiness only -- not production monitoring and not financial advice."
    )

    return _result(
        status=status, backtest_gate=backtest_gate,
        caveats=caveats, by_symbol=by_symbol,
        symbols=[s["symbol"] for s in by_symbol],
        coverage={"total_rows": total, "warn_rows": warn_count,
                  "real_factor_rows": real_count, "invalid_ohlc_rows": invalid_count},
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
        return 0 if result["backtest_gate"] == "pass" else 1

    _print_text(result)
    return 0 if result["backtest_gate"] == "pass" else 1


def _print_text(result: dict) -> None:
    cov = result.get("coverage", {})
    print("=" * 62)
    print(f"Adjusted OHLCV Readiness  |  status={result['status']}")
    print("=" * 62)
    print(f"  total_rows          : {cov.get('total_rows', 0):>12,}")
    print(f"  warn_rows           : {cov.get('warn_rows', 0):>12,}  (adj = raw, factor=1.0)")
    print(f"  real_factor_rows    : {cov.get('real_factor_rows', 0):>12,}  (factor != 1.0)")
    print(f"  invalid_ohlc_rows   : {cov.get('invalid_ohlc_rows', 0):>12,}")
    print(f"  backtest_gate       : {result['backtest_gate']}")
    if result.get("symbols"):
        print(f"  symbols             : {', '.join(result['symbols'])}")
    print("-" * 62)
    print("  Per-symbol:")
    for s in result.get("by_symbol", []):
        ok = "[PASS]" if s["backtest_gate"] == "pass" else "[BLOCK]"
        print(f"    {ok} {s['symbol']:<6}  total={s['total_rows']:>6,}  "
              f"warn={s['warn_rows']:>6,}  real={s['real_factor_rows']:>6,}")
    print("-" * 62)
    print("  Caveats:")
    for c in result.get("caveats", []):
        print(f"    - {c}")
    print("=" * 62)


if __name__ == "__main__":
    raise SystemExit(main())
