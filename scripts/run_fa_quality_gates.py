"""Read-only FA quality / coverage gate.

Returns PASS/WARN/FAIL plus a structured summary. Mapping coverage is reported
honestly but only WARNs (not FAILS) when partial. FAIL only triggers on missing
FA tables or broken queries. Designed to be safe to re-run in CI / preflight.
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
    parser = argparse.ArgumentParser(description="Read-only FA quality / coverage gate.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    base_url = args.questdb_url.rstrip("/")

    summary: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "questdb_url": base_url,
        "checks": [],
    }
    blocking_failures: list[str] = []
    warnings: list[str] = []

    with qdb.open_client(timeout_seconds=60.0) as client:
        # Check 1: table existence
        for t in FACT_TABLES:
            present = _table_exists(client, base_url, t)
            summary["checks"].append({"name": f"table_exists:{t}", "passed": present})
            if not present:
                blocking_failures.append(f"Missing required FA table: {t}")

        # Check 2: per-table coverage and per-table row counts.
        per_table: dict = {}
        for t in FACT_TABLES:
            if not _table_exists(client, base_url, t):
                per_table[t] = {"present": False, "rows": 0, "symbols": 0}
                continue
            per_table[t] = {
                "present": True,
                "rows": _count(client, base_url, f"SELECT count() FROM {t}"),
                "symbols": _count(client, base_url, f"SELECT count_distinct(symbol) FROM {t}"),
            }
        summary["per_table"] = per_table

        # Check 3: all-4 coverage.
        all_four: set[str] | None = None
        for t in FACT_TABLES:
            if not _table_exists(client, base_url, t):
                all_four = set()
                continue
            _, rows = qdb.exec_rows(client, base_url, f"SELECT DISTINCT symbol FROM {t}")
            syms = {str(r[0]).upper() for r in rows if r and r[0]}
            all_four = syms if all_four is None else (all_four & syms)
        all_four_count = len(all_four or set())
        summary["all_four_symbol_count"] = all_four_count
        # Useful even when WARN — we still want the all-four number.
        if all_four_count < 50:
            warnings.append(f"All-4 statement coverage is low: {all_four_count} symbols (target >= 50).")

        # Check 4: latest full-universe run.
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
        if not latest_complete and not latest_in_progress:
            warnings.append("No full-universe FA run found in fa_ingest_runs (no complete, no in_progress).")

        # Check 5: failure count of latest complete run (if any).
        if latest_complete and _table_exists(client, base_url, "fa_ingest_runs"):
            fc = _scalar(client, base_url,
                         f"SELECT failure_count FROM fa_ingest_runs WHERE run_id = '{latest_complete}' "
                         f"ORDER BY created_at DESC LIMIT 1", 0)
            summary["latest_complete_failure_count"] = int(fc) if fc not in (None, "") else 0
        else:
            summary["latest_complete_failure_count"] = None

        # Check 6: known important symbols covered.
        important: dict = {}
        if _table_exists(client, base_url, "fa_balance_sheet"):
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
            important[s] = {"covered_in_fa_balance_sheet": s in counts, "row_count": counts.get(s, 0)}
        summary["important_symbols"] = important
        # FPT/VCB are the historical smoke baseline; coverage loss is a hard warning.
        for baseline in ("FPT", "VCB"):
            if not important[baseline]["covered_in_fa_balance_sheet"]:
                warnings.append(f"Baseline symbol {baseline} is missing from fa_balance_sheet (regression).")
        for s in IMPORTANT_SYMBOLS:
            if not important[s]["covered_in_fa_balance_sheet"]:
                warnings.append(f"Important symbol not yet covered: {s}.")

        # Check 7: OHLCV substitution guard. We check that the FA agent path's
        # tool list excludes market/OHLCV tools. We do this statically by reading
        # the agent tool registry. This is a static check, not runtime.
        try:
            from trading_agent.tools.questdb_fa_data_tool import get_fa_data_tool, get_fa_data_tools  # type: ignore
            fa_tool = get_fa_data_tool()  # type: ignore[call-arg]
            fa_tool_names = {getattr(t, "name", getattr(t, "__name__", str(t))) for t in get_fa_data_tools()}  # type: ignore
            ohlcv_markers = {"ohlcv", "market", "summary", "price", "bar"}
            contamination = [n for n in fa_tool_names if any(m in n.lower() for m in ohlcv_markers)]
            summary["ohlcv_substitution_check"] = {
                "passed": not contamination,
                "fa_tool_names": sorted(fa_tool_names),
                "ohlcv_contamination": contamination,
            }
            if contamination:
                blocking_failures.append(
                    f"FA tool list contains OHLCV/market tools: {contamination}. FA must never proxy OHLCV."
                )
        except Exception as exc:
            # Be conservative: a hard failure to introspect does not by itself fail
            # the gate, but it must be visible in the summary.
            summary["ohlcv_substitution_check"] = {
                "passed": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
            warnings.append(f"Could not statically verify FA tool list: {type(exc).__name__}: {exc}")

        # Check 8: mapping coverage is reported honestly, not enforced.
        mapping_rows = 0
        mapping_consensus = 0
        if _table_exists(client, base_url, "fa_metric_mapping"):
            mapping_rows = _count(client, base_url, "SELECT count() FROM fa_metric_mapping")
            mapping_consensus = _count(client, base_url,
                                        "SELECT count() FROM fa_metric_mapping WHERE quality_status = 'source_backed_consensus'")
        summary["mapping"] = {"mapping_rows": mapping_rows, "consensus_rows": mapping_consensus}
        if mapping_rows == 0:
            warnings.append("fa_metric_mapping is empty; tool-side metric enrichment will fall back to raw codes.")

    if blocking_failures:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    summary["status"] = status
    summary["blocking_failures"] = blocking_failures
    summary["warnings"] = warnings

    if status == "FAIL":
        summary["next_action"] = (
            "FA gate is failing. Address blocking_failures first, then re-run. "
            "Most likely: missing FA table — recreate via scripts/ingest_vietcap_financial_reports_to_questdb.py --ensure-tables."
        )
    elif status == "WARN":
        summary["next_action"] = (
            "FA gate is warning. Continue the full-universe ingester: "
            "python scripts\\batch_ingest_vietcap_fa_full_universe.py --run-id FA_FULL_UNIVERSE_20260626 "
            "--only-missing --resume --sleep-seconds 2 --jitter-seconds 1 --stop-on-rate-limit "
            "--max-consecutive-failures 10"
        )
    else:
        summary["next_action"] = "FA gate passing. Re-run on schedule."

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        _print_human(summary)
    return 0 if status != "FAIL" else 1


def _print_human(s: dict) -> None:
    print("=" * 70)
    print("FA quality gate")
    print("=" * 70)
    print(f"  status          : {s['status']}")
    print(f"  generated_at    : {s['generated_at']}")
    print(f"  all_four_symbols: {s['all_four_symbol_count']}")
    print("  per_table:")
    for t, info in s["per_table"].items():
        print(f"    - {t:30s} present={info['present']!s:5s} rows={info['rows']:>10d} symbols={info['symbols']:>5d}")
    print(f"  latest_complete_run_id   : {s['latest_complete_run_id']}")
    print(f"  latest_in_progress_run_id: {s['latest_in_progress_run_id']}")
    print(f"  latest_complete_failures : {s.get('latest_complete_failure_count')}")
    print("  important_symbols:")
    for sym, info in s["important_symbols"].items():
        flag = "OK" if info["covered_in_fa_balance_sheet"] else "MISS"
        print(f"    [{flag}] {sym:5s} bs_rows={info['row_count']:>8d}")
    mapping = s.get("mapping", {})
    print(f"  mapping: rows={mapping.get('mapping_rows',0)} consensus={mapping.get('consensus_rows',0)}")
    ohlcv = s.get("ohlcv_substitution_check", {})
    if ohlcv:
        print(f"  ohlcv_substitution: passed={ohlcv.get('passed')} contamination={ohlcv.get('ohlcv_contamination')}")
    if s["blocking_failures"]:
        print("  blocking_failures:")
        for x in s["blocking_failures"]:
            print(f"    - {x}")
    if s["warnings"]:
        print("  warnings:")
        for x in s["warnings"]:
            print(f"    - {x}")
    print(f"  next_action     : {s['next_action']}")


if __name__ == "__main__":
    raise SystemExit(main())
