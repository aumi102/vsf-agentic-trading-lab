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
    by_symbol = readiness.get("by_symbol", [])
    sym_status = {s["symbol"]: s for s in by_symbol}

    pass_syms = [s for s in symbols if sym_status.get(s, {}).get("backtest_gate") == "pass"]
    block_syms = [s for s in symbols if sym_status.get(s, {}).get("backtest_gate") == "blocked"]

    if args.json:
        step1 = {
            "step": "adjusted_ohlc_readiness",
            "gate": gate,
            "status": status,
            "pass_symbols": pass_syms,
            "blocked_symbols": block_syms,
        }
    else:
        print(f"\n{SEP}")
        print(f"  STEP 1: Adjusted OHLC Readiness")
        print(f"{SEP}")
        print(f"  status:   {status}")
        print(f"  gate:     {gate}")
        print(f"{SEP2}")
        for sym in symbols:
            s = sym_status.get(sym, {})
            if s.get("backtest_gate") == "pass":
                src = s.get("source", "?")
                rows = s.get("row_count", 0)
                print(f"    [PASS] {sym:<6}  rows={rows:>6,}  source={src}")
            else:
                reason = (s.get("blocked_reason") or "unknown")[:80]
                print(f"    [BLOCK] {sym:<6}  {reason}")
        print(f"{SEP2}")
        for c in readiness["caveats"]:
            print(f"  {c}")
        print(f"{SEP}")

    if gate == "blocked":
        if args.json:
            print(_json.dumps({
                "status": "BLOCKED",
                "step": "adjusted_ohlc_readiness",
                "gate": gate,
                "symbols": symbols,
                "blocked_symbols": block_syms,
                "caveats": readiness["caveats"],
            }, indent=2))
        else:
            print(f"\n  {SEP}")
            print(f"  TRADE GATE: BLOCKED (all symbols)")
            print(f"{SEP}")
            print(f"  Stopped -- no source-backed adjusted OHLC for any requested symbol.")
            print(f"  Need corporate action source for: {', '.join(block_syms)}")
            print(f"{SEP}")
        return 1

    # ── Step 2: Strategy signals ─────────────────────────────────────────────
    with qdb.open_client(timeout_seconds=60.0) as client:
        results, caveats, sig_overall = compute_signals(
            client, base_url, symbols, args.strategy,
            lookback=120, require_all=False,
        )

    if args.json:
        step2 = {"step": "strategy_signals", "overall": sig_overall, "results": results}
    else:
        print(f"\n  STEP 2: Strategy Signals (strategy={args.strategy})")
        print(f"{SEP}")
        for r in results:
            sig = str(r.get("signal", "?"))
            print(f"    [{sig:6s}] {r['symbol']:<6}  score={str(r.get('score'))}  as_of={r.get('as_of')}")
            print(f"            {r.get('reason', '')}")

    # ── Step 3: Custom backtest ─────────────────────────────────────────────
    with qdb.open_client(timeout_seconds=60.0) as client:
        bk_results, bk_caveats, bk_overall = run_backtest(
            client, base_url, symbols,
            args.from_date, args.to_date,
            args.strategy, args.initial_cash,
            require_all=False,
        )

    if args.json:
        step3 = {"step": "custom_backtest", "overall": bk_overall, "results": bk_results}
        print(_json.dumps({
            "status": "PARTIAL" if gate == "partial" else "ok",
            "step1": step1,
            "step2": step2,
            "step3": step3,
            "caveats": caveats + bk_caveats,
        }, indent=2))
    else:
        print(f"\n  STEP 3: Custom Backtest (strategy={args.strategy})")
        print(f"{SEP}")
        for r in bk_results:
            if r.get("status") == "BLOCKED":
                print(f"    [BLOCK] {r['symbol']:<6}  {r.get('reason', '')[:80]}")
            else:
                m = r.get("metrics", {})
                trades = len(r.get("trade_ledger", []))
                print(f"    {r['symbol']:<6}  ret={m.get('total_return_pct', 0):+.1f}%  "
                      f"sharpe={m.get('sharpe_ratio', 0):.2f}  "
                      f"dd={m.get('max_drawdown_pct', 0):.1f}%  "
                      f"trades={trades}")
                print(f"            equity: {r.get('portfolio', {}).get('final_equity', 0):,.0f} VND")
        print(f"\n{SEP}")
        overall = "PARTIAL" if gate == "partial" else "ok"
        print(f"  overall: {overall}")
        print(f"{SEP}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())