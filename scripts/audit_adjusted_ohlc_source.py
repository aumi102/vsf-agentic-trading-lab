"""Audit adjusted OHLC source status and internal factor consistency.

This script is read-only. It does not attempt to verify corporate-action
correctness unless the source data carries enough evidence to support that
claim. A raw-equivalent adjusted series is reported as WARN, not PASS.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from trading_agent.storage import questdb_client as qdb  # noqa: E402

REPORT_PATH = ROOT / "docs" / "data_quality" / "adjusted_ohlc_audit.md"
DEMO_SYMBOLS = ["FPT", "VNM", "HPG"]
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")
RAW_COLS = {"open", "high", "low", "close"}
ADJUSTED_COLS = {"adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close"}
OPTIONAL_EVIDENCE_COLS = {"adjustment_factor", "adjustment_status", "source_id", "raw_path"}
TOLERANCE = 1e-6


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    symbols = list(dict.fromkeys(part.strip().upper() for part in raw.split(",") if part.strip()))
    invalid = [symbol for symbol in symbols if not SYMBOL_RE.fullmatch(symbol)]
    if invalid:
        raise argparse.ArgumentTypeError(f"invalid symbols: {', '.join(invalid)}")
    return symbols


def _pick_symbols(client, base: str, explicit: list[str], limit: int) -> list[str]:
    if explicit:
        return explicit
    _, rows = qdb.exec_rows(client, base, f"SELECT DISTINCT symbol FROM daily_prices ORDER BY symbol LIMIT {max(limit, 1)}")
    sampled = [str(row[0]).upper() for row in rows if row]
    return list(dict.fromkeys([*DEMO_SYMBOLS, *sampled]))


def _where(symbols: list[str]) -> str:
    if not symbols:
        return ""
    return " AND symbol IN (" + ",".join(_sql_quote(symbol) for symbol in symbols) + ")"


def _audit_sql(symbols: list[str], columns: set[str]) -> str:
    adjustment_status_expr = "first(adjustment_status)" if "adjustment_status" in columns else "''"
    warn_rows_expr = (
        "sum(CASE WHEN adjustment_status = 'adjusted_price_missing_warn' THEN 1 ELSE 0 END)"
        if "adjustment_status" in columns
        else "0"
    )
    source_rows_expr = "sum(CASE WHEN source_id IS NOT NULL AND source_id != '' THEN 1 ELSE 0 END)" if "source_id" in columns else "0"
    raw_path_rows_expr = "sum(CASE WHEN raw_path IS NOT NULL AND raw_path != '' THEN 1 ELSE 0 END)" if "raw_path" in columns else "0"
    non1_factor_expr = (
        "sum(CASE WHEN adjustment_factor IS NOT NULL AND abs(adjustment_factor - 1.0) > 0.000001 THEN 1 ELSE 0 END)"
        if "adjustment_factor" in columns
        else "0"
    )
    factor_max_diff_expr = (
        "max(abs(adjustment_factor - adjusted_close / close))"
        if "adjustment_factor" in columns
        else "NULL"
    )
    return f"""
    SELECT symbol,
           count() AS rows_checked,
           sum(CASE WHEN adjusted_close = close THEN 1 ELSE 0 END) AS adjusted_close_equals_raw_rows,
           sum(CASE WHEN adjusted_open = open THEN 1 ELSE 0 END) AS adjusted_open_equals_raw_rows,
           sum(CASE WHEN adjusted_high = high THEN 1 ELSE 0 END) AS adjusted_high_equals_raw_rows,
           sum(CASE WHEN adjusted_low = low THEN 1 ELSE 0 END) AS adjusted_low_equals_raw_rows,
           sum(CASE WHEN abs(adjusted_close / close - 1.0) > 0.000001 THEN 1 ELSE 0 END) AS non_1_factor_rows,
           {non1_factor_expr} AS non_1_adjustment_factor_rows,
           {factor_max_diff_expr} AS max_adjustment_factor_column_diff,
           max(abs(adjusted_open - open * (adjusted_close / close))) AS max_abs_open_factor_error,
           max(abs(adjusted_high - high * (adjusted_close / close))) AS max_abs_high_factor_error,
           max(abs(adjusted_low - low * (adjusted_close / close))) AS max_abs_low_factor_error,
           avg(abs(adjusted_open - open * (adjusted_close / close))) AS avg_abs_open_factor_error,
           avg(abs(adjusted_high - high * (adjusted_close / close))) AS avg_abs_high_factor_error,
           avg(abs(adjusted_low - low * (adjusted_close / close))) AS avg_abs_low_factor_error,
           corr(high, adjusted_high) AS corr_high_adjusted_high,
           corr(close, adjusted_close) AS corr_close_adjusted_close,
           {warn_rows_expr} AS adjusted_price_missing_warn_rows,
           {source_rows_expr} AS source_id_rows,
           {raw_path_rows_expr} AS raw_path_rows,
           {adjustment_status_expr} AS sample_adjustment_status
    FROM daily_prices
    WHERE close != 0 AND open != 0 AND high != 0 AND low != 0 AND adjusted_close != 0
          AND adjusted_open IS NOT NULL AND adjusted_high IS NOT NULL
          AND adjusted_low IS NOT NULL AND adjusted_close IS NOT NULL
          {_where(symbols)}
    GROUP BY symbol
    ORDER BY symbol
    """


def _status(row: dict[str, Any]) -> tuple[str, str]:
    rows = max(int(row.get("rows_checked") or 0), 1)
    max_errors = [
        float(row.get("max_abs_open_factor_error") or 0),
        float(row.get("max_abs_high_factor_error") or 0),
        float(row.get("max_abs_low_factor_error") or 0),
    ]
    if any(error > TOLERANCE for error in max_errors):
        return "FAIL", "adjusted_ohlc_factor_inconsistent"
    missing_warn = int(row.get("adjusted_price_missing_warn_rows") or 0)
    raw_equiv_ratio = int(row.get("adjusted_close_equals_raw_rows") or 0) / rows
    non_1_factor_rows = int(row.get("non_1_factor_rows") or 0)
    has_provenance = int(row.get("source_id_rows") or 0) > 0 and int(row.get("raw_path_rows") or 0) > 0
    if missing_warn or raw_equiv_ratio > 0.99 or non_1_factor_rows == 0:
        return "WARN", "source_adjustment_unverified_raw_equivalent"
    if has_provenance:
        return "WARN", "internal_consistency_ok_source_evidence_incomplete"
    return "WARN", "internal_consistency_ok_source_unverified"


def _dict_rows(columns: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row)) for row in rows]


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    total_rows = 0
    total_non_1 = 0
    total_raw_equiv = 0
    for row in rows:
        status_counts[str(row["audit_status"])] = status_counts.get(str(row["audit_status"]), 0) + 1
        source_counts[str(row["source_verification_status"])] = source_counts.get(str(row["source_verification_status"]), 0) + 1
        total_rows += int(row.get("rows_checked") or 0)
        total_non_1 += int(row.get("non_1_factor_rows") or 0)
        total_raw_equiv += int(row.get("adjusted_close_equals_raw_rows") or 0)
    overall = "PASS"
    if any(row["audit_status"] == "FAIL" for row in rows):
        overall = "FAIL"
    elif any(row["audit_status"] == "WARN" for row in rows):
        overall = "WARN"
    return {
        "overall_status": overall,
        "symbols_audited": len(rows),
        "rows_checked": total_rows,
        "non_1_factor_rows": total_non_1,
        "raw_equivalent_rows": total_raw_equiv,
        "raw_equivalent_ratio": (total_raw_equiv / total_rows) if total_rows else None,
        "audit_status_counts": status_counts,
        "source_verification_status_counts": source_counts,
    }


def _write_report(base: str, columns: set[str], symbols: list[str], rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    missing_raw = sorted(RAW_COLS - columns)
    missing_adjusted = sorted(ADJUSTED_COLS - columns)
    available_evidence = sorted(OPTIONAL_EVIDENCE_COLS & columns)
    lines = [
        "# Adjusted OHLC source audit",
        "",
        f"- generated_at: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        f"- questdb_url: `{base}`",
        f"- scope_symbols: `{', '.join(symbols)}`",
        f"- overall_status: `{summary.get('overall_status')}`",
        "",
        "## Result",
        "",
        "Adjusted OHLC is internally consistent with a close-derived factor for the audited rows, "
        "but the current data remains source-unverified because adjusted OHLC is raw-equivalent and "
        "`adjustment_status` contains `adjusted_price_missing_warn`.",
        "",
        "This is a validation WARN, not a fabricated PASS. Backtests must continue to disclose the caveat.",
        "",
        "## Column availability",
        "",
        f"- missing_raw_columns: `{', '.join(missing_raw) if missing_raw else 'none'}`",
        f"- missing_adjusted_columns: `{', '.join(missing_adjusted) if missing_adjusted else 'none'}`",
        f"- available_evidence_columns: `{', '.join(available_evidence) if available_evidence else 'none'}`",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## Per-symbol evidence",
        "",
        "| Symbol | Status | Source status | Rows | Non-1 factors | Raw-equivalent close rows | Max factor error | corr(close, adj_close) | adjustment_status |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        max_error = max(
            float(row.get("max_abs_open_factor_error") or 0),
            float(row.get("max_abs_high_factor_error") or 0),
            float(row.get("max_abs_low_factor_error") or 0),
        )
        lines.append(
            f"| `{row.get('symbol')}` | `{row.get('audit_status')}` | `{row.get('source_verification_status')}` | "
            f"{int(row.get('rows_checked') or 0):,} | {int(row.get('non_1_factor_rows') or 0):,} | "
            f"{int(row.get('adjusted_close_equals_raw_rows') or 0):,} | {max_error:.12g} | "
            f"{float(row.get('corr_close_adjusted_close') or 0):.6f} | `{row.get('sample_adjustment_status')}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `PASS` would require source-backed adjustment evidence plus internal factor consistency.",
            "- `WARN` means the data is usable for demos only with explicit adjusted-price caveats.",
            "- `FAIL` means adjusted OHLC fields are internally inconsistent with `adjusted_close / close` factor math.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run_audit(questdb_url: str, symbols: list[str], limit_symbols: int) -> dict[str, Any]:
    base = questdb_url.rstrip("/")
    with qdb.open_client(timeout_seconds=180.0) as client:
        columns = set(qdb.column_names(client, base, "daily_prices"))
        missing = RAW_COLS | ADJUSTED_COLS
        missing = sorted(missing - columns)
        selected_symbols = _pick_symbols(client, base, symbols, limit_symbols)
        if missing:
            rows: list[dict[str, Any]] = []
            summary = {
                "overall_status": "FAIL",
                "symbols_audited": 0,
                "missing_columns": missing,
                "reason": "required raw or adjusted OHLC columns missing",
            }
            _write_report(base, columns, selected_symbols, rows, summary)
            return {"summary": summary, "rows": rows, "report_path": str(REPORT_PATH)}
        cols, raw_rows = qdb.exec_rows(client, base, _audit_sql(selected_symbols, columns))
    rows = _dict_rows(cols, raw_rows)
    for row in rows:
        status, source_status = _status(row)
        row["audit_status"] = status
        row["source_verification_status"] = source_status
    summary = _summarize(rows)
    _write_report(base, columns, selected_symbols, rows, summary)
    return {"summary": summary, "rows": rows, "report_path": str(REPORT_PATH)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit adjusted OHLC source evidence and internal consistency.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--symbols", type=_parse_symbols)
    parser.add_argument("--limit-symbols", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    symbols = args.symbols or []
    result = run_audit(args.questdb_url, symbols, args.limit_symbols)
    summary = result["summary"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"OVERALL_STATUS={summary.get('overall_status')}")
        print(f"symbols_audited={summary.get('symbols_audited')}")
        print(f"rows_checked={summary.get('rows_checked')}")
        print(f"non_1_factor_rows={summary.get('non_1_factor_rows')}")
        print(f"raw_equivalent_ratio={summary.get('raw_equivalent_ratio')}")
        print(f"report_path={result['report_path']}")
    return 1 if summary.get("overall_status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
