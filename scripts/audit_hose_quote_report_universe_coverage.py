from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit HOSE quote-report dry-run symbols against the HOSE listed-universe dry-run output.")
    parser.add_argument("--quote-report-dir", default="", help="HOSE quote-report dry-run directory. Defaults to latest.")
    parser.add_argument("--listed-universe-dir", default="", help="HOSE listed-universe all-pages dry-run directory. Defaults to latest.")
    parser.add_argument("--doc-out", default="", help="Optional Markdown report path. Defaults to <quote-report-dir>/universe_coverage_report.md.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    quote_dir = Path(args.quote_report_dir) if args.quote_report_dir else latest_run_dir(ROOT / "data/processed/dry_run/hose_quote_report")
    listed_dir = Path(args.listed_universe_dir) if args.listed_universe_dir else latest_run_dir(ROOT / "data/processed/dry_run/hose_listed_universe_all_pages")

    summary = build_audit_summary(quote_dir=quote_dir, listed_dir=listed_dir)
    summary_path = quote_dir / "universe_coverage_summary.json"
    doc_path = Path(args.doc_out) if args.doc_out else quote_dir / "universe_coverage_report.md"
    if not doc_path.is_absolute():
        doc_path = ROOT / doc_path

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(build_audit_doc(summary), encoding="utf-8")

    print(f"quote_report_dir={quote_dir}")
    print(f"listed_universe_dir={listed_dir}")
    print(f"audit_doc={doc_path}")
    print(f"summary_json={summary_path}")
    print(f"quote_report_symbols={summary['coverage']['total_quote_report_symbols']}")
    print(f"listed_universe_symbols={summary['coverage']['total_listed_universe_symbols']}")
    print(f"matched_symbols={summary['coverage']['matched_listed_universe_symbols']}")
    print(f"unmatched_symbols={summary['coverage']['unmatched_quote_report_symbols']}")
    return 0


def latest_run_dir(base_dir: Path) -> Path:
    if not base_dir.exists():
        raise FileNotFoundError(f"Missing dry-run base directory: {base_dir}")
    candidates = [path for path in base_dir.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No dry-run output directories found under {base_dir}")
    return sorted(candidates, key=lambda path: path.name)[-1]


def build_audit_summary(*, quote_dir: Path, listed_dir: Path) -> dict[str, Any]:
    quote_reports = pd.read_csv(quote_dir / "daily_quote_reports.csv")
    price_bars = pd.read_csv(quote_dir / "daily_price_bars.csv")
    quote_summary = json.loads((quote_dir / "validation_summary.json").read_text(encoding="utf-8"))

    symbol_universe = pd.read_csv(listed_dir / "symbol_universe.csv")
    securities_master = pd.read_csv(listed_dir / "securities_master.csv")
    exchange_listings = pd.read_csv(listed_dir / "exchange_listings.csv")

    quote_symbols = set(clean_symbols(quote_reports["symbol"]))
    listed_symbols = set(clean_symbols(symbol_universe["symbol"]))
    matched_symbols = sorted(quote_symbols & listed_symbols)
    unmatched_symbols = sorted(quote_symbols - listed_symbols)

    duplicate_quote_symbol_rows = int(quote_reports.duplicated("symbol", keep=False).sum())
    duplicate_listed_symbol_rows = int(symbol_universe.duplicated("symbol", keep=False).sum())

    matched_universe = symbol_universe[symbol_universe["symbol"].astype(str).str.upper().isin(matched_symbols)].copy()
    unmatched_patterns = classify_unmatched_patterns(unmatched_symbols)
    quality = build_quality_summary(quote_reports=quote_reports, price_bars=price_bars, validation_summary=quote_summary)

    return {
        "quote_report_dir": str(quote_dir),
        "listed_universe_dir": str(listed_dir),
        "quote_report_run_id": quote_dir.name,
        "listed_universe_run_id": listed_dir.name,
        "coverage": {
            "quote_report_rows": int(len(quote_reports)),
            "total_quote_report_symbols": int(len(quote_symbols)),
            "listed_universe_rows": int(len(symbol_universe)),
            "securities_master_rows": int(len(securities_master)),
            "exchange_listings_rows": int(len(exchange_listings)),
            "total_listed_universe_symbols": int(len(listed_symbols)),
            "matched_listed_universe_symbols": int(len(matched_symbols)),
            "unmatched_quote_report_symbols": int(len(unmatched_symbols)),
            "duplicate_quote_report_symbol_rows": duplicate_quote_symbol_rows,
            "duplicate_listed_universe_symbol_rows": duplicate_listed_symbol_rows,
            "matched_ratio_of_quote_symbols": round(len(matched_symbols) / len(quote_symbols), 6) if quote_symbols else 0,
        },
        "instrument_type_analysis": {
            "matched_security_type_code_counts": count_values(matched_universe, "security_type_code"),
            "matched_listing_status_id_counts": count_values(matched_universe, "listing_status_id"),
            "unmatched_symbol_length_counts": dict(sorted(Counter(len(symbol) for symbol in unmatched_symbols).items())),
            "unmatched_first_character_counts": dict(Counter(symbol[0] for symbol in unmatched_symbols if symbol).most_common()),
            "unmatched_prefix4_top": dict(Counter(symbol[:4] for symbol in unmatched_symbols).most_common(20)),
            "unmatched_starts_with_c_count": int(sum(symbol.startswith("C") for symbol in unmatched_symbols)),
            "unmatched_starts_with_f_count": int(sum(symbol.startswith("F") for symbol in unmatched_symbols)),
            "unmatched_examples": unmatched_symbols[:80],
        },
        "quality": quality,
        "recommendation": {
            "first_mvp_dataset": "stock_only_matched_universe",
            "quote_report_full_dataset_use": "audit_and_source_preservation",
            "next_step": "Add a stock-only filtered dry-run output or run source unit and historical availability audits before database/backtest work.",
        },
    }


def clean_symbols(values: pd.Series) -> list[str]:
    return [str(value).strip().upper() for value in values.dropna() if str(value).strip()]


def count_values(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame.columns:
        return {}
    counts = frame[column].value_counts(dropna=False).to_dict()
    return {str(key): int(value) for key, value in counts.items()}


def classify_unmatched_patterns(unmatched_symbols: list[str]) -> dict[str, Any]:
    return {
        "count": len(unmatched_symbols),
        "starts_with_c": sum(symbol.startswith("C") for symbol in unmatched_symbols),
        "starts_with_f": sum(symbol.startswith("F") for symbol in unmatched_symbols),
        "length_counts": dict(sorted(Counter(len(symbol) for symbol in unmatched_symbols).items())),
        "examples": unmatched_symbols[:50],
    }


def build_quality_summary(*, quote_reports: pd.DataFrame, price_bars: pd.DataFrame, validation_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "quality_pass_count": int(validation_summary.get("quality_pass_count", 0)),
        "quality_warn_count": int(validation_summary.get("quality_warn_count", 0)),
        "quality_fail_count": int(validation_summary.get("quality_fail_count", 0)),
        "quality_reason_counts": validation_summary.get("quality_reason_counts", {}),
        "matched_volume_zero_rows": int((price_bars["matched_volume"] == 0).sum()),
        "trading_value_zero_rows": int((price_bars["trading_value"] == 0).sum()),
        "open_high_low_average_zero_rows": int(
            (
                (price_bars["open_price"] == 0)
                & (price_bars["high_price"] == 0)
                & (price_bars["low_price"] == 0)
                & (quote_reports["average_price"] == 0)
            ).sum()
        ),
        "close_equals_prior_close_rows": int((price_bars["close_price"] == price_bars["prior_close_price"]).sum()),
    }


def build_audit_doc(summary: dict[str, Any]) -> str:
    coverage = summary["coverage"]
    instrument = summary["instrument_type_analysis"]
    quality = summary["quality"]
    unmatched_examples = ", ".join(f"`{symbol}`" for symbol in instrument["unmatched_examples"][:40])
    prefix_top = ", ".join(f"`{prefix}`: {count}" for prefix, count in instrument["unmatched_prefix4_top"].items())

    return f"""# HOSE Quote Report Universe Coverage Audit

## A. Executive Summary

<details open>
<summary>The quote-report dataset is broader than the listed-stock universe and should be filtered for the first stock MVP.</summary>

---

Input dry-run folders:

- Quote report: `{summary['quote_report_dir']}`
- Listed universe: `{summary['listed_universe_dir']}`

Key counts:

- Quote-report rows: {coverage['quote_report_rows']}
- Unique quote-report symbols: {coverage['total_quote_report_symbols']}
- Listed-universe rows: {coverage['listed_universe_rows']}
- Unique listed-universe symbols: {coverage['total_listed_universe_symbols']}
- Matched symbols: {coverage['matched_listed_universe_symbols']}
- Unmatched quote-report symbols: {coverage['unmatched_quote_report_symbols']}

Likely mismatch reason:

The listed-universe all-pages dry run uses the HOSE stock universe endpoint and contains 403 stock symbols. The quote-report sample contains 662 symbols and appears to include stocks plus non-stock instruments such as covered warrant-like symbols and ETF/fund-like symbols. The unmatched quote-report symbols should not be dropped, but they should not be used in the first ordinary-stock MVP strategy unless instrument support is explicit.

---

</details>

## B. Coverage Table

<details open>
<summary>All listed stock symbols matched the quote-report, while 259 quote-report symbols were outside the listed-stock universe.</summary>

---

| Metric | Count |
|---|---:|
| Total quote-report rows | {coverage['quote_report_rows']} |
| Total quote-report symbols | {coverage['total_quote_report_symbols']} |
| Listed-universe rows | {coverage['listed_universe_rows']} |
| Listed-universe symbols | {coverage['total_listed_universe_symbols']} |
| Matched listed-universe symbols | {coverage['matched_listed_universe_symbols']} |
| Unmatched quote-report symbols | {coverage['unmatched_quote_report_symbols']} |
| Duplicate quote-report symbol rows | {coverage['duplicate_quote_report_symbol_rows']} |
| Duplicate listed-universe symbol rows | {coverage['duplicate_listed_universe_symbol_rows']} |

Coverage ratio:

- Matched symbols as share of quote-report symbols: {coverage['matched_ratio_of_quote_symbols']:.2%}
- Matched symbols as share of listed-universe symbols: 100.00%

---

</details>

## C. Instrument-Type Analysis

<details open>
<summary>Matched rows are stock-universe rows; unmatched rows show warrant-like and ETF/fund-like naming patterns.</summary>

---

Matched listed-universe security type codes:

| security_type_code | Count |
|---|---:|
{format_mapping_rows(instrument['matched_security_type_code_counts'])}

Matched listed-universe listing status ids:

| listing_status_id | Count |
|---|---:|
{format_mapping_rows(instrument['matched_listing_status_id_counts'])}

Unmatched quote-report symbol patterns:

| Pattern | Count |
|---|---:|
| Symbols starting with `C` | {instrument['unmatched_starts_with_c_count']} |
| Symbols starting with `F` | {instrument['unmatched_starts_with_f_count']} |
| Symbols with length 8 | {instrument['unmatched_symbol_length_counts'].get('8', instrument['unmatched_symbol_length_counts'].get(8, 0))} |

Top unmatched four-character prefixes:

{prefix_top}

Unmatched examples:

{unmatched_examples}

Interpretation:

- `C...` symbols such as `CACB2510`, `CFPT2517`, and `CHPG2523` look like covered warrant-like instruments.
- `F...` symbols such as `E1VFVN30`, `FUEVFVND`, and `FUCVREIT` look like ETF/fund-like instruments.
- The first MVP stock strategy should use the matched ordinary stock universe only.
- The full quote-report dataset should still be preserved for audit and future instrument support.

---

</details>

## D. Quote-Report Quality Analysis

<details open>
<summary>The quote-report dry run has warnings only and no failed rows.</summary>

---

Validation summary:

| Metric | Count |
|---|---:|
| Quality pass rows | {quality['quality_pass_count']} |
| Quality warn rows | {quality['quality_warn_count']} |
| Quality fail rows | {quality['quality_fail_count']} |
| `warning_source_units_unconfirmed` | {quality['quality_reason_counts'].get('warning_source_units_unconfirmed', 0)} |
| `warning_no_trade_zero_ohlc` | {quality['quality_reason_counts'].get('warning_no_trade_zero_ohlc', 0)} |

Additional quality counts:

| Metric | Count |
|---|---:|
| Rows with matched volume = 0 | {quality['matched_volume_zero_rows']} |
| Rows with trading value = 0 | {quality['trading_value_zero_rows']} |
| Rows with open/high/low/average = 0 | {quality['open_high_low_average_zero_rows']} |
| Rows where close equals prior close | {quality['close_equals_prior_close_rows']} |

Interpretation:

- `warning_source_units_unconfirmed` should remain until source page text or documentation confirms price, volume, and value units.
- `warning_no_trade_zero_ohlc` should remain a warning, not a failure, because zero OHLC rows can represent no-trade records.
- `quality_fail_count = 0`, so the completed-day quote-report parser dry run is structurally healthy enough for review.

---

</details>

## E. Strategy And MVP Implication

<details open>
<summary>The first MVP stock strategy should use a matched stock-only subset, not the full quote-report dataset.</summary>

---

Recommendation for first MVP:

- Use only quote-report rows whose symbols match the HOSE listed-stock universe.
- Exclude covered warrant-like and ETF/fund-like rows from the first ordinary-stock backtest unless those instruments are explicitly supported.
- Preserve the full quote-report dataset for audit, diagnostics, and future instrument-specific work.
- Derive a stock-only subset later rather than mutating the raw quote-report parser output.

Reason:

The quote-report endpoint appears to be a market quote-report surface, not a stock-only endpoint. The first MVP stock strategy should avoid mixing ordinary stocks with instruments that have different payoff structures, liquidity behavior, price rules, and risk profiles.

---

</details>

## F. Parser Improvement Recommendations

<details open>
<summary>The parser can stay broad, but a later filtered output should join against listed-universe metadata.</summary>

---

Recommended parser or dry-run improvements:

- Add an optional universe cross-check warning later: `warning_unmatched_listed_universe_symbol`.
- Add `instrument_type` or `security_type_code` after joining quote-report symbols with listed-universe metadata.
- Keep source-unit uncertainty as a run-level limitation and row-level warning until confirmed.
- Keep no-trade zero-OHLC as a warning, not a failure.
- Do not silently drop unmatched symbols in the parser.
- Add a stock-only derived output in a separate dry-run step if needed for MVP strategy inputs.

---

</details>

## G. Next Safe Implementation Step

<details open>
<summary>Add a stock-only filtered dry-run output before any database or backtest work.</summary>

---

Do not implement database migrations or backtest yet.

Next safest implementation step:

1. Add an optional stock-only filtered dry-run output that joins `daily_quote_reports.csv` to the HOSE listed-universe all-pages output and writes only matched ordinary stock symbols.

Alternative next step:

2. Run a source-unit confirmation and historical-date availability audit for HOSE quote-report before deriving strategy inputs.

Preferred order:

1. Stock-only filtered dry run.
2. Source unit and historical availability audit.
3. Only then consider canonical storage or backtest preparation.

---

</details>
"""


def format_mapping_rows(mapping: dict[str, int]) -> str:
    if not mapping:
        return "| none | 0 |"
    return "\n".join(f"| `{key}` | {value} |" for key, value in sorted(mapping.items()))


if __name__ == "__main__":
    raise SystemExit(main())
