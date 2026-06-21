from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.validate_reviewed_adjusted_price_package import validate_package
from trading_agent.ingestion.adjusted_readiness import get_adjusted_ohlc_readiness


DEMO_DB_PATH = Path("data/demo/mvp_trading_agent.sqlite")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reviewed adjusted-price local execute readiness.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--factor-output", required=True)
    parser.add_argument("--validation-output", required=True)
    parser.add_argument("--readiness-output", required=True)
    parser.add_argument("--report-md", required=True)
    parser.add_argument("--require-dry-run-report", default=None)
    parser.add_argument("--allow-demo-db", action="store_true")
    args = parser.parse_args()

    result = run_local_execute_readiness(
        package_dir=Path(args.package_dir),
        symbols=_parse_symbols(args.symbols),
        db_path=Path(args.db_path),
        factor_output_path=Path(args.factor_output),
        validation_output_path=Path(args.validation_output),
        readiness_output_path=Path(args.readiness_output),
        report_md_path=Path(args.report_md),
        require_dry_run_report=Path(args.require_dry_run_report) if args.require_dry_run_report else None,
        allow_demo_db=args.allow_demo_db,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def run_local_execute_readiness(
    *,
    package_dir: Path,
    symbols: list[str],
    db_path: Path | None,
    factor_output_path: Path | None,
    validation_output_path: Path | None,
    readiness_output_path: Path | None,
    report_md_path: Path | None,
    require_dry_run_report: Path | None = None,
    allow_demo_db: bool = False,
) -> dict[str, Any]:
    request_errors = _validate_request(
        db_path=db_path,
        factor_output_path=factor_output_path,
        validation_output_path=validation_output_path,
        readiness_output_path=readiness_output_path,
        report_md_path=report_md_path,
        require_dry_run_report=require_dry_run_report,
        allow_demo_db=allow_demo_db,
    )
    if request_errors:
        result = _summary(status="invalid_request", symbols=symbols, db_path=db_path, reasons=request_errors)
        if report_md_path is not None:
            _write_markdown_report(result, report_md_path)
        return result

    validation = validate_package(
        package_dir=package_dir,
        symbols=symbols,
        validation_output_path=validation_output_path,
        factor_output_path=factor_output_path,
        db_path=db_path,
        execute=True,
    )
    if validation.get("status") != "ok" and validation.get("db_mutation_made") is not True:
        readiness = {
            "status": "skipped",
            "backtest_gate": "blocked",
            "reason": "validation_failed_no_db_mutation",
            "symbols": symbols,
            "db_path": str(db_path),
            "caveats": [
                "Readiness skipped because package validation failed before DB mutation.",
            ],
        }
    else:
        readiness = get_adjusted_ohlc_readiness(db_path=db_path, symbols=symbols)
    _write_json(readiness_output_path, readiness)

    reasons = []
    if validation.get("status") != "ok":
        reasons.append(f"validation_status:{validation.get('status')}")
    if readiness.get("reason") == "validation_failed_no_db_mutation":
        reasons.append("validation_failed_no_db_mutation")
    if validation.get("readiness_status") != "ok":
        reasons.append(f"validation_readiness_status:{validation.get('readiness_status')}")
    if validation.get("backtest_gate") != "pass":
        reasons.append(f"validation_backtest_gate:{validation.get('backtest_gate')}")
    if validation.get("db_mutation_made") is not True:
        reasons.append("db_mutation_not_made")
    if readiness.get("status") != "ok":
        reasons.append(f"readiness_status:{readiness.get('status')}")
    if readiness.get("backtest_gate") != "pass":
        reasons.append(f"backtest_gate:{readiness.get('backtest_gate')}")

    status = "ok" if not reasons else "not_ready"
    result = _summary(status=status, symbols=symbols, db_path=db_path, reasons=reasons)
    result["validation"] = validation
    result["readiness"] = readiness
    result["factor_output_path"] = str(factor_output_path)
    result["validation_output_path"] = str(validation_output_path)
    result["readiness_output_path"] = str(readiness_output_path)
    result["report_md_path"] = str(report_md_path)
    result["db_mutation_made"] = bool(validation.get("db_mutation_made"))
    result["readiness_status"] = readiness.get("status")
    result["backtest_gate"] = readiness.get("backtest_gate")
    _write_markdown_report(result, report_md_path)
    return result


def _validate_request(
    *,
    db_path: Path | None,
    factor_output_path: Path | None,
    validation_output_path: Path | None,
    readiness_output_path: Path | None,
    report_md_path: Path | None,
    require_dry_run_report: Path | None,
    allow_demo_db: bool,
) -> list[str]:
    reasons: list[str] = []
    if db_path is None:
        reasons.append("db_path_required")
    elif _is_demo_db(db_path) and not allow_demo_db:
        reasons.append("demo_db_blocked")
    if factor_output_path is None:
        reasons.append("factor_output_required")
    if validation_output_path is None:
        reasons.append("validation_output_required")
    if readiness_output_path is None:
        reasons.append("readiness_output_required")
    if report_md_path is None:
        reasons.append("report_md_required")
    if require_dry_run_report is not None:
        reasons.extend(validate_required_dry_run_report(require_dry_run_report))
    return reasons


def validate_required_dry_run_report(path: Path) -> list[str]:
    reasons: list[str] = []
    if not path.exists():
        return [f"required_dry_run_report_missing:{path}"]
    if path.suffix.lower() != ".md":
        reasons.append("required_dry_run_report_must_be_markdown")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return reasons + ["required_dry_run_report_unreadable"]
    if "# Reviewed Adjusted Price Evidence Dry-Run Report" not in text:
        reasons.append("required_dry_run_report_invalid_format")
    if "- Status: `ok`" not in text:
        reasons.append("required_dry_run_report_not_ok")
    if "Fix the evidence package" in text:
        reasons.append("required_dry_run_report_failed_recommendation")
    if "Backtrader/VN100 must remain blocked" not in text:
        reasons.append("required_dry_run_report_missing_backtrader_block")
    return reasons


def _summary(*, status: str, symbols: list[str], db_path: Path | None, reasons: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "symbols": symbols,
        "db_path": str(db_path) if db_path else None,
        "reasons": reasons,
        "caveats": [
            "Local execute readiness only; no live fetch or production DB default.",
            "Backtrader/VN100 remains blocked until reviewed evidence and adjusted readiness pass.",
        ],
    }


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _write_markdown_report(result: dict[str, Any], path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    readiness = result.get("readiness") if isinstance(result.get("readiness"), dict) else {}
    lines = [
        "# Reviewed Adjusted Price Local Execute Readiness",
        "",
        f"- Decision: `{_decision(result)}`",
        f"- Status: `{result.get('status')}`",
        f"- Symbols: `{', '.join(result.get('symbols') or [])}`",
        f"- DB path: `{result.get('db_path')}`",
        f"- Factor output path: `{result.get('factor_output_path')}`",
        f"- Validation output path: `{result.get('validation_output_path')}`",
        f"- Readiness output path: `{result.get('readiness_output_path')}`",
        f"- Report path: `{result.get('report_md_path')}`",
        f"- DB mutation made: `{result.get('db_mutation_made', False)}`",
        f"- Validation status: `{validation.get('status')}`",
        f"- Readiness status: `{readiness.get('status')}`",
        f"- Backtest gate: `{readiness.get('backtest_gate')}`",
        "",
        "## Reasons",
        "",
        *_bullet_list([str(item) for item in result.get("reasons") or []]),
        "",
        "## Validation Reasons",
        "",
        *_bullet_list([str(item) for item in validation.get("reasons") or []]),
        "",
        "## Readiness Reasons",
        "",
        *_bullet_list(_readiness_reasons(readiness)),
        "",
        "## Recommendation",
        "",
        _recommendation(result),
        "",
        "This is not Backtrader.",
        "",
        "This is not production DB population.",
        "",
        "Backtrader/VN100 remains blocked until reviewed evidence and adjusted readiness pass.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _recommendation(result: dict[str, Any]) -> str:
    if result.get("status") == "ok":
        return "READY_FOR_LOCAL_REVIEW_ONLY: local execute readiness passed for this explicit DB and reviewed package."
    return "Fix the reviewed package, local DB coverage, or readiness blockers before any broader use."


def _decision(result: dict[str, Any]) -> str:
    return "READY_FOR_LOCAL_REVIEW_ONLY" if result.get("status") == "ok" else "BLOCKED"


def _readiness_reasons(readiness: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    raw_reasons = readiness.get("reasons")
    if isinstance(raw_reasons, list):
        reasons.extend(str(item) for item in raw_reasons)
    reason = readiness.get("reason")
    if reason:
        reasons.append(str(reason))
    raw_caveats = readiness.get("caveats")
    if isinstance(raw_caveats, list):
        reasons.extend(str(item) for item in raw_caveats)
    return reasons


def _bullet_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None."]


def _is_demo_db(path: Path) -> bool:
    return path.resolve(strict=False) == (ROOT / DEMO_DB_PATH).resolve(strict=False)


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
