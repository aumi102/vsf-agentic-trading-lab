"""Audit adjusted OHLC consistency in QuestDB daily_prices without DB writes."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.storage import questdb_client as qdb  # noqa: E402

REPORT_PATH = ROOT / "docs/data_quality/adjusted_ohlc_quality_report.md"
REQUIRED_ADJUSTED = {"adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close"}
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")


def _parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    symbols = list(dict.fromkeys(s.strip().upper() for s in raw.split(",") if s.strip()))
    invalid = [s for s in symbols if not SYMBOL_RE.fullmatch(s)]
    if invalid:
        raise ValueError(f"invalid symbols: {', '.join(invalid)}")
    return symbols


def _where(symbols: list[str]) -> str:
    if not symbols:
        return ""
    return "WHERE symbol IN (" + ", ".join(f"'{s}'" for s in symbols) + ")"


def _select_symbols(client, base_url: str, explicit: list[str], limit: int | None) -> list[str]:
    if explicit:
        return explicit
    if limit is None:
        return []
    _, rows = qdb.exec_rows(client, base_url, f"SELECT DISTINCT symbol FROM daily_prices ORDER BY symbol LIMIT {limit}")
    return [str(row[0]) for row in rows if row]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _audit_sql(symbols: list[str]) -> str:
    where = _where(symbols)
    denominator_filter = "close != 0 AND high != 0 AND open != 0 AND low != 0 AND adjusted_close != 0"
    if where:
        denominator_filter = where + " AND " + denominator_filter
    else:
        denominator_filter = "WHERE " + denominator_filter
    return f"""
    SELECT symbol,
           count() AS rows_checked,
           corr(high, adjusted_high) AS corr_high_adjusted_high,
           corr(close, adjusted_close) AS corr_close_adjusted_close,
           corr(high / close, adjusted_high / adjusted_close) AS corr_high_close_ratio,
           approx_percentile(abs(adjusted_close / close - adjusted_high / high), 0.5) AS median_abs_factor_diff_high,
           max(abs(adjusted_close / close - adjusted_high / high)) AS max_abs_factor_diff_high,
           approx_percentile(abs(adjusted_close / close - adjusted_open / open), 0.5) AS median_abs_factor_diff_open,
           max(abs(adjusted_close / close - adjusted_open / open)) AS max_abs_factor_diff_open,
           approx_percentile(abs(adjusted_close / close - adjusted_low / low), 0.5) AS median_abs_factor_diff_low,
           max(abs(adjusted_close / close - adjusted_low / low)) AS max_abs_factor_diff_low,
           avg(abs(adjusted_close / close - adjusted_high / high)) AS avg_abs_factor_diff_high,
           avg(abs(adjusted_close / close - adjusted_open / open)) AS avg_abs_factor_diff_open,
           avg(abs(adjusted_close / close - adjusted_low / low)) AS avg_abs_factor_diff_low,
           sum(CASE WHEN adjusted_close = close THEN 1 ELSE 0 END) AS adjusted_close_equals_close_rows,
           sum(CASE WHEN adjusted_high = high THEN 1 ELSE 0 END) AS adjusted_high_equals_high_rows,
           sum(CASE WHEN adjusted_open = open THEN 1 ELSE 0 END) AS adjusted_open_equals_open_rows,
           sum(CASE WHEN adjusted_low = low THEN 1 ELSE 0 END) AS adjusted_low_equals_low_rows,
           first(adjustment_status) AS sample_adjustment_status
    FROM daily_prices
    {denominator_filter}
    GROUP BY symbol
    ORDER BY symbol
    """


def _status(row: dict[str, Any]) -> str:
    rows = max(int(row.get("rows_checked") or 0), 1)
    equals_close = int(row.get("adjusted_close_equals_close_rows") or 0) / rows
    adjustment_status = str(row.get("sample_adjustment_status") or "")
    if equals_close >= 0.999 or "missing_warn" in adjustment_status:
        return "source_adjustment_unverified"
    correlations = [
        _safe_float(row.get("corr_high_adjusted_high")),
        _safe_float(row.get("corr_close_adjusted_close")),
        _safe_float(row.get("corr_high_close_ratio")),
    ]
    max_diffs = [
        _safe_float(row.get("max_abs_factor_diff_high")),
        _safe_float(row.get("max_abs_factor_diff_open")),
        _safe_float(row.get("max_abs_factor_diff_low")),
    ]
    if all(c is None or c >= 0.99 for c in correlations) and all(d is None or d <= 1e-6 for d in max_diffs):
        return "pass"
    return "review_required"


def _rows_to_dicts(cols: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(cols, row)) for row in rows]


def _write_report(base_url: str, scope: str, columns: list[str], rows: list[dict[str, Any]], missing: list[str]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Adjusted OHLC Quality Audit",
        "",
        f"QuestDB: `{base_url}`",
        f"Scope: `{scope}`",
        "",
        "## Column availability",
        "",
        "Required adjusted OHLC columns: `adjusted_open`, `adjusted_high`, `adjusted_low`, `adjusted_close`.",
        "",
        f"Available adjusted columns: `{', '.join(c for c in columns if c.startswith('adjusted_'))}`",
        f"Missing adjusted columns: `{', '.join(missing) if missing else 'none'}`",
        "",
        "## Interpretation",
        "",
        "`source_adjustment_unverified` is a caveat, not a hard failure: current source rows carry `adjusted_price_missing_warn` and/or adjusted close equals close for nearly all rows.",
        "",
        "## Per-symbol audit",
        "",
        "| Symbol | Rows | Status | corr(high, adj_high) | corr(close, adj_close) | corr(high/close, adj_high/adj_close) | max factor diff | adjustment_status |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        max_diff = max(
            _safe_float(row.get("max_abs_factor_diff_high")) or 0.0,
            _safe_float(row.get("max_abs_factor_diff_open")) or 0.0,
            _safe_float(row.get("max_abs_factor_diff_low")) or 0.0,
        )
        lines.append(
            f"| `{row.get('symbol')}` | {int(row.get('rows_checked') or 0):,} | `{row.get('adjusted_ohlc_status')}` | "
            f"{_safe_float(row.get('corr_high_adjusted_high')) or 0:.6f} | "
            f"{_safe_float(row.get('corr_close_adjusted_close')) or 0:.6f} | "
            f"{_safe_float(row.get('corr_high_close_ratio')) or 0:.6f} | "
            f"{max_diff:.12g} | `{row.get('sample_adjustment_status')}` |"
        )
    lines.extend([
        "",
        "## Caveats",
        "",
        "- Audit is read-only; it does not alter QuestDB tables.",
        "- Median factor differences use QuestDB `approx_percentile(..., 0.5)`.",
        "- If source adjusted OHLC remains identical to raw OHLC, downstream backtests should keep the adjusted-price caveat visible.",
    ])
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit adjusted OHLC consistency in QuestDB daily_prices.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--symbols")
    group.add_argument("--limit-symbols", type=int)
    args = parser.parse_args()
    if args.limit_symbols is not None and args.limit_symbols < 1:
        parser.error("--limit-symbols must be >= 1")
    try:
        explicit = _parse_symbols(args.symbols)
    except ValueError as exc:
        parser.error(str(exc))
    base_url = args.questdb_url.rstrip("/")
    with qdb.open_client(timeout_seconds=180.0) as client:
        columns = qdb.column_names(client, base_url, "daily_prices")
        missing = sorted(REQUIRED_ADJUSTED - set(columns))
        symbols = _select_symbols(client, base_url, explicit, args.limit_symbols)
        if missing and "adjusted_close" not in missing:
            print("adjusted_open/high/low unavailable; derive expected values from adjusted_close / close factor")
        elif missing:
            print(f"missing adjusted columns: {', '.join(missing)}")
            _write_report(base_url, ",".join(symbols) if symbols else "ALL", columns, [], missing)
            return 0
        cols, dataset = qdb.exec_rows(client, base_url, _audit_sql(symbols))
    rows = _rows_to_dicts(cols, dataset)
    for row in rows:
        row["adjusted_ohlc_status"] = _status(row)
    scope = ",".join(symbols) if symbols else "ALL"
    _write_report(base_url, scope, columns, rows, missing)
    print(f"scope={scope}")
    print(f"symbols_audited={len(rows)}")
    for status in sorted({str(row['adjusted_ohlc_status']) for row in rows}):
        count = sum(1 for row in rows if row["adjusted_ohlc_status"] == status)
        print(f"{status}={count}")
    print(f"report_path={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
