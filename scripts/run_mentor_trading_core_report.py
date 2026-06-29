"""Mentor trading core status report.

Reads current state and produces a structured report.
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
    parser = argparse.ArgumentParser(description="Mentor trading core status report.")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--from", dest="from_date", default="2021-01-01")
    parser.add_argument("--to", dest="to_date", default="2025-12-31")
    parser.add_argument("--strategy", default="ma_cross_v1",
                        choices=["ma_cross_v1", "momentum_v1", "mean_reversion_v1",
                                 "baseline_buy_hold_v1"])
    parser.add_argument("--initial-cash", type=float, default=100_000_000)
    parser.add_argument("--commission-bps", type=float, default=15.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--price-band-guard", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-md", default=None,
                        help="Write markdown report to this path")
    parser.add_argument(
        "--source-policy",
        choices=["approved_only", "prototype_allowed"],
        default="approved_only",
        help="approved_only: vnstock rows NOT approved (default). "
             "prototype_allowed: vnstock rows counted as prototype.",
    )
    args = parser.parse_args()

    base_url = args.questdb_url.rstrip("/")
    report = {}

    with qdb.open_client(timeout_seconds=120.0) as client:
        # 1. Inventory (source-policy aware)
        inventory = list_adjusted_symbols(
            client, base_url, limit=args.limit,
            source_policy=args.source_policy
        )
        # Under approved_only: approved_symbols=[] (FPT/VNM are prototype/unapproved)
        # Under prototype_allowed: prototype_symbols contains FPT/VNM
        approved_syms = [s["symbol"] for s in inventory.get("approved_symbols", [])]
        prototype_syms = [s["symbol"] for s in inventory.get("prototype_symbols", [])]
        all_pass_syms = approved_syms + prototype_syms
        approved_count = inventory.get("approved_count", 0)
        prototype_count = inventory.get("prototype_count", 0)
        blocked_unapproved_count = inventory.get("blocked_unapproved_count", 0)
        missing_count = inventory.get("missing_adjusted_source_count", 0)

        # 2. FPT/HPG/VCB/CTG/VNM/VHM status (uses same source_policy)
        target_syms = ["FPT", "VNM", "HPG", "VCB", "CTG", "VHM"]
        readiness = check_adjusted_readiness(
            client, base_url, target_syms,
            source_policy=args.source_policy
        )
        sym_status = {s["symbol"]: s for s in readiness.get("by_symbol", [])}

        # 3. Signals for pass symbols (prototype_allowed needed for FPT/VNM)
        # Use prototype_allowed so signals/backtests can run on prototype data
        if all_pass_syms:
            # Run with prototype policy so vnstock symbols can proceed
            sigs, _, _ = compute_signals(
                client, base_url, all_pass_syms, args.strategy, lookback=120,
                source_policy=args.source_policy,
            )
        else:
            sigs = []

        # 4. Backtest summary
        if all_pass_syms:
            base_res, _, _ = run_backtest(
                client, base_url, all_pass_syms,
                args.from_date, args.to_date,
                "baseline_buy_hold_v1",
                args.initial_cash,
                commission_bps=args.commission_bps,
                slippage_bps=args.slippage_bps,
                price_band_guard=args.price_band_guard,
                source_policy=args.source_policy,
            )
            alpha_res, _, _ = run_backtest(
                client, base_url, all_pass_syms,
                args.from_date, args.to_date,
                args.strategy,
                args.initial_cash,
                commission_bps=args.commission_bps,
                slippage_bps=args.slippage_bps,
                price_band_guard=args.price_band_guard,
                source_policy=args.source_policy,
            )
        else:
            base_res, alpha_res = [], []

        def _metrics_summary(results: list) -> dict:
            returns = [r["metrics"].get("total_return_pct") for r in results if r.get("metrics")]
            returns = [x for x in returns if x is not None]
            trades = [r["metrics"].get("total_trades") or 0 for r in results if r.get("metrics")]
            commissions = [r["metrics"].get("total_commission") or 0 for r in results if r.get("metrics")]
            slippages = [r["metrics"].get("total_slippage_estimate") or 0 for r in results if r.get("metrics")]
            pf_vals = [r["metrics"].get("profit_factor") for r in results if r.get("metrics", {}).get("profit_factor") is not None]
            wr_vals = [r["metrics"].get("win_rate") for r in results if r.get("metrics", {}).get("win_rate") is not None]
            return {
                "symbols_evaluated": len(results),
                "median_return_pct": round(sorted(returns)[len(returns)//2], 2) if returns else None,
                "mean_return_pct": round(sum(returns)/len(returns), 2) if returns else None,
                "total_trades": sum(trades),
                "total_commission": round(sum(commissions), 2),
                "total_slippage_estimate": round(sum(slippages), 2),
                "profit_factors": pf_vals,
                "win_rates": wr_vals,
            }

        # Build verdict based on source_policy
        if approved_count > 0:
            verdict_base = "TRADING_CORE_APPROVED"
        elif prototype_count > 0 and args.source_policy == "prototype_allowed":
            verdict_base = "TRADING_CORE_PROTOTYPE_ONLY"
        else:
            verdict_base = "TRADING_CORE_APPROVED_SOURCE_BLOCKED"

        report = {
            "report_date": "2026-06-29",
            "source_policy": args.source_policy,
            "adjusted_ohlc_pipeline": {
                "approved_adjusted_symbols_count": approved_count,
                "prototype_adjusted_symbols_count": prototype_count,
                "blocked_unapproved_symbols_count": blocked_unapproved_count,
                "missing_adjusted_source_symbols_count": missing_count,
                "approved_adjusted_symbols": approved_syms,
                "prototype_adjusted_symbols": prototype_syms,
                "target_50_achieved": approved_count >= 50,
                "target_100_achieved": approved_count >= 100,
                "source": "vnstock:company_events" if (prototype_count > 0 or blocked_unapproved_count > 0) else None,
                "method": "backward_exdate_price_ratio_audited",
                "factor_method": "factor = close_pre_exdate / close_on_exdate",
                "status_label": "prototype_only" if prototype_count > 0 else ("approved" if approved_count > 0 else "no_approved_source"),
                "caveat": (
                    "vnstock is NOT approved under source_policy=approved_only. "
                    "Only prototype results available (not for production trading)."
                ) if prototype_count > 0 or blocked_unapproved_count > 0 else None,
                "target_symbols": {
                    sym: {
                        "status": sym_status.get(sym, {}).get("status", "UNKNOWN"),
                        "gate": sym_status.get(sym, {}).get("backtest_gate", "unknown"),
                        "source_approval_status": sym_status.get(sym, {}).get("source_approval_status", "UNKNOWN"),
                        "adjustment_source": sym_status.get(sym, {}).get("adjustment_source"),
                        "blocked_reason": sym_status.get(sym, {}).get("blocked_reason"),
                    }
                    for sym in ["FPT", "VNM", "HPG", "VCB", "CTG", "VHM"]
                },
                "raw_fallback": "NOT USED for trading computation",
            },
            "risk_cost_slippage": {
                "commission_bps": args.commission_bps,
                "slippage_bps": args.slippage_bps,
                "price_band_guard_enabled": args.price_band_guard,
                "hose_band": "±7%",
                "upcom_band": "±15%",
                "hnx_band": "±10%",
                "status": "IMPLEMENTED",
                "caveats": [
                    "commission and slippage are user-configurable ASSUMPTIONS, not broker-specific verified values",
                    "price band guard requires exchange field in data (HOSE assumed when unknown)",
                ],
            },
            "trade_level_metrics": {
                "profit_factor_source": "trade-level realized PnL (FIFO), NOT daily returns",
                "win_rate_source": "trade-level closed trades, NOT daily returns",
                "status": "IMPLEMENTED",
                "caveats": [
                    "profit_factor and win_rate are null when no closed trades exist",
                ],
            },
            "strategy": {
                "baseline_buy_hold_v1": {
                    "purpose": "Engine validation only (not alpha)",
                    "backtest_summary": _metrics_summary(base_res),
                },
                args.strategy: {
                    "purpose": "Deterministic alpha strategy",
                    "signals_latest": {
                        s["symbol"]: s["signal"] for s in sigs
                    },
                    "backtest_summary": _metrics_summary(alpha_res),
                },
                "other_strategies": ["momentum_v1", "mean_reversion_v1", "buy_hold_v1"],
            },
            "remaining_blockers": {
                "approved_source_missing": (
                    f"approved_adjusted_symbols_count={approved_count}. "
                    f"source_policy={args.source_policy}. "
                    "No approved corporate action source available. "
                    "Options: (1) parse official FPT PDF for structured fields, "
                    "(2) ingest HSX/HOSE structured corporate action, "
                    "(3) purchase vendor adjusted prices."
                ),
                "vnstock_not_approved": (
                    f"{prototype_count + blocked_unapproved_count} symbols have vnstock-derived "
                    "adjusted OHLC (prototype only, NOT approved)."
                ) if (prototype_count + blocked_unapproved_count) > 0 else None,
                "broad_coverage": (
                    f"Only {approved_count} approved symbols. "
                    "Corporate action source needed for broader coverage."
                ),
                "hpg_vcb_ctg_vhm": "No corporate action source found for HPG, VCB, CTG, VHM.",
                "cost_assumptions": "Commission and slippage are research assumptions (15 bps / 5 bps), not verified against a broker.",
            },
            "verdict": verdict_base,
        }

    output = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output_md:
        _write_md(report, Path(args.output_md))

    if args.json:
        print(output)
        return 0

    # Text summary
    p = report["adjusted_ohlc_pipeline"]
    print("=" * 62)
    print("  MENTOR TRADING CORE STATUS REPORT")
    print(f"  source_policy={args.source_policy}")
    print("=" * 62)
    print()
    print("  ADJUSTED OHLC PIPELINE")
    print(f"    Approved symbols : {p['approved_adjusted_symbols_count']} (target 50+: {'NO' if not p['target_50_achieved'] else 'YES'})")
    print(f"    Prototype symbols: {p['prototype_adjusted_symbols_count']}")
    print(f"    Blocked (unapproved): {p['blocked_unapproved_symbols_count']}")
    print(f"    Missing source    : {p['missing_adjusted_source_symbols_count']}")
    print(f"    Status label     : {p['status_label']}")
    if p.get("caveat"):
        print(f"    Caveat           : {p['caveat']}")
    print()
    print("  SYMBOL STATUS (per source_policy)")
    for sym in ["FPT", "VNM", "HPG", "VCB", "CTG", "VHM"]:
        s = sym_status.get(sym, {})
        print(f"    {sym}: {s.get('status', 'UNKNOWN')} / {s.get('backtest_gate', '?')} / {s.get('source_approval_status', '?')}")
    print()
    print("  RISK / COST / SLIPPAGE")
    print(f"    Commission: {args.commission_bps} bps/side (assumption)")
    print(f"    Slippage:   {args.slippage_bps} bps/side (assumption)")
    print(f"    Price band: {'ENABLED' if args.price_band_guard else 'DISABLED'}")
    print(f"    HOSE=±7%  UPCoM=±15%  HNX=±10%")
    print()
    print("  TRADE METRICS")
    print("    profit_factor : from trade-level realized PnL (FIFO)")
    print("    win_rate      : from closed trades")
    print()
    print("  STRATEGIES")
    print(f"    baseline_buy_hold_v1: engine validation only")
    print(f"    {args.strategy}: deterministic MA cross alpha")
    print()
    print("  REMAINING BLOCKERS")
    blockers = report["remaining_blockers"]
    if blockers.get("approved_source_missing"):
        print(f"    {blockers['approved_source_missing']}")
    print()
    print(f"  VERDICT: {report['verdict']}")
    print("=" * 62)

    return 0


def _write_md(report: dict, path: Path) -> None:
    p = report["adjusted_ohlc_pipeline"]
    r = report["risk_cost_slippage"]
    m = report["trade_level_metrics"]
    s = report["strategy"]
    b = report["remaining_blockers"]

    lines = [
        "# Mentor Trading Core Status Report",
        f"",
        f"- report_date: `{report['report_date']}`",
        f"- source_policy: `{report['source_policy']}`",
        f"- verdict: `{report['verdict']}`",
        f"",
        "## 1. Adjusted OHLC Pipeline",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Approved symbols | {p['approved_adjusted_symbols_count']} |",
        f"| Prototype symbols | {p['prototype_adjusted_symbols_count']} |",
        f"| Blocked (unapproved) | {p['blocked_unapproved_symbols_count']} |",
        f"| Missing adjusted source | {p['missing_adjusted_source_symbols_count']} |",
        f"| Target 50+ achieved | {'YES' if p['target_50_achieved'] else 'NO'} |",
        f"| Status label | {p['status_label']} |",
        f"| Raw fallback | {p['raw_fallback']} |",
        f"",
    ]
    if p.get("approved_adjusted_symbols"):
        lines.append(f"| Approved list | {', '.join(p['approved_adjusted_symbols'])} |")
    if p.get("prototype_adjusted_symbols"):
        lines.append(f"| Prototype list | {', '.join(p['prototype_adjusted_symbols'])} (vnstock, NOT approved) |")
    if p.get("caveat"):
        lines.append(f"| Caveat | {p['caveat']} |")

    lines.append(f"")
    lines.append("### Target Symbol Status")
    lines.append(f"")
    for sym, info in p["target_symbols"].items():
        gate = info.get("gate", "?")
        status = info.get("status", "?")
        approval = info.get("source_approval_status", "?")
        lines.append(f"- **{sym}**: `{status}` / `{gate}` / `{approval}`")

    lines.extend([
        f"",
        "## 2. Risk / Cost / Slippage",
        f"",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| Commission | {r['commission_bps']} bps/side |",
        f"| Slippage | {r['slippage_bps']} bps/side |",
        f"| Price band guard | {'ENABLED' if r['price_band_guard_enabled'] else 'DISABLED'} |",
        f"| HOSE band | {r['hose_band']} |",
        f"| UPCoM band | {r['upcom_band']} |",
        f"| HNX band | {r['hnx_band']} |",
        f"| Implementation status | {r['status']} |",
        f"",
        "## 3. Trade-Level Metrics",
        f"",
        f"- **Profit Factor source**: {m['profit_factor_source']}",
        f"- **Win Rate source**: {m['win_rate_source']}",
        f"- **Implementation**: {m['status']}",
        f"- **Caveat**: {m['caveats'][0]}",
        f"",
        "## 4. Strategy",
        f"",
        f"- `baseline_buy_hold_v1`: {s['baseline_buy_hold_v1']['purpose']}",
        f"  - Median return: {s['baseline_buy_hold_v1']['backtest_summary'].get('median_return_pct')}",
        f"  - Mean return: {s['baseline_buy_hold_v1']['backtest_summary'].get('mean_return_pct')}",
        f"  - Total trades: {s['baseline_buy_hold_v1']['backtest_summary'].get('total_trades')}",
        f"",
        f"- `{s.get(args.strategy, {}).get('purpose', 'alpha strategy')}`:",
        f"  - Signals: {s.get(args.strategy, {}).get('signals_latest', 'N/A')}",
        f"  - Median return: {s.get(args.strategy, {}).get('backtest_summary', {}).get('median_return_pct')}",
        f"  - Mean return: {s.get(args.strategy, {}).get('backtest_summary', {}).get('mean_return_pct')}",
        f"  - Total trades: {s.get(args.strategy, {}).get('backtest_summary', {}).get('total_trades')}",
        f"",
        "## 5. Remaining Blockers",
        f"",
    ])
    if b.get("approved_source_missing"):
        lines.append(f"- **{args.source_policy}**: {b['approved_source_missing']}")
    if b.get("vnstock_not_approved"):
        lines.append(f"- **vnstock**: {b['vnstock_not_approved']}")
    if b.get("broad_coverage"):
        lines.append(f"- **Coverage**: {b['broad_coverage']}")
    if b.get("hpg_vcb_ctg_vhm"):
        lines.append(f"- **HPG/VCB/CTG/VHM**: {b['hpg_vcb_ctg_vhm']}")
    if b.get("cost_assumptions"):
        lines.append(f"- **Cost**: {b['cost_assumptions']}")
    lines.extend([
        f"",
        "## 6. Verdict",
        f"",
        f"`{report['verdict']}`",
    ])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Report written to: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
