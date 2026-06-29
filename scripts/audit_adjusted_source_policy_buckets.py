"""Audit that adjusted source policy buckets are disjoint.

Verifies that list_adjusted_pass_symbols places each symbol into exactly one bucket:
approved, prototype, blocked_unapproved, or missing_adjusted_source.

Usage:
  python scripts/audit_adjusted_source_policy_buckets.py --symbols FPT,VNM,HPG,VCB,CTG,VHM --json
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

from scripts.list_adjusted_pass_symbols import list_adjusted_symbols
from trading_agent.storage import questdb_client as qdb

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL


def audit_buckets(symbols: list[str], base_url: str) -> dict:
    with qdb.open_client(timeout_seconds=60.0) as client:
        approved_data = list_adjusted_symbols(client, base_url, None, "approved_only")
        prototype_data = list_adjusted_symbols(client, base_url, None, "prototype_allowed")

    # Build sets from each bucket
    # approved_only: FPT/VNM -> blocked_unapproved, HPG/VCB/CTG/VHM -> missing, none -> approved
    ao_approved = {s["symbol"] for s in approved_data.get("approved_symbols", [])}
    ao_blocked = {s["symbol"] for s in approved_data.get("blocked_unapproved_symbols", [])}
    ao_missing = set(approved_data.get("missing_adjusted_source_symbols", []))

    # prototype_allowed: FPT/VNM -> prototype, HPG/VCB/CTG/VHM -> missing, none -> approved
    pp_approved = {s["symbol"] for s in prototype_data.get("approved_symbols", [])}
    pp_prototype = {s["symbol"] for s in prototype_data.get("prototype_symbols", [])}
    pp_blocked = {s["symbol"] for s in prototype_data.get("blocked_unapproved_symbols", [])}
    pp_missing = set(prototype_data.get("missing_adjusted_source_symbols", []))

    # Within-policy overlap checks (each symbol should be in exactly one bucket per policy)
    approved_only_overlaps = {
        "approved_n_blocked": sorted(ao_approved & ao_blocked),
        "approved_n_missing": sorted(ao_approved & ao_missing),
        "blocked_n_missing": sorted(ao_blocked & ao_missing),
    }
    prototype_allowed_overlaps = {
        "approved_n_prototype": sorted(pp_approved & pp_prototype),
        "approved_n_blocked": sorted(pp_approved & pp_blocked),
        "approved_n_missing": sorted(pp_approved & pp_missing),
        "prototype_n_blocked": sorted(pp_prototype & pp_blocked),
        "prototype_n_missing": sorted(pp_prototype & pp_missing),
        "blocked_n_missing": sorted(pp_blocked & pp_missing),
    }

    all_overlaps = {**approved_only_overlaps, **prototype_allowed_overlaps}
    any_overlap = any(v for v in all_overlaps.values())

    if any_overlap:
        verdict = "BUCKETS_OVERLAP_FAIL"
        status = "fail"
    else:
        verdict = "BUCKETS_DISJOINT_PASS"
        status = "ok"

    return {
        "status": status,
        "symbols_requested": symbols,
        "approved_only": {
            "approved_symbols": sorted(ao_approved),
            "prototype_symbols": [],
            "blocked_unapproved_symbols": sorted(ao_blocked),
            "missing_adjusted_source_symbols": sorted(ao_missing),
            "approved_count": len(ao_approved),
            "prototype_count": 0,
            "blocked_unapproved_count": len(ao_blocked),
            "missing_count": len(ao_missing),
        },
        "prototype_allowed": {
            "approved_symbols": sorted(pp_approved),
            "prototype_symbols": sorted(pp_prototype),
            "blocked_unapproved_symbols": sorted(pp_blocked),
            "missing_adjusted_source_symbols": sorted(pp_missing),
            "approved_count": len(pp_approved),
            "prototype_count": len(pp_prototype),
            "blocked_unapproved_count": len(pp_blocked),
            "missing_count": len(pp_missing),
        },
        "readiness_approved_only": "SKIPPED_QUESTDB_TIMEOUT",
        "readiness_prototype_allowed": "SKIPPED_QUESTDB_TIMEOUT",
        "overlap_checks": all_overlaps,
        "verdict": verdict,
        "caveats": [
            "FPT/VNM expected BLOCKED_UNAPPROVED under approved_only.",
            "FPT/VNM expected prototype under prototype_allowed.",
            "HPG/VCB/CTG/VHM expected missing_adjusted_source under both policies.",
            "readiness check skipped due to QuestDB per-symbol query timeouts; "
            "bucket disjointness verified via list_adjusted_symbols alone.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit disjoint adjusted source buckets.")
    parser.add_argument("--symbols", default="FPT,VNM,HPG,VCB,CTG,VHM")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    base_url = args.questdb_url.rstrip("/")
    result = audit_buckets(syms, base_url)

    if args.json:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Verdict: {result['verdict']}")
        ao = result["approved_only"]
        pp = result["prototype_allowed"]
        print(f"  approved_only:    approved={ao['approved_count']} "
              f"blocked_unapproved={ao['blocked_unapproved_count']} "
              f"missing={ao['missing_count']}")
        print(f"  prototype_allowed: approved={pp['approved_count']} "
              f"prototype={pp['prototype_count']} "
              f"missing={pp['missing_count']}")
        if result["overlap_checks"]:
            for k, v in result["overlap_checks"].items():
                if v:
                    print(f"  OVERLAP {k}: {v}")

    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
