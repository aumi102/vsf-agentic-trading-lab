"""parse_vietcap_iq_fa_metric_mapping_dry_run.py

Offline dry-run parser for the Vietcap IQ FA metric mapping payload.

Reads the saved mapping payload only — no network, no DB writes.
Outputs:
  1. A deterministic CSV of code → name entries (line_item_code, line_item_name_en, …)
  2. Optionally: a per-(symbol, section) coverage report against saved FA probe payloads

Null-field entries in the mapping are section-level display headers; they are
included in output with is_header=true so callers can filter them explicitly.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

# Default path — the first successful mapping probe run
_DEFAULT_MAPPING_PAYLOAD = (
    "data/raw/httpx_diagnostic/source=vietcap_iq"
    "/run_id=20260610T025420Z"
    "/vietcap_iq_fa_metrics_mapping_probe/payload.json"
)

# Columns in the output mapping CSV
_MAPPING_COLUMNS = [
    "section",
    "line_item_code",
    "line_item_name_en",
    "line_item_name_vi",
    "level",
    "parent",
    "name",
    "is_header",
]

# Columns in the output coverage CSV
_COVERAGE_COLUMNS = [
    "probe_run_id",
    "symbol",
    "section",
    "total_codes",
    "covered_codes",
    "coverage_pct",
    "probe_dir_name",
]

# Keys present in every FA period row that are metadata, not metric codes
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
    }
)


# ---------------------------------------------------------------------------
# Core parsing
# ---------------------------------------------------------------------------


def load_mapping_payload(path: str | Path) -> dict[str, Any]:
    """Load and return the raw mapping JSON from disk. Raises FileNotFoundError."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Mapping payload not found: {p}")
    raw = p.read_bytes()
    return json.loads(raw.decode("utf-8", errors="replace"))


def parse_mapping_entries(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Return flat mapping rows from the payload.

    Each row has the columns in _MAPPING_COLUMNS.
    Entries with a null/empty ``field`` are section-level display headers;
    they are kept with ``is_header=true`` so the caller can filter them.
    The output is sorted deterministically: section → is_header → line_item_code.
    """
    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected payload['data'] to be a dict, got {type(data).__name__}"
        )

    rows: list[dict[str, str]] = []
    for section, entries in data.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            field = entry.get("field") or ""
            rows.append(
                {
                    "section": section,
                    "line_item_code": field,
                    "line_item_name_en": entry.get("titleEn") or "",
                    "line_item_name_vi": entry.get("titleVi") or "",
                    "level": str(entry.get("level") or ""),
                    "parent": entry.get("parent") or "",
                    "name": entry.get("name") or "",
                    "is_header": "false" if field else "true",
                }
            )

    rows.sort(key=lambda r: (r["section"], r["is_header"], r["line_item_code"]))
    return rows


def build_mapping_index(rows: list[dict[str, str]]) -> dict[str, str]:
    """Return a code → line_item_name_en dict from non-header mapping rows."""
    return {
        r["line_item_code"]: r["line_item_name_en"]
        for r in rows
        if r["is_header"] == "false" and r["line_item_code"]
    }


# ---------------------------------------------------------------------------
# Coverage against saved probe payloads
# ---------------------------------------------------------------------------


def _metric_codes_from_fa_payload(payload: dict[str, Any]) -> set[str]:
    """Extract the set of metric column names from an FA section payload."""
    codes: set[str] = set()
    data = payload.get("data", {})
    for period_type in ("quarters", "years"):
        for row in data.get(period_type, []):
            codes.update(k for k in row if k not in _FA_META_KEYS)
    return codes


def compute_coverage(
    mapping_index: dict[str, str],
    probe_root: str | Path,
) -> list[dict[str, str]]:
    """Scan *probe_root* for FA probe payloads and compute per-(symbol, section) coverage.

    Each probe directory is expected to contain:
    - payload.json — the raw FA response
    - metadata.json — at minimum ``symbol``, ``section``, and ``access_status``

    Only probes with ``access_status=verified`` and a quarters/years envelope are counted.
    """
    root = Path(probe_root)
    results: list[dict[str, str]] = []

    for payload_path in sorted(root.rglob("payload.json")):
        meta_path = payload_path.parent / "metadata.json"
        if not meta_path.exists():
            continue

        try:
            meta = json.loads(meta_path.read_bytes().decode("utf-8", errors="replace"))
        except Exception:
            continue

        if meta.get("access_status") != "verified":
            continue

        # Only process FA section payloads, not mapping or search-bar
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
            continue

        codes = _metric_codes_from_fa_payload(payload)
        if not codes:
            continue

        covered = sum(1 for c in codes if c in mapping_index)
        run_id = _extract_run_id(payload_path)
        results.append(
            {
                "probe_run_id": run_id,
                "symbol": symbol,
                "section": section,
                "total_codes": str(len(codes)),
                "covered_codes": str(covered),
                "coverage_pct": f"{100 * covered / len(codes):.1f}",
                "probe_dir_name": payload_path.parent.name,
            }
        )

    results.sort(key=lambda r: (r["symbol"], r["section"]))
    return results


def _extract_run_id(payload_path: Path) -> str:
    """Extract the run_id path component from a probe payload path."""
    for part in payload_path.parts:
        if part.startswith("run_id="):
            return part[len("run_id="):]
    return ""


# ---------------------------------------------------------------------------
# CSV output helper
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
            "Offline dry-run parser for Vietcap IQ FA metric mapping. "
            "No network calls. No DB writes."
        )
    )
    parser.add_argument(
        "--mapping-payload",
        default=_DEFAULT_MAPPING_PAYLOAD,
        help="Path to the saved mapping payload.json",
    )
    parser.add_argument(
        "--output-mapping",
        default="data/processed/vietcap_iq/fa_metric_mapping.csv",
        help="Output CSV for parsed mapping entries",
    )
    parser.add_argument(
        "--probe-dir",
        default=None,
        help="Root directory to scan for saved FA probe payloads (coverage report)",
    )
    parser.add_argument(
        "--output-coverage",
        default="data/processed/vietcap_iq/fa_metric_mapping_coverage.csv",
        help="Output CSV for coverage report (written only when --probe-dir is given)",
    )
    args = parser.parse_args(argv)

    try:
        payload = load_mapping_payload(args.mapping_payload)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    rows = parse_mapping_entries(payload)
    _write_csv(rows, _MAPPING_COLUMNS, Path(args.output_mapping))

    non_header = sum(1 for r in rows if r["is_header"] == "false")
    header_count = len(rows) - non_header
    sections = sorted({r["section"] for r in rows})

    print(f"Mapping parsed: {non_header} metric codes, {header_count} section headers")
    print(f"Sections: {', '.join(sections)}")
    print(f"Output: {args.output_mapping}")

    if args.probe_dir:
        mapping_index = build_mapping_index(rows)
        coverage_rows = compute_coverage(mapping_index, args.probe_dir)
        _write_csv(coverage_rows, _COVERAGE_COLUMNS, Path(args.output_coverage))
        print(f"Coverage: {args.output_coverage} ({len(coverage_rows)} probe(s) scanned)")


if __name__ == "__main__":
    main()
