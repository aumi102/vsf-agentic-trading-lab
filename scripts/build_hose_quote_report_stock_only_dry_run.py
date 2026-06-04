from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

METADATA_COLUMNS = [
    "security_id",
    "company_name",
    "display_text",
    "security_type_code",
    "listing_status_id",
    "listed_volume",
    "outstanding_volume",
    "listed_universe_run_id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build stock-only HOSE quote-report dry-run outputs by joining to the HOSE listed universe.")
    parser.add_argument("--quote-report-dir", default="", help="HOSE quote-report dry-run directory. Defaults to latest.")
    parser.add_argument("--listed-universe-dir", default="", help="HOSE listed-universe all-pages dry-run directory. Defaults to latest.")
    parser.add_argument("--output-dir", default="", help="Output directory. Defaults to <quote-report-dir>/stock_only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        quote_dir = Path(args.quote_report_dir) if args.quote_report_dir else latest_run_dir(ROOT / "data/processed/dry_run/hose_quote_report")
        listed_dir = Path(args.listed_universe_dir) if args.listed_universe_dir else latest_run_dir(ROOT / "data/processed/dry_run/hose_listed_universe_all_pages")
        output_dir = Path(args.output_dir) if args.output_dir else quote_dir / "stock_only"
        outputs = build_stock_only_outputs(quote_dir=quote_dir, listed_dir=listed_dir)
        write_outputs(outputs=outputs, output_dir=output_dir)
    except Exception as exc:
        print(f"hose_quote_report_stock_only_filter_failed={exc}", file=sys.stderr)
        return 1

    summary = outputs["summary"]
    print(f"quote_report_dir={quote_dir}")
    print(f"listed_universe_dir={listed_dir}")
    print(f"output_dir={output_dir}")
    print(f"daily_price_bars_stock_only={output_dir / 'daily_price_bars_stock_only.csv'}")
    print(f"daily_quote_reports_stock_only={output_dir / 'daily_quote_reports_stock_only.csv'}")
    print(f"market_ohlcv_snapshots_stock_only={output_dir / 'market_ohlcv_snapshots_stock_only.csv'}")
    print(f"excluded_non_stock_symbols={output_dir / 'excluded_non_stock_symbols.csv'}")
    print(f"stock_only_filter_summary={output_dir / 'stock_only_filter_summary.json'}")
    print(f"stock_only_filter_report={output_dir / 'stock_only_filter_report.md'}")
    print(f"stock_only_rows={summary['stock_only_rows']}")
    print(f"stock_only_unique_symbols={summary['stock_only_unique_symbols']}")
    print(f"excluded_rows={summary['excluded_rows']}")
    print(f"excluded_unique_symbols={summary['excluded_unique_symbols']}")
    return 0


def latest_run_dir(base_dir: Path) -> Path:
    if not base_dir.exists():
        raise FileNotFoundError(f"Missing dry-run base directory: {base_dir}")
    candidates = [path for path in base_dir.iterdir() if path.is_dir() and path.name != "stock_only"]
    if not candidates:
        raise FileNotFoundError(f"No dry-run output directories found under {base_dir}")
    return sorted(candidates, key=lambda path: path.name)[-1]


def build_stock_only_outputs(*, quote_dir: Path, listed_dir: Path) -> dict[str, Any]:
    quote_frames = {
        "daily_price_bars": pd.read_csv(quote_dir / "daily_price_bars.csv"),
        "daily_quote_reports": pd.read_csv(quote_dir / "daily_quote_reports.csv"),
        "market_ohlcv_snapshots": pd.read_csv(quote_dir / "market_ohlcv_snapshots.csv"),
    }
    quote_summary = json.loads((quote_dir / "validation_summary.json").read_text(encoding="utf-8"))

    universe_frames = {
        "symbol_universe": pd.read_csv(listed_dir / "symbol_universe.csv"),
        "securities_master": pd.read_csv(listed_dir / "securities_master.csv"),
        "exchange_listings": pd.read_csv(listed_dir / "exchange_listings.csv"),
    }

    validate_quote_report_identity(quote_frames["daily_quote_reports"])
    universe_metadata, universe_warnings = build_universe_metadata(universe_frames=universe_frames, listed_universe_run_id=listed_dir.name)
    stock_symbols = set(universe_metadata["symbol_norm"])

    stock_only_frames: dict[str, pd.DataFrame] = {}
    for name, frame in quote_frames.items():
        stock_only_frames[name] = enrich_stock_only_frame(frame, universe_metadata=universe_metadata, stock_symbols=stock_symbols)

    excluded = build_excluded_frame(quote_frames["daily_quote_reports"], stock_symbols=stock_symbols)
    summary = build_summary(
        quote_dir=quote_dir,
        listed_dir=listed_dir,
        quote_reports=quote_frames["daily_quote_reports"],
        symbol_universe=universe_frames["symbol_universe"],
        stock_only_quote_reports=stock_only_frames["daily_quote_reports"],
        excluded=excluded,
        quote_summary=quote_summary,
        universe_warnings=universe_warnings,
    )

    return {
        "daily_price_bars_stock_only": stock_only_frames["daily_price_bars"],
        "daily_quote_reports_stock_only": stock_only_frames["daily_quote_reports"],
        "market_ohlcv_snapshots_stock_only": stock_only_frames["market_ohlcv_snapshots"],
        "excluded_non_stock_symbols": excluded,
        "summary": summary,
    }


def validate_quote_report_identity(quote_reports: pd.DataFrame) -> None:
    required = {"symbol", "trading_date", "data_status"}
    missing = sorted(required - set(quote_reports.columns))
    if missing:
        raise ValueError(f"Quote-report input missing required columns: {missing}")
    duplicate_count = int(quote_reports.assign(symbol_norm=normalize_symbol_series(quote_reports["symbol"])).duplicated(
        subset=["symbol_norm", "trading_date", "data_status"],
        keep=False,
    ).sum())
    if duplicate_count:
        raise ValueError(f"Duplicate quote-report symbol + trading_date + data_status rows: {duplicate_count}")


def build_universe_metadata(*, universe_frames: dict[str, pd.DataFrame], listed_universe_run_id: str) -> tuple[pd.DataFrame, list[str]]:
    symbol_universe = with_symbol_norm(universe_frames["symbol_universe"])
    securities_master = with_symbol_norm(universe_frames["securities_master"])
    exchange_listings = with_symbol_norm(universe_frames["exchange_listings"])

    duplicate_count = int(symbol_universe.duplicated("symbol_norm", keep=False).sum())
    warnings: list[str] = []
    if duplicate_count:
        warnings.append(f"warning_duplicate_listed_universe_symbols_kept_first:{duplicate_count}")

    symbol_universe = symbol_universe.drop_duplicates("symbol_norm", keep="first")
    securities_master = securities_master.drop_duplicates("symbol_norm", keep="first")
    exchange_listings = exchange_listings.drop_duplicates("symbol_norm", keep="first")

    columns = ["symbol_norm", "symbol"]
    for column in ["display_text", "company_name", "security_type_code", "listing_status_id"]:
        if column in symbol_universe.columns:
            columns.append(column)
    metadata = symbol_universe[columns].copy()

    securities_columns = ["symbol_norm"]
    for column in ["security_id", "company_name", "outstanding_volume"]:
        if column in securities_master.columns:
            securities_columns.append(column)
    metadata = metadata.merge(
        securities_master[securities_columns],
        on="symbol_norm",
        how="left",
        suffixes=("", "_securities"),
    )
    if "company_name_securities" in metadata.columns:
        metadata["company_name"] = metadata.get("company_name").combine_first(metadata["company_name_securities"])
        metadata = metadata.drop(columns=["company_name_securities"])

    listing_columns = ["symbol_norm"]
    for column in ["security_type_code", "listing_status_id", "listed_volume"]:
        if column in exchange_listings.columns:
            listing_columns.append(column)
    metadata = metadata.merge(
        exchange_listings[listing_columns],
        on="symbol_norm",
        how="left",
        suffixes=("", "_listing"),
    )
    for column in ["security_type_code", "listing_status_id"]:
        listing_column = f"{column}_listing"
        if listing_column in metadata.columns:
            metadata[column] = metadata.get(column).combine_first(metadata[listing_column])
            metadata = metadata.drop(columns=[listing_column])

    metadata["listed_universe_run_id"] = listed_universe_run_id
    keep_columns = ["symbol_norm"] + [column for column in METADATA_COLUMNS if column in metadata.columns]
    return metadata[keep_columns].copy(), warnings


def enrich_stock_only_frame(frame: pd.DataFrame, *, universe_metadata: pd.DataFrame, stock_symbols: set[str]) -> pd.DataFrame:
    working = with_symbol_norm(frame)
    filtered = working[working["symbol_norm"].isin(stock_symbols)].copy()
    enriched = filtered.merge(universe_metadata, on="symbol_norm", how="left")
    enriched = enriched.drop(columns=["symbol_norm"])
    original_columns = [column for column in frame.columns if column in enriched.columns]
    metadata_columns = [column for column in METADATA_COLUMNS if column in enriched.columns]
    return enriched[original_columns + metadata_columns].copy()


def build_excluded_frame(quote_reports: pd.DataFrame, *, stock_symbols: set[str]) -> pd.DataFrame:
    working = with_symbol_norm(quote_reports)
    excluded = working[~working["symbol_norm"].isin(stock_symbols)].copy()
    excluded["exclusion_reason"] = "not_in_hose_listed_stock_universe"
    return excluded.drop(columns=["symbol_norm"])


def build_summary(
    *,
    quote_dir: Path,
    listed_dir: Path,
    quote_reports: pd.DataFrame,
    symbol_universe: pd.DataFrame,
    stock_only_quote_reports: pd.DataFrame,
    excluded: pd.DataFrame,
    quote_summary: dict[str, Any],
    universe_warnings: list[str],
) -> dict[str, Any]:
    quote_symbols = normalize_symbol_series(quote_reports["symbol"])
    listed_symbols = normalize_symbol_series(symbol_universe["symbol"])
    stock_symbols = normalize_symbol_series(stock_only_quote_reports["symbol"])
    excluded_symbols = normalize_symbol_series(excluded["symbol"]) if "symbol" in excluded.columns else pd.Series([], dtype=str)

    return {
        "quote_report_dir": str(quote_dir),
        "listed_universe_dir": str(listed_dir),
        "quote_report_run_id": quote_dir.name,
        "listed_universe_run_id": listed_dir.name,
        "quote_report_rows": int(len(quote_reports)),
        "quote_report_unique_symbols": int(quote_symbols.nunique()),
        "listed_universe_rows": int(len(symbol_universe)),
        "listed_universe_unique_symbols": int(listed_symbols.nunique()),
        "stock_only_rows": int(len(stock_only_quote_reports)),
        "stock_only_unique_symbols": int(stock_symbols.nunique()),
        "excluded_rows": int(len(excluded)),
        "excluded_unique_symbols": int(excluded_symbols.nunique()),
        "duplicate_symbol_count_quote_report": int(quote_reports.assign(symbol_norm=quote_symbols).duplicated(
            subset=["symbol_norm", "trading_date", "data_status"],
            keep=False,
        ).sum()),
        "duplicate_symbol_count_listed_universe": int(symbol_universe.assign(symbol_norm=listed_symbols).duplicated(
            subset=["symbol_norm"],
            keep=False,
        ).sum()),
        "data_status_counts": count_values(quote_reports, "data_status"),
        "quality_status_counts_before_filter": count_values(quote_reports, "quality_status"),
        "quality_status_counts_after_filter": count_values(stock_only_quote_reports, "quality_status"),
        "excluded_symbol_prefix_counts": dict(Counter(str(symbol)[:4] for symbol in excluded_symbols).most_common(20)),
        "excluded_symbol_examples": sorted(excluded_symbols.unique().tolist())[:80],
        "source_quality_reason_counts": quote_summary.get("quality_reason_counts", {}),
        "warnings": universe_warnings,
        "run_quality_status": "warn" if universe_warnings else "pass",
        "recommendation": "Use stock-only outputs for the first MVP ordinary-stock strategy; preserve full quote-report outputs for audit.",
    }


def write_outputs(*, outputs: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs["daily_price_bars_stock_only"].to_csv(output_dir / "daily_price_bars_stock_only.csv", index=False)
    outputs["daily_quote_reports_stock_only"].to_csv(output_dir / "daily_quote_reports_stock_only.csv", index=False)
    outputs["market_ohlcv_snapshots_stock_only"].to_csv(output_dir / "market_ohlcv_snapshots_stock_only.csv", index=False)
    outputs["excluded_non_stock_symbols"].to_csv(output_dir / "excluded_non_stock_symbols.csv", index=False)
    (output_dir / "stock_only_filter_summary.json").write_text(
        json.dumps(outputs["summary"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "stock_only_filter_report.md").write_text(build_report(outputs["summary"]), encoding="utf-8")


def with_symbol_norm(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    if "symbol" not in working.columns:
        raise ValueError("Input frame must include symbol column.")
    working["symbol_norm"] = normalize_symbol_series(working["symbol"])
    return working


def normalize_symbol_series(values: pd.Series) -> pd.Series:
    return values.fillna("").astype(str).str.strip().str.upper()


def count_values(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame.columns:
        return {}
    counts = frame[column].value_counts(dropna=False).to_dict()
    return {str(key): int(value) for key, value in counts.items()}


def build_report(summary: dict[str, Any]) -> str:
    return f"""# HOSE Quote Report Stock-Only Filter Report

- quote_report_dir: `{summary['quote_report_dir']}`
- listed_universe_dir: `{summary['listed_universe_dir']}`
- run_quality_status: `{summary['run_quality_status']}`

## Counts

| Metric | Count |
|---|---:|
| Quote-report rows | {summary['quote_report_rows']} |
| Quote-report unique symbols | {summary['quote_report_unique_symbols']} |
| Listed-universe rows | {summary['listed_universe_rows']} |
| Listed-universe unique symbols | {summary['listed_universe_unique_symbols']} |
| Stock-only rows | {summary['stock_only_rows']} |
| Stock-only unique symbols | {summary['stock_only_unique_symbols']} |
| Excluded rows | {summary['excluded_rows']} |
| Excluded unique symbols | {summary['excluded_unique_symbols']} |
| Duplicate quote-report symbol/date/status rows | {summary['duplicate_symbol_count_quote_report']} |
| Duplicate listed-universe symbol rows | {summary['duplicate_symbol_count_listed_universe']} |

## Data Status Counts

{format_mapping(summary['data_status_counts'])}

## Quality Status Counts After Filter

{format_mapping(summary['quality_status_counts_after_filter'])}

## Excluded Prefix Counts

{format_mapping(summary['excluded_symbol_prefix_counts'])}

## Warnings

{format_list(summary['warnings'])}
"""


def format_mapping(mapping: dict[str, int]) -> str:
    if not mapping:
        return "- none"
    return "\n".join(f"- `{key}`: {value}" for key, value in sorted(mapping.items()))


def format_list(values: list[str]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- `{value}`" for value in values)


if __name__ == "__main__":
    raise SystemExit(main())
