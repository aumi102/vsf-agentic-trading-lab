"""Read-only inspector: classify failure patterns for FA_FULL_UNIVERSE_20260626.

Categorises symbols into:
  - covered_all4      : in all four FA tables
  - covered_partial   : in some but not all four tables
  - attempted_http_fail: raw_payload rows with non-2xx http OR access_status != verified
  - attempted_zero_facts: raw_payload rows with http=200, status=verified, but no BS rows
  - pending_never_attempted: not in raw_payloads at all
  - likely_no_fa_expected: heuristic ETF/fund/warrant prefix (FUE*, E1*, BMK*, BHH*, etc.)

Outputs counts + preview tables. Read-only — no writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (str(SRC), str(SCRIPT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_RUN_ID = "FA_FULL_UNIVERSE_20260626"
DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL
FA_TABLES = ("fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes")
# Heuristic: ETF / fund / derivative / structured-product prefixes that rarely have FA.
# These are heuristic — no metadata confirmed.
NO_FA_HEURISTIC_PREFIXES = (
    "FUE", "E1V", "E1F", "E1H", "E1Q", "E1R", "E1S",
    "BSC", "BVS", "BHM", "VND", "SSI", "CTS",  # fund codes
)
NO_FA_HEURISTIC_PATTERNS = (
    "ETF", "FUE", "VNM",  # already covered stocks — keep only structured
)


def _table_exists(client, base_url: str, table: str) -> bool:
    _, rows = qdb.exec_rows(client, base_url, "SHOW TABLES")
    return table in {str(r[0]) for r in rows if r}


def _distinct_symbols(client, base_url: str, table: str, run_id: str | None = None) -> set[str]:
    if not _table_exists(client, base_url, table):
        return set()
    if table == "securities":
        sql = "SELECT DISTINCT symbol FROM securities ORDER BY symbol"
    elif run_id:
        sql = f"SELECT DISTINCT symbol FROM {table} WHERE run_id = '{run_id}'"
    else:
        sql = f"SELECT DISTINCT symbol FROM {table}"
    _, rows = qdb.exec_rows(client, base_url, sql)
    return {str(r[0]).upper() for r in rows if r}


def _raw_payload_breakdown(client, base_url: str, run_id: str) -> dict:
    """Return per-symbol breakdown of raw_payload http/access_status."""
    if not _table_exists(client, base_url, "fa_raw_payloads"):
        return {}
    sql = (
        f"SELECT symbol, http_status, access_status, count() "
        f"FROM fa_raw_payloads WHERE run_id = '{run_id}' "
        f"GROUP BY symbol, http_status, access_status"
    )
    _, rows = qdb.exec_rows(client, base_url, sql)
    result: dict[str, dict] = defaultdict(lambda: {"http_codes": set(), "access_statuses": set(), "sections": 0})
    for symbol, http, status, cnt in rows:
        s = str(symbol).upper()
        result[s]["http_codes"].add(int(http) if http else 0)
        result[s]["access_statuses"].add(str(status) if status else "")
        result[s]["section_count"] = result[s].get("section_count", 0) + int(cnt)
    return dict(result)


def _is_heuristic_no_fa(symbol: str) -> bool:
    s = str(symbol).upper()
    for pfx in NO_FA_HEURISTIC_PREFIXES:
        if s.startswith(pfx):
            return True
    return False


def _heavily_shortened(symbol: str) -> bool:
    """Likely warrant/structured product: 3-4 chars, all caps, often has digits."""
    s = str(symbol).upper()
    if len(s) <= 4 and any(c.isdigit() for c in s):
        return True
    return False


def inspect(client, base_url: str, run_id: str, as_json: bool = False) -> dict:
    # Universe
    universe = _distinct_symbols(client, base_url, "securities")
    # Per-table coverage
    per_table: dict[str, set[str]] = {}
    for tbl in FA_TABLES:
        per_table[tbl] = _distinct_symbols(client, base_url, tbl, run_id=None)
    all4 = per_table[FA_TABLES[0]]
    for tbl in FA_TABLES[1:]:
        all4 &= per_table[tbl]
    # Raw payload breakdown
    raw = _raw_payload_breakdown(client, base_url, run_id)
    attempted = set(raw.keys())
    # Symbols with balance-sheet rows for this run_id
    covered_bs_run = _distinct_symbols(client, base_url, "fa_balance_sheet", run_id)
    # Zero-facts: attempted (raw_payload exists) but no BS rows
    zero_facts = attempted - covered_bs_run
    # HTTP failures: any non-2xx in raw_payload
    http_failures: dict[str, dict] = {}
    for sym, info in raw.items():
        codes = info["http_codes"]
        if not codes.issubset({200, 201, 204, 0}) or "verified" not in info["access_statuses"]:
            http_failures[sym] = {
                "http_codes": sorted(codes),
                "access_statuses": sorted(info["access_statuses"]),
                "sections": info.get("section_count", 0),
            }
    # Pending: never attempted
    pending = universe - attempted
    # Heuristic no-FA
    heuristic_no_fa = {s for s in pending if _is_heuristic_no_fa(s) or _heavily_shortened(s)}
    # Summary
    summary = {
        "universe": len(universe),
        "attempted": len(attempted),
        "covered_all4": len(all4),
        "covered_partial": len(universe & attempted) - len(all4),
        "attempted_zero_facts": len(zero_facts),
        "attempted_http_fail": len(http_failures),
        "pending_never_attempted": len(pending),
        "likely_no_fa_heuristic": len(heuristic_no_fa),
        "pending_real": len(pending) - len(heuristic_no_fa),
    }
    # Important symbols
    important = ["FPT", "VHM", "VCB", "VNM", "CTG", "HPG"]
    important_status = {}
    for sym in important:
        in_all4 = sym in all4
        in_attempted = sym in attempted
        bs_rows = qdb.exec_scalar(client, base_url, f"SELECT count() FROM fa_balance_sheet WHERE symbol = '{sym}'", 0)
        important_status[sym] = {
            "in_all4": in_all4,
            "in_attempted": in_attempted,
            "bs_rows": int(bs_rows) if bs_rows else 0,
        }
    # Top missing preview (pending, sorted)
    pending_sorted = sorted(pending)
    # HTTP failure samples
    http_fail_samples = dict(list(http_failures.items())[:30])
    # Zero-facts samples (just symbol names)
    zero_fact_samples = list(zero_facts)[:30]
    # Latest processed symbol (last attempted by index in universe)
    universe_list = sorted(universe)
    last_in_run = max((universe_list.index(s) for s in attempted if s in universe_list), default=-1)
    latest_processed_symbol = universe_list[last_in_run] if last_in_run >= 0 else None
    # Next symbols to process
    next_symbols = [s for s in universe_list if s not in attempted][:30]

    result = {
        "run_id": run_id,
        "summary": summary,
        "important_symbols": important_status,
        "http_fail_samples": http_fail_samples,
        "zero_fact_samples": list(zero_fact_samples),
        "latest_processed_symbol": latest_processed_symbol,
        "next_symbols": next_symbols,
        "top_missing_preview": pending_sorted[:20],
    }
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_text(result)
    return result


def _print_text(result: dict) -> None:
    s = result["summary"]
    print("=" * 70)
    print("FA Universe Failure Pattern Inspector")
    print(f"  run_id            : {result.get('run_id', 'FA_FULL_UNIVERSE_20260626')}")
    print("-" * 70)
    print(f"  universe                          : {s['universe']}")
    print(f"  attempted                         : {s['attempted']}")
    print(f"  covered_all4                      : {s['covered_all4']}")
    print(f"  covered_partial                   : {s['covered_partial']}")
    print(f"  attempted_zero_facts              : {s['attempted_zero_facts']}  (http=200 but no BS rows)")
    print(f"  attempted_http_fail               : {s['attempted_http_fail']}  (non-2xx or non-verified)")
    print(f"  pending_never_attempted           : {s['pending_never_attempted']}")
    print(f"    likely_no_fa_heuristic          : {s['likely_no_fa_heuristic']}  (ETF/fund prefix, warrants)")
    print(f"    pending_real                    : {s['pending_real']}")
    print("-" * 70)
    print("  Important Symbols:")
    for sym, st in result["important_symbols"].items():
        ok = "[OK]" if st["in_all4"] else "[??]"
        bs = st["bs_rows"]
        print(f"    {ok} {sym:<6}  all4={st['in_all4']}  bs_rows={bs}")
    print("-" * 70)
    print(f"  Latest processed symbol          : {result['latest_processed_symbol']}")
    print(f"  Next 30 symbols to process        : {','.join(result['next_symbols'][:10])}...")
    print(f"  Top missing preview               : {','.join(result['top_missing_preview'][:10])}...")
    print("-" * 70)
    http_samples = result.get("http_fail_samples", {})
    if http_samples:
        print(f"  HTTP failure samples ({len(http_samples)} of {s['attempted_http_fail']}):")
        for sym, info in list(http_samples.items())[:10]:
            codes = info.get("http_codes", [])
            print(f"    {sym:<12}  codes={codes}  status={info.get('access_statuses', [])}")
    zero = result.get("zero_fact_samples", [])
    if zero:
        print(f"  Zero-fact samples ({len(zero)} of {s['attempted_zero_facts']}):")
        for sym in zero[:10]:
            print(f"    {sym}")
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only FA universe failure inspector.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of text.")
    args = parser.parse_args()
    base_url = args.questdb_url.rstrip("/")
    with qdb.open_client(timeout_seconds=60.0) as client:
        inspect(client, base_url, args.run_id, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
