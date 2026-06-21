from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.adjusted_ohlc_execution_audit import (
    audit_adjusted_ohlc_execution,
    render_adjusted_ohlc_audit_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit adjusted OHLC execution outputs without DB mutation.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--factor-records", default=None)
    parser.add_argument("--validation-report", default=None)
    parser.add_argument("--readiness-report", default=None)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-md", default=None)
    parser.add_argument("--allow-demo-db", action="store_true")
    args = parser.parse_args()

    result = audit_adjusted_ohlc_execution(
        db_path=Path(args.db_path),
        symbols=_parse_symbols(args.symbols),
        factor_records_path=Path(args.factor_records) if args.factor_records else None,
        validation_report_path=Path(args.validation_report) if args.validation_report else None,
        readiness_report_path=Path(args.readiness_report) if args.readiness_report else None,
        allow_demo_db=args.allow_demo_db,
    )
    if args.output_json:
        _write_json(Path(args.output_json), result)
    if args.output_md:
        _write_text(Path(args.output_md), render_adjusted_ohlc_audit_markdown(result))
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
