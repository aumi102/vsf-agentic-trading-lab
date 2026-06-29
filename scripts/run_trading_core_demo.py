"""Trading-core end-to-end demo -- checks all gates honestly.

Steps:
  1. Adjusted OHLC readiness check
  2. Strategy signals (if adjusted feed valid)
  3. Custom backtest (if adjusted feed valid)

If adjusted feed is blocked, stops honestly at the gate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "src"), str(SCRIPT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_agent.storage import questdb_client as qdb  # noqa: E402
from scripts.adjusted_ohlc_readiness import check_adjusted_readiness  # noqa: E402
from scripts.run_trading_signals import compute_signals, STRATEGIES  # noqa: E402
from scripts.run_custom_backtest import run_backtest  # noqa: E402

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL

SEP = "=" * 62
SEP2 = "-" * 62


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading-core end-to-end demo.")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. FPT,HPG,VCB")
    parser.add_argument("--from", dest="from_date", default="2021-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default="2025-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--strategy", default="momentum_v1",
                        choices=list(STRATEGIES.keys()))
    parser.add_argument("--initial-cash", type=float, default=100_000_000)
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    base_url = args.questdb_url.rstrip("/")

    import json as _json

    # ── Step 1: Adjusted OHLC readiness ─────────────────────────────────────
    with qdb.open_client(timeout_seconds=60.0) as client:
        readiness = check_adjusted_readiness(client, base_url, symbols)

    gate = readiness["backtest_gate"]
    status = readiness["status"]
    total_rows = readiness["coverage"]["total_rows"]
    warn_rows = readiness["coverage"]["warn_rows"]
    real_rows = readiness["coverage"]["real_factor_rows"]

    if args.json:
        step1 = {
            "step": "adjusted_ohlc_readiness",
            "gate": gate,
            "status": status,
            "total_rows": total_rows,
            "warn_rows": warn_rows,
            "real_factor_rows": real_rows,
        }
    else:
        print(f"\n{SEP}")
        print(f"  STEP 1: Adjusted OHLC Readiness")
        print(f"{SEP}")
        print(f"  status:          {status}")
        print(f"  backtest_gate:  {gate}")
        print(f"  total_rows:     {total_rows:,}")
        print(f"  warn_rows:      {warn_rows:,}  (adj == raw, factor=1.0)")
        print(f"  real_factor_rows: {real_rows:,}  (factor != 1.0)")
        print(f"{SEP2}")
        for s in readiness["caveats"]:
            print(f"  {s}")
        print(f"{SEP}")

    if gate == "blocked":
        blocked_msg = (
            "BLOCKED_ADJUSTED_FACTOR_FABRICATED"
            if "FABRICATED" in status
            else "BLOCKED_ADJUSTED_FEED_MISSING"
        )
        if args.json:
            print(_json.dumps({
                "status": blocked_msg,
                "step": "adjusted_ohlc_readiness",
                "gate": gate,
                "symbols": symbols,
                "total_rows": total_rows,
                "real_factor_rows": real_rows,
                "next_action": "Need source-backed adjusted price / corporate action factor",
                "caveats": readiness["caveats"],
            }, indent=2))
        else:
            print(f"\n  {SEP}")
            print(f"  TRADE GATE: {blocked_msg}")
            print(f"{SEP}")
            print(f"  Stopped -- adjusted OHLCV source factors are fabricated (adj == raw).")
            print(f"  Need source-backed adjusted price / corporate action factor before")
            print(f"  real strategy signals or backtest.")
            print(f"{SEP}")
        return 1

    # ── Step 2: Strategy signals ─────────────────────────────────────────────
    with qdb.open_client(timeout_seconds=60.0) as client:
        results, caveats = compute_signals(client, base_url, symbols, args.strategy, lookback=120)

    if args.json:
        step2 = {"step": "strategy_signals", "results": results}
    else:
        print(f"\n  STEP 2: Strategy Signals (strategy={args.strategy})")
        print(f"{SEP}")
        for r in results:
            print(f"\n  [{r['signal']:4s}] {r['symbol']}  score={r['score']:+.4f}  as_of={r['as_of']}")
            print(f"           reason: {r['reason']}")
            print(f"           features: {r['features_used']}")
            if r.get('risk_flags'):
                print(f"           risk_flags: {r['risk_flags']}")

    # ── Step 3: Custom backtest ─────────────────────────────────────────────
    with qdb.open_client(timeout_seconds=60.0) as client:
        bk_results, bk_caveats = run_backtest(
            client, base_url, symbols,
            args.from_date, args.to_date,
            args.strategy, args.initial_cash,
        )

    if args.json:
        step3 = {"step": "custom_backtest", "results": bk_results}
        print(_json.dumps({
            "status": "ok",
            "steps": [step1, step2, step3],
            "caveats": caveats + bk_caveats,
        }, indent=2))
    else:
        for r in bk_results:
            print(f"\n  {r['symbol']}  reason={r['reason']}")
            print(f"  portfolio: {r['portfolio']}")
            print(f"  metrics:   {r['metrics']}")
            print(f"  trades:    {len(r['trade_ledger'])}")
        print(f"\n{SEP}")
        print(f"  Done. All steps complete.")
        print(f"{SEP}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())