"""Fetch the full Vietcap tradable universe from the verified search-bar endpoint.

Outputs (overwritten each run, plus a run-stamped raw copy for provenance):
  * data/cache/vietcap/universe/latest_universe.json
  * data/cache/vietcap/universe/latest_universe.csv
  * data/raw/vietcap_universe/run_id=<RUN_ID>/payload.json + metadata.json

Fails loudly (exit 2) if fewer than --min-symbols tradable tickers are found.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Vietnamese company names -> force UTF-8 stdout on the Windows console.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - older interpreters
    pass

from trading_agent.ingestion.vietcap_full_ohlcv_fetcher import (  # noqa: E402
    UNIVERSE_URL,
    extract_universe,
    fetch_universe_payload,
    make_run_id,
    utc_now_iso,
)

UNIVERSE_CACHE_DIR = ROOT / "data/cache/vietcap/universe"
RAW_DIR = ROOT / "data/raw/vietcap_universe"
CSV_COLUMNS = ["symbol", "security_id", "exchange", "company_name", "short_name", "company_type_code"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the full Vietcap tradable universe.")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--min-symbols", type=int, default=1000)
    args = parser.parse_args()

    run_id = make_run_id()
    print(f"Fetching universe from {UNIVERSE_URL}")
    payload, http_status, raw_bytes = fetch_universe_payload(args.timeout_seconds)
    info = extract_universe(payload)
    tradable = info["tradable"]

    # Persist raw payload + metadata for provenance.
    raw_run_dir = RAW_DIR / f"run_id={run_id}"
    raw_run_dir.mkdir(parents=True, exist_ok=True)
    (raw_run_dir / "payload.json").write_bytes(raw_bytes)
    content_hash = hashlib.sha256(raw_bytes).hexdigest()
    metadata = {
        "source_name": "vietcap_iq",
        "dataset": "vietcap_iq_company_search_bar",
        "endpoint": UNIVERSE_URL,
        "run_id": run_id,
        "http_status": http_status,
        "content_hash": content_hash,
        "byte_size": len(raw_bytes),
        "crawled_at": utc_now_iso(),
        "total_raw_rows": info["total_raw_rows"],
        "unique_tradable_symbols": info["unique_tradable_symbols"],
        "excluded_index_rows": info["excluded_index_rows"],
        "excluded_non_tradable_floor_rows": info["excluded_non_tradable_floor_rows"],
        "excluded_invalid_rows": info["excluded_invalid_rows"],
    }
    (raw_run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    # Persist the canonical latest universe (json + csv).
    UNIVERSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    latest = {"run_id": run_id, "fetched_at": metadata["crawled_at"], "summary": metadata, "tradable": tradable}
    (UNIVERSE_CACHE_DIR / "latest_universe.json").write_text(
        json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(tradable)
    (UNIVERSE_CACHE_DIR / "latest_universe.csv").write_text(buffer.getvalue(), encoding="utf-8")

    # Report.
    exchanges: dict[str, int] = {}
    for row in tradable:
        exchanges[row["exchange"]] = exchanges.get(row["exchange"], 0) + 1
    print(f"http_status={http_status}")
    print(f"total_raw_rows={info['total_raw_rows']}")
    print(f"unique_tradable_symbols={info['unique_tradable_symbols']}")
    print(f"listed_market_candidates_by_exchange={exchanges}")
    print(f"excluded_index_rows={info['excluded_index_rows']}")
    print(f"excluded_non_tradable_floor_rows={info['excluded_non_tradable_floor_rows']}")
    print(f"excluded_invalid_rows={info['excluded_invalid_rows']}")
    print(f"universe_json={UNIVERSE_CACHE_DIR / 'latest_universe.json'}")
    print(f"universe_csv={UNIVERSE_CACHE_DIR / 'latest_universe.csv'}")

    if info["unique_tradable_symbols"] < args.min_symbols:
        print(
            f"FAIL: only {info['unique_tradable_symbols']} tradable symbols found, "
            f"expected >= {args.min_symbols}. Endpoint or filter may have changed.",
            file=sys.stderr,
        )
        return 2
    print(f"OK: {info['unique_tradable_symbols']} tradable symbols (>= {args.min_symbols}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
