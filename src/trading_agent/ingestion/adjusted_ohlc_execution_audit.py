from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from trading_agent.ingestion.apply_adjustment_factors import load_adjustment_factor_records


DEMO_DB_PATH = Path("data/demo/mvp_trading_agent.sqlite")
REQUIRED_ADJUSTED_COLUMNS = (
    "adjustment_factor",
    "adjusted_open",
    "adjusted_high",
    "adjusted_low",
    "adjusted_close",
)
PROVENANCE_COLUMNS = ("adjustment_source_id", "adjustment_raw_path", "adjustment_method")
RAW_OHLC_COLUMNS = ("open", "high", "low", "close")
ADJUSTED_OHLC_COLUMNS = ("adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close")
EPSILON = 1e-6


def audit_adjusted_ohlc_execution(
    *,
    db_path: str | Path,
    symbols: list[str],
    factor_records_path: str | Path | None = None,
    validation_report_path: str | Path | None = None,
    readiness_report_path: str | Path | None = None,
    raw_baseline_path: str | Path | None = None,
    allow_demo_db: bool = False,
    require_factor_records: bool = True,
    require_validation_report: bool = True,
    require_readiness_report: bool = True,
    allow_incomplete_evidence: bool = False,
) -> dict[str, Any]:
    requested_symbols = _normalize_symbols(symbols)
    path = Path(db_path)
    evidence_mode = "incomplete" if allow_incomplete_evidence else "strict"
    request_reasons = _request_reasons(path, requested_symbols, allow_demo_db)
    if request_reasons:
        return _summary(
            status="invalid_request",
            db_path=path,
            symbols=requested_symbols,
            reasons=request_reasons,
            evidence_mode=evidence_mode,
        )

    factor_records, factor_load_reasons = load_factor_records(factor_records_path)
    validation = _load_status_report(validation_report_path, "validation")
    readiness = _load_status_report(readiness_report_path, "readiness")
    baseline_records, baseline_load_reasons = load_raw_ohlc_baseline(raw_baseline_path)
    required_evidence_reasons = _required_evidence_reasons(
        factor_records_path=factor_records_path,
        validation_report_path=validation_report_path,
        readiness_report_path=readiness_report_path,
        require_factor_records=require_factor_records and not allow_incomplete_evidence,
        require_validation_report=require_validation_report and not allow_incomplete_evidence,
        require_readiness_report=require_readiness_report and not allow_incomplete_evidence,
    )

    with _connect_readonly(path) as con:
        columns = _column_names(con, "daily_prices")
        if not columns:
            return _summary(
                status="invalid_request",
                db_path=path,
                symbols=requested_symbols,
                reasons=["daily_prices_table_missing"],
                validation=validation,
                readiness=readiness,
                evidence_mode=evidence_mode,
            )
        rows = _load_daily_price_rows(con, requested_symbols)

    coverage = audit_symbol_coverage(rows, requested_symbols)
    row_audit = audit_adjusted_ohlc_rows(rows, columns)
    factor_audit = audit_factor_consistency(rows, factor_records) if factor_records_path else _empty_factor_audit()
    baseline_audit = audit_raw_ohlc_baseline(rows, baseline_records) if raw_baseline_path else _baseline_not_provided()
    validation_reasons = _validation_report_reasons(validation)
    readiness_reasons = _readiness_report_reasons(readiness)

    reasons = [
        *required_evidence_reasons,
        *factor_load_reasons,
        *baseline_load_reasons,
        *coverage["reasons"],
        *row_audit["reasons"],
        *factor_audit["reasons"],
        *baseline_audit["reasons"],
        *validation_reasons,
        *readiness_reasons,
    ]
    status = "ok" if not reasons else "not_ready"
    required_evidence_present = not required_evidence_reasons
    backtest_planning_gate = "pass" if status == "ok" and evidence_mode == "strict" and required_evidence_present else "blocked"
    return _summary(
        status=status,
        db_path=path,
        symbols=requested_symbols,
        rows_total=coverage["rows_total"],
        adjusted_rows=row_audit["adjusted_rows"],
        unadjusted_rows=row_audit["unadjusted_rows"],
        missing_symbols=coverage["missing_symbols"],
        invalid_rows=row_audit["invalid_rows"],
        factor_consistency_errors=factor_audit["factor_consistency_errors"],
        provenance_errors=row_audit["provenance_errors"] + factor_audit["provenance_errors"],
        raw_ohlc_baseline_status=baseline_audit["status"],
        raw_ohlc_baseline_errors=baseline_audit["errors"],
        readiness_status=readiness.get("status"),
        backtest_gate=readiness.get("backtest_gate"),
        validation_status=validation.get("status"),
        db_mutation_made=validation.get("db_mutation_made"),
        reasons=reasons,
        validation=validation,
        readiness=readiness,
        evidence_mode=evidence_mode,
        required_evidence_present=required_evidence_present,
        backtest_planning_gate=backtest_planning_gate,
        incomplete_evidence=allow_incomplete_evidence,
    )


def load_factor_records(path: str | Path | None) -> tuple[list[Any], list[str]]:
    if path is None:
        return [], []
    try:
        return load_adjustment_factor_records(path), []
    except FileNotFoundError:
        return [], [f"factor_records_missing:{path}"]
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return [], [f"factor_records_invalid:{exc}"]


def load_raw_ohlc_baseline(path: str | Path | None) -> tuple[list[dict[str, Any]], list[str]]:
    if path is None:
        return [], []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return [], [f"raw_ohlc_baseline_missing:{path}"]
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [], [f"raw_ohlc_baseline_invalid:{exc}"]
    if not isinstance(payload, list):
        return [], ["raw_ohlc_baseline_must_be_list"]
    records: list[dict[str, Any]] = []
    reasons: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            reasons.append(f"raw_ohlc_baseline_record_must_be_object:{index}")
            continue
        records.append(item)
    return records, reasons


def audit_symbol_coverage(rows: list[dict[str, Any]], symbols: list[str]) -> dict[str, Any]:
    found = {str(row.get("symbol") or "").upper() for row in rows}
    missing = [symbol for symbol in symbols if symbol not in found]
    reasons = [f"missing_symbol:{symbol}" for symbol in missing]
    if not rows:
        reasons.append("daily_prices_rows_missing")
    return {
        "rows_total": len(rows),
        "missing_symbols": missing,
        "reasons": reasons,
    }


def audit_adjusted_ohlc_rows(rows: list[dict[str, Any]], columns: set[str]) -> dict[str, Any]:
    reasons: list[str] = []
    invalid_rows: list[dict[str, Any]] = []
    provenance_errors: list[dict[str, Any]] = []
    adjusted_rows = 0
    unadjusted_rows = 0

    missing_adjusted_columns = [column for column in REQUIRED_ADJUSTED_COLUMNS if column not in columns]
    if missing_adjusted_columns:
        reasons.append(f"missing_adjusted_columns:{','.join(missing_adjusted_columns)}")
    missing_provenance_columns = [column for column in PROVENANCE_COLUMNS if column not in columns]
    if missing_provenance_columns:
        reasons.append(f"missing_provenance_columns:{','.join(missing_provenance_columns)}")

    for row in rows:
        row_id = _row_id(row)
        raw_missing = [column for column in RAW_OHLC_COLUMNS if _to_float(row.get(column)) is None]
        if raw_missing:
            invalid_rows.append({"row": row_id, "reason": f"raw_ohlc_missing:{','.join(raw_missing)}"})
            reasons.append(f"raw_ohlc_missing:{row_id}")

        adjusted_missing = [column for column in ADJUSTED_OHLC_COLUMNS if _to_float(row.get(column)) is None]
        factor = _to_float(row.get("adjustment_factor"))
        if adjusted_missing or factor is None:
            unadjusted_rows += 1
            invalid_rows.append({"row": row_id, "reason": "adjusted_ohlc_missing"})
            reasons.append(f"adjusted_ohlc_missing:{row_id}")
            continue

        adjusted_rows += 1
        if factor <= 0:
            invalid_rows.append({"row": row_id, "reason": "adjustment_factor_non_positive"})
            reasons.append(f"adjustment_factor_non_positive:{row_id}")

        adjusted_open = _to_float(row.get("adjusted_open"))
        adjusted_high = _to_float(row.get("adjusted_high"))
        adjusted_low = _to_float(row.get("adjusted_low"))
        adjusted_close = _to_float(row.get("adjusted_close"))
        if (
            adjusted_high is not None
            and adjusted_low is not None
            and adjusted_open is not None
            and adjusted_close is not None
            and (adjusted_high < max(adjusted_open, adjusted_close) or adjusted_low > min(adjusted_open, adjusted_close) or adjusted_high < adjusted_low)
        ):
            invalid_rows.append({"row": row_id, "reason": "adjusted_ohlc_inconsistent"})
            reasons.append(f"adjusted_ohlc_inconsistent:{row_id}")

        if not missing_provenance_columns:
            missing_provenance = [
                column
                for column in PROVENANCE_COLUMNS
                if not str(row.get(column) or "").strip() or (column == "adjustment_method" and row.get(column) == "unknown")
            ]
            if missing_provenance:
                provenance_errors.append({"row": row_id, "missing": missing_provenance})
                reasons.append(f"adjustment_provenance_missing:{row_id}")

    return {
        "adjusted_rows": adjusted_rows,
        "unadjusted_rows": unadjusted_rows,
        "invalid_rows": invalid_rows,
        "provenance_errors": provenance_errors,
        "reasons": _dedupe(reasons),
    }


def audit_factor_consistency(rows: list[dict[str, Any]], factor_records: list[Any]) -> dict[str, Any]:
    factor_map = {
        (str(record.symbol).upper(), str(record.trade_date)): record
        for record in factor_records
        if getattr(record, "status", None) == "ok" and getattr(record, "factor", None) is not None
    }
    reasons: list[str] = []
    factor_errors: list[dict[str, Any]] = []
    provenance_errors: list[dict[str, Any]] = []

    for row in rows:
        row_id = _row_id(row)
        key = (str(row.get("symbol") or "").upper(), str(row.get("trade_date") or ""))
        record = factor_map.get(key)
        if record is None:
            factor_errors.append({"row": row_id, "reason": "factor_record_missing"})
            reasons.append(f"factor_record_missing:{row_id}")
            continue
        factor = _to_float(getattr(record, "factor", None))
        if factor is None or factor <= 0:
            factor_errors.append({"row": row_id, "reason": "factor_record_invalid"})
            reasons.append(f"factor_record_invalid:{row_id}")
            continue
        for raw_column, adjusted_column in zip(RAW_OHLC_COLUMNS, ADJUSTED_OHLC_COLUMNS, strict=True):
            raw_value = _to_float(row.get(raw_column))
            adjusted_value = _to_float(row.get(adjusted_column))
            if raw_value is None or adjusted_value is None:
                continue
            expected = raw_value * factor
            if abs(adjusted_value - expected) > EPSILON:
                factor_errors.append(
                    {
                        "row": row_id,
                        "column": adjusted_column,
                        "expected": expected,
                        "actual": adjusted_value,
                    }
                )
                reasons.append(f"factor_mismatch:{row_id}:{adjusted_column}")
        if str(row.get("adjustment_source_id") or "") != str(getattr(record, "source_id", "")):
            provenance_errors.append({"row": row_id, "reason": "adjustment_source_id_mismatch"})
            reasons.append(f"factor_provenance_mismatch:{row_id}:adjustment_source_id")
        if str(row.get("adjustment_raw_path") or "") != str(getattr(record, "raw_path", "")):
            provenance_errors.append({"row": row_id, "reason": "adjustment_raw_path_mismatch"})
            reasons.append(f"factor_provenance_mismatch:{row_id}:adjustment_raw_path")
        if str(row.get("adjustment_method") or "") != str(getattr(record, "method", "")):
            provenance_errors.append({"row": row_id, "reason": "adjustment_method_mismatch"})
            reasons.append(f"factor_provenance_mismatch:{row_id}:adjustment_method")

    return {
        "factor_consistency_errors": factor_errors,
        "provenance_errors": provenance_errors,
        "reasons": _dedupe(reasons),
    }


def audit_raw_ohlc_baseline(rows: list[dict[str, Any]], baseline_records: list[dict[str, Any]]) -> dict[str, Any]:
    row_map = {
        (str(row.get("symbol") or "").upper(), str(row.get("trade_date") or "")): row
        for row in rows
    }
    reasons: list[str] = []
    errors: list[dict[str, Any]] = []
    for record in baseline_records:
        symbol = str(record.get("symbol") or "").strip().upper()
        trade_date = str(record.get("trade_date") or "").strip()
        row = row_map.get((symbol, trade_date))
        if row is None:
            errors.append({"symbol": symbol, "trade_date": trade_date, "reason": "row_missing"})
            reasons.append(f"raw_ohlc_baseline_row_missing:{symbol}:{trade_date}")
            continue
        for column in RAW_OHLC_COLUMNS:
            expected = _to_float(record.get(column))
            actual = _to_float(row.get(column))
            if expected is None or actual is None or abs(actual - expected) > EPSILON:
                errors.append(
                    {
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "column": column,
                        "expected": expected,
                        "actual": actual,
                    }
                )
                reasons.append(f"raw_ohlc_baseline_mismatch:{symbol}:{trade_date}:{column}")
    return {"status": "ok" if not reasons else "not_ready", "errors": errors, "reasons": _dedupe(reasons)}


def render_adjusted_ohlc_audit_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Adjusted OHLC Execution Audit",
        "",
        f"- Status: `{result.get('status')}`",
        f"- Evidence mode: `{result.get('evidence_mode')}`",
        f"- Backtest planning gate: `{result.get('backtest_planning_gate')}`",
        f"- Required evidence present: `{result.get('required_evidence_present')}`",
        f"- Raw OHLC baseline status: `{result.get('raw_ohlc_baseline_status')}`",
        f"- Symbols: `{', '.join(result.get('symbols') or [])}`",
        f"- Rows total: `{result.get('rows_total')}`",
        f"- Adjusted rows: `{result.get('adjusted_rows')}`",
        f"- Unadjusted rows: `{result.get('unadjusted_rows')}`",
        f"- Validation status: `{result.get('validation_status')}`",
        f"- DB mutation made: `{result.get('db_mutation_made')}`",
        f"- Readiness status: `{result.get('readiness_status')}`",
        f"- Backtest gate: `{result.get('backtest_gate')}`",
        "",
        "## Reasons",
        "",
        *_bullet_list([str(item) for item in result.get("reasons") or []]),
        "",
        "## Caveats",
        "",
        *_bullet_list([str(item) for item in result.get("caveats") or []]),
        "",
        "## Backtest Planning Decision",
        "",
        _planning_recommendation(result),
        "",
        "This audit is read-only. It is not Backtrader, not production DB population, and not investment advice.",
        "",
        "Backtrader/VN100 remains blocked until reviewed evidence, adjusted OHLC execution audit, and adjusted readiness pass.",
    ]
    return "\n".join(lines) + "\n"


def _planning_recommendation(result: dict[str, Any]) -> str:
    if result.get("backtest_planning_gate") == "pass":
        return "Sufficient for small-symbol adjusted OHLC backtest feed planning."
    if result.get("evidence_mode") == "incomplete":
        return "Incomplete evidence mode is not sufficient for backtest planning."
    return "Fix audit blockers before small-symbol backtest feed planning."


def _request_reasons(db_path: Path, symbols: list[str], allow_demo_db: bool) -> list[str]:
    reasons: list[str] = []
    if not symbols:
        reasons.append("explicit_symbols_required")
    if not db_path.exists():
        reasons.append(f"db_missing:{db_path}")
    if _is_demo_db(db_path) and not allow_demo_db:
        reasons.append("demo_db_blocked")
    return reasons


def _required_evidence_reasons(
    *,
    factor_records_path: str | Path | None,
    validation_report_path: str | Path | None,
    readiness_report_path: str | Path | None,
    require_factor_records: bool,
    require_validation_report: bool,
    require_readiness_report: bool,
) -> list[str]:
    reasons: list[str] = []
    if require_factor_records and factor_records_path is None:
        reasons.append("factor_records_required")
    if require_validation_report and validation_report_path is None:
        reasons.append("validation_report_required")
    if require_readiness_report and readiness_report_path is None:
        reasons.append("readiness_report_required")
    return reasons


def _load_daily_price_rows(con: sqlite3.Connection, symbols: list[str]) -> list[dict[str, Any]]:
    placeholders = ", ".join(["?"] * len(symbols))
    rows = con.execute(
        f"""
        SELECT *
        FROM daily_prices
        WHERE symbol IN ({placeholders})
        ORDER BY symbol, trade_date, security_id, source_id
        """,
        symbols,
    ).fetchall()
    return [dict(row) for row in rows]


def _load_status_report(path: str | Path | None, label: str) -> dict[str, Any]:
    if path is None:
        return {"status": None, "reasons": []}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"status": "missing_report", "reasons": [f"{label}_report_missing:{path}"]}
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"status": "invalid_report", "reasons": [f"{label}_report_invalid:{exc}"]}
    if not isinstance(payload, dict):
        return {"status": "invalid_report", "reasons": [f"{label}_report_must_be_object"]}
    return payload


def _validation_report_reasons(report: dict[str, Any]) -> list[str]:
    if report.get("status") is None:
        return []
    reasons = [str(item) for item in report.get("reasons") or []]
    if report.get("status") != "ok":
        reasons.append(f"validation_status_not_ok:{report.get('status')}")
    if report.get("db_mutation_made") is not True:
        reasons.append("validation_db_mutation_not_made")
    return _dedupe(reasons)


def _readiness_report_reasons(report: dict[str, Any]) -> list[str]:
    if report.get("status") is None:
        return []
    reasons = [str(item) for item in report.get("reasons") or []]
    if report.get("status") != "ok":
        reasons.append(f"readiness_status_not_ok:{report.get('status')}")
    if report.get("backtest_gate") != "pass":
        reasons.append(f"readiness_backtest_gate_not_pass:{report.get('backtest_gate')}")
    return _dedupe(reasons)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    tables = {
        str(row["name"])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if table not in tables:
        return set()
    return {str(row["name"]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _summary(
    *,
    status: str,
    db_path: Path,
    symbols: list[str],
    rows_total: int = 0,
    adjusted_rows: int = 0,
    unadjusted_rows: int = 0,
    missing_symbols: list[str] | None = None,
    invalid_rows: list[dict[str, Any]] | None = None,
    factor_consistency_errors: list[dict[str, Any]] | None = None,
    provenance_errors: list[dict[str, Any]] | None = None,
    raw_ohlc_baseline_status: str = "not_provided",
    raw_ohlc_baseline_errors: list[dict[str, Any]] | None = None,
    readiness_status: str | None = None,
    backtest_gate: str | None = None,
    validation_status: str | None = None,
    db_mutation_made: bool | None = None,
    reasons: list[str] | None = None,
    validation: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
    evidence_mode: str = "strict",
    required_evidence_present: bool = False,
    backtest_planning_gate: str = "blocked",
    incomplete_evidence: bool = False,
) -> dict[str, Any]:
    caveats = [
        "Read-only adjusted OHLC execution audit.",
        "No DB mutation, no live fetch, no Backtrader, and no full VN100 run.",
    ]
    if incomplete_evidence:
        caveats.append("Incomplete evidence mode; not sufficient for backtest planning.")
    if raw_ohlc_baseline_status == "not_provided":
        caveats.append(
            "Raw OHLC baseline not provided; audit only confirms read-only behavior, not pre-execute raw OHLC equality."
        )
    return {
        "status": status,
        "db_path": str(db_path),
        "symbols": symbols,
        "rows_total": rows_total,
        "adjusted_rows": adjusted_rows,
        "unadjusted_rows": unadjusted_rows,
        "missing_symbols": missing_symbols or [],
        "invalid_rows": invalid_rows or [],
        "factor_consistency_errors": factor_consistency_errors or [],
        "provenance_errors": provenance_errors or [],
        "raw_ohlc_baseline_status": raw_ohlc_baseline_status,
        "raw_ohlc_baseline_errors": raw_ohlc_baseline_errors or [],
        "readiness_status": readiness_status,
        "backtest_gate": backtest_gate,
        "validation_status": validation_status,
        "db_mutation_made": db_mutation_made,
        "evidence_mode": evidence_mode,
        "required_evidence_present": required_evidence_present,
        "backtest_planning_gate": backtest_planning_gate,
        "reasons": _dedupe(reasons or []),
        "validation": validation or {},
        "readiness": readiness or {},
        "caveats": caveats,
    }


def _empty_factor_audit() -> dict[str, Any]:
    return {"factor_consistency_errors": [], "provenance_errors": [], "reasons": []}


def _baseline_not_provided() -> dict[str, Any]:
    return {"status": "not_provided", "errors": [], "reasons": []}


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


def _row_id(row: dict[str, Any]) -> str:
    return f"{row.get('symbol')}:{row.get('trade_date')}:{row.get('security_id')}"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _bullet_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None."]
