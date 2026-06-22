from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.strategy.strategy_adapter_registry import list_strategy_adapters


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List the read-only strategy adapter registry families."
    )
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = {
        "registry": "strategy_adapter_registry",
        "families": list_strategy_adapters(),
        "not_financial_advice": True,
        "caveats": [
            "Planning registry only; no real strategy adapter is enabled.",
            "No performance, profitability, or recommendation claim.",
        ],
    }
    if args.output_json:
        output = Path(args.output_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
