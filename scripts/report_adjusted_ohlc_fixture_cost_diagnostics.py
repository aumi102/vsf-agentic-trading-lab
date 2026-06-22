from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.backtest.adjusted_ohlc_fixture_cost_diagnostics import (
    compute_fixture_cost_diagnostics,
    render_fixture_cost_diagnostics_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report fixture-only cost/slippage bps-unit diagnostics.")
    parser.add_argument("--preparation-json", required=True)
    parser.add_argument("--roundtrip-json", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--max-rows", type=int, default=20)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    result = compute_fixture_cost_diagnostics(
        preparation_path=Path(args.preparation_json),
        roundtrip_path=Path(args.roundtrip_json),
        symbols=[item.strip().upper() for item in args.symbols.split(",") if item.strip()],
        max_rows=args.max_rows,
    )
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if args.output_md:
        path = Path(args.output_md)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_fixture_cost_diagnostics_markdown(result), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
