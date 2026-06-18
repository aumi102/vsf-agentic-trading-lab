from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.factor_source_verification import (
    CANDIDATE_METHODS,
    verify_factor_source_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a local adjusted-close or corporate-action factor payload (no network)."
    )
    parser.add_argument("--payload", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--raw-path", required=True)
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    if args.method not in CANDIDATE_METHODS:
        return _print_error(
            "unknown_method",
            f"Unknown method: {args.method}. Expected one of {sorted(CANDIDATE_METHODS)}.",
        )

    payload_path = Path(args.payload)
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return _print_error("missing_payload", f"Payload not found: {payload_path}")
    except json.JSONDecodeError as exc:
        return _print_error("invalid_json", f"Invalid JSON payload: {exc}")

    result = verify_factor_source_payload(
        payload,
        method=args.method,
        source_id=args.source_id,
        raw_path=args.raw_path,
        symbols=_parse_csv(args.symbols),
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" and result["usable_records"] > 0 else 1


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def _print_error(status: str, message: str) -> int:
    print(
        json.dumps(
            {
                "status": status,
                "error": message,
                "usable_records": 0,
                "network_request_made": False,
                "db_mutation_made": False,
                "adjusted_ohlc_populated": False,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
