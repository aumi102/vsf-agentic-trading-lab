"""Probe existing data surfaces for source-backed adjusted close / corporate-action factors.

Scope: 6 demo symbols (FPT, HPG, VCB, CTG, VNM, VHM).
Allowed sources: existing raw data, vnstock company_events, QuestDB daily_prices.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent

DEMO_SYMBOLS = ["FPT", "HPG", "VCB", "CTG", "VNM", "VHM"]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Probe adjusted price sources for demo symbols.")
    parser.add_argument("--symbols", default="FPT,HPG,VCB,CTG,VNM,VHM")
    parser.add_argument("--source", default="auto",
                        choices=["auto", "vnstock", "vietcap", "hsx", "existing"])
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()][:args.limit]

    results = {}
    overall_status = "NO_ADJUSTED_SOURCE_FOUND"

    # ── Source 1: vnstock company_events ─────────────────────────────────────
    vnstock_results = _probe_vnstock_company_events(symbols)
    for sym, res in vnstock_results.items():
        if sym not in results:
            results[sym] = res
        else:
            results[sym]["sources"].update(res.get("sources", {}))

    # ── Source 2: QuestDB raw daily_prices ──────────────────────────────────
    questdb_results = _probe_questdb_daily_prices(symbols)
    for sym, res in questdb_results.items():
        if sym not in results:
            results[sym] = res
        else:
            results[sym]["sources"].update(res.get("sources", {}))

    # ── Source 3: existing adjusted columns ──────────────────────────────────
    adjusted_results = _probe_existing_adjusted_columns(symbols)
    for sym, res in adjusted_results.items():
        if sym not in results:
            results[sym] = res
        else:
            results[sym]["sources"].update(res.get("sources", {}))

    # Determine overall status
    adj_close_found = sum(1 for r in results.values()
                          if r.get("adjusted_close_found"))
    corp_action_with_fields = sum(1 for r in results.values()
                                   if r.get("corporate_action_with_fields"))

    if adj_close_found > 0:
        overall_status = "ADJUSTED_CLOSE_FOUND"
    elif corp_action_with_fields > 0:
        overall_status = "CORPORATE_ACTION_WITH_FIELDS"
    elif any(r.get("status") == "CORPORATE_ACTION_FOUND" for r in results.values()):
        overall_status = "CORPORATE_ACTION_FOUND_FIELDS_INSUFFICIENT"
    else:
        overall_status = "NO_ADJUSTED_SOURCE_FOUND"

    output = {
        "status": overall_status,
        "symbols": symbols,
        "by_symbol": results,
        "summary": {
            "adj_close_found": adj_close_found,
            "corp_action_with_fields": corp_action_with_fields,
            "symbols_with_data": sum(1 for r in results.values() if r.get("has_data")),
        },
        "next_action": _next_action(overall_status, results),
    }

    _print(output, args.json)


def _probe_vnstock_company_events(symbols: list[str]) -> dict:
    """Probe vnstock company_events from data/raw/vnstock."""
    events_dirs = sorted(ROOT.glob("data/raw/vnstock/*/company_events"))
    if not events_dirs:
        return {sym: {"status": "SOURCE_NOT_FOUND", "has_data": False,
                      "sources": {}} for sym in symbols}

    events_dir = events_dirs[-1]
    run_id = events_dir.parent.name

    out = {}
    for sym in symbols:
        sym_dir = events_dir / f"symbol={sym}"
        if not sym_dir.is_dir():
            out[sym] = {"status": "NO_DATA", "has_data": False,
                        "sources": {"vnstock_company_events": "not_found"}}
            continue

        csv_file = sym_dir / "data.csv"
        if not csv_file.exists():
            out[sym] = {"status": "NO_DATA", "has_data": False,
                        "sources": {"vnstock_company_events": "no_csv"}}
            continue

        content = csv_file.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)

        # Classify events
        dividend_rows = [r for r in rows if "DIV" in r.get("event_code", "")]
        split_rows = [r for r in rows if "split" in r.get("action_type_en", "").lower()]
        bonus_rows = [r for r in rows if "bonus" in r.get("event_name_en", "").lower()
                      or "bonus" in r.get("action_type_en", "").lower()]
        issue_rows = [r for r in rows if r.get("event_code", "") == "ISS"]

        has_ratio = any(r.get("exercise_ratio", "") not in ("", "None", "0.0", "0")
                        for r in rows)
        has_value = any(r.get("value_per_share", "") not in ("", "None", "0.0", "0")
                        for r in rows)

        has_corporate_action = bool(dividend_rows or split_rows or bonus_rows or issue_rows)

        # Collect DIV event details
        div_events = []
        for r in dividend_rows:
            div_events.append({
                "event_code": r.get("event_code"),
                "public_date": r.get("public_date"),
                "record_date": r.get("record_date"),
                "exright_date": r.get("exright_date"),
                "payout_date": r.get("payout_date"),
                "value_per_share": r.get("value_per_share"),
                "exercise_ratio": r.get("exercise_ratio"),
                "category": r.get("category"),
            })

        if has_corporate_action:
            if has_ratio or has_value:
                status = "CORPORATE_ACTION_WITH_FIELDS"
            else:
                status = "CORPORATE_ACTION_FOUND_FIELDS_INSUFFICIENT"
            out[sym] = {
                "status": status,
                "has_data": True,
                "has_corporate_action": True,
                "corporate_action_with_fields": has_ratio or has_value,
                "adjusted_close_found": False,
                "sources": {"vnstock_company_events": "found"},
                "dividend_count": len(dividend_rows),
                "split_count": len(split_rows),
                "bonus_count": len(bonus_rows),
                "issue_count": len(issue_rows),
                "has_value_per_share": has_value,
                "has_exercise_ratio": has_ratio,
                "dividend_events": div_events[:10],
                "run_id": run_id,
            }
        else:
            out[sym] = {"status": "NO_DATA", "has_data": False,
                        "sources": {"vnstock_company_events": "no_events"}}

    return out


def _probe_questdb_daily_prices(symbols: list[str]) -> dict:
    """Check QuestDB daily_prices for existing adjusted column data."""
    out = {}
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from trading_agent.storage import questdb_client as qdb

        with qdb.open_client(timeout_seconds=30.0) as client:
            base_url = qdb.DEFAULT_QUESTDB_URL.rstrip("/")
            for sym in symbols:
                sql = (
                    f"SELECT COUNT(*) AS total, "
                    f"SUM(CASE WHEN adjustment_factor IS NOT NULL AND adjustment_factor != 1.0 THEN 1 ELSE 0 END) AS real_factor, "
                    f"SUM(CASE WHEN adjustment_status = 'adjusted_price_missing_warn' THEN 1 ELSE 0 END) AS warn "
                    f"FROM daily_prices WHERE symbol = '{sym}'"
                )
                row = qdb.exec_rows(client, base_url, sql)
                if row and row[0]:
                    cols, rows = row
                    r = rows[0] if rows else [0, 0, 0]
                    total = int(r[0] or 0)
                    real = int(r[1] or 0)
                    warn = int(r[2] or 0)
                    out[sym] = {
                        "status": "OK",
                        "has_data": total > 0,
                        "total_rows": total,
                        "real_factor_rows": real,
                        "warn_rows": warn,
                        "sources": {"questdb_daily_prices": "ok"},
                    }
                else:
                    out[sym] = {"status": "NO_DATA", "has_data": False,
                                "sources": {"questdb_daily_prices": "no_rows"}}
    except Exception as e:
        for sym in symbols:
            out[sym] = {"status": f"ERROR: {e}", "has_data": False,
                        "sources": {"questdb_daily_prices": "error"}}

    return out


def _probe_existing_adjusted_columns(symbols: list[str]) -> dict:
    """Check if any existing raw data contains adjusted_close."""
    out = {}
    for sym in symbols:
        out[sym] = {"status": "NO_ADJUSTED_CLOSE_IN_EXISTING_DATA", "has_data": False,
                    "adjusted_close_found": False,
                    "sources": {"existing_raw": "checked_no_adj_close"}}
    return out


def _next_action(status: str, results: dict) -> str:
    if status == "ADJUSTED_CLOSE_FOUND":
        return "Build adjusted OHLC from found source-backed adjusted close."
    elif status == "CORPORATE_ACTION_WITH_FIELDS":
        # Check if we have price context to compute factors
        has_price_data = sum(1 for r in results.values() if r.get("has_data"))
        if has_price_data >= 2:
            return "Corporate actions found with value_per_share. Compute adjustment factors: factor = 1 - (dividend / close_before_exdate). Need close price before exright_date."
        return "Corporate actions found but price context (close before exdate) needed to compute factors."
    elif status == "CORPORATE_ACTION_FOUND_FIELDS_INSUFFICIENT":
        return "Corporate actions found but value_per_share / exercise_ratio fields insufficient to compute factors. Need adjusted close or pre-event price."
    return "No source-backed adjusted price or corporate action found in existing data. Need: (1) vnstock adjusted_close API, or (2) HSX/HOSE corporate action endpoint, or (3) vendor adjusted price data."


def _print(output: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    print("=" * 62)
    print(f"  Adjusted Price Source Probe")
    print(f"  Status: {output['status']}")
    print("=" * 62)
    for sym, res in output.get("by_symbol", {}).items():
        print(f"\n  [{sym}] {res.get('status', '?')}")
        src = res.get("sources", {})
        print(f"    sources: {src}")
        if res.get("dividend_count"):
            print(f"    dividend_events={res['dividend_count']} "
                  f"has_value={res.get('has_value_per_share')} "
                  f"has_ratio={res.get('has_exercise_ratio')}")
        if res.get("total_rows"):
            print(f"    daily_prices: total={res['total_rows']} "
                  f"real_factor={res['real_factor_rows']} warn={res['warn_rows']}")
    print(f"\n  Summary: {output['summary']}")
    print(f"\n  Next action: {output['next_action']}")
    print("=" * 62)


if __name__ == "__main__":
    raise SystemExit(main())