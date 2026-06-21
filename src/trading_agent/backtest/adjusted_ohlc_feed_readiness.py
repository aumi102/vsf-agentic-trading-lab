from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DEMO_DB_PATH = Path("data/demo/mvp_trading_agent.sqlite")
REQUIRED_PROVENANCE = ("adjustment_source_id", "adjustment_raw_path", "adjustment_method")
FEED_CONTRACT_VERSION = "adjusted_ohlc_feed_v1"
SOURCE_PRICE_BASIS = "adjusted_ohlc"

# Audit metadata that PR #47 always emits and that the feed gate now requires.
REQUIRED_AUDIT_FIELDS = (
    "evidence_mode",
    "required_evidence_present",
    "symbols",
    "readiness_status",
    "backtest_gate",
    "validation_status",
    "db_mutation_made",
    "unadjusted_rows",
)

# A row is eligible for the adjusted OHLC feed only when adjusted OHLC, the
# adjustment factor, provenance, and quality status are all present and valid.
_ELIGIBLE_FILTER = """
    quality_status = 'ok'
    AND adjustment_factor IS NOT NULL
    AND adjusted_open IS NOT NULL
    AND adjusted_high IS NOT NULL
    AND adjusted_low IS NOT NULL
    AND adjusted_close IS NOT NULL
    AND adjustment_source_id IS NOT NULL
    AND TRIM(adjustment_source_id) != ''
    AND adjustment_raw_path IS NOT NULL
    AND TRIM(adjustment_raw_path) != ''
    AND adjustment_method IS NOT NULL
    AND TRIM(adjustment_method) != ''
    AND adjustment_method != 'unknown'
"""


def check_adjusted_ohlc_feed_readiness(
    *,
    db_path: str | Path,
    symbols: list[str],
    audit_report_path: str | Path,
    start_date: str | None = None,
    end_date: str | None = None,
    max_rows: int = 20,
    allow_demo_db: bool = False,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    path = Path(db_path)
    reasons = _request_reasons(path, requested, Path(audit_report_path), allow_demo_db)
    reasons.extend(_validate_date_and_rows(start_date, end_date, max_rows))
    audit_report = _load_audit_report(audit_report_path)
    reasons.extend(_audit_report_reasons(audit_report, requested_symbols=requested, db_path=path))
    if reasons:
        return _summary(
            status="not_ready" if path.exists() and requested else "invalid_request",
            db_path=path,
            symbols=requested,
            start_date=start_date,
            end_date=end_date,
            audit_report=audit_report,
            reasons=reasons,
        )

    with _connect_readonly(path) as con:
        eligible_by_symbol = _eligible_counts_by_symbol(con, requested, start_date, end_date)
        rows = _load_feed_rows(con, requested, start_date, end_date, max_rows)
        blockers = _row_blockers(con, requested, start_date, end_date)

    missing_symbols = [symbol for symbol in requested if eligible_by_symbol.get(symbol, 0) == 0]
    symbols_with_eligible_rows = [symbol for symbol in requested if eligible_by_symbol.get(symbol, 0) > 0]
    total_eligible_rows = sum(eligible_by_symbol.values())

    reasons.extend(blockers)
    for symbol in missing_symbols:
        reasons.append(f"missing_requested_symbol:{symbol}")
    if not rows:
        reasons.append("no_adjusted_feed_rows")
    reasons = _dedupe(reasons)
    status = "ok" if rows and not reasons else "not_ready"
    return _summary(
        status=status,
        db_path=path,
        symbols=requested,
        start_date=start_date,
        end_date=end_date,
        audit_report=audit_report,
        rows=rows,
        row_count=len(rows),
        total_eligible_rows=total_eligible_rows,
        missing_symbols=missing_symbols,
        symbols_with_eligible_rows=symbols_with_eligible_rows,
        reasons=reasons,
    )


def build_adjusted_ohlc_feed_preview(
    *,
    db_path: str | Path,
    symbols: list[str],
    audit_report_path: str | Path,
    start_date: str | None = None,
    end_date: str | None = None,
    max_rows: int = 20,
    allow_demo_db: bool = False,
) -> dict[str, Any]:
    return check_adjusted_ohlc_feed_readiness(
        db_path=db_path,
        symbols=symbols,
        audit_report_path=audit_report_path,
        start_date=start_date,
        end_date=end_date,
        max_rows=max_rows,
        allow_demo_db=allow_demo_db,
    )


def _load_feed_rows(
    con: sqlite3.Connection,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
    max_rows: int,
) -> list[dict[str, Any]]:
    where, params = _filters(symbols, start_date, end_date)
    rows = con.execute(
        f"""
        SELECT
            symbol,
            trade_date AS datetime,
            adjusted_open AS open,
            adjusted_high AS high,
            adjusted_low AS low,
            adjusted_close AS close,
            volume,
            adjustment_factor,
            adjustment_source_id,
            adjustment_raw_path,
            adjustment_method
        FROM daily_prices
        {where}
          AND {_ELIGIBLE_FILTER}
        ORDER BY symbol, trade_date
        LIMIT ?
        """,
        [*params, int(max_rows)],
    ).fetchall()
    return [
        {
            "symbol": row["symbol"],
            "datetime": row["datetime"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "source_price_basis": SOURCE_PRICE_BASIS,
            "adjustment_factor": row["adjustment_factor"],
            "adjustment_source_id": row["adjustment_source_id"],
            "adjustment_raw_path": row["adjustment_raw_path"],
            "adjustment_method": row["adjustment_method"],
        }
        for row in rows
    ]


def _eligible_counts_by_symbol(
    con: sqlite3.Connection,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> dict[str, int]:
    where, params = _filters(symbols, start_date, end_date)
    rows = con.execute(
        f"""
        SELECT symbol, COUNT(*) AS eligible_rows
        FROM daily_prices
        {where}
          AND {_ELIGIBLE_FILTER}
        GROUP BY symbol
        """,
        params,
    ).fetchall()
    return {str(row["symbol"]): int(row["eligible_rows"] or 0) for row in rows}


def _row_blockers(
    con: sqlite3.Connection,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> list[str]:
    where, params = _filters(symbols, start_date, end_date)
    row = con.execute(
        f"""
        SELECT
            COUNT(*) AS total_rows,
            SUM(CASE WHEN adjusted_open IS NULL OR adjusted_high IS NULL OR adjusted_low IS NULL OR adjusted_close IS NULL THEN 1 ELSE 0 END) AS missing_adjusted_rows,
            SUM(CASE WHEN adjustment_source_id IS NULL OR TRIM(adjustment_source_id) = ''
                 OR adjustment_raw_path IS NULL OR TRIM(adjustment_raw_path) = ''
                 OR adjustment_method IS NULL OR TRIM(adjustment_method) = ''
                 OR adjustment_method = 'unknown' THEN 1 ELSE 0 END) AS missing_provenance_rows,
            SUM(CASE WHEN quality_status != 'ok' THEN 1 ELSE 0 END) AS non_ok_quality_rows
        FROM daily_prices
        {where}
        """,
        params,
    ).fetchone()
    reasons: list[str] = []
    if int(row["total_rows"] or 0) == 0:
        reasons.append("no_rows_for_requested_filters")
    if int(row["missing_adjusted_rows"] or 0) > 0:
        reasons.append(f"missing_adjusted_rows:{int(row['missing_adjusted_rows'] or 0)}")
    if int(row["missing_provenance_rows"] or 0) > 0:
        reasons.append(f"missing_provenance_rows:{int(row['missing_provenance_rows'] or 0)}")
    if int(row["non_ok_quality_rows"] or 0) > 0:
        reasons.append(f"non_ok_quality_rows:{int(row['non_ok_quality_rows'] or 0)}")
    return reasons


def _filters(symbols: list[str], start_date: str | None, end_date: str | None) -> tuple[str, list[Any]]:
    clauses = []
    params: list[Any] = []
    if symbols:
        placeholders = ", ".join(["?"] * len(symbols))
        clauses.append(f"symbol IN ({placeholders})")
        params.extend(symbols)
    if start_date:
        clauses.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("trade_date <= ?")
        params.append(end_date)
    return f"WHERE {' AND '.join(clauses)}" if clauses else "WHERE 1=1", params


def _request_reasons(
    db_path: Path,
    symbols: list[str],
    audit_report_path: Path,
    allow_demo_db: bool,
) -> list[str]:
    reasons: list[str] = []
    if not symbols:
        reasons.append("explicit_symbols_required")
    if not db_path.exists():
        reasons.append(f"db_missing:{db_path}")
    if _is_demo_db(db_path) and not allow_demo_db:
        reasons.append("demo_db_blocked")
    if not audit_report_path.exists():
        reasons.append(f"audit_report_missing:{audit_report_path}")
    return reasons


def _validate_date_and_rows(
    start_date: str | None,
    end_date: str | None,
    max_rows: int,
) -> list[str]:
    reasons: list[str] = []
    if start_date is not None and not _is_iso_date(start_date):
        reasons.append(f"invalid_start_date_format:{start_date}")
    if end_date is not None and not _is_iso_date(end_date):
        reasons.append(f"invalid_end_date_format:{end_date}")
    if (
        start_date is not None
        and end_date is not None
        and _is_iso_date(start_date)
        and _is_iso_date(end_date)
        and start_date > end_date
    ):
        reasons.append("invalid_date_range:start_after_end")
    try:
        rows = int(max_rows)
    except (TypeError, ValueError):
        reasons.append("max_rows_must_be_positive")
        return reasons
    if rows <= 0:
        reasons.append("max_rows_must_be_positive")
    return reasons


def _is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
    except (TypeError, ValueError):
        return False
    return True


def _load_audit_report(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"status": "missing_report", "reasons": ["audit_report_missing"]}
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"status": "invalid_report", "reasons": [f"audit_report_invalid:{exc}"]}
    if not isinstance(payload, dict):
        return {"status": "invalid_report", "reasons": ["audit_report_must_be_object"]}
    return payload


def _audit_report_reasons(
    report: dict[str, Any],
    *,
    requested_symbols: list[str],
    db_path: Path,
) -> list[str]:
    reasons = [str(item) for item in report.get("reasons") or []]
    if report.get("status") != "ok":
        reasons.append(f"audit_status_not_ok:{report.get('status')}")
    if report.get("backtest_planning_gate") != "pass":
        reasons.append(f"audit_backtest_planning_gate_not_pass:{report.get('backtest_planning_gate')}")

    # A stale or minimal audit report must not pass just because status=ok. The
    # PR #47 strict audit emits the metadata below, so require it here.
    for field in REQUIRED_AUDIT_FIELDS:
        if field not in report:
            reasons.append(f"audit_missing_required_field:{field}")

    if "evidence_mode" in report and report.get("evidence_mode") != "strict":
        reasons.append(f"audit_evidence_mode_not_strict:{report.get('evidence_mode')}")
    if "required_evidence_present" in report and report.get("required_evidence_present") is not True:
        reasons.append("audit_required_evidence_not_present")

    audit_symbols = {str(symbol).strip().upper() for symbol in (report.get("symbols") or [])}
    for symbol in requested_symbols:
        if symbol not in audit_symbols:
            reasons.append(f"audit_missing_symbol:{symbol}")

    if report.get("db_path") is not None and not _paths_match(report.get("db_path"), db_path):
        reasons.append("audit_db_path_mismatch")

    if "unadjusted_rows" in report and report.get("unadjusted_rows") is not None:
        try:
            unadjusted = int(report.get("unadjusted_rows"))
        except (TypeError, ValueError):
            unadjusted = -1
        if unadjusted != 0:
            reasons.append(f"audit_unadjusted_rows_present:{report.get('unadjusted_rows')}")

    if report.get("readiness_status") is not None and report.get("readiness_status") != "ok":
        reasons.append(f"audit_readiness_status_not_ok:{report.get('readiness_status')}")
    if report.get("backtest_gate") is not None and report.get("backtest_gate") != "pass":
        reasons.append(f"audit_backtest_gate_not_pass:{report.get('backtest_gate')}")
    if report.get("validation_status") is not None and report.get("validation_status") != "ok":
        reasons.append(f"audit_validation_status_not_ok:{report.get('validation_status')}")
    if "db_mutation_made" in report and report.get("db_mutation_made") is not True:
        reasons.append("audit_db_mutation_not_made")

    return _dedupe(reasons)


def _paths_match(left: str | Path | None, right: str | Path | None) -> bool:
    if left is None or right is None:
        return False
    return Path(str(left)).resolve(strict=False) == Path(str(right)).resolve(strict=False)


def _summary(
    *,
    status: str,
    db_path: Path,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
    audit_report: dict[str, Any],
    reasons: list[str],
    rows: list[dict[str, Any]] | None = None,
    row_count: int = 0,
    total_eligible_rows: int = 0,
    missing_symbols: list[str] | None = None,
    symbols_with_eligible_rows: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "feed_contract_version": FEED_CONTRACT_VERSION,
        "source_price_basis": SOURCE_PRICE_BASIS,
        "db_path": str(db_path),
        "symbols": symbols,
        "requested_symbols": symbols,
        "symbols_with_eligible_rows": symbols_with_eligible_rows or [],
        "missing_symbols": missing_symbols or [],
        "start_date": start_date,
        "end_date": end_date,
        "rows": rows or [],
        "row_count": row_count,
        "total_eligible_rows": total_eligible_rows,
        "audit_status": audit_report.get("status"),
        "audit_backtest_planning_gate": audit_report.get("backtest_planning_gate"),
        "reasons": _dedupe(reasons),
        "caveats": [
            "Adjusted OHLC feed preview only; no Backtrader implementation or strategy execution.",
            "Raw OHLC is diagnostics only and is not exposed as trading price fields.",
            "No DB mutation and no network fetch.",
        ],
    }


def _connect_readonly(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _is_demo_db(path: Path) -> bool:
    root = Path(__file__).resolve().parents[3]
    return path.resolve(strict=False) == (root / DEMO_DB_PATH).resolve(strict=False)


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in symbols:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    return normalized


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
