"""
Offline planner: emit firm-type mapping group for each symbol in the
Vietcap IQ universe (or for a provided symbol list).

Reads instrument_universe.csv from a local Vietcap IQ universe run directory.
Produces a deterministic CSV:

  symbol, proposed_firm_type, mapping_source_symbol, mapping_group,
  confidence, evidence, fallback_policy, notes

No network, no DB, no backtest.

Design reference:
  docs/data_sources/vietcap_iq_fa_firm_type_determination.md

Usage:
  python scripts/plan_vietcap_iq_fa_firm_type_mapping.py \\
    --universe data/processed/dry_run/vietcap_iq_universe/<run_id>/instrument_universe.csv \\
    --output data/processed/vietcap_iq/fa_firm_type_mapping.csv

  # classify a specific set of symbols (no universe file required):
  python scripts/plan_vietcap_iq_fa_firm_type_mapping.py \\
    --symbols VCI SSI VCB BVH FPT \\
    --output data/processed/vietcap_iq/fa_firm_type_mapping.csv
"""

import argparse
import csv
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — hand-reviewed, directly-probed symbols (highest confidence)
# ---------------------------------------------------------------------------

# Symbols whose mapping payloads have been directly probed and verified.
# These override metadata classification.
_EXPLICIT_OVERRIDES: dict[str, str] = {
    "VCI": "securities",
    "SSI": "securities",
    "VCB": "bank",
    "BVH": "insurance",
    # Gap-probe 2026-06-11: CT and QU firm types confirmed to return identical
    # 345-code general mapping (bsa*/isa*/cfa* codes; no bss*/bsb*/bsi* variants).
    "FPT": "general",
    "HPG": "general",
    "E1VFVN30": "general",
}

# company_type_code → mapping group
_COMPANY_TYPE_TO_GROUP: dict[str, str] = {
    "NH": "bank",       # Ngân hàng
    "BH": "insurance",  # Bảo hiểm
    "CK": "securities", # Chứng khoán
    "CT": "general",    # Công ty (general)
    "QU": "general",    # Quỹ (fund — confirmed identical to CT mapping via E1VFVN30 probe)
}

# Mapping group → representative source symbol whose payload file to use
_GROUP_TO_SOURCE_SYMBOL: dict[str, str] = {
    "bank":       "VCB",
    "insurance":  "BVH",
    "securities": "VCI",
    "general":    "",
}

# Mapping group → human-readable fallback policy
_GROUP_TO_FALLBACK_POLICY: dict[str, str] = {
    "bank":       "primary=VCB_mapping; fallback=union_consensus_conflict_free_section_matched",
    "insurance":  "primary=BVH_mapping; fallback=union_consensus_conflict_free_section_matched",
    "securities": "primary=VCI_mapping; fallback=union_consensus_conflict_free_section_matched",
    "general":    "no_primary_mapping; fallback=union_consensus_conflict_free_section_matched_only",
}

OUTPUT_COLUMNS = [
    "symbol",
    "proposed_firm_type",
    "mapping_source_symbol",
    "mapping_group",
    "confidence",
    "evidence",
    "fallback_policy",
    "notes",
]


def classify_symbol(
    symbol: str,
    company_type_code: str = "",
    is_bank: str = "",
) -> dict:
    """Return the mapping group classification for one symbol.

    Priority:
      1. Explicit override table (directly probed symbols)
      2. company_type_code from universe metadata
      3. is_bank fallback (if company_type_code missing)
      4. Default to general
    """
    ctc = company_type_code.strip()
    ib = is_bank.strip().lower() == "true"
    notes: list[str] = []

    # 1. Explicit override (directly probed — highest confidence)
    if symbol in _EXPLICIT_OVERRIDES:
        group = _EXPLICIT_OVERRIDES[symbol]
        confidence = "high"
        evidence = f"explicit_override (directly probed)"
        # consistency check against metadata
        expected_from_ctc = _COMPANY_TYPE_TO_GROUP.get(ctc)
        if expected_from_ctc and expected_from_ctc != group:
            notes.append(
                f"NOTE: company_type_code={ctc!r} maps to {expected_from_ctc!r} "
                f"but override assigns {group!r}"
            )
        if group == "bank" and not ib and ctc:
            notes.append(f"NOTE: override=bank but is_bank={is_bank!r}")
        return _build_row(symbol, group, confidence, evidence, notes)

    # 2. company_type_code from universe metadata
    if ctc in _COMPANY_TYPE_TO_GROUP:
        group = _COMPANY_TYPE_TO_GROUP[ctc]
        confidence = "high"
        evidence = f"company_type_code={ctc!r}"
        if ctc == "NH" and not ib:
            notes.append(f"WARNING: company_type_code=NH but is_bank={is_bank!r}")
        if ib and ctc != "NH":
            notes.append(f"WARNING: is_bank=True but company_type_code={ctc!r}")
        if ctc == "QU":
            notes.append("fund type; no dedicated mapping probed; treated as general")
        return _build_row(symbol, group, confidence, evidence, notes)

    # 3. is_bank fallback (company_type_code missing or unrecognised)
    if ib:
        group = "bank"
        confidence = "medium"
        evidence = f"is_bank=True (company_type_code={ctc!r} not recognised)"
        notes.append("company_type_code missing or unrecognised; classified via is_bank")
        return _build_row(symbol, group, confidence, evidence, notes)

    # 4. Default: no signal — treat as general conservatively
    group = "general"
    confidence = "none"
    if ctc:
        evidence = f"company_type_code={ctc!r} not in known set; defaulted to general"
    else:
        evidence = "no_classification_signal; defaulted to general"
    notes.append("no firm-type signal found in metadata; consensus fallback only")
    return _build_row(symbol, group, confidence, evidence, notes)


def _build_row(
    symbol: str,
    group: str,
    confidence: str,
    evidence: str,
    notes: list[str],
) -> dict:
    return {
        "symbol": symbol,
        "proposed_firm_type": group,
        "mapping_source_symbol": _GROUP_TO_SOURCE_SYMBOL[group],
        "mapping_group": group,
        "confidence": confidence,
        "evidence": evidence,
        "fallback_policy": _GROUP_TO_FALLBACK_POLICY[group],
        "notes": "; ".join(notes),
    }


def load_universe(universe_path: Path) -> dict[str, dict]:
    """Return {symbol: {company_type_code, is_bank, is_index}} from instrument_universe.csv."""
    result: dict[str, dict] = {}
    with open(universe_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            sym = row.get("symbol", "").strip()
            if not sym:
                continue
            result[sym] = {
                "company_type_code": row.get("company_type_code", "").strip(),
                "is_bank": row.get("is_bank", "").strip(),
                "is_index": row.get("is_index", "").strip(),
            }
    return result


def classify_universe(
    universe: dict[str, dict],
    symbol_filter: list[str] | None = None,
) -> list[dict]:
    """Classify all (or filtered) symbols from a loaded universe dict."""
    symbols = symbol_filter if symbol_filter else sorted(universe.keys())
    rows: list[dict] = []
    for sym in symbols:
        meta = universe.get(sym, {})
        # Skip pure index rows (is_index=True; these are not FA-parseable companies)
        if meta.get("is_index", "").lower() == "true":
            continue
        rows.append(
            classify_symbol(
                sym,
                company_type_code=meta.get("company_type_code", ""),
                is_bank=meta.get("is_bank", ""),
            )
        )
    return rows


def write_output(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit firm-type mapping group for Vietcap IQ symbols (offline)."
    )
    parser.add_argument(
        "--universe",
        type=Path,
        help="Path to instrument_universe.csv from a Vietcap IQ universe run",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        metavar="SYMBOL",
        help="Classify only these symbols (no metadata; uses explicit overrides or defaults)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/vietcap_iq/fa_firm_type_mapping.csv"),
        help="Output CSV path",
    )
    args = parser.parse_args(argv)

    if args.universe and args.symbols:
        print(
            "ERROR: --universe and --symbols are mutually exclusive",
            file=sys.stderr,
        )
        return 1

    if args.universe:
        if not args.universe.exists():
            print(f"ERROR: universe file not found: {args.universe}", file=sys.stderr)
            return 1
        universe = load_universe(args.universe)
        rows = classify_universe(universe)
    elif args.symbols:
        rows = [classify_symbol(sym) for sym in args.symbols]
    else:
        print(
            "ERROR: provide --universe or --symbols",
            file=sys.stderr,
        )
        return 1

    # Deterministic: sort by symbol
    rows.sort(key=lambda r: r["symbol"])

    write_output(rows, args.output)
    print(
        f"Wrote {len(rows)} rows to {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
