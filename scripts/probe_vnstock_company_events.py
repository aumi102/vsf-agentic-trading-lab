"""Probe vnstock company_events for adjusted price / corporate-action factors."""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Probe vnstock company_events for adjusted price data.")
    parser.add_argument("--symbols", default="FPT,HPG,VCB,CTG,VNM,VHM")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    # Find latest company_events run
    events_dirs = sorted(ROOT.glob("data/raw/vnstock/*/company_events"))
    if not events_dirs:
        _result({
            "status": "NO_SOURCE_FOUND",
            "message": "No company_events data found in data/raw/vnstock",
            "symbols": symbols,
            "by_symbol": {},
        }, args.json)
        return

    # Use latest run
    events_dir = events_dirs[-1]
    run_id = events_dir.parent.name

    results = {}
    all_event_types = set()
    all_categories = set()

    for sym in symbols:
        sym_dir = events_dir / f"symbol={sym}"
        if not sym_dir.is_dir():
            results[sym] = {"status": "NO_DATA", "message": f"No company_events for {sym}"}
            continue

        csv_file = sym_dir / "data.csv"
        meta_file = sym_dir / "metadata.json"

        meta = {}
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))

        if not csv_file.exists():
            results[sym] = {"status": "NO_DATA", "message": f"No data.csv for {sym}"}
            continue

        content = csv_file.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)

        # Categorize events
        dividend_rows = []
        split_rows = []
        bonus_rows = []
        rights_rows = []
        other_rows = []

        for r in rows:
            ev_code = r.get("event_code", "").lower()
            ev_en = r.get("event_name_en", "").lower()
            action_en = r.get("action_type_en", "").lower()
            category = r.get("category", "").lower()

            if "dividend" in ev_code or "dividend" in ev_en or "cash" in category:
                dividend_rows.append(r)
            elif "split" in ev_code or "split" in action_en:
                split_rows.append(r)
            elif "bonus" in ev_code or "bonus" in ev_en or "bonus" in action_en:
                bonus_rows.append(r)
            elif "right" in ev_code or "right" in ev_en:
                rights_rows.append(r)
            else:
                other_rows.append(r)

            all_event_types.add(r.get("event_code", "") or r.get("event_name_en", ""))
            all_categories.add(r.get("category", ""))

        # Check for adjusted close or factor fields
        has_adjusted_price = False
        has_price_context = False
        has_ratio_fields = False

        for r in rows:
            # Check if any field looks like adjusted price
            for v in r.values():
                if v and isinstance(v, str) and "adjusted" in v.lower():
                    has_adjusted_price = True

            # Check for ratio fields (split/bonus ratio)
            ratio = r.get("exercise_ratio", "")
            if ratio and ratio not in ("", "None"):
                has_ratio_fields = True

            # Check for price-related fields
            value = r.get("value_per_share", "")
            if value and value not in ("", "None", "0"):
                has_price_context = True

        # Determine status
        has_corporate_action = bool(dividend_rows or split_rows or bonus_rows or rights_rows)

        if has_adjusted_price:
            status = "ADJUSTED_CLOSE_FOUND"
        elif has_corporate_action:
            status = "CORPORATE_ACTION_FOUND"
            if has_ratio_fields or has_price_context:
                status += "_WITH_FIELDS"
            else:
                status += "_FIELDS_INSUFFICIENT"
        else:
            status = "NO_ADJUSTED_SOURCE_FOUND"

        results[sym] = {
            "status": status,
            "total_rows": len(rows),
            "dividend_rows": len(dividend_rows),
            "split_rows": len(split_rows),
            "bonus_rows": len(bonus_rows),
            "rights_rows": len(rights_rows),
            "other_rows": len(other_rows),
            "has_ratio_fields": has_ratio_fields,
            "has_price_context": has_price_context,
            "source": "vnstock",
            "run_id": run_id,
            "event_types": sorted(set(r.get("event_code", "") for r in rows if r.get("event_code"))),
            "categories": sorted(set(r.get("category", "") for r in rows if r.get("category"))),
            "sample": [_sanitize_row(r) for r in rows[:3]],
        }

    # Summarize
    found_count = sum(1 for r in results.values() if "FOUND" in r.get("status", ""))
    corp_action_count = sum(1 for r in results.values() if "CORPORATE_ACTION" in r.get("status", ""))
    adj_close_count = sum(1 for r in results.values() if "ADJUSTED_CLOSE" in r.get("status", ""))

    overall_status = "ADJUSTED_CLOSE_FOUND" if adj_close_count else \
                     "CORPORATE_ACTION_FOUND" if corp_action_count else \
                     "NO_ADJUSTED_SOURCE_FOUND"

    output = {
        "status": overall_status,
        "source": "vnstock",
        "run_id": run_id,
        "all_event_types": sorted(all_event_types),
        "all_categories": sorted(all_categories),
        "symbols": symbols,
        "by_symbol": results,
        "summary": {
            "found_count": found_count,
            "corp_action_count": corp_action_count,
            "adj_close_count": adj_close_count,
        },
    }

    _result(output, args.json)


def _sanitize_row(r: dict) -> dict:
    """Remove None/empty, truncate long values."""
    return {k: (str(v)[:100] if v else None) for k, v in r.items() if v}


def _result(output: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=" * 62)
        print(f"  Source: {output['source']}")
        print(f"  Run:    {output.get('run_id', 'unknown')}")
        print(f"  Status: {output['status']}")
        print(f"  Event types: {output.get('all_event_types', [])}")
        print(f"  Categories:  {output.get('all_categories', [])}")
        print("=" * 62)
        for sym, res in output.get("by_symbol", {}).items():
            print(f"\n  [{sym}] {res.get('status', '?')}")
            print(f"    rows={res.get('total_rows', 0)} "
                  f"dividend={res.get('dividend_rows', 0)} "
                  f"split={res.get('split_rows', 0)} "
                  f"bonus={res.get('bonus_rows', 0)} "
                  f"rights={res.get('rights_rows', 0)}")
            print(f"    ratio_fields={res.get('has_ratio_fields')} "
                  f"price_context={res.get('has_price_context')}")
        print("=" * 62)


if __name__ == "__main__":
    raise SystemExit(main())