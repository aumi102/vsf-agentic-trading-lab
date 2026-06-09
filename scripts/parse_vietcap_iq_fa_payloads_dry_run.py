from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = ROOT / "data/raw/httpx_diagnostic/source=vietcap_iq"
DEFAULT_OUTPUT_ROOT = ROOT / "data/processed/fa_dry_run"

# Fields that are period/row metadata, not metric values.
METADATA_FIELDS: frozenset[str] = frozenset({
    "ticker",
    "organCode",
    "yearReport",
    "lengthReport",
    "publicDate",
    "updateDate",
    "createDate",
})

_LONG_FORMAT_COLUMNS: list[str] = [
    "source_name",
    "symbol",
    "organ_code",
    "statement_type",
    "section",
    "period_type",
    "fiscal_year",
    "fiscal_quarter",
    "length_report",
    "source_period_label",
    "public_date",
    "public_date_semantics",
    "line_item_code",
    "line_item_name",
    "value",
    "value_status",
    "unit",
    "currency",
    "source_run_id",
    "source_dataset",
    "source_content_hash",
    "source_payload_path",
    "source_server_datetime",
    "crawled_at",
    "availability_status",
    "parser_warning",
]

PUBLIC_DATE_SEMANTICS: str = "candidate_availability_publication_date_unconfirmed"
AVAILABILITY_STATUS: str = "unknown_until_publicDate_validated"
WARNING_NO_NAME: str = "line_item_name_unknown_no_mapping"
WARNING_PIT: str = "publicDate_semantics_unconfirmed"
WARNING_CODE_TICKER_DIFFER: str = "organCode_ticker_differ"


def _section_from_metadata_or_url(meta: dict) -> str:
    """Return section from metadata['section'] field; fall back to URL parsing."""
    section = meta.get("section", "")
    if section:
        return section
    url = meta.get("target_url", "")
    if "section=" in url:
        return url.split("section=")[-1].split("&")[0]
    return ""


def _value_status(v: Any) -> str:
    if v is None:
        return "missing"
    try:
        if float(v) == 0.0:
            return "zero"
    except (TypeError, ValueError):
        pass
    return "present"


def _get_metric_columns(row: dict) -> list[str]:
    return [k for k in row if k not in METADATA_FIELDS]


def melt_period_rows(
    rows: list[dict],
    period_type: str,
    meta: dict,
    server_datetime: str,
) -> tuple[list[dict], list[dict]]:
    """Convert wide-format period rows into long-format fact records.

    Returns (facts, errors). Errors are structural issues that cause a row to be skipped.
    """
    symbol = meta.get("symbol") or ""
    section = _section_from_metadata_or_url(meta)
    statement_type = section
    source_run_id = meta.get("run_id") or ""
    source_dataset = meta.get("dataset") or ""
    source_content_hash = meta.get("content_hash") or ""
    source_payload_path = str(meta.get("raw_path") or "")
    crawled_at = meta.get("crawled_at") or ""

    facts: list[dict] = []
    errors: list[dict] = []

    for i, row in enumerate(rows):
        organ_code = row.get("organCode") or ""
        ticker = row.get("ticker") or ""
        year_report = row.get("yearReport")
        length_report = row.get("lengthReport")
        public_date = row.get("publicDate") or ""

        if year_report is None:
            errors.append({
                "run_id": source_run_id,
                "symbol": symbol,
                "section": section,
                "period_type": period_type,
                "row_index": i,
                "error": "missing_yearReport",
            })
            continue

        if length_report is None:
            errors.append({
                "run_id": source_run_id,
                "symbol": symbol,
                "section": section,
                "period_type": period_type,
                "row_index": i,
                "error": "missing_lengthReport",
            })
            continue

        if period_type == "quarter":
            if length_report not in (1, 2, 3, 4):
                errors.append({
                    "run_id": source_run_id,
                    "symbol": symbol,
                    "section": section,
                    "period_type": period_type,
                    "row_index": i,
                    "error": f"unexpected_lengthReport_for_quarter:{length_report}",
                })
                continue
            fiscal_quarter: int | str = length_report
            source_period_label = f"{year_report}Q{length_report}"
        else:
            if length_report != 5:
                errors.append({
                    "run_id": source_run_id,
                    "symbol": symbol,
                    "section": section,
                    "period_type": period_type,
                    "row_index": i,
                    "error": f"unexpected_lengthReport_for_year:{length_report}",
                })
                continue
            fiscal_quarter = ""
            source_period_label = f"{year_report}Y"

        row_warnings: list[str] = []
        if organ_code and ticker and organ_code != ticker:
            row_warnings.append(WARNING_CODE_TICKER_DIFFER)

        metric_cols = _get_metric_columns(row)

        for col in metric_cols:
            value = row[col]
            vs = _value_status(value)
            warnings = row_warnings + [WARNING_NO_NAME]
            if public_date:
                warnings.append(WARNING_PIT)

            facts.append({
                "source_name": "vietcap_iq",
                "symbol": symbol,
                "organ_code": organ_code,
                "statement_type": statement_type,
                "section": section,
                "period_type": period_type,
                "fiscal_year": year_report,
                "fiscal_quarter": fiscal_quarter,
                "length_report": length_report,
                "source_period_label": source_period_label,
                "public_date": public_date,
                "public_date_semantics": PUBLIC_DATE_SEMANTICS,
                "line_item_code": col,
                "line_item_name": "",
                "value": "" if value is None else value,
                "value_status": vs,
                "unit": "",
                "currency": "",
                "source_run_id": source_run_id,
                "source_dataset": source_dataset,
                "source_content_hash": source_content_hash,
                "source_payload_path": source_payload_path,
                "source_server_datetime": server_datetime,
                "crawled_at": crawled_at,
                "availability_status": AVAILABILITY_STATUS,
                "parser_warning": "|".join(warnings),
            })

    return facts, errors


def parse_payload(
    meta: dict,
    *,
    fail_on_missing_public_date: bool = False,
) -> tuple[list[dict], list[dict], dict]:
    """Parse a single saved payload file into long-format fact records.

    Returns (facts, errors, stats).
    """
    raw_path = Path(meta["raw_path"])
    payload = json.loads(raw_path.read_text(encoding="utf-8"))

    data = payload.get("data") or {}
    quarters: list[dict] = data.get("quarters") or []
    years: list[dict] = data.get("years") or []
    server_datetime: str = payload.get("serverDateTime") or ""

    q_facts, q_errors = melt_period_rows(quarters, "quarter", meta, server_datetime)
    y_facts, y_errors = melt_period_rows(years, "year", meta, server_datetime)

    facts = q_facts + y_facts
    errors = q_errors + y_errors

    q_pd_nonnull = sum(1 for r in quarters if r.get("publicDate"))
    y_pd_nonnull = sum(1 for r in years if r.get("publicDate"))

    if fail_on_missing_public_date:
        missing = [r for r in (quarters + years) if not r.get("publicDate")]
        if missing:
            raise ValueError(
                f"run_id={meta.get('run_id')}: {len(missing)} rows missing publicDate"
            )

    first_row = (quarters or years or [None])[0]
    metric_col_count = len(_get_metric_columns(first_row)) if first_row else 0

    stats: dict = {
        "run_id": meta.get("run_id", ""),
        "symbol": meta.get("symbol", ""),
        "section": _section_from_metadata_or_url(meta),
        "dataset": meta.get("dataset", ""),
        "quarter_rows_read": len(quarters),
        "year_rows_read": len(years),
        "metric_column_count": metric_col_count,
        "output_fact_rows": len(facts),
        "q_publicdate_nonnull": q_pd_nonnull,
        "y_publicdate_nonnull": y_pd_nonnull,
    }

    return facts, errors, stats


def discover_payloads(
    input_root: Path,
    run_ids: list[str],
    datasets: list[str],
) -> list[dict]:
    """Discover fa-direct verified payloads under input_root.

    If run_ids is non-empty, restrict to those run directories.
    """
    if run_ids:
        run_dirs = [input_root / f"run_id={rid}" for rid in run_ids]
    else:
        if not input_root.exists():
            return []
        run_dirs = sorted(
            (d for d in input_root.iterdir() if d.is_dir()),
            key=lambda d: d.name,
        )

    found: list[dict] = []
    for run_dir in run_dirs:
        if not run_dir.exists():
            continue
        dataset_dirs = sorted(
            (d for d in run_dir.iterdir() if d.is_dir()),
            key=lambda d: d.name,
        )
        for dataset_dir in dataset_dirs:
            if datasets and dataset_dir.name not in datasets:
                continue
            meta_path = dataset_dir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if meta.get("diagnostic_target") != "fa-direct":
                continue
            if meta.get("access_status") != "verified":
                continue
            raw = meta.get("raw_path", "")
            if not raw or not Path(raw).exists():
                continue
            found.append(meta)

    return found


def generate_report(
    all_stats: list[dict],
    all_facts: list[dict],
    all_errors: list[dict],
) -> str:
    lines: list[str] = [
        "# Vietcap IQ FA Parser Dry-Run Report",
        "",
        "**Parser mode:** dry-run — local output only. No DB write. No backtest. No full-universe fetch.",
        "",
        "## Input Payloads",
        "",
        "| run_id | symbol | section | dataset | Q rows | Y rows | metric cols |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for s in all_stats:
        lines.append(
            f"| `{s['run_id']}` | `{s['symbol']}` | `{s['section']}` "
            f"| `{s['dataset']}` "
            f"| {s['quarter_rows_read']} | {s['year_rows_read']} "
            f"| {s['metric_column_count']} |"
        )

    total = sum(s["output_fact_rows"] for s in all_stats)
    n_present = sum(1 for f in all_facts if f["value_status"] == "present")
    n_zero = sum(1 for f in all_facts if f["value_status"] == "zero")
    n_missing = sum(1 for f in all_facts if f["value_status"] == "missing")

    lines += [
        "",
        "## Output Facts",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Total fact rows | {total:,} |",
        f"| `value_status=present` | {n_present:,} |",
        f"| `value_status=zero` | {n_zero:,} |",
        f"| `value_status=missing` (null) | {n_missing:,} |",
        f"| Parse errors | {len(all_errors):,} |",
        "",
        "## publicDate Coverage",
        "",
        "| run_id | symbol | section | Q publicDate non-null | Y publicDate non-null |",
        "|---|---|---|---:|---:|",
    ]
    for s in all_stats:
        lines.append(
            f"| `{s['run_id']}` | `{s['symbol']}` | `{s['section']}` "
            f"| {s['q_publicdate_nonnull']}/{s['quarter_rows_read']} "
            f"| {s['y_publicdate_nonnull']}/{s['year_rows_read']} |"
        )

    lines += [
        "",
        "## Parser Warnings",
        "",
        "All fact rows carry at least these warnings in `parser_warning`:",
        "",
        f"- `{WARNING_NO_NAME}` — metric code to human-readable name mapping not available in payload",
        f"- `{WARNING_PIT}` — `publicDate` present but exact semantics unconfirmed",
        f"- `{WARNING_CODE_TICKER_DIFFER}` — emitted per row when `organCode` ≠ `ticker`",
        "",
        "## Parser-Readiness Assessment",
        "",
        "| Item | Status |",
        "|---|---|",
        "| Raw payloads parsed | **Yes** |",
        "| Wide-to-long pivot | **Done** |",
        "| Period encoding (`yearReport` + `lengthReport`) | **Done** |",
        "| `publicDate` copied | **Yes** — as candidate field only |",
        "| `publicDate` PIT semantics | **Unconfirmed** |",
        "| Line item names | **Not available** — opaque codes only |",
        "| DB write | **Not implemented** |",
        "| Full-universe fetch | **Not implemented** |",
        "| Backtest | **Not implemented** |",
        "",
        "## PIT / Backtest Warning",
        "",
        "> **`publicDate`** is present and non-null for all rows in all tested payloads. "
        "It is a **candidate availability/publication field** only. "
        "Its exact semantics — whether it represents the exchange filing date, "
        "the auditor sign-off date, or the date Vietcap entered the data — "
        "have not been confirmed against authoritative filing records. "
        "Do not use this data for historical point-in-time backtest until "
        "`publicDate` semantics are confirmed.",
        "",
    ]

    return "\n".join(lines)


def write_outputs(
    facts: list[dict],
    errors: list[dict],
    report: str,
    output_root: Path,
    fmt: str,
) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    if fmt == "jsonl":
        facts_path = output_root / "financial_statement_facts.jsonl"
        with facts_path.open("w", encoding="utf-8") as fh:
            for row in facts:
                jsonl_row = dict(row)
                if jsonl_row.get("value") == "":
                    jsonl_row["value"] = None
                if jsonl_row.get("fiscal_quarter") == "":
                    jsonl_row["fiscal_quarter"] = None
                fh.write(json.dumps(jsonl_row, ensure_ascii=False) + "\n")
    else:
        facts_path = output_root / "financial_statement_facts.csv"
        with facts_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_LONG_FORMAT_COLUMNS)
            writer.writeheader()
            writer.writerows(facts)
    paths["facts"] = str(facts_path)

    report_path = output_root / "financial_statement_parse_report.md"
    report_path.write_text(report, encoding="utf-8")
    paths["report"] = str(report_path)

    if errors:
        errors_path = output_root / "financial_statement_parse_errors.csv"
        error_cols = ["run_id", "symbol", "section", "period_type", "row_index", "error"]
        with errors_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=error_cols)
            writer.writeheader()
            writer.writerows(errors)
        paths["errors"] = str(errors_path)

    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Parse saved Vietcap IQ FA payloads into long-format local dry-run output. "
            "No DB write. No backtest. No live network requests."
        )
    )
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument(
        "--run-id",
        action="append",
        dest="run_ids",
        default=[],
        metavar="RUN_ID",
        help="Run ID to parse (repeatable; also accepts comma-separated).",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        default=[],
        metavar="DATASET",
        help="Dataset name filter (repeatable; also accepts comma-separated).",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--format", choices=["csv", "jsonl"], default="csv")
    parser.add_argument("--max-rows", type=int, default=None, help="Truncate output for preview.")
    parser.add_argument(
        "--fail-on-missing-public-date",
        action="store_true",
        default=False,
    )
    args = parser.parse_args(argv)

    run_ids: list[str] = []
    for v in args.run_ids:
        run_ids.extend(x.strip() for x in v.split(",") if x.strip())

    datasets: list[str] = []
    for v in args.datasets:
        datasets.extend(x.strip() for x in v.split(",") if x.strip())

    metas = discover_payloads(args.input_root, run_ids, datasets)
    if not metas:
        print(
            "No matching fa-direct verified payloads found. "
            "Check --input-root and --run-id.",
            file=sys.stderr,
        )
        sys.exit(1)

    all_facts: list[dict] = []
    all_errors: list[dict] = []
    all_stats: list[dict] = []

    for meta in metas:
        try:
            facts, errors, stats = parse_payload(
                meta,
                fail_on_missing_public_date=args.fail_on_missing_public_date,
            )
        except Exception as exc:
            print(f"ERROR parsing run_id={meta.get('run_id')}: {exc}", file=sys.stderr)
            continue
        all_facts.extend(facts)
        all_errors.extend(errors)
        all_stats.append(stats)
        print(
            f"  parsed run_id={stats['run_id']} symbol={stats['symbol']} "
            f"section={stats['section']} "
            f"-> {stats['output_fact_rows']:,} fact rows"
        )

    # Generate report before any max_rows truncation so counts are accurate.
    report = generate_report(all_stats, all_facts, all_errors)

    if args.max_rows is not None:
        all_facts = all_facts[: args.max_rows]

    paths = write_outputs(all_facts, all_errors, report, args.output_root, args.format)

    print(f"\nOutput written to: {args.output_root}")
    for key, path in paths.items():
        print(f"  {key}: {path}")

    total = sum(s["output_fact_rows"] for s in all_stats)
    n_present = sum(1 for f in all_facts if f["value_status"] == "present")
    n_zero = sum(1 for f in all_facts if f["value_status"] == "zero")
    n_missing = sum(1 for f in all_facts if f["value_status"] == "missing")
    print(
        f"\nTotal fact rows (full parse): {total:,} "
        f"| present: {n_present:,}  zero: {n_zero:,}  missing: {n_missing:,} "
        f"| errors: {len(all_errors):,}"
    )


if __name__ == "__main__":
    main()
