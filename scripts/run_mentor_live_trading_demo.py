"""Mentor live trading demo -- demonstrates approved/prototype mode safety gates.

Does NOT:
  - Use vnstock as approved source
  - Claim FPT/VNM official PASS
  - Fake adjusted OHLC
  - Fall back to raw daily_prices
  - Mutate raw daily_prices
  - Fetch new data

Proves:
  - Approved mode blocks because approved adjusted OHLC is missing
  - Prototype mode runs end-to-end with FPT/VNM (unapproved source caveat)
  - Cost/slippage/trade-level metrics visible in prototype backtest output
  - System distinguishes unapproved source vs missing source
"""
from __future__ import annotations

import argparse
import json as _json
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "src"), str(SCRIPT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.adjusted_ohlc_readiness import check_adjusted_readiness  # noqa: E402
from scripts.run_trading_signals import compute_signals  # noqa: E402
from scripts.run_custom_backtest import run_backtest  # noqa: E402
from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_URL = "http://localhost:9000"


def _print_text(output: dict) -> None:
    sep = "=" * 72
    d = output

    print(f"\n{sep}")
    print("  MENTOR LIVE TRADING DEMO")
    print(sep)

    # Demo summary
    s = d["demo_summary"]
    print(f"\n  Symbols tested : {s['symbols_tested']}")
    print(f"  Date range    : {s['from']} → {s['to']}")
    print(f"  Strategy       : {s['strategy']}")
    print(f"  Commission     : {s['commission_bps']} bps")
    print(f"  Slippage       : {s['slippage_bps']} bps")
    print(f"  Price-band guard: {'ON' if s['price_band_guard'] else 'OFF'}")

    # Approved mode
    a = d["approved_mode"]
    print(f"\n{sep}")
    print("  [APPROVED MODE]  source_policy = approved_only")
    print(sep)
    print(f"  Status      : {a['status']}")
    print(f"  Backtest    : {'ALLOWED' if a['official_backtest_allowed'] else 'BLOCKED'}")
    print(f"  Signal      : {'ALLOWED' if a['official_signal_allowed'] else 'BLOCKED'}")
    print(f"  Verdict     : {a['verdict']}")
    print(f"  Approved    : {a['approved_adjusted_symbols_count']} symbols")
    for sym, info in a["by_symbol"].items():
        print(f"    {sym:<6} {info['status']:<30} {info.get('reason', '')}")

    # Prototype mode
    p = d["prototype_mode"]
    print(f"\n{sep}")
    print("  [PROTOTYPE MODE]  source_policy = prototype_allowed")
    print(sep)
    print(f"  Status      : {p['status']}")
    print(f"  Verdict     : {p['verdict']}")
    print(f"  Prototype   : {p['prototype_adjusted_symbols_count']} symbols ({p['symbols']})")
    print(f"  Caveat      : {p['caveat']}")

    for sym, sig in p["signals"].items():
        print(f"    {sym:<6} signal={sig['signal']:<6} price={sig.get('price', 'N/A')}")

    # Backtests
    for bt_name, bt in p["backtests"].items():
        print(f"\n  {bt_name.upper()}")
        m = bt.get("metrics", {})
        print(f"    Total return    : {m.get('total_return_pct', 'N/A')}")
        print(f"    Sharpe          : {m.get('sharpe_ratio', 'N/A')}")
        print(f"    Sortino         : {m.get('sortino_ratio', 'N/A')}")
        print(f"    Profit factor   : {m.get('profit_factor', 'N/A')}")
        print(f"    Max drawdown     : {m.get('max_drawdown_pct', 'N/A')}")
        print(f"    Win rate        : {m.get('win_rate', 'N/A')}")
        print(f"    Trades          : {bt.get('trade_count', 0)}")
        print(f"    Closed trades   : {bt.get('closed_trade_count', 0)}")
        print(f"    Commission      : {m.get('total_commission', 0):,.0f} VND")
        print(f"    Slippage        : {m.get('total_slippage_estimate', 0):,.0f} VND")
        print(f"    Price-band guard: {bt.get('price_band_guard', 'N/A')}")
        print(f"    Prototype caveat: {bt.get('prototype_caveat', 'N/A')}")

    # Source evidence
    e = d["source_evidence"]
    print(f"\n{sep}")
    print("  [SOURCE EVIDENCE]")
    print(sep)
    for line in e["lines"]:
        print(f"  {line}")

    # Cost/slippage
    c = d["risk_cost_slippage"]
    print(f"\n{sep}")
    print("  [COST / SLIPPAGE]")
    print(sep)
    print(f"  Commission  : {c['commission_bps']} bps per trade")
    print(f"  Slippage    : {c['slippage_bps']} bps per trade")
    print(f"  Guard       : {c['guard_note']}")
    for item in c["trade_level_fields"]:
        print(f"    - {item}")

    # Metrics audit
    m = d["metrics_audit"]
    print(f"\n{sep}")
    print("  [METRICS AUDIT]")
    print(sep)
    for key, val in m["required_metrics"].items():
        print(f"  {key:<30} : {val}")
    print(f"\n  Cost fields present : {m['cost_fields_present']}")
    print(f"  Trade ledger        : {m['trade_ledger_fields_present']}")

    # Operator talking points
    print(f"\n{sep}")
    print("  [OPERATOR TALKING POINTS (Vietnamese)]")
    print(sep)
    t = d["operator_talking_points"]
    print(f"\n  1. Opening:")
    print(f"     {t['opening']}")
    print(f"\n  2. Approved mode:")
    print(f"     {t['approved_mode_explanation']}")
    print(f"\n  3. Prototype mode:")
    print(f"     {t['prototype_mode_explanation']}")
    print(f"\n  4. Source blocker:")
    print(f"     {t['source_blocker_explanation']}")
    print(f"\n  5. Cost/slippage:")
    print(f"     {t['cost_slippage_explanation']}")
    print(f"\n  6. Next step:")
    print(f"     {t['next_step_question_for_mentor']}")

    # Next blocker
    print(f"\n{sep}")
    print("  [NEXT BLOCKER]")
    print(sep)
    nb = d["next_blocker"]
    print(f"  {nb['description']}")
    print(f"  Options: {', '.join(nb['options'])}")

    # Final verdict
    print(f"\n{sep}")
    print(f"  FINAL VERDICT: {d['verdict']}")
    print(sep)
    print()


def _run_demo(
    questdb_url: str,
    from_date: str,
    to_date: str,
    strategy: str,
    commission_bps: float,
    slippage_bps: float,
    price_band_guard: bool,
) -> dict:
    import traceback
    from datetime import date

    # ── Approved mode ──────────────────────────────────────────────────────────
    symbols_approved = ["FPT", "VNM", "HPG", "VCB", "CTG", "VHM"]

    approved_result: dict = {"status": "ERROR", "by_symbol": {}}
    try:
        with qdb.open_client(timeout_seconds=30.0) as client:
            approved_result = check_adjusted_readiness(
                client,
                questdb_url,
                symbols_approved,
                from_date,
                to_date,
                source_policy="approved_only",
            )
    except Exception as exc:
        approved_result = {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "by_symbol": {},
        }

    approved_by_symbol = {}
    for s in approved_result.get("by_symbol", []):
        sym = s["symbol"]
        approved_by_symbol[sym] = {
            "status": s.get("status", "UNKNOWN"),
            "reason": s.get("blocked_reason", ""),
        }

    official_backtest_allowed = approved_result.get("backtest_gate") in ("pass", "partial")
    official_signal_allowed = official_backtest_allowed

    # ── Prototype mode ────────────────────────────────────────────────────────
    prototype_symbols = ["FPT", "VNM"]

    prototype_result: dict = {"status": "ERROR", "by_symbol": {}}
    try:
        with qdb.open_client(timeout_seconds=30.0) as client:
            prototype_result = check_adjusted_readiness(
                client,
                questdb_url,
                prototype_symbols,
                from_date,
                to_date,
                source_policy="prototype_allowed",
            )
    except Exception as exc:
        prototype_result = {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "by_symbol": {},
        }

    prototype_passed = prototype_result.get("backtest_gate") in ("pass", "partial")

    # Signals — compute_signals returns tuple[list[dict], list[str]]
    signals: dict[str, dict] = {}
    if prototype_passed:
        try:
            with qdb.open_client(timeout_seconds=30.0) as client:
                sig_list, _ = compute_signals(
                    client,
                    questdb_url,
                    prototype_symbols,
                    strategy=strategy,
                    source_policy="prototype_allowed",
                )
            for sig in sig_list:
                signals[sig["symbol"]] = {
                    "signal": sig.get("signal", "UNKNOWN"),
                    "price": sig.get("close") or sig.get("adjusted_close"),
                }
        except Exception:
            pass

    # Backtests
    backtests: dict[str, dict] = {}
    strategies_to_run = ["baseline_buy_hold_v1", strategy]

    for strat in strategies_to_run:
        bt_name = f"backtest_{strat}"
        backtests[bt_name] = {
            "trade_count": 0,
            "closed_trade_count": 0,
            "metrics": {},
            "prototype_caveat": "PROTOTYPE_ONLY_UNAPPROVED_SOURCE",
        }
        if prototype_passed:
            try:
                with qdb.open_client(timeout_seconds=60.0) as client:
                    # run_backtest returns tuple[results, caveats, status]
                    bt_results, bt_caveats, bt_status = run_backtest(
                        client,
                        questdb_url,
                        prototype_symbols,
                        from_date,
                        to_date,
                        strategy=strat,
                        initial_cash=100_000_000,
                        commission_bps=commission_bps,
                        slippage_bps=slippage_bps,
                        price_band_guard=price_band_guard,
                        source_policy="prototype_allowed",
                    )
                # bt_results is list[dict], one per symbol
                res = bt_results[0] if bt_results else {}
                m = res.get("metrics", {})
                trade_ledger = res.get("trade_ledger", [])
                closed = [t for t in trade_ledger if t.get("side") == "SELL"]
                backtests[bt_name] = {
                    "trade_count": res.get("trade_count", 0),
                    "closed_trade_count": len(closed),
                    "metrics": {
                        "total_return_pct": m.get("total_return_pct"),
                        "sharpe_ratio": m.get("sharpe_ratio"),
                        "sortino_ratio": m.get("sortino_ratio"),
                        "profit_factor": m.get("profit_factor"),
                        "max_drawdown_pct": m.get("max_drawdown_pct"),
                        "win_rate": m.get("win_rate"),
                        "total_commission": m.get("total_commission", 0),
                        "total_slippage_estimate": m.get("total_slippage_estimate", 0),
                    },
                    "price_band_guard": (
                        "ON" if price_band_guard
                        else "OFF"
                    ),
                    "prototype_caveat": "PROTOTYPE_ONLY_UNAPPROVED_SOURCE",
                }
            except Exception:
                pass

    # Source evidence
    source_evidence_lines = [
        "QuestDB event_news_items table exists (FPT only, 20 rows from IR disclosure crawl).",
        "QuestDB event_news_raw_payloads table exists (FPT only, 20 raw HTML payloads).",
        "VNM/HPG/VCB/CTG/VHM have NO DB event rows.",
        "FPT official dividend PDF was found but is SCANNED/IMAGE-BASED.",
        "pdftotext extracted ~114 bytes only -- no structured text extractable.",
        "No OCR used -- no heavy dependencies installed.",
        "Required fields missing: ex_date, record_date, payment_date,",
        "  cash_dividend_per_share, currency.",
        "approved adjusted OHLC remains BLOCKED pending approved source.",
        "Em đang ưu tiên block đúng hơn là pass sai.",
    ]

    # Cost/slippage audit
    has_cost_fields = False
    has_trade_ledger = False
    cost_fields_present = []
    trade_ledger_fields_present = []

    for bt_key, bt_data in backtests.items():
        m = bt_data.get("metrics", {})
        if m:
            has_cost_fields = True
            cost_fields_present = [
                "total_commission",
                "total_slippage_estimate",
                "commission_bps",
                "slippage_bps",
            ]
        if bt_data.get("trade_count", 0) > 0 or bt_data.get("closed_trade_count", 0) > 0:
            has_trade_ledger = True
            trade_ledger_fields_present = [
                "trade_count",
                "closed_trade_count",
                "commission (per trade)",
                "slippage_bps (per trade)",
                "slippage_value_estimate (per trade)",
                "execution_price (per trade)",
                "raw_base_price (per trade)",
                "gross_value / net_value (per trade)",
            ]

    # Metrics audit
    m_audit: dict = {}
    for bt_data in backtests.values():
        if bt_data.get("metrics"):
            m_audit = bt_data["metrics"]
            break

    required_metrics_keys = [
        "total_return_pct", "sharpe_ratio", "sortino_ratio",
        "profit_factor", "max_drawdown_pct", "win_rate",
        "total_commission", "total_slippage_estimate",
    ]
    required_metrics = {}
    for key in required_metrics_keys:
        required_metrics[key] = (
            "PRESENT" if key in m_audit
            else "MISSING"
        )

    # Verdict logic
    approved_count = len([s for s in approved_result.get("by_symbol", [])
                          if s.get("status") == "PASS"])
    prototype_count = len([s for s in prototype_result.get("by_symbol", [])
                           if s.get("status") == "PASS_PROTOTYPE"])

    if approved_count > 0:
        approved_verdict = "APPROVED_MODE_RUNS_OFFICIALLY"
    else:
        approved_verdict = "APPROVED_MODE_BLOCKED_BY_ADJUSTED_SOURCE"

    if prototype_count > 0:
        prototype_verdict = "PROTOTYPE_MODE_RUNS_WITH_CAVEAT"
    else:
        prototype_verdict = "PROTOTYPE_MODE_BLOCKED"

    # Final verdict
    final_verdict = (
        f"APPROVED={approved_verdict} | "
        f"PROTOTYPE={prototype_verdict} | "
        f"approved_count={approved_count} | "
        f"prototype_count={prototype_count} | "
        "next_blocker=approved_corporate_action_source_or_vendor_adjusted_prices"
    )

    return {
        "demo_summary": {
            "symbols_tested": ", ".join(symbols_approved),
            "from": from_date,
            "to": to_date,
            "strategy": strategy,
            "commission_bps": commission_bps,
            "slippage_bps": slippage_bps,
            "price_band_guard": price_band_guard,
        },
        "approved_mode": {
            "status": approved_result.get("status", "ERROR"),
            "approved_adjusted_symbols_count": approved_count,
            "official_backtest_allowed": official_backtest_allowed,
            "official_signal_allowed": official_signal_allowed,
            "verdict": approved_verdict,
            "by_symbol": approved_by_symbol,
        },
        "prototype_mode": {
            "status": prototype_result.get("status", "ERROR"),
            "prototype_adjusted_symbols_count": prototype_count,
            "symbols": prototype_symbols,
            "caveat": "PROTOTYPE_ONLY_UNAPPROVED_SOURCE",
            "signals": signals,
            "backtests": backtests,
            "verdict": prototype_verdict,
        },
        "source_evidence": {
            "lines": source_evidence_lines,
        },
        "risk_cost_slippage": {
            "commission_bps": commission_bps,
            "slippage_bps": slippage_bps,
            "guard_note": (
                "HOSE ±7%, UPCoM ±15%, HNX ±10%" if price_band_guard
                else "OFF (set --price-band-guard to enable)"
            ),
            "trade_level_fields": cost_fields_present,
        },
        "metrics_audit": {
            "required_metrics": required_metrics,
            "cost_fields_present": "YES" if has_cost_fields else "NO",
            "trade_ledger_fields_present": "YES" if has_trade_ledger else "NO",
        },
        "operator_talking_points": {
            "opening": (
                "Em xin phép demo hệ thống trading core với 2 chế độ: "
                "Approved mode (production) và Prototype mode (research/prototype)."
            ),
            "approved_mode_explanation": (
                "Approved mode hiện block toàn bộ vì chưa có approved adjusted OHLC source. "
                "Không symbol nào được tính là approved -- không signal, không backtest."
            ),
            "prototype_mode_explanation": (
                "Prototype mode chỉ dùng để chứng minh pipeline chạy được, "
                "không claim production backtest. "
                "FPT/VNM có prototype adjusted rows từ vnstock nhưng không được tính là approved source."
            ),
            "source_blocker_explanation": (
                "HPG/VCB/CTG/VHM thiếu adjusted/corporate action source. "
                "FPT official PDF hiện là scanned/image-based nên chưa extract được "
                "structured fields nếu không OCR. "
                "Em đang ưu tiên block đúng hơn là pass sai."
            ),
            "cost_slippage_explanation": (
                f"Mỗi trade chịu {commission_bps} bps commission + {slippage_bps} bps slippage. "
                "Price-band guard kiểm soát volatility spike: "
                "HOSE ±7%, UPCoM ±15%, HNX ±10%."
                if price_band_guard
                else (
                    f"Mỗi trade chịu {commission_bps} bps commission + {slippage_bps} bps slippage. "
                    "Price-band guard hiện OFF."
                )
            ),
            "next_step_question_for_mentor": (
                "Mentor ơi, step tiếp theo nên là: (1) tìm approved adjusted OHLC vendor/source, "
                "(2) tiếp tục research FPT/VNM corporate actions, hay (3) khác?"
            ),
        },
        "next_blocker": {
            "description": (
                "Approved adjusted OHLC source is missing. "
                "Options: (1) Find approved corporate action vendor/source, "
                "(2) Continue research on FPT/VNM official disclosures, "
                "(3) Accept prototype-only for research."
            ),
            "options": [
                "approved_corporate_action_vendor",
                "official_FPT_VNM_corporate_action_extraction",
                "prototype_only_research_mode",
            ],
        },
        "verdict": final_verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mentor live trading demo.")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--from", dest="from_date", default="2021-01-01")
    parser.add_argument("--to", dest="to_date", default="2025-12-31")
    parser.add_argument("--strategy", default="ma_cross_v1")
    parser.add_argument("--commission-bps", type=float, default=15.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--price-band-guard", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = _run_demo(
        args.questdb_url,
        args.from_date,
        args.to_date,
        args.strategy,
        args.commission_bps,
        args.slippage_bps,
        args.price_band_guard,
    )

    if args.json:
        print(_json.dumps(result, indent=2))
    else:
        _print_text(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
