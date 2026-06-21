from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a reviewed adjusted-price validation report.")
    parser.add_argument("--validation-report", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--expected-symbols", default="")
    parser.add_argument("--min-usable-records", type=int, default=1)
    args = parser.parse_args()

    result = summarize_validation_report(
        validation_report_path=Path(args.validation_report),
        output_md_path=Path(args.output_md),
        expected_symbols=_parse_symbols(args.expected_symbols),
        min_usable_records=args.min_usable_records,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def summarize_validation_report(
    *,
    validation_report_path: Path,
    output_md_path: Path,
    expected_symbols: list[str] | None = None,
    min_usable_records: int = 1,
) -> dict[str, Any]:
    try:
        report = json.loads(validation_report_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return _summary(
            status="missing_report",
            validation_report_path=validation_report_path,
            output_md_path=output_md_path,
            reasons=[f"Validation report not found: {validation_report_path}"],
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _summary(
            status="invalid_report_json",
            validation_report_path=validation_report_path,
            output_md_path=output_md_path,
            reasons=[f"Invalid validation report JSON: {exc}"],
        )

    if not isinstance(report, dict):
        return _summary(
            status="invalid_report_json",
            validation_report_path=validation_report_path,
            output_md_path=output_md_path,
            reasons=["Validation report must be a JSON object."],
        )

    reasons = _validation_reasons(report, expected_symbols or [], min_usable_records)
    status = "ok" if not reasons else "not_ready"
    markdown = _render_markdown(report, validation_report_path, reasons)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text(markdown, encoding="utf-8")
    return _summary(
        status=status,
        validation_report_path=validation_report_path,
        output_md_path=output_md_path,
        reasons=reasons,
    )


def _validation_reasons(report: dict[str, Any], expected_symbols: list[str], min_usable_records: int) -> list[str]:
    reasons: list[str] = []
    if report.get("status") != "ok":
        reasons.append(f"validation_status:{report.get('status')}")
    integrity = report.get("manifest_integrity")
    if not isinstance(integrity, dict):
        reasons.append("manifest_integrity_missing")
    elif integrity.get("payload_sha256_match") is not True:
        reasons.append("payload_sha256_not_matched")
    invalid = _to_int(report.get("invalid_records"))
    if invalid > 0:
        reasons.append(f"invalid_records_present:{invalid}")
    missing = _to_int(report.get("missing_records"))
    if missing > 0:
        reasons.append(f"missing_records_present:{missing}")
    report_symbols = {_normalize_symbol(item) for item in report.get("symbols") or []}
    missing_symbols = [symbol for symbol in expected_symbols if symbol not in report_symbols]
    if missing_symbols:
        reasons.append(f"expected_symbols_missing:{','.join(missing_symbols)}")
    usable = _to_int(report.get("usable_records"))
    if usable < min_usable_records:
        reasons.append(f"usable_records_below_min:{usable}<{min_usable_records}")
    return reasons


def _render_markdown(report: dict[str, Any], validation_report_path: Path, reasons: list[str]) -> str:
    status = str(report.get("status"))
    recommendation = _recommendation(report, reasons)
    lines = [
        "# Reviewed Adjusted Price Evidence Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- Validation report: `{validation_report_path}`",
        f"- Status: `{status}`",
        f"- Symbols: `{', '.join(str(item) for item in report.get('symbols') or [])}`",
        f"- Rows total: `{_to_int(report.get('rows_total'))}`",
        f"- Usable records: `{_to_int(report.get('usable_records'))}`",
        f"- Invalid records: `{_to_int(report.get('invalid_records'))}`",
        f"- Missing records: `{_to_int(report.get('missing_records'))}`",
        f"- Readiness status: `{report.get('readiness_status')}`",
        f"- Backtest gate: `{report.get('backtest_gate')}`",
        "",
        "## Manifest Integrity",
        "",
    ]
    integrity = report.get("manifest_integrity") if isinstance(report.get("manifest_integrity"), dict) else {}
    if integrity:
        for key in [
            "source_id",
            "raw_path",
            "reviewer",
            "reviewed_at",
            "evidence_basis",
            "payload_sha256",
            "computed_payload_sha256",
            "payload_sha256_match",
            "not_real_market_data",
        ]:
            if key in integrity:
                lines.append(f"- {key}: `{integrity.get(key)}`")
    else:
        lines.append("- Not present.")

    lines.extend(
        [
            "",
            "## Reasons",
            "",
            *_bullet_list([*reasons, *[str(item) for item in report.get("reasons") or []]]),
            "",
            "## Caveats",
            "",
            *_bullet_list([str(item) for item in report.get("caveats") or []]),
            "",
            "## Recommendation",
            "",
            recommendation,
            "",
            "Backtrader/VN100 must remain blocked until reviewed evidence passes and adjusted readiness passes.",
        ]
    )
    return "\n".join(lines) + "\n"


def _recommendation(report: dict[str, Any], reasons: list[str]) -> str:
    if reasons:
        return "Fix the evidence package before any execute-mode DB population."
    if report.get("readiness_status") in (None, "") and report.get("backtest_gate") in (None, ""):
        return "Dry-run validation passed. Ready for reviewed execute dry-run on an explicit local DB."
    if report.get("readiness_status") == "ok" and report.get("backtest_gate") == "pass":
        return "Execute validation passed on the local DB. Inspect readiness before any broader use."
    return "Validation passed, but readiness is not a pass signal. Keep Backtrader blocked."


def _summary(
    *,
    status: str,
    validation_report_path: Path,
    output_md_path: Path,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "validation_report_path": str(validation_report_path),
        "output_md_path": str(output_md_path),
        "reasons": reasons,
        "caveats": [
            "Report summary only; no evidence fetch, DB mutation, or Backtrader run.",
            "Do not commit real evidence or generated reports unless explicitly curated.",
        ],
    }


def _bullet_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None."]


def _parse_symbols(value: str) -> list[str]:
    return [_normalize_symbol(item) for item in str(value or "").split(",") if _normalize_symbol(item)]


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
