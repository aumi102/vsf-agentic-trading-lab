from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.strategy.strategy_adapter import run_strategy_adapter_preview


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a no-op strategy adapter interface preview.")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--prepared-input", required=True)
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = run_strategy_adapter_preview(
        contract_path=Path(args.contract),
        prepared_input_path=Path(args.prepared_input),
    )
    if args.output_json:
        output = Path(args.output_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
