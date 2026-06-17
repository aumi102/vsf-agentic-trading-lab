from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.db.build_mvp_store import DEFAULT_DB_PATH, DEFAULT_RAW_BASE_DIR
from trading_agent.ingestion.ohlcv_ingestion import DEFAULT_SOURCE, run_ohlcv_ingestion


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local OHLCV ingestion foundation.")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. FPT,VNM,VCB.")
    parser.add_argument("--mode", choices=["cached", "live"], default="cached")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--raw-base-dir", default=str(DEFAULT_RAW_BASE_DIR))
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--allow-network", action="store_true", help="Required before any future live network mode can run.")
    parser.add_argument("--refresh-features", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--refresh-signals", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    result = run_ohlcv_ingestion(
        symbols=_parse_symbols(args.symbols),
        db_path=args.db_path,
        source=args.source,
        mode=args.mode,
        allow_network=args.allow_network,
        refresh_features=args.refresh_features,
        refresh_signals=args.refresh_signals,
        raw_base_dir=args.raw_base_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    _print_quality_table(result)
    return 0 if result["status"] in {"ok", "partial_ok"} else 1


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _print_quality_table(result: dict[str, object]) -> None:
    quality = result.get("quality")
    if not isinstance(quality, dict):
        return
    print()
    print("quality_table")
    print("table | rows | pass | warn | fail")
    print("--- | ---: | ---: | ---: | ---:")
    for name in ["daily_prices", "feature_snapshots", "signals"]:
        item = quality.get(name)
        if not isinstance(item, dict):
            continue
        print(
            f"{name} | {item.get('row_count', 0)} | {item.get('pass_count', 0)} | "
            f"{item.get('warn_count', 0)} | {item.get('fail_count', 0)}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
