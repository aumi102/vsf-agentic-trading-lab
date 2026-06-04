from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.parsers.vietcap_iq_universe_parser import parse_vietcap_iq_universe_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse a saved Vietcap IQ search-bar universe probe into dry-run canonical CSV outputs.")
    parser.add_argument("--raw-path", default="", help="Optional raw Vietcap IQ search-bar JSON path.")
    parser.add_argument("--metadata-path", default="", help="Optional Vietcap IQ search-bar metadata JSON path.")
    parser.add_argument("--raw-base-dir", default="data/raw/source_probe/source=vietcap_iq")
    parser.add_argument("--output-base-dir", default="data/processed/dry_run/vietcap_iq_universe")
    parser.add_argument("--hose-listed-universe-dir", default="", help="Optional HOSE listed-universe all-pages dry-run directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        raw_path, metadata_path = resolve_inputs(args)
        result = parse_vietcap_iq_universe_payload(raw_path=raw_path, metadata_path=metadata_path)
    except Exception as exc:
        print(f"vietcap_iq_universe_dry_run_failed={exc}", file=sys.stderr)
        return 1

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_base_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    securities_path = output_dir / "securities_master.csv"
    listings_path = output_dir / "exchange_listings.csv"
    universe_path = output_dir / "symbol_universe.csv"
    instruments_path = output_dir / "instrument_universe.csv"
    report_path = output_dir / "validation_report.md"
    summary_path = output_dir / "validation_summary.json"

    result.securities_master.to_csv(securities_path, index=False)
    result.exchange_listings.to_csv(listings_path, index=False)
    result.symbol_universe.to_csv(universe_path, index=False)
    result.instrument_universe.to_csv(instruments_path, index=False)

    hose_dir = Path(args.hose_listed_universe_dir) if args.hose_listed_universe_dir else discover_latest_hose_listed_universe_dir()
    overlap_summary = build_hose_overlap_summary(vietcap_symbols=result.symbol_universe["symbol"], hose_listed_universe_dir=hose_dir)

    summary = {
        **result.validation_summary,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "hose_overlap": overlap_summary,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(
        build_validation_report(summary, securities_path, listings_path, universe_path, instruments_path),
        encoding="utf-8",
    )

    print(f"run_id={run_id}")
    print(f"raw_path={raw_path}")
    print(f"metadata_path={metadata_path}")
    print(f"output_dir={output_dir}")
    print(f"securities_master={securities_path}")
    print(f"exchange_listings={listings_path}")
    print(f"symbol_universe={universe_path}")
    print(f"instrument_universe={instruments_path}")
    print(f"validation_report={report_path}")
    print(f"validation_summary={summary_path}")
    print(f"row_count={summary['symbol_universe_count']}")
    print(f"floor_counts={json.dumps(summary['floor_counts'], ensure_ascii=False, sort_keys=True)}")
    print(f"quality_pass_count={summary['quality_pass_count']}")
    print(f"quality_warn_count={summary['quality_warn_count']}")
    print(f"quality_fail_count={summary['quality_fail_count']}")
    if overlap_summary.get("status") == "computed":
        print(f"hose_overlap_count={overlap_summary['overlap_count']}")
        print(f"hose_symbols_missing_from_vietcap={overlap_summary['hose_symbols_missing_from_vietcap_count']}")
        print(f"vietcap_symbols_not_in_hose={overlap_summary['vietcap_symbols_not_in_hose_count']}")
    else:
        print(f"hose_overlap_status={overlap_summary['status']}")
    return 0


def resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path]:
    raw_path = Path(args.raw_path) if args.raw_path else None
    metadata_path = Path(args.metadata_path) if args.metadata_path else None

    if raw_path is not None and metadata_path is None:
        metadata_path = raw_path.parent / "metadata.json"
    if metadata_path is not None and raw_path is None:
        metadata = _read_metadata(metadata_path)
        raw_path = Path(metadata.get("raw_path", metadata_path.parent / "payload.json"))
    if raw_path is not None and metadata_path is not None:
        return raw_path, metadata_path

    return find_latest_verified_vietcap_search_bar_payload(Path(args.raw_base_dir))


def find_latest_verified_vietcap_search_bar_payload(base_dir: Path) -> tuple[Path, Path]:
    candidates: list[tuple[str, Path, Path]] = []
    for metadata_path in base_dir.glob("run_id=*/**/metadata.json"):
        metadata = _read_metadata(metadata_path)
        if metadata.get("source_name") != "vietcap_iq":
            continue
        if metadata.get("dataset") != "vietcap_iq_company_search_bar":
            continue
        if metadata.get("access_status") != "verified" or metadata.get("status") != "success":
            continue
        raw_path = Path(metadata.get("raw_path", ""))
        if not raw_path.exists():
            raw_path = metadata_path.parent / "payload.json"
        if raw_path.exists():
            candidates.append((str(metadata.get("crawled_at") or metadata_path.stat().st_mtime), raw_path, metadata_path))
    if not candidates:
        raise FileNotFoundError(f"No verified Vietcap IQ search-bar payload found under {base_dir}.")
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, raw_path, metadata_path = candidates[0]
    return raw_path, metadata_path


def discover_latest_hose_listed_universe_dir() -> Path | None:
    base = ROOT / "data/processed/dry_run/hose_listed_universe_all_pages"
    if not base.exists():
        return None
    dirs = [path for path in base.iterdir() if path.is_dir() and (path / "symbol_universe.csv").exists()]
    if not dirs:
        return None
    dirs.sort(key=lambda path: path.name, reverse=True)
    return dirs[0]


def build_hose_overlap_summary(vietcap_symbols: pd.Series, hose_listed_universe_dir: Path | None) -> dict[str, Any]:
    vietcap_set = set(_normalize_symbols(vietcap_symbols))
    summary: dict[str, Any] = {
        "status": "not_available",
        "vietcap_total_symbols": len(vietcap_set),
        "hose_symbols": None,
        "overlap_count": None,
        "hose_symbols_missing_from_vietcap_count": None,
        "vietcap_symbols_not_in_hose_count": None,
        "hose_symbols_missing_from_vietcap_examples": [],
        "vietcap_symbols_not_in_hose_examples": [],
        "hose_listed_universe_dir": str(hose_listed_universe_dir) if hose_listed_universe_dir else "",
    }
    if hose_listed_universe_dir is None:
        return summary
    path = hose_listed_universe_dir / "symbol_universe.csv"
    if not path.exists():
        return summary
    frame = pd.read_csv(path)
    if "symbol" not in frame.columns:
        return summary
    hose_set = set(_normalize_symbols(frame["symbol"]))
    overlap = vietcap_set.intersection(hose_set)
    hose_missing = sorted(hose_set.difference(vietcap_set))
    vietcap_not_hose = sorted(vietcap_set.difference(hose_set))
    summary.update(
        {
            "status": "computed",
            "hose_symbols": len(hose_set),
            "overlap_count": len(overlap),
            "hose_symbols_missing_from_vietcap_count": len(hose_missing),
            "vietcap_symbols_not_in_hose_count": len(vietcap_not_hose),
            "hose_symbols_missing_from_vietcap_examples": hose_missing[:20],
            "vietcap_symbols_not_in_hose_examples": vietcap_not_hose[:20],
        }
    )
    return summary


def _normalize_symbols(values: pd.Series) -> list[str]:
    return [
        str(value).strip().upper()
        for value in values.dropna()
        if str(value).strip()
    ]


def _read_metadata(metadata_path: Path) -> dict[str, Any]:
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def build_validation_report(
    summary: dict[str, Any],
    securities_path: Path,
    listings_path: Path,
    universe_path: Path,
    instruments_path: Path,
) -> str:
    lines = [
        "# Vietcap IQ Universe Dry-Run Validation Report",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- source_name: `{summary['source_name']}`",
        f"- dataset: `{summary['dataset']}`",
        f"- raw_path: `{summary['raw_path']}`",
        f"- metadata_path: `{summary['metadata_path']}`",
        f"- raw_content_hash: `{summary['raw_content_hash']}`",
        f"- parser_version: `{summary['parser_version']}`",
        f"- schema_version: `{summary['schema_version']}`",
        f"- securities_master: `{securities_path}`",
        f"- exchange_listings: `{listings_path}`",
        f"- symbol_universe: `{universe_path}`",
        f"- instrument_universe: `{instruments_path}`",
        "",
        "## Counts",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| JSON rows | {summary['json_row_count']} |",
        f"| Unique symbols | {summary['unique_symbol_count']} |",
        f"| Securities master rows | {summary['securities_master_count']} |",
        f"| Exchange listing rows | {summary['exchange_listings_count']} |",
        f"| Symbol universe rows | {summary['symbol_universe_count']} |",
        f"| Instrument universe rows | {summary['instrument_universe_count']} |",
        f"| Quality pass rows | {summary['quality_pass_count']} |",
        f"| Quality warn rows | {summary['quality_warn_count']} |",
        f"| Quality fail rows | {summary['quality_fail_count']} |",
        f"| Duplicate symbol + floor rows | {summary['duplicate_symbol_exchange_or_floor_count']} |",
        "",
        "## Floor Counts",
        "",
        "| Floor | Count |",
        "|---|---:|",
    ]
    for floor, count in summary.get("floor_counts", {}).items():
        lines.append(f"| `{floor}` | {count} |")

    lines.extend(["", "## Quality Reasons", ""])
    reason_counts = summary.get("quality_reason_counts", {})
    if reason_counts:
        lines.extend(["| Reason | Count |", "|---|---:|"])
        for reason, count in sorted(reason_counts.items()):
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("- none")

    overlap = summary.get("hose_overlap", {})
    lines.extend(
        [
            "",
            "## HOSE Overlap",
            "",
            f"- status: `{overlap.get('status')}`",
            f"- Vietcap symbols: `{overlap.get('vietcap_total_symbols')}`",
            f"- HOSE symbols: `{overlap.get('hose_symbols')}`",
            f"- overlap count: `{overlap.get('overlap_count')}`",
            f"- HOSE symbols missing from Vietcap: `{overlap.get('hose_symbols_missing_from_vietcap_count')}`",
            f"- Vietcap symbols not in HOSE: `{overlap.get('vietcap_symbols_not_in_hose_count')}`",
            "",
            "## Terms Notes",
            "",
            summary.get("terms_notes") or "none",
            "",
            "## Limitations",
            "",
        ]
    )
    for limitation in summary.get("limitations", []):
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
