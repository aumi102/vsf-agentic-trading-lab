"""Multi-symbol trading core demo.

Scope: all PASS symbols from adjusted_daily_prices (source-backed corporate action).
Runs readiness summary, latest signals, baseline + alpha backtests.

Output:
  - pass/blocked symbol counts
  - signal distribution
  - backtest summary (baseline vs alpha)
  - cost/slippage assumptions
  - honest BROAD_DEMO_LIMITED_SOURCE_BACKED_SYMBOLS if < 50 pass symbols
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for p in (str(ROOT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_agent.storage import questdb_client as qdb
from scripts.adjusted_ohlc_readiness import check_adjusted_readiness
from scripts.list_adjusted_pass_symbols import list_adjusted_symbols
from scripts.run_trading_signals import compute_signals
from scripts.run_custom_backtest import run_backtest

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-symbol trading core demo.")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--limit", type=int, default=100,
                        help="Max PASS symbols to include (default: 100)")
    parser.add_argument("--from", dest="from_date", default="2021-01-01")
    parser.add_argument("--to", dest="to_date", default="2025-12-31")
    parser.add_argument("--strategy", default="ma_cross_v1",
                        choices=["ma_cross_v1", "momentum_v1", "mean_reversion_v1",
                                 "buy_hold_v1", "baseline_buy_hold_v1"])
    parser.add_argument("--initial-cash", type=float, default=100_000_000)
    parser.add_argument("--commission-bps", type=float, default=15.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--price-band-guard", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--source-policy",
        choices=["approved_only", "prototype_allowed"],
        default="approved_only",
        help="approved_only: vnstock rows NOT approved (default). "
             "prototype_allowed: vnstock rows counted as prototype.",
    )
    args = parser.parse_args()

    base_url = args.questdb_url.rstrip("/")
    all_pass = []
    all_blocked = []

    with qdb.open_client(timeout_seconds=60.0) as client:
        # Step 1: readiness summary (source-policy aware)
        inventory = list_adjusted_symbols(
            client, base_url, limit=args.limit,
            source_policy=args.source_policy
        )
        approved_syms = [s["symbol"] for s in inventory.get("approved_symbols", [])]
        prototype_syms = [s["symbol"] for s in inventory.get("prototype_symbols", [])]
        all_pass = approved_syms + prototype_syms
        blocked_unapproved_syms = [s["symbol"] for s in inventory.get("blocked_unapproved_symbols", [])]
        missing_syms = inventory.get("missing_adjusted_source_symbols", [])
        all_blocked = blocked_unapproved_syms + missing_syms

        approved_count = len(approved_syms)
        prototype_count = len(prototype_syms)
        pass_count = len(all_pass)
        blocked_count = len(all_blocked)
        broad_limit_flag = approved_count < 50

        result = {
            "demo_status": (
                "BROAD_DEMO_APPROVED_SOURCE_BLOCKED"
                if approved_count == 0 else
                "BROAD_DEMO_LIMITED_APPROVED_SYMBOLS"
                if broad_limit_flag else
                "BROAD_DEMO_OK"
            ),
            "source_policy": args.source_policy,
            "approved_adjusted_symbols_count": approved_count,
            "prototype_adjusted_symbols_count": prototype_count,
            "blocked_unapproved_symbols_count": len(blocked_unapproved_syms),
            "missing_adjusted_source_symbols_count": len(missing_syms),
            "pass_symbols_count": pass_count,
            "blocked_symbols_count": blocked_count,
            "limit_requested": args.limit,
            "limit_reason": (
                f"approved_adjusted_symbols_count={approved_count} under source_policy={args.source_policy}. "
                "No approved corporate action source available."
            ) if approved_count == 0 else (
                f"Only {approved_count} approved symbols under source_policy={args.source_policy}. "
                "Target 50+ requires approved corporate action source."
            ) if broad_limit_flag else f"{approved_count} approved symbols (target met)",
            "broad_demo_limited": broad_limit_flag,
            "approved_adjusted_symbols": approved_syms,
            "prototype_adjusted_symbols": prototype_syms,
            "blocked_unapproved_symbols": blocked_unapproved_syms,
            "missing_adjusted_source_symbols": missing_syms,
            "parameters": {
                "from_date": args.from_date,
                "to_date": args.to_date,
                "strategy": args.strategy,
                "initial_cash": args.initial_cash,
                "commission_bps": args.commission_bps,
                "slippage_bps": args.slippage_bps,
                "price_band_guard": args.price_band_guard,
            },
        }

        if not all_pass:
            result["error"] = f"No PASS symbols under source_policy={args.source_policy}"
            if args.json:
                print(json.dumps(result, indent=2))
            return 1

        # Step 2: latest signals
        sigs, sig_caveats, sig_overall = compute_signals(
            client, base_url, all_pass, args.strategy, lookback=120,
            source_policy=args.source_policy,
        )
        buy_count = sum(1 for s in sigs if s.get("signal") == "BUY")
        sell_count = sum(1 for s in sigs if s.get("signal") == "SELL")
        hold_count = sum(1 for s in sigs if s.get("signal") == "HOLD")
        blocked_sig = sum(1 for s in sigs if s.get("signal") == "BLOCKED")

        result["signals"] = {
            "strategy": args.strategy,
            "overall": sig_overall,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "blocked_count": blocked_sig,
            "by_symbol": sigs,
        }

        # Step 3: backtests
        base_results, base_caveats, base_overall = run_backtest(
            client, base_url, all_pass,
            args.from_date, args.to_date,
            "baseline_buy_hold_v1",
            args.initial_cash,
            commission_bps=args.commission_bps,
            slippage_bps=args.slippage_bps,
            price_band_guard=args.price_band_guard,
            source_policy=args.source_policy,
        )

        alpha_results, alpha_caveats, alpha_overall = run_backtest(
            client, base_url, all_pass,
            args.from_date, args.to_date,
            args.strategy,
            args.initial_cash,
            commission_bps=args.commission_bps,
            slippage_bps=args.slippage_bps,
            price_band_guard=args.price_band_guard,
            source_policy=args.source_policy,
        )

        def _agg(results: list) -> dict:
            total_returns = [r["metrics"].get("total_return_pct", 0) for r in results if r.get("metrics")]
            returns_no_none = [x for x in total_returns if x is not None]
            agg = {
                "n_results": len(results),
                "n_with_trades": sum(1 for r in results if r.get("metrics", {}).get("total_trades", 0) > 0),
                "median_return_pct": round(sorted(returns_no_none)[len(returns_no_none)//2], 2) if returns_no_none else None,
                "mean_return_pct": round(sum(returns_no_none)/len(returns_no_none), 2) if returns_no_none else None,
                "best_5": [],
                "worst_5": [],
            }
            ranked = sorted(results, key=lambda r: r.get("metrics", {}).get("total_return_pct") or 0, reverse=True)
            for r in ranked[:5]:
                agg["best_5"].append({
                    "symbol": r["symbol"],
                    "return_pct": r["metrics"].get("total_return_pct"),
                    "trades": r["metrics"].get("total_trades"),
                })
            for r in ranked[-5:]:
                agg["worst_5"].append({
                    "symbol": r["symbol"],
                    "return_pct": r["metrics"].get("total_return_pct"),
                    "trades": r["metrics"].get("total_trades"),
                })
            agg["aggregate_trades"] = sum(r.get("metrics", {}).get("total_trades", 0) for r in results)
            agg["aggregate_commission"] = round(sum(
                r.get("metrics", {}).get("total_commission", 0) or 0 for r in results), 2)
            agg["aggregate_slippage"] = round(sum(
                r.get("metrics", {}).get("total_slippage_estimate", 0) or 0 for r in results), 2)
            return agg

        result["backtests"] = {
            "baseline_buy_hold_v1": {
                "overall": base_overall,
                "aggregation": _agg(base_results),
                "caveats": base_caveats,
            },
            args.strategy: {
                "overall": alpha_overall,
                "aggregation": _agg(alpha_results),
                "caveats": alpha_caveats,
            },
        }

        result["cost_assumptions"] = {
            "commission_bps": args.commission_bps,
            "slippage_bps": args.slippage_bps,
            "price_band_guard": args.price_band_guard,
            "caveats": [
                f"commission={args.commission_bps} bps per side (user-configurable assumption)",
                f"slippage={args.slippage_bps} bps per side (user-configurable assumption)",
                "HOSE/HSX price band=±7%, UPCoM=±15%, HNX=±10%",
            ],
        }

        result["caveats"] = [
            f"source_policy={args.source_policy}.",
            f"Approved symbols: {approved_count}. "
            f"Prototype symbols: {prototype_count} (vnstock-derived, NOT approved). "
            f"Blocked (unapproved): {len(blocked_unapproved_syms)}.",
            f"Missing adjusted source: {len(missing_syms)}.",
            "Prototype backtest results are for prototype/demo only, not production.",
        ]

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print("=" * 62)
    print(f"  Multi-Symbol Trading Core Demo  |  source_policy={args.source_policy}")
    print("=" * 62)
    print(f"  Approved symbols    : {approved_count}")
    print(f"  Prototype symbols  : {prototype_count} (vnstock, NOT approved)")
    print(f"  Blocked (unapproved): {len(blocked_unapproved_syms)}")
    print(f"  Missing source     : {len(missing_syms)}")
    print(f"  demo_status        : {result['demo_status']}")
    print()
    print(f"  Strategy          : {args.strategy}")
    print(f"  Period            : {args.from_date} -> {args.to_date}")
    print(f"  Commission        : {args.commission_bps} bps/side")
    print(f"  Slippage          : {args.slippage_bps} bps/side")
    print(f"  Price band guard : {args.price_band_guard}")
    print()
    print("  Signals (PASS only):")
    print(f"    BUY={buy_count}  SELL={sell_count}  HOLD={hold_count}  BLOCKED={blocked_sig}")
    if result.get("backtests"):
        ba = result["backtests"]["baseline_buy_hold_v1"]["aggregation"]
        aa = result["backtests"][args.strategy]["aggregation"]
        print(f"  Baseline:  median_return={ba['median_return_pct']}%  mean_return={ba['mean_return_pct']}%  "
              f"total_trades={ba['aggregate_trades']}")
        print(f"  Alpha:     median_return={aa['median_return_pct']}%  mean_return={aa['mean_return_pct']}%  "
              f"total_trades={aa['aggregate_trades']}")
    print("=" * 62)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
