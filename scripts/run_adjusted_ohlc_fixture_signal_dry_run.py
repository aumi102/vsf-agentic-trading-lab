from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.backtest.adjusted_ohlc_fixture_signal_dry_run import (
    build_fixture_signal_preview,
    render_fixture_signal_report_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic fixture signal dry-run preview over a PR #49 preparation JSON."
    )
    parser.add_argument("--preparation-json", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--signal-mode", default="all_cash")
    parser.add_argument("--max-rows", type=int, default=20)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-md", default=None)
    args = parser.parse_args()

    result = build_fixture_signal_preview(
        preparation_path=Path(args.preparation_json),
        symbols=_parse_symbols(args.symbols),
        signal_mode=args.signal_mode,
        max_rows=args.max_rows,
    )
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
    if args.output_md:
        md_path = Path(args.output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_fixture_signal_report_markdown(result), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
