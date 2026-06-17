from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOL_CONFIG = ROOT / "configs" / "ingestion" / "live_symbols_mvp.json"
DEFAULT_RATE_CONFIG = ROOT / "configs" / "ingestion" / "rate_limit_policy.json"
DEFAULT_RAW_BASE_DIR = Path("data/raw/controlled_fetch/source=vietcap_iq")


def plan_live_ingestion_run(
    *,
    symbols: list[str] | None = None,
    config_path: str | Path = DEFAULT_SYMBOL_CONFIG,
    rate_limit_path: str | Path = DEFAULT_RATE_CONFIG,
    count_back: int | None = None,
    raw_base_dir: str | Path = DEFAULT_RAW_BASE_DIR,
) -> dict[str, Any]:
    symbol_config = _load_json(Path(config_path))
    rate_config = _load_json(Path(rate_limit_path))
    allowed = _normalize_symbols(symbol_config.get("allowed_symbols", []))
    requested = _normalize_symbols(symbols or symbol_config.get("default_symbols", []))
    default_count_back = int(symbol_config.get("default_count_back") or 100)
    effective_count_back = int(count_back if count_back is not None else default_count_back)
    max_symbols_per_batch = min(
        int(symbol_config.get("max_symbols_per_batch") or 3),
        int(rate_config.get("max_symbols_per_batch") or 3),
    )
    caveats = [
        "Dry-run plan only; no network request made.",
        "No DB mutation, scheduler, or full-universe crawl is performed.",
    ]
    validation = _validate(
        requested=requested,
        allowed=allowed,
        count_back=effective_count_back,
        max_symbols_per_batch=max_symbols_per_batch,
        rate_config=rate_config,
    )
    status = "ok" if not validation else "blocked"
    batches = []
    if status == "ok":
        batches = [
            {
                "batch_id": 1,
                "symbols": requested,
                "count_back": effective_count_back,
                "estimated_raw_paths": [
                    str(Path(raw_base_dir) / "planned_run_id" / f"vietcap_iq_gap_chart_{symbol.lower()}_countback_{effective_count_back}" / "payload.json")
                    for symbol in requested
                ],
            }
        ]
    return {
        "status": status,
        "source": str(symbol_config.get("source") or "vietcap_iq_gap_chart"),
        "mode": "dry_run",
        "symbols_requested": requested,
        "allowed_symbols": allowed,
        "count_back": effective_count_back,
        "max_symbols_per_batch": max_symbols_per_batch,
        "rate_limit_policy": {
            "policy_name": rate_config.get("policy_name"),
            "min_seconds_between_requests": rate_config.get("min_seconds_between_requests"),
            "max_batches_per_manual_run": rate_config.get("max_batches_per_manual_run"),
            "scheduler_enabled": bool(rate_config.get("scheduler_enabled")),
            "raw_retention_days": rate_config.get("raw_retention_days"),
            "requires_manual_allow_network": bool(rate_config.get("requires_manual_allow_network", True)),
        },
        "planned_batches": batches,
        "blocked_reasons": validation,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "network_request_made": False,
        "db_mutation_made": False,
        "caveats": caveats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan a controlled live OHLCV ingestion run without network access.")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbols. Defaults to config symbols.")
    parser.add_argument("--config", default=str(DEFAULT_SYMBOL_CONFIG))
    parser.add_argument("--rate-limit-config", default=str(DEFAULT_RATE_CONFIG))
    parser.add_argument("--count-back", type=int, default=None)
    parser.add_argument("--raw-base-dir", default=str(DEFAULT_RAW_BASE_DIR))
    args = parser.parse_args()
    result = plan_live_ingestion_run(
        symbols=_parse_symbols(args.symbols),
        config_path=args.config,
        rate_limit_path=args.rate_limit_config,
        count_back=args.count_back,
        raw_base_dir=args.raw_base_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    _print_batches(result)
    return 0 if result["status"] == "ok" else 1


def _validate(
    *,
    requested: list[str],
    allowed: list[str],
    count_back: int,
    max_symbols_per_batch: int,
    rate_config: dict[str, Any],
) -> list[str]:
    reasons = []
    if not requested:
        reasons.append("No symbols requested.")
    unknown = [symbol for symbol in requested if symbol not in allowed]
    if unknown:
        reasons.append(f"Symbols not in allowlist: {', '.join(unknown)}.")
    if len(requested) > max_symbols_per_batch:
        reasons.append(f"Requested {len(requested)} symbols; max per batch is {max_symbols_per_batch}.")
    if count_back <= 0:
        reasons.append("count_back must be positive.")
    if int(rate_config.get("min_seconds_between_requests") or 0) < 1:
        reasons.append("min_seconds_between_requests must be at least 1.")
    if int(rate_config.get("max_batches_per_manual_run") or 0) < 1:
        reasons.append("max_batches_per_manual_run must be at least 1.")
    if bool(rate_config.get("scheduler_enabled")):
        reasons.append("scheduler_enabled must remain false for this dry-run planner.")
    return reasons


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_symbols(value: str) -> list[str]:
    return _normalize_symbols(value.split(",") if value else [])


def _normalize_symbols(values: Any) -> list[str]:
    seen = set()
    normalized = []
    for value in values or []:
        symbol = str(value or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    return normalized


def _print_batches(result: dict[str, Any]) -> None:
    print()
    print("planned_batches")
    print("batch | symbols | count_back | estimated_raw_paths")
    print("---: | --- | ---: | ---")
    for batch in result.get("planned_batches", []):
        if not isinstance(batch, dict):
            continue
        paths = batch.get("estimated_raw_paths") or []
        print(
            f"{batch.get('batch_id')} | {','.join(batch.get('symbols') or [])} | "
            f"{batch.get('count_back')} | {';'.join(str(path) for path in paths)}"
        )
    if not result.get("planned_batches"):
        print("- | - | - | -")
    print()
    print("no network request made")


if __name__ == "__main__":
    raise SystemExit(main())
