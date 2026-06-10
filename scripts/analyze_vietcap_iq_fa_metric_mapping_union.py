"""analyze_vietcap_iq_fa_metric_mapping_union.py

Offline union analysis for Vietcap IQ FA metric mapping payloads.

Reads multiple saved mapping payloads (no network, no DB).
Computes:
  1. A union mapping CSV — all codes across all retrieved mapping payloads,
     with conflict detection for codes that have different English names across
     firm types.
  2. A coverage CSV — per-(symbol, section) coverage for VCI-only vs union
     mapping, against saved FA probe payloads.

A "conflict" is a code that appears in two or more mapping payloads with
different `titleEn` values. Conflicting codes are flagged but not dropped —
the union mapping includes all of them with `conflict=true` and an empty
`line_item_name_en_consensus` so callers can decide how to handle them.

No network. No DB writes. No invented names.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

_SECTION_KEYS: frozenset[str] = frozenset(
    {"BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW", "NOTE"}
)

_FA_META_KEYS: frozenset[str] = frozenset(
    {
        "yearReport",
        "lengthReport",
        "publicDate",
        "ticker",
        "audited",
        "reportType",
        "unitPrice",
        "note",
        "organCode",
        "updateDate",
        "createDate",
    }
)

_UNION_COLUMNS = [
    "section",
    "line_item_code",
    "line_item_name_en_consensus",
    "conflict",
    "sources",
    "names_per_source",
    "level",
    "parent",
]

_COVERAGE_COLUMNS = [
    "probe_run_id",
    "symbol",
    "section",
    "total_codes",
    "vci_only_covered",
    "vci_only_pct",
    "union_covered",
    "union_pct",
    "union_consensus_covered",
    "union_consensus_pct",
    "delta_pct",
    "probe_dir_name",
]


# ---------------------------------------------------------------------------
# Mapping payload discovery
# ---------------------------------------------------------------------------


def discover_mapping_payloads(probe_root: Path) -> list[tuple[str, Path]]:
    """Return list of (symbol, payload_path) for verified mapping payloads under probe_root.

    A payload is classified as a mapping payload (not an FA section payload) when:
    - its metadata has ``access_status=verified``
    - its ``data`` field is a dict keyed by section names (BALANCE_SHEET, etc.)
    - its ``data`` dict does NOT contain 'quarters' or 'years' keys
    """
    results: list[tuple[str, Path]] = []
    for payload_path in sorted(probe_root.rglob("payload.json")):
        meta_path = payload_path.parent / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_bytes().decode("utf-8", errors="replace"))
        except Exception:
            continue
        if meta.get("access_status") != "verified":
            continue
        try:
            payload = json.loads(
                payload_path.read_bytes().decode("utf-8", errors="replace")
            )
        except Exception:
            continue
        data = payload.get("data", {})
        if not isinstance(data, dict):
            continue
        if "quarters" in data or "years" in data:
            continue
        if not _SECTION_KEYS.intersection(data.keys()):
            continue
        symbol = meta.get("symbol", "unknown")
        results.append((symbol, payload_path))
    return results


# ---------------------------------------------------------------------------
# Union computation
# ---------------------------------------------------------------------------


def build_union_mapping(
    payload_map: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Build a flat union mapping from multiple symbol payloads.

    Returns rows sorted deterministically: section → line_item_code.
    Each row has columns matching _UNION_COLUMNS.
    Codes with different titleEn across symbols are flagged conflict=true.
    """
    # code -> {symbol -> {titleEn, level, parent}}
    code_data: dict[str, dict[str, dict[str, str]]] = {}
    # code -> section
    code_section: dict[str, str] = {}

    for symbol, payload in payload_map.items():
        data = payload.get("data", {})
        for section, entries in data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                field = entry.get("field") or ""
                if not field:
                    continue
                code_section[field] = section
                code_data.setdefault(field, {})[symbol] = {
                    "titleEn": entry.get("titleEn") or "",
                    "level": str(entry.get("level") or ""),
                    "parent": entry.get("parent") or "",
                }

    rows: list[dict[str, str]] = []
    for code, sym_info in code_data.items():
        section = code_section[code]
        name_values = {v["titleEn"] for v in sym_info.values()}
        is_conflict = len(name_values) > 1
        consensus = "" if is_conflict else next(iter(name_values))
        sources = "|".join(sorted(sym_info.keys()))
        # Build names_per_source only when there is a conflict
        if is_conflict:
            names_per_source = "; ".join(
                f"{s}={sym_info[s]['titleEn']}" for s in sorted(sym_info)
            )
        else:
            names_per_source = ""
        # Take level/parent from the first source alphabetically
        first_sym = sorted(sym_info.keys())[0]
        rows.append(
            {
                "section": section,
                "line_item_code": code,
                "line_item_name_en_consensus": consensus,
                "conflict": "true" if is_conflict else "false",
                "sources": sources,
                "names_per_source": names_per_source,
                "level": sym_info[first_sym]["level"],
                "parent": sym_info[first_sym]["parent"],
            }
        )

    rows.sort(key=lambda r: (r["section"], r["line_item_code"]))
    return rows


def build_union_index(rows: list[dict[str, str]]) -> dict[str, str]:
    """Return code → consensus name for non-conflicting union rows (for safe name population)."""
    return {
        r["line_item_code"]: r["line_item_name_en_consensus"]
        for r in rows
        if r["conflict"] == "false" and r["line_item_code"]
    }


def build_union_code_set(rows: list[dict[str, str]]) -> set[str]:
    """Return the full set of union codes regardless of conflict status.

    Used for coverage computation: a code is 'covered' if it appears in ANY
    mapping payload, even if its name conflicts across firm types.
    """
    return {r["line_item_code"] for r in rows if r["line_item_code"]}


def build_vci_only_index(payload_map: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Return code → titleEn for the VCI mapping payload only."""
    vci_payload = payload_map.get("VCI", {})
    index: dict[str, str] = {}
    for section, entries in vci_payload.get("data", {}).items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            field = entry.get("field") or ""
            if field:
                index[field] = entry.get("titleEn") or ""
    return index


# ---------------------------------------------------------------------------
# Coverage computation
# ---------------------------------------------------------------------------


def _metric_codes_from_fa_payload(payload: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    data = payload.get("data", {})
    for period_type in ("quarters", "years"):
        for row in data.get(period_type, []):
            codes.update(k for k in row if k not in _FA_META_KEYS)
    return codes


def _extract_run_id(payload_path: Path) -> str:
    for part in payload_path.parts:
        if part.startswith("run_id="):
            return part[len("run_id="):]
    return ""


def compute_union_coverage(
    vci_index: dict[str, str],
    union_all_codes: set[str],
    union_index: dict[str, str],
    probe_root: Path,
) -> list[dict[str, str]]:
    """Compute VCI-only vs union coverage for all verified FA section payloads.

    Two union coverage metrics are computed:
    - union_covered / union_pct: codes present in any mapping payload (including conflicting ones)
    - union_consensus_covered / union_consensus_pct: codes with a conflict-free consensus name
    """
    results: list[dict[str, str]] = []
    for payload_path in sorted(probe_root.rglob("payload.json")):
        meta_path = payload_path.parent / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_bytes().decode("utf-8", errors="replace"))
        except Exception:
            continue
        if meta.get("access_status") != "verified":
            continue
        symbol = meta.get("symbol", "")
        section = meta.get("section", "")
        if not symbol or not section:
            continue
        try:
            payload = json.loads(
                payload_path.read_bytes().decode("utf-8", errors="replace")
            )
        except Exception:
            continue
        data = payload.get("data", {})
        if "quarters" not in data and "years" not in data:
            continue  # skip mapping payloads
        codes = _metric_codes_from_fa_payload(payload)
        if not codes:
            continue
        vci_cov = sum(1 for c in codes if c in vci_index)
        union_cov = sum(1 for c in codes if c in union_all_codes)
        union_consensus_cov = sum(1 for c in codes if c in union_index)
        vci_pct = 100 * vci_cov / len(codes)
        union_pct = 100 * union_cov / len(codes)
        union_consensus_pct = 100 * union_consensus_cov / len(codes)
        results.append(
            {
                "probe_run_id": _extract_run_id(payload_path),
                "symbol": symbol,
                "section": section,
                "total_codes": str(len(codes)),
                "vci_only_covered": str(vci_cov),
                "vci_only_pct": f"{vci_pct:.1f}",
                "union_covered": str(union_cov),
                "union_pct": f"{union_pct:.1f}",
                "union_consensus_covered": str(union_consensus_cov),
                "union_consensus_pct": f"{union_consensus_pct:.1f}",
                "delta_pct": f"{union_pct - vci_pct:+.1f}",
                "probe_dir_name": payload_path.parent.name,
            }
        )
    results.sort(key=lambda r: (r["symbol"], r["section"]))
    return results


# ---------------------------------------------------------------------------
# Conflict summary
# ---------------------------------------------------------------------------


def count_conflicts(rows: list[dict[str, str]]) -> int:
    return sum(1 for r in rows if r["conflict"] == "true")


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _write_csv(rows: list[dict[str, str]], columns: list[str], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Offline union analysis for Vietcap IQ FA metric mapping payloads. "
            "No network. No DB writes."
        )
    )
    parser.add_argument(
        "--probe-dir",
        default="data/raw/httpx_diagnostic/source=vietcap_iq",
        help="Root directory containing all probe run_id directories",
    )
    parser.add_argument(
        "--output-union",
        default="data/processed/vietcap_iq/fa_metric_mapping_union.csv",
        help="Output CSV for union mapping entries",
    )
    parser.add_argument(
        "--output-coverage",
        default="data/processed/vietcap_iq/fa_metric_mapping_union_coverage.csv",
        help="Output CSV for VCI-only vs union coverage",
    )
    args = parser.parse_args(argv)

    probe_root = Path(args.probe_dir)
    if not probe_root.exists():
        print(f"error: probe-dir not found: {probe_root}", file=sys.stderr)
        sys.exit(1)

    # Discover and load mapping payloads
    discovered = discover_mapping_payloads(probe_root)
    if not discovered:
        print("error: no verified mapping payloads found under probe-dir", file=sys.stderr)
        sys.exit(1)

    payload_map: dict[str, dict[str, Any]] = {}
    for symbol, path in discovered:
        raw = path.read_bytes().decode("utf-8", errors="replace")
        payload_map[symbol] = json.loads(raw)

    print(f"Mapping payloads loaded: {sorted(payload_map.keys())}")

    # Build union
    union_rows = build_union_mapping(payload_map)
    _write_csv(union_rows, _UNION_COLUMNS, Path(args.output_union))
    n_conflicts = count_conflicts(union_rows)
    n_codes = len(union_rows)
    print(
        f"Union mapping: {n_codes} codes, {n_conflicts} conflicts "
        f"({100 * n_conflicts / n_codes:.1f}% of union)"
    )
    print(f"Output: {args.output_union}")

    # Coverage
    vci_index = build_vci_only_index(payload_map)
    union_all_codes = build_union_code_set(union_rows)
    union_index = build_union_index(union_rows)
    coverage_rows = compute_union_coverage(vci_index, union_all_codes, union_index, probe_root)
    _write_csv(coverage_rows, _COVERAGE_COLUMNS, Path(args.output_coverage))
    print(f"Coverage output: {args.output_coverage} ({len(coverage_rows)} probe(s))")

    # Print summary
    if coverage_rows:
        print()
        print(
            f"{'Symbol':<6} {'Section':<18} {'FA codes':<10} "
            f"{'VCI%':<8} {'Union%':<10} {'Consensus%':<12} {'Delta':<8} {'Gate(95%)'}"
        )
        for r in coverage_rows:
            gate = 'MET' if float(r['union_pct']) >= 95.0 else 'blocked'
            print(
                f"{r['symbol']:<6} {r['section']:<18} {r['total_codes']:<10} "
                f"{r['vci_only_pct']:<8} {r['union_pct']:<10} "
                f"{r['union_consensus_pct']:<12} {r['delta_pct']:<8} {gate}"
            )


if __name__ == "__main__":
    main()
