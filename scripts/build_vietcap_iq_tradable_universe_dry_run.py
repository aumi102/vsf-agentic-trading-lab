from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TRADABLE_FLOORS = {"HOSE", "HNX", "UPCOM"}
SPECIAL_FLOORS = {"OTC", "OTHER", "STOP"}
REQUIRED_INPUTS = [
    "securities_master.csv",
    "exchange_listings.csv",
    "symbol_universe.csv",
    "instrument_universe.csv",
    "validation_summary.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Vietcap IQ tradable-universe candidate dry-run subset.")
    parser.add_argument("--vietcap-universe-dir", default="", help="Input Vietcap IQ universe dry-run directory. Defaults to latest.")
    parser.add_argument("--output-dir", default="", help="Output directory. Defaults to <vietcap-universe-dir>/tradable_universe.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        input_dir = Path(args.vietcap_universe_dir) if args.vietcap_universe_dir else latest_run_dir(ROOT / "data/processed/dry_run/vietcap_iq_universe")
        output_dir = Path(args.output_dir) if args.output_dir else input_dir / "tradable_universe"
        result = build_tradable_universe(input_dir=input_dir, output_dir=output_dir)
    except Exception as exc:
        print(f"vietcap_iq_tradable_universe_dry_run_failed={exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    print(f"input_dir={input_dir}")
    print(f"output_dir={output_dir}")
    print(f"run_status={summary['run_status']}")
    print(f"tradable_row_count={summary['tradable_row_count']}")
    print(f"tradable_unique_symbols={summary['tradable_unique_symbols']}")
    print(f"excluded_row_count={summary['excluded_row_count']}")
    print(f"excluded_unique_symbols={summary['excluded_unique_symbols']}")
    print(f"included_floor_counts={json.dumps(summary['included_floor_counts'], ensure_ascii=False, sort_keys=True)}")
    print(f"excluded_floor_counts={json.dumps(summary['excluded_floor_counts'], ensure_ascii=False, sort_keys=True)}")
    print(f"tradable_universe_summary={result['summary_path']}")
    print(f"tradable_universe_report={result['report_path']}")
    return 0


def build_tradable_universe(*, input_dir: Path, output_dir: Path) -> dict[str, Any]:
    validate_input_dir(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    securities = pd.read_csv(input_dir / "securities_master.csv")
    listings = pd.read_csv(input_dir / "exchange_listings.csv")
    symbols = pd.read_csv(input_dir / "symbol_universe.csv")
    instruments = pd.read_csv(input_dir / "instrument_universe.csv")
    source_summary = json.loads((input_dir / "validation_summary.json").read_text(encoding="utf-8"))

    decisions = build_filter_decisions(symbols)
    included = decisions[decisions["include_tradable_candidate"]].copy()
    excluded = decisions[~decisions["include_tradable_candidate"]].copy()

    included_indexes = set(included["raw_row_index"])
    securities_tradable = securities[securities["raw_row_index"].isin(included_indexes)].copy()
    listings_tradable = listings[listings["raw_row_index"].isin(included_indexes)].copy()
    symbols_tradable = symbols[symbols["raw_row_index"].isin(included_indexes)].copy()
    instruments_tradable = instruments[instruments["raw_row_index"].isin(included_indexes)].copy()

    duplicate_after_filter = int(symbols_tradable.duplicated(subset=["symbol", "exchange_or_floor"], keep=False).sum()) if not symbols_tradable.empty else 0
    if symbols_tradable.empty:
        run_status = "fail"
        run_reasons = ["no_tradable_rows_after_filter"]
    elif duplicate_after_filter > 0:
        run_status = "fail"
        run_reasons = ["duplicate_symbol_floor_after_filter"]
    elif not excluded.empty:
        run_status = "warn"
        run_reasons = ["rows_excluded_for_audit"]
    else:
        run_status = "pass"
        run_reasons = []

    excluded_audit = excluded.copy()
    excluded_audit = excluded_audit[
        [
            "raw_row_index",
            "symbol",
            "exchange_or_floor",
            "display_name",
            "company_name",
            "company_type_code",
            "is_bank",
            "is_index",
            "quality_status",
            "quality_reasons",
            "exclusion_reasons",
        ]
    ]

    output_paths = {
        "securities_master_tradable": output_dir / "securities_master_tradable.csv",
        "exchange_listings_tradable": output_dir / "exchange_listings_tradable.csv",
        "symbol_universe_tradable": output_dir / "symbol_universe_tradable.csv",
        "instrument_universe_tradable": output_dir / "instrument_universe_tradable.csv",
        "excluded_universe_rows": output_dir / "excluded_universe_rows.csv",
    }
    securities_tradable.to_csv(output_paths["securities_master_tradable"], index=False)
    listings_tradable.to_csv(output_paths["exchange_listings_tradable"], index=False)
    symbols_tradable.to_csv(output_paths["symbol_universe_tradable"], index=False)
    instruments_tradable.to_csv(output_paths["instrument_universe_tradable"], index=False)
    excluded_audit.to_csv(output_paths["excluded_universe_rows"], index=False)

    summary = build_summary(
        input_dir=input_dir,
        output_dir=output_dir,
        source_summary=source_summary,
        symbols=symbols,
        symbols_tradable=symbols_tradable,
        excluded=excluded,
        duplicate_after_filter=duplicate_after_filter,
        run_status=run_status,
        run_reasons=run_reasons,
    )
    summary_path = output_dir / "tradable_universe_summary.json"
    report_path = output_dir / "tradable_universe_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(build_report(summary, output_paths), encoding="utf-8")
    return {"summary": summary, "summary_path": summary_path, "report_path": report_path, "output_paths": output_paths}


def build_filter_decisions(symbols: pd.DataFrame) -> pd.DataFrame:
    rows = symbols.copy()
    rows["symbol_norm"] = rows.get("symbol", pd.Series(dtype=object)).map(_normalize_text)
    rows["floor_norm"] = rows.get("exchange_or_floor", pd.Series(dtype=object)).map(_normalize_text)
    rows["is_index_bool"] = rows.get("is_index", pd.Series(dtype=object)).map(_as_bool)
    rows["quality_status_norm"] = rows.get("quality_status", pd.Series(dtype=object)).map(lambda value: str(value).strip().lower() if pd.notna(value) else "")

    reasons: list[str] = []
    include: list[bool] = []
    for _, row in rows.iterrows():
        row_reasons: list[str] = []
        if not row["symbol_norm"]:
            row_reasons.append("excluded_missing_symbol")
        if not row["floor_norm"]:
            row_reasons.append("excluded_missing_floor")
        elif row["floor_norm"] not in TRADABLE_FLOORS:
            row_reasons.append("excluded_non_tradable_floor")
        if row["is_index_bool"] is True:
            row_reasons.append("excluded_index_candidate")
        if row["quality_status_norm"] == "fail":
            row_reasons.append("excluded_quality_fail")
        reasons.append(";".join(row_reasons))
        include.append(len(row_reasons) == 0)
    rows["exclusion_reasons"] = reasons
    rows["include_tradable_candidate"] = include
    return rows


def build_summary(
    *,
    input_dir: Path,
    output_dir: Path,
    source_summary: dict[str, Any],
    symbols: pd.DataFrame,
    symbols_tradable: pd.DataFrame,
    excluded: pd.DataFrame,
    duplicate_after_filter: int,
    run_status: str,
    run_reasons: list[str],
) -> dict[str, Any]:
    excluded_reason_counts: dict[str, int] = {}
    for value in excluded.get("exclusion_reasons", pd.Series(dtype=object)).dropna():
        for reason in str(value).split(";"):
            if reason:
                excluded_reason_counts[reason] = excluded_reason_counts.get(reason, 0) + 1

    return {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "run_status": run_status,
        "run_reasons": run_reasons,
        "source_vietcap_universe_dir": str(input_dir),
        "output_dir": str(output_dir),
        "source_parser_run_id": source_summary.get("run_id"),
        "full_row_count": int(len(symbols)),
        "full_unique_symbols": int(_unique_count(symbols.get("symbol"))),
        "tradable_row_count": int(len(symbols_tradable)),
        "tradable_unique_symbols": int(_unique_count(symbols_tradable.get("symbol"))),
        "excluded_row_count": int(len(excluded)),
        "excluded_unique_symbols": int(_unique_count(excluded.get("symbol"))),
        "included_floor_counts": _value_counts(symbols_tradable.get("exchange_or_floor")),
        "excluded_floor_counts": _value_counts(excluded.get("exchange_or_floor")),
        "excluded_reason_counts": excluded_reason_counts,
        "quality_status_counts_before_filter": _value_counts(symbols.get("quality_status")),
        "quality_status_counts_after_filter": _value_counts(symbols_tradable.get("quality_status")),
        "duplicate_symbol_floor_fail_count": int((symbols.get("quality_reasons", pd.Series(dtype=object)).fillna("").str.contains("duplicate_symbol_exchange_or_floor")).sum()),
        "duplicate_symbol_floor_after_filter_count": duplicate_after_filter,
        "index_excluded_count": int((excluded.get("exclusion_reasons", pd.Series(dtype=object)).fillna("").str.contains("excluded_index_candidate")).sum()),
        "otc_other_stop_excluded_count": int(
            excluded.get("exchange_or_floor", pd.Series(dtype=object)).fillna("").astype(str).str.upper().isin(SPECIAL_FLOORS).sum()
        ),
        "filter_rules": {
            "included_floors": sorted(TRADABLE_FLOORS),
            "excluded_floors": sorted(SPECIAL_FLOORS),
            "excluded_if_is_index": True,
            "excluded_if_quality_fail": True,
        },
        "limitations": [
            "This is a dry run only. No database write or backtest was performed.",
            "OTC, OTHER, STOP, index, and quality-fail rows are preserved in excluded_universe_rows.csv.",
            "Trading eligibility and Vietcap IQ field semantics still need review before canonical promotion.",
        ],
    }


def build_report(summary: dict[str, Any], output_paths: dict[str, Path]) -> str:
    lines = [
        "# Vietcap IQ Tradable Universe Dry-Run Report",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- run_status: `{summary['run_status']}`",
        f"- source_vietcap_universe_dir: `{summary['source_vietcap_universe_dir']}`",
        f"- output_dir: `{summary['output_dir']}`",
        "",
        "## Output Files",
        "",
    ]
    for label, path in output_paths.items():
        lines.append(f"- {label}: `{path}`")

    lines.extend(
        [
            "",
            "## Counts",
            "",
            "| Metric | Count |",
            "|---|---:|",
            f"| Full rows | {summary['full_row_count']} |",
            f"| Full unique symbols | {summary['full_unique_symbols']} |",
            f"| Tradable rows | {summary['tradable_row_count']} |",
            f"| Tradable unique symbols | {summary['tradable_unique_symbols']} |",
            f"| Excluded rows | {summary['excluded_row_count']} |",
            f"| Excluded unique symbols | {summary['excluded_unique_symbols']} |",
            f"| Duplicate symbol + floor rows after filter | {summary['duplicate_symbol_floor_after_filter_count']} |",
            f"| Index excluded rows | {summary['index_excluded_count']} |",
            f"| OTC/OTHER/STOP excluded rows | {summary['otc_other_stop_excluded_count']} |",
            "",
            "## Included Floor Counts",
            "",
            "| Floor | Count |",
            "|---|---:|",
        ]
    )
    for floor, count in summary["included_floor_counts"].items():
        lines.append(f"| `{floor}` | {count} |")

    lines.extend(["", "## Excluded Floor Counts", "", "| Floor | Count |", "|---|---:|"])
    for floor, count in summary["excluded_floor_counts"].items():
        lines.append(f"| `{floor}` | {count} |")

    lines.extend(["", "## Exclusion Reasons", "", "| Reason | Count |", "|---|---:|"])
    for reason, count in sorted(summary["excluded_reason_counts"].items()):
        lines.append(f"| `{reason}` | {count} |")

    lines.extend(["", "## Limitations", ""])
    for limitation in summary["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def validate_input_dir(input_dir: Path) -> None:
    missing = [name for name in REQUIRED_INPUTS if not (input_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing required Vietcap IQ universe dry-run files in {input_dir}: {', '.join(missing)}")


def latest_run_dir(base_dir: Path) -> Path:
    if not base_dir.exists():
        raise FileNotFoundError(f"Vietcap IQ universe dry-run base directory not found: {base_dir}")
    candidates = [path for path in base_dir.iterdir() if path.is_dir() and all((path / name).exists() for name in REQUIRED_INPUTS)]
    if not candidates:
        raise FileNotFoundError(f"No complete Vietcap IQ universe dry-run directory found under {base_dir}.")
    candidates.sort(key=lambda path: path.name, reverse=True)
    return candidates[0]


def _normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().upper()


def _as_bool(value: object) -> bool | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _value_counts(series: pd.Series | None) -> dict[str, int]:
    if series is None:
        return {}
    return {str(key): int(value) for key, value in series.fillna("UNKNOWN").astype(str).value_counts().sort_index().items()}


def _unique_count(series: pd.Series | None) -> int:
    if series is None:
        return 0
    return int(series.dropna().astype(str).str.strip().str.upper().replace("", pd.NA).dropna().nunique())


if __name__ == "__main__":
    raise SystemExit(main())
