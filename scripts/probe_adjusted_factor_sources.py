from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.adjusted_factor_probe import (
    inspect_payload_for_adjustment_evidence,
    plan_adjusted_factor_probe,
)


DEFAULT_CONFIG = ROOT / "configs" / "ingestion" / "adjusted_factor_probe_mvp.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or inspect adjusted-factor source evidence.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--symbols", default="")
    parser.add_argument("--candidate-sources", default="")
    parser.add_argument("--inspect-payload", default="")
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()

    if args.inspect_payload:
        payload_path = Path(args.inspect_payload)
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return _print_error("missing_payload", f"Payload not found: {payload_path}")
        except json.JSONDecodeError as exc:
            return _print_error("invalid_json", f"Invalid JSON payload: {exc}")
        result = inspect_payload_for_adjustment_evidence(payload)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    config = _load_json(Path(args.config))
    symbols = _parse_csv(args.symbols) or _normalize_symbols(config.get("default_symbols", []))
    candidate_sources = _parse_csv(args.candidate_sources) or list(config.get("candidate_sources", []))
    result = plan_adjusted_factor_probe(
        symbols=symbols,
        candidate_sources=candidate_sources,
        allow_network=bool(args.allow_network or config.get("allow_network_default", False)),
        max_symbols=int(config.get("max_symbols_per_probe") or 3),
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_csv(value: str) -> list[str]:
    return _normalize_symbols(value.split(",") if value else [])


def _normalize_symbols(values: object) -> list[str]:
    seen = set()
    normalized = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text.upper() if text.isalpha() else text)
    return normalized


def _print_error(status: str, message: str) -> int:
    print(
        json.dumps(
            {
                "status": status,
                "error": message,
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
