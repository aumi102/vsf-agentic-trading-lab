from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/processed/vietcap_iq/fa_full_history_manifest.csv"

ALLOWED_SECTIONS: tuple[str, ...] = (
    "BALANCE_SHEET",
    "INCOME_STATEMENT",
    "CASH_FLOW",
)

ENDPOINT_TEMPLATE: str = (
    "iq.vietcap.com.vn/api/iq-insight-service/v1/company/{symbol}"
    "/financial-statement?section={section}"
)

_MANIFEST_COLUMNS: list[str] = [
    "symbol",
    "section",
    "request_type",
    "endpoint_template_or_name",
    "status",
    "reason",
    "requires_network",
    "requires_mapping",
    "requires_pit_validation",
    "planned_raw_storage_prefix",
    "notes",
]

_PROBE_STATUS: dict[str, str] = {
    "BALANCE_SHEET": "confirmed_200_vci_fpt",
    "INCOME_STATEMENT": "confirmed_200_vci_only",
    "CASH_FLOW": "not_yet_probed",
}

_SECTION_NOTES: dict[str, str] = {
    "BALANCE_SHEET": (
        "331 metric codes per row for VCI and FPT; "
        "nos* columns null for non-securities firms"
    ),
    "INCOME_STATEMENT": (
        "181 metric codes per row for VCI; "
        "FPT INCOME_STATEMENT not yet probed"
    ),
    "CASH_FLOW": (
        "Section not yet probed; assumed by analogy with confirmed sections; "
        "must be probed before adding to a live fetch run"
    ),
}

_OPEN_GATES: str = (
    "metric_mapping_incomplete"
    "|publicDate_PIT_unconfirmed"
    "|db_write_not_implemented"
    "|full_history_fetcher_not_implemented"
)


def _planned_raw_storage_prefix(symbol: str, section: str) -> str:
    return (
        "data/raw/vietcap_iq/fa/"
        f"source=vietcap_iq/section={section}/symbol={symbol}/"
    )


def _build_manifest(symbols: list[str], sections: list[str]) -> list[dict]:
    rows: list[dict] = []
    for symbol in sorted(symbols):
        for section in sorted(sections):
            probe_note = _PROBE_STATUS.get(section, "unknown")
            section_note = _SECTION_NOTES.get(section, "")
            notes = f"probe_status={probe_note}; {section_note}"
            rows.append({
                "symbol": symbol,
                "section": section,
                "request_type": "GET",
                "endpoint_template_or_name": ENDPOINT_TEMPLATE,
                "status": "planned_pending_gates",
                "reason": _OPEN_GATES,
                "requires_network": "yes",
                "requires_mapping": "yes",
                "requires_pit_validation": "yes",
                "planned_raw_storage_prefix": _planned_raw_storage_prefix(symbol, section),
                "notes": notes,
            })
    return rows


def _parse_csv_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Plan a Vietcap IQ FA full-history fetch manifest without making network requests. "
            "Output is a deterministic CSV describing what would be fetched and what gates remain open. "
            "No DB write. No backtest. No live HTTP requests."
        )
    )
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated list of ticker symbols, e.g. VCI,FPT",
    )
    parser.add_argument(
        "--sections",
        required=True,
        help=(
            f"Comma-separated FA sections. Allowed: {', '.join(ALLOWED_SECTIONS)}. "
            "Example: BALANCE_SHEET,INCOME_STATEMENT,CASH_FLOW"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output CSV path (default: data/processed/vietcap_iq/fa_full_history_manifest.csv)",
    )
    args = parser.parse_args(argv)

    symbols = _parse_csv_list(args.symbols)
    sections = _parse_csv_list(args.sections)

    if not symbols:
        print("ERROR: --symbols must be non-empty.", file=sys.stderr)
        sys.exit(1)

    unknown_sections = [s for s in sections if s not in ALLOWED_SECTIONS]
    if unknown_sections:
        print(
            f"ERROR: Unknown section(s): {unknown_sections}. "
            f"Allowed: {list(ALLOWED_SECTIONS)}",
            file=sys.stderr,
        )
        sys.exit(2)

    if not sections:
        print("ERROR: --sections must be non-empty.", file=sys.stderr)
        sys.exit(1)

    rows = _build_manifest(symbols, sections)

    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Manifest written: {output_path}")
    print(f"  rows: {len(rows)}")
    print(f"  symbols: {sorted(symbols)}")
    print(f"  sections: {sorted(sections)}")
    print(
        "\nNOTE: This is a dry-run planning manifest only. "
        "No network requests were made. "
        "All rows carry status=planned_pending_gates."
    )
    print(
        "Open gates: metric mapping incomplete; publicDate PIT unconfirmed; "
        "DB write not implemented; full-history fetcher not implemented."
    )


if __name__ == "__main__":
    main()
