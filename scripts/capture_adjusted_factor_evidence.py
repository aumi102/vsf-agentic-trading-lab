from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.adjusted_factor_evidence import capture_payload_adjustment_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture adjusted-factor evidence from a local JSON payload.")
    parser.add_argument("--source", required=True, help="Source identifier for the inspected payload.")
    parser.add_argument("--symbol", required=True, help="Ticker symbol for the inspected payload.")
    parser.add_argument("--payload", required=True, help="Path to a local JSON payload.")
    parser.add_argument("--output", help="Optional path to write the evidence JSON.")
    args = parser.parse_args()

    result = capture_payload_adjustment_evidence(
        symbol=args.symbol,
        source=args.source,
        payload_path=args.payload,
    )
    if args.output and result["status"] not in {"missing_payload", "invalid_json"}:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] not in {"missing_payload", "invalid_json"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
