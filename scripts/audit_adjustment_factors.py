"""Audit adjustment factor formula for cash dividend events.

Compares three methods for each dividend event:
  A) price_ratio_inverse = close_on_exdate / close_before_exdate
     (pre-ex prices scaled DOWN by this factor)
  B) price_ratio = close_before_exdate / close_on_exdate
     (pre-ex prices scaled UP by this factor)
  C) dividend_formula = (close_before - dividend) / close_before
     (explicit cash dividend deduction)

Continuity check: for the bar ON ex-date, price should gap down by approximately
the dividend amount. Verify each method produces continuity around ex-date.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "src"), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_agent.storage import questdb_client as qdb

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL


def _offset(d: date, days: int) -> date:
    return d + timedelta(days=days)


def _parse_date(v: Any) -> date | None:
    if v is None:
        return None
    s = str(v)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _load_dividend_events(symbol: str) -> list[dict]:
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
    return [r for r in reader if r.get("event_code") == "DIV" and r.get("exright_date")]


def _fetch_around_exdate(
    client, base_url: str,
    symbol: str, ex_date: date,
) -> dict[str, float | None]:
    """Fetch close price 5 days before and after ex-date."""
    before_date = _offset(ex_date, -5)
    after_date = _offset(ex_date, 5)
    sql = (
        f"SELECT trade_date, close FROM daily_prices "
        f"WHERE symbol = '{symbol}' "
        f"AND trade_date >= '{before_date.isoformat()}' "
        f"AND trade_date <= '{after_date.isoformat()}' "
        f"ORDER BY trade_date ASC"
    )
    _, rows = qdb.exec_rows(client, base_url, sql)
    if not rows:
        return {}

    # Group by date
    by_date = {}
    for r in rows:
        td = _parse_date(r[0])
        if td and r[1]:
            close = float(r[1])
            if td not in by_date:
                by_date[td] = close

    # Find closest before, on, and after ex-date
    close_before = None
    close_on = None
    close_after = None
    closest_before = None
    closest_on = None
    closest_after = None

    for td, close in sorted(by_date.items()):
        diff = (td - ex_date).days
        if diff < 0:
            if closest_before is None or ex_date - td < ex_date - closest_before:
                closest_before = td
                close_before = close
        elif diff == 0:
            closest_on = td
            close_on = close
        elif diff > 0:
            if closest_after is None or td - ex_date < closest_after - ex_date:
                closest_after = td
                close_after = close

    return {
        "close_before_exdate": close_before,
        "close_on_exdate": close_on,
        "close_after_exdate": close_after,
        "date_before_exdate": str(closest_before) if closest_before else None,
        "date_on_exdate": str(closest_on) if closest_on else None,
        "date_after_exdate": str(closest_after) if closest_after else None,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Audit adjustment factor formula.")
    parser.add_argument("--symbols", default="FPT,VNM")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    base_url = args.questdb_url.rstrip("/")

    results = {}

    with qdb.open_client(timeout_seconds=60.0) as client:
        for sym in symbols:
            events = _load_dividend_events(sym)
            if not events:
                results[sym] = {"status": "NO_EVENTS", "events": []}
                continue

            event_results = []
            for ev in events:
                ex_str = ev.get("exright_date", "")[:10]
                if not ex_str or ex_str in ("None", ""):
                    continue
                try:
                    ex_date = date.fromisoformat(ex_str)
                except ValueError:
                    continue

                div_vnd = float(ev.get("value_per_share") or 0)

                # Fetch prices
                price_data = _fetch_around_exdate(client, base_url, sym, ex_date)
                cb = price_data.get("close_before_exdate")
                co = price_data.get("close_on_exdate")
                ca = price_data.get("close_after_exdate")

                if cb is None or co is None:
                    event_results.append({
                        "event": ev.get("event_name_en"),
                        "exright_date": ex_str,
                        "dividend_vnd": div_vnd,
                        "status": "MISSING_PRICE",
                    })
                    continue

                # Method A: inverse price ratio (close_on / close_before)
                # Pre-ex prices multiplied by this -> scaled down
                factor_a = co / cb if cb > 0 else None

                # Method B: price ratio (close_before / close_on)
                # Pre-ex prices multiplied by this -> scaled up
                factor_b = cb / co if co > 0 else None

                # Method C: dividend formula (close_before - dividend) / close_before
                # Only valid if dividend < close_before
                if div_vnd > 0 and div_vnd < cb:
                    factor_c = (cb - div_vnd) / cb
                else:
                    factor_c = None

                # Continuity check: adjusted ON-ex-date close should equal close_before
                # (i.e., make it look like the price never dropped)
                # Method A: adj_on_exdate = close_on * factor_a = close_on * (close_on/close_before) = close_on^2/close_before
                adj_a_on = (co * factor_a) if factor_a else None
                # Method B: adj_on_exdate = close_on * factor_b = close_on * (close_before/close_on) = close_before
                adj_b_on = cb  # = close_before by construction
                # Method C: adj_on_exdate = close_on * factor_c (if we apply same factor on ex-date)
                adj_c_on = (co * factor_c) if factor_c else None

                # Actual price drop on ex-date
                actual_drop = cb - co if cb and co else None
                actual_drop_pct = (actual_drop / cb * 100) if actual_drop and cb else None
                dividend_drop_pct = (div_vnd / cb * 100) if div_vnd and cb else None

                # Error: how far is each adjusted value from the pre-ex close (the target)?
                err_a = abs(adj_a_on - cb) if adj_a_on is not None and cb else None
                err_b = abs(adj_b_on - cb) if cb else None  # exactly 0
                err_c = abs(adj_c_on - cb) if adj_c_on is not None and cb else None

                # Best method: smallest error on ex-date continuity
                errors = [(e, n) for e, n in [(err_a, "A"), (err_b, "B"), (err_c, "C")] if e is not None]
                best = min(errors, key=lambda x: x[0]) if errors else (None, None)

                event_results.append({
                    "event": ev.get("event_name_en"),
                    "exright_date": ex_str,
                    "dividend_vnd": div_vnd,
                    "close_before_exdate": round(cb, 2) if cb else None,
                    "close_on_exdate": round(co, 2) if co else None,
                    "close_after_exdate": round(ca, 2) if ca else None,
                    "actual_drop_pct": round(actual_drop_pct, 4) if actual_drop_pct else None,
                    "dividend_drop_pct": round(dividend_drop_pct, 4) if dividend_drop_pct else None,
                    "factor_A_price_ratio_inverse": round(factor_a, 8) if factor_a else None,
                    "factor_B_price_ratio": round(factor_b, 8) if factor_b else None,
                    "factor_C_dividend_formula": round(factor_c, 8) if factor_c else None,
                    "adj_on_exdate_A": round(adj_a_on, 2) if adj_a_on else None,
                    "adj_on_exdate_B": round(adj_b_on, 2) if adj_b_on else None,  # == close_before
                    "adj_on_exdate_C": round(adj_c_on, 2) if adj_c_on else None,
                    "continuity_error_A": round(err_a, 2) if err_a else None,
                    "continuity_error_B": round(err_b, 2) if err_b else None,
                    "continuity_error_C": round(err_c, 2) if err_c else None,
                    "recommended_method": best[1] if best[1] else "INSUFFICIENT",
                    "status": "OK",
                    "run_id": None,
                })

            results[sym] = {
                "status": "AUDITED",
                "events": event_results,
                "summary": _summarize(event_results),
            }

    # Print
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for sym, res in results.items():
            print(f"{'='*62}")
            print(f"  [{sym}] {res['status']}")
            print(f"{'='*62}")
            for ev in res.get("events", []):
                if ev.get("status") == "MISSING_PRICE":
                    print(f"  {ev['exright_date']}: MISSING_PRICE")
                    continue
                rec = ev.get("recommended_method", "?")
                print(f"  {ev['exright_date']}  div={ev.get('dividend_vnd')} VND  rec={rec}")
                print(f"    close_before={ev.get('close_before_exdate')}  "
                      f"close_on={ev.get('close_on_exdate')}  "
                      f"close_after={ev.get('close_after_exdate')}")
                print(f"    A(price_inv)={ev.get('factor_A_price_ratio_inverse')}  "
                      f"err={ev.get('continuity_error_A')}")
                print(f"    B(price_ratio)={ev.get('factor_B_price_ratio')}  "
                      f"err={ev.get('continuity_error_B')}")
                print(f"    C(div_formula)={ev.get('factor_C_dividend_formula')}  "
                      f"err={ev.get('continuity_error_C')}")
                if args.detail:
                    print(f"    actual_drop={ev.get('actual_drop_pct')}%  "
                          f"div_drop={ev.get('dividend_drop_pct')}%")
            smry = res.get("summary", {})
            if smry:
                print(f"  Summary: {smry}")
            print()


def _summarize(events: list[dict]) -> dict:
    counts = {}
    for ev in events:
        m = ev.get("recommended_method", "?")
        counts[m] = counts.get(m, 0) + 1
    return {"method_counts": counts}


if __name__ == "__main__":
    raise SystemExit(main())
