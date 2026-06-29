"""Build source-backed adjusted OHLC from vnstock company_events + QuestDB raw prices.

Sources:
  - dividend events: data/raw/vnstock/.../company_events (FPT, VNM have data)
  - price context: QuestDB daily_prices (raw, adjustment_status='adjusted_price_missing_warn')
  - factor method: backward adjustment via ex-date price ratios

Adjustment formula:
  factor = close_pre_exdate / close_on_exdate
  adjusted_ohlc = raw_ohlc / cumulative_factor

Cumulative factor = product of all dividend factors from events after the row date.
Only FPT and VNM have vnstock company_events data.
HPG, VCB, CTG, VHM remain blocked (no corporate action source found).
"""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "src"), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_agent.storage import questdb_client as qdb

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL
RUN_ID = f"ADJ_OHLC_{date.today().strftime('%Y%m%d')}"

DEMO_SYMBOLS = ["FPT", "HPG", "VCB", "CTG", "VNM", "VHM"]


def _load_dividend_events(symbol: str) -> list[dict]:
    """Load vnstock company_events DIV rows for a symbol."""
    events_dirs = sorted(ROOT.glob("data/raw/vnstock/*/company_events"))
    if not events_dirs:
        return []
    events_dir = events_dirs[-1]
    sym_dir = events_dir / f"symbol={symbol}"
    csv_file = sym_dir / "data.csv"
    if not csv_file.exists():
        return []
    content = csv_file.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    return [
        r for r in reader
        if r.get("event_code") == "DIV" and r.get("exright_date")
        and r.get("exright_date") not in ("", "None")
    ]


def _compute_dividend_factors(
    client, base_url: str,
    symbol: str,
    events: list[dict],
) -> dict[str, float]:
    """Compute factor per ex-date from price gap around ex-right_date.

    factor = close_before_exdate / close_on_exdate
    """
    factors = {}
    for ev in events:
        ex_str = ev.get("exright_date", "")[:10]  # "2025-06-12"
        if not ex_str or ex_str == "None":
            continue
        try:
            ex_date = date.fromisoformat(ex_str)
        except ValueError:
            continue

        # Get price on and before ex-date
        sql = (
            f"SELECT trade_date, close FROM daily_prices "
            f"WHERE symbol = '{symbol}' "
            f"AND trade_date >= '{_offset(ex_date, -5)}' "
            f"AND trade_date <= '{_offset(ex_date, 5)}' "
            f"ORDER BY trade_date ASC"
        )
        _, rows = qdb.exec_rows(client, base_url, sql)
        if not rows:
            continue

        # Find closest pre-ex and on-ex closes
        on_ex_close = None
        pre_ex_close = None
        for r in rows:
            td = _parse_date(r[0])
            if td is None:
                continue
            if td == ex_date:
                on_ex_close = float(r[1]) if r[1] else None
            elif td < ex_date:
                pre_ex_close = float(r[1]) if r[1] else None

        if pre_ex_close and on_ex_close and on_ex_close > 0:
            factor = pre_ex_close / on_ex_close
            if 0.80 <= factor <= 1.20:  # sanity: dividend rarely > 20%
                factors[ex_str] = factor
                print(
                    f"  {symbol} ex={ex_str}: pre={pre_ex_close:.2f} "
                    f"on={on_ex_close:.2f} factor={factor:.6f} "
                    f"div={pre_ex_close - on_ex_close:.2f}"
                )

    return factors


def _offset(d: date, days: int) -> str:
    return (d.replace(day=1) + __import__("datetime").timedelta(days=1)).isoformat() if False else (
        (d + __import__("datetime").timedelta(days=days)).isoformat()
    )


def _parse_date(v: Any) -> date | None:
    if v is None:
        return None
    s = str(v)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _compute_cumulative_factor(
    row_date: date,
    ex_dates: list[str],
    factors: dict[str, float],
) -> float:
    """Product of all dividend factors from ex-dates AFTER row_date.

    Backward adjustment: rows before ex-date get multiplied by the
    price-ratio factor (pre_ex_close / on_ex_close), making them
    equivalent to what they would be if no dividend had occurred.
    Rows ON or before ex-date have factor=1.0 (price already dropped).
    """
    result = 1.0
    row_str = row_date.isoformat()
    for ex_str in ex_dates:
        # Apply factor only if ex-date is AFTER the row
        if ex_str > row_str:
            f = factors.get(ex_str)
            if f:
                result *= f
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Build source-backed adjusted OHLC for demo symbols.")
    parser.add_argument("--symbols", default="FPT,HPG,VCB,CTG,VNM,VHM")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--dry-run", action="store_true", help="Show factors only, no writes")
    parser.add_argument("--write-derived", action="store_true", help="Write to adjusted_daily_prices table")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    base_url = args.questdb_url.rstrip("/")

    print(f"{'='*62}")
    print(f"  Source-Backed Adjusted OHLC Builder")
    print(f"  Run: {RUN_ID}")
    print(f"  Symbols: {symbols}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE' if args.write_derived else 'PREVIEW'}")
    print(f"{'='*62}")

    with qdb.open_client(timeout_seconds=60.0) as client:
        all_results = {}
        all_ex_dates = {}
        all_factors = {}

        for sym in symbols:
            print(f"\n  [{sym}]")
            events = _load_dividend_events(sym)
            if not events:
                print(f"    No vnstock company_events for {sym}")
                all_results[sym] = {
                    "status": "NO_CORPORATE_ACTION_SOURCE",
                    "rows_updated": 0,
                }
                continue

            print(f"    {len(events)} dividend events loaded")
            factors = _compute_dividend_factors(client, base_url, sym, events)
            ex_dates = sorted(factors.keys())

            if not factors:
                print(f"    No computable factors (no matching price data)")
                all_results[sym] = {
                    "status": "FACTOR_COMPUTE_FAILED",
                    "rows_updated": 0,
                }
                continue

            print(f"    {len(factors)} factors computed: {ex_dates}")
            all_ex_dates[sym] = ex_dates
            all_factors[sym] = factors

            # Preview: count affected rows
            if ex_dates:
                first_ex = ex_dates[0]
                latest_ex = ex_dates[-1]
                sql = (
                    f"SELECT COUNT(*) FROM daily_prices "
                    f"WHERE symbol = '{sym}' AND trade_date >= '{first_ex}'"
                )
                count = qdb.exec_scalar(client, base_url, sql) or 0
                print(f"    Rows affected (trade_date >= {first_ex}): {count}")

            all_results[sym] = {
                "status": "READY",
                "factors": factors,
                "ex_dates": ex_dates,
                "event_count": len(events),
            }

        if args.dry_run:
            print(f"\n{'='*62}")
            print("  DRY RUN -- no writes performed")
            print(f"{'='*62}")
            return 0

        if not args.write_derived:
            print(f"\n{'='*62}")
            print("  PREVIEW -- use --write-derived to write adjusted_daily_prices")
            print(f"{'='*62}")
            return 0

        # ── Write to adjusted_daily_prices (WAL table, all columns) ──────────
        print(f"\n  Writing adjusted_daily_prices (WAL table)...")
        total_written = 0

        for sym in symbols:
            if sym not in all_factors:
                print(f"    {sym}: no corporate action -- skipped")
                continue
            ex_dates = all_ex_dates[sym]
            factors = all_factors[sym]
            if not ex_dates:
                print(f"    {sym}: no computable factors -- skipped")
                continue

            # Fetch raw rows
            sql = (
                f"SELECT trade_date, open, high, low, close, volume, exchange "
                f"FROM daily_prices "
                f"WHERE symbol = '{sym}' "
                f"ORDER BY trade_date ASC"
            )
            _, rows = qdb.exec_rows(client, base_url, sql)

            csv_rows = []
            for r in rows:
                trade_date_raw = r[0]
                td = _parse_date(trade_date_raw)
                if td is None:
                    continue

                open_, high_, low_, close_ = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                volume_ = float(r[5]) if r[5] else 0.0
                exchange_ = r[6]

                cum_factor = _compute_cumulative_factor(td, ex_dates, factors)
                adj_factor = cum_factor  # raw factor is 1.0
                adj_open = open_ * adj_factor
                adj_high = high_ * adj_factor
                adj_low = low_ * adj_factor
                adj_close = close_ * adj_factor

                csv_rows.append({
                    "symbol": sym,
                    "trade_date": str(trade_date_raw)[:10],
                    "open": adj_open,
                    "high": adj_high,
                    "low": adj_low,
                    "close": adj_close,
                    "volume": volume_,
                    "exchange": exchange_ or "HOSE",
                    "adjustment_factor": adj_factor,
                    "adjustment_status": "source_backed_corporate_action",
                    "adjustment_source": f"vnstock:company_events:{sym}",
                    "run_id": RUN_ID,
                    "factor_method": "backward_exdate_price_ratio",
                    "dividend_exdates": ";".join(ex_dates),
                })

            if csv_rows:
                n = _write_batch(client, base_url, csv_rows)
                total_written += n
                print(f"    {sym}: wrote {n} rows to adjusted_daily_prices")

        print(f"\n{'='*62}")
        print(f"  Total written: {total_written}")
        print(f"{'='*62}")
        print(f"  Next: re-run adjusted_ohlc_readiness.py to verify gate")
        print(f"  Note: daily_prices adjustment_factor unchanged (non-WAL table)")
        print(f"  Gate now reads adjusted_daily_prices for source-backed factors")

    return 0


def _write_batch(client, base_url: str, rows: list[dict]) -> int:
    """Write rows to adjusted_daily_prices via QuestDB ILP (CSV format).
    Returns number of rows written.
    """
    if not rows:
        return 0

    import httpx
    table = "adjusted_daily_prices"
    cols = [
        "symbol", "trade_date", "open", "high", "low", "close",
        "volume", "exchange", "adjustment_factor", "adjustment_status",
        "adjustment_source", "run_id", "factor_method", "dividend_exdates",
    ]

    # Create WAL table if not exists (same pattern as ingest_to_questdb.py)
    create_sql = (
        "CREATE TABLE IF NOT EXISTS adjusted_daily_prices ("
        "symbol SYMBOL, trade_date TIMESTAMP, open DOUBLE, high DOUBLE, "
        "low DOUBLE, close DOUBLE, volume DOUBLE, exchange SYMBOL, "
        "adjustment_factor DOUBLE, adjustment_status SYMBOL, "
        "adjustment_source SYMBOL, run_id SYMBOL, "
        "factor_method SYMBOL, dividend_exdates STRING"
        ") TIMESTAMP(trade_date) PARTITION BY DAY WAL "
        "DEDUP UPSERT KEYS(symbol, trade_date, run_id);"
    )
    resp = client.get(f"{base_url}/exec", params={"query": create_sql})
    resp.raise_for_status()

    # Build CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for row in rows:
        writer.writerow([
            row["symbol"],
            row["trade_date"] + "T00:00:00.000000Z",
            f"{row['open']:.4f}",
            f"{row['high']:.4f}",
            f"{row['low']:.4f}",
            f"{row['close']:.4f}",
            f"{row['volume']:.0f}",
            row["exchange"] or "HOSE",
            f"{row['adjustment_factor']:.8f}",
            row["adjustment_status"],
            row["adjustment_source"],
            row["run_id"],
            row["factor_method"],
            row["dividend_exdates"],
        ])

    csv_bytes = buf.getvalue().encode("utf-8")

    # POST via imp with overwrite=false for idempotent upserts
    resp = client.post(
        f"{base_url}/imp",
        params={"name": table, "overwrite": "false", "forceHeader": "true"},
        files={"data": (f"{table}.csv", csv_bytes, "text/csv")},
    )
    resp.raise_for_status()

    # Wait for WAL
    query = f"SELECT writerTxn, sequencerTxn FROM wal_tables() WHERE name = '{table}'"
    for _ in range(20):
        r = client.get(f"{base_url}/exec", params={"query": query})
        r.raise_for_status()
        dataset = r.json().get("dataset") or []
        if dataset and dataset[0][0] == dataset[0][1]:
            break
        import time as _time
        _time.sleep(0.25)

    return len(rows)


if __name__ == "__main__":
    raise SystemExit(main())