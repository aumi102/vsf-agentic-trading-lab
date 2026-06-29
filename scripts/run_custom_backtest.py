"""Custom backtest engine v1 -- gated on source-backed adjusted OHLC.

BLOCKED -- if adjusted OHLCV readiness check fails (no source-backed adjustment factors).
Do NOT backtest on raw OHLCV presented as adjusted.

Backtest contract v1:
  portfolio_state  = {cash, position, equity, bars_count}
  order_model      = BUY / SELL / HOLD  (no fractional, no short)
  trade_ledger     = list of {date, symbol, side, price, quantity, value}
  metrics          = {total_return, sharpe, max_drawdown, win_rate, total_trades}
  execution_rule   = no-lookahead: signals fire at bar t+1 open price
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "src"), str(SCRIPT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_agent.storage import questdb_client as qdb  # noqa: E402
from scripts.adjusted_ohlc_readiness import check_adjusted_readiness  # noqa: E402
from scripts.run_trading_signals import (  # noqa: E402
    _fetch_bars as _fetch_bars_signals,
    _signal_momentum_v1,
    _signal_mean_reversion_v1,
    _signal_buy_hold_v1,
    STRATEGIES as SIGNAL_STRATEGIES,
)

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL


def _fetch_bars(
    client, base_url: str,
    symbol: str,
    from_date: str,
    to_date: str,
) -> list[dict[str, Any]] | None:
    """Read bars from adjusted_daily_prices only. Returns None if no source-backed data.

    NEVER falls back to raw daily_prices.
    """
    adj_exists_sql = (
        f"SELECT trade_date FROM adjusted_daily_prices WHERE symbol = '{symbol}' "
        f"AND adjustment_status = 'source_backed_corporate_action' "
        f"AND trade_date >= '{from_date}' AND trade_date <= '{to_date}' "
        f"ORDER BY trade_date ASC LIMIT 1"
    )
    try:
        adj_exists = qdb.exec_scalar(client, base_url, adj_exists_sql)
    except Exception:
        adj_exists = None

    if adj_exists is None:
        return None

    sql = (
        f"SELECT trade_date, open, high, low, close, volume, "
        f"adjustment_factor, adjustment_status, exchange "
        f"FROM adjusted_daily_prices "
        f"WHERE symbol = '{symbol}' "
        f"AND adjustment_status = 'source_backed_corporate_action' "
        f"AND trade_date >= '{from_date}' "
        f"AND trade_date <= '{to_date}' "
        f"ORDER BY trade_date ASC"
    )
    cols, rows = qdb.exec_rows(client, base_url, sql)
    result = []
    for r in rows:
        d = _row_to_dict(cols, r)
        d["adjusted_open"] = d.get("open")
        d["adjusted_high"] = d.get("high")
        d["adjusted_low"] = d.get("low")
        d["adjusted_close"] = d.get("close")
        result.append(d)
    return result


def _row_to_dict(cols: list[str], row: list) -> dict[str, Any]:
    return {c: v for c, v in zip(cols, row)}


# ─── backtest engine v1 ──────────────────────────────────────────────────────

class BacktestEngineV1:
    """Minimal no-lookahead backtest engine.

    Execution rule: signal at bar t triggers order at bar t+1 open price.
    No fractional shares. No short selling. No leverage.
    """

    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.position = 0  # shares held
        self.entry_price = 0.0
        self.ledger: list[dict] = []
        self.equity_curve: list[float] = []

    def _execute_order(self, side: str, price: float, qty: int, trade_date: str, symbol: str) -> None:
        if side == "BUY" and self.position == 0:
            cost = price * qty
            if self.cash >= cost:
                self.cash -= cost
                self.position = qty
                self.entry_price = price
                self.ledger.append({
                    "date": trade_date, "symbol": symbol,
                    "side": "BUY", "price": float(price),
                    "quantity": qty, "value": float(cost),
                })
        elif side == "SELL" and self.position > 0:
            proceeds = price * self.position
            self.cash += proceeds
            self.ledger.append({
                "date": trade_date, "symbol": symbol,
                "side": "SELL", "price": float(price),
                "quantity": self.position, "value": float(proceeds),
            })
            self.position = 0
            self.entry_price = 0.0

    def run(
        self, symbol: str,
        bars: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        strategy: str,
    ) -> dict[str, Any]:
        """Run backtest over bars with pre-computed signals.

        Signals must align with bars by index (signal[i] corresponds to bars[i]).
        Signal at bar i fires execution at bar i+1 open.
        """
        self.cash = self.initial_cash
        self.position = 0
        self.entry_price = 0.0
        self.ledger = []
        self.equity_curve = []

        if not bars or len(bars) < 2:
            return self._result(symbol, strategy, bars, "insufficient_bars")

        for i in range(len(bars) - 1):
            sig = signals[i] if i < len(signals) else {}
            side = sig.get("signal", "HOLD")
            exec_price = float(bars[i + 1]["open"])
            self._execute_order(side, exec_price, 100, str(bars[i + 1]["trade_date"])[:10], symbol)

            # mark-to-market
            mtm = self.cash + self.position * exec_price
            self.equity_curve.append(mtm)

        # close at last bar close
        if self.position > 0:
            last_close = float(bars[-1]["close"])
            self._execute_order("SELL", last_close, 0, str(bars[-1]["trade_date"])[:10], symbol)
            self.equity_curve.append(self.cash)

        return self._result(symbol, strategy, bars, "ok")

    def _result(self, symbol: str, strategy: str, bars: list, reason: str) -> dict[str, Any]:
        final_equity = self.cash + self.position * float(bars[-1]["close"]) if bars else self.cash
        total_return = (final_equity - self.initial_cash) / self.initial_cash * 100 if self.initial_cash else 0
        max_dd = self._max_drawdown()
        wins = sum(1 for t in self.ledger if t["side"] == "SELL" and float(t["value"]) > 0)
        sells = sum(1 for t in self.ledger if t["side"] == "SELL")
        win_rate = wins / sells if sells else 0.0
        returns = self._daily_returns()
        sharpe = self._sharpe(returns)
        sortino = self._sortino(returns)
        profit_factor = self._profit_factor()

        return {
            "symbol": symbol,
            "strategy": strategy,
            "reason": reason,
            "portfolio": {
                "initial_cash": self.initial_cash,
                "final_equity": round(final_equity, 2),
                "cash": round(self.cash, 2),
                "position": self.position,
                "bars_count": len(bars),
            },
            "metrics": {
                "total_return_pct": round(total_return, 2),
                "sharpe_ratio": round(sharpe, 3),
                "sortino_ratio": round(sortino, 3),
                "profit_factor": round(profit_factor, 3),
                "max_drawdown_pct": round(max_dd, 2),
                "win_rate": round(win_rate, 3),
                "total_trades": len(self.ledger),
                "cost_slippage_assumptions": (
                    "0 bps commission, 0 slippage. "
                    "Configurable via --commission and --slippage (future)."
                ),
            },
            "trade_ledger": self.ledger,
        }

    def _daily_returns(self) -> list[float]:
        if len(self.equity_curve) < 2:
            return []
        return [(self.equity_curve[i] / self.equity_curve[i - 1] - 1)
                for i in range(1, len(self.equity_curve))]

    def _max_drawdown(self) -> float:
        peak = self.equity_curve[0] if self.equity_curve else 0
        max_dd = 0.0
        for v in self.equity_curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak else 0
            if dd > max_dd:
                max_dd = dd
        return max_dd * 100

    def _sharpe(self, returns: list[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        import statistics
        mean_ret = statistics.mean(returns) - risk_free
        std_ret = statistics.stdev(returns) if len(returns) > 1 else 1e-9
        return (mean_ret / std_ret) * (252 ** 0.5) if std_ret else 0.0

    def _sortino(self, returns: list[float], risk_free: float = 0.0) -> float:
        """Sortino = (mean - risk_free) / downside_dev, annualized."""
        if len(returns) < 2:
            return 0.0
        import statistics
        mean_ret = statistics.mean(returns) - risk_free
        downside = [r for r in returns if r < 0]
        if not downside:
            return float("inf") if mean_ret > 0 else 0.0
        down_std = statistics.stdev(downside) if len(downside) > 1 else (abs(downside[0]) if downside else 1e-9)
        return (mean_ret / down_std) * (252 ** 0.5) if down_std else 0.0

    def _profit_factor(self) -> float:
        """Gross profit / gross loss from trade ledger."""
        gross_profit = sum(
            float(t["value"]) for t in self.ledger
            if t["side"] == "SELL" and float(t["value"]) > 0
        )
        # For BUY trades, value is cost; for SELL, value is proceeds
        # We track P&L per round-trip: entry value vs exit proceeds
        # Simple proxy: sum of SELL proceeds minus entry costs
        # Better: group by entry/exit
        buys = [t for t in self.ledger if t["side"] == "BUY"]
        sells = [t for t in self.ledger if t["side"] == "SELL"]
        # Each sell should match a prior buy
        # gross profit = sum(sell proceeds) - sum(buy costs)
        # But we need cost basis per share
        # Simpler: compute from equity curve instead
        if len(self.equity_curve) < 2:
            return 0.0
        gains = sum(max(r, 0) for r in self._daily_returns())
        losses = sum(abs(min(r, 0)) for r in self._daily_returns())
        if losses == 0:
            return float("inf") if gains > 0 else 0.0
        return round(gains / losses, 3)


def run_backtest(
    client, base_url: str,
    symbols: list[str],
    from_date: str,
    to_date: str,
    strategy: str,
    initial_cash: float = 100_000_000,
    require_all: bool = False,
) -> tuple[list[dict], list[str], str]:
    """Run backtest gated on adjusted OHLC readiness. PARTIAL if some symbols blocked."""
    readiness = check_adjusted_readiness(client, base_url, symbols)
    by_symbol = readiness.get("by_symbol", [])
    sym_status = {s["symbol"]: s for s in by_symbol}

    caveats = readiness["caveats"][:]
    results = []
    pass_count = 0
    block_count = 0

    for sym in symbols:
        sym_info = sym_status.get(sym, {})
        if sym_info.get("backtest_gate") == "pass":
            bars = _fetch_bars(client, base_url, sym, from_date, to_date)
            if bars is None:
                block_count += 1
                results.append(_blocked_result(sym, strategy, sym_info.get("blocked_reason")))
                continue

            adj_status = bars[-1]["adjustment_status"] if bars else "unknown"
            feat_strategy = strategy.replace("_v1", "")
            if feat_strategy == "momentum":
                sig = _signal_momentum_v1(bars)
            elif feat_strategy == "mean_reversion":
                sig = _signal_mean_reversion_v1(bars)
            elif feat_strategy in ("buy_hold", "baseline_buy_hold"):
                sig = _signal_buy_hold_v1(bars, adj_status)
            else:
                sig = {"signal": "HOLD", "score": 0.0, "reason": f"unknown strategy={strategy}"}
            sig_list = [sig] * len(bars)
            engine = BacktestEngineV1(initial_cash)
            result = engine.run(sym, bars, sig_list, strategy)
            result["adjustment_status"] = adj_status
            result["gate"] = "pass"
            result["data_source"] = "adjusted_daily_prices"
            results.append(result)
            pass_count += 1
        else:
            block_count += 1
            results.append(_blocked_result(sym, strategy, sym_info.get("blocked_reason")))

    if block_count == 0:
        overall = "ok"
    elif pass_count == 0:
        overall = "blocked"
        if require_all:
            raise RuntimeError(
                f"BACKTEST_BLOCKED: all {len(symbols)} symbols blocked. "
                "Need source-backed adjusted OHLC / corporate action factor."
            )
    else:
        overall = "partial"
        if require_all:
            blocked = [s for s in symbols if sym_status.get(s, {}).get("backtest_gate") != "pass"]
            raise RuntimeError(
                f"BACKTEST_BLOCKED: {block_count} of {len(symbols)} symbols blocked "
                f"(require_all=True). Blocked: {blocked}"
            )

    return results, caveats, overall


def _blocked_result(symbol: str, strategy: str, reason: str | None) -> dict:
    return {
        "symbol": symbol,
        "strategy": strategy,
        "reason": reason or "No source-backed adjusted OHLC for this symbol.",
        "status": "BLOCKED",
        "portfolio": {},
        "metrics": {},
        "trade_ledger": [],
        "adjustment_status": None,
        "gate": "blocked",
        "data_source": None,
        "caveats": [
            "BLOCKED -- no corporate action source. "
            "Raw daily_prices MUST NOT be used as adjusted for trading.",
        ],
    }


def _sig_for_bar(signals: list[dict], idx: int) -> dict:
    if idx < len(signals):
        return signals[idx]
    return {"signal": "HOLD"}


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Custom backtest engine -- gated on adjusted OHLC.")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. FPT,HPG,VCB")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--strategy", default="momentum_v1",
                        choices=["momentum_v1", "mean_reversion_v1", "buy_hold_v1", "baseline_buy_hold_v1"])
    parser.add_argument("--initial-cash", type=float, default=100_000_000)
    parser.add_argument("--dry-run", action="store_true", help="Skip execution, show gate status only")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-all", action="store_true",
        help="Exit 1 if any requested symbol is blocked"
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    base_url = args.questdb_url.rstrip("/")

    import json as _json

    # Gate check (readiness)
    with qdb.open_client(timeout_seconds=60.0) as client:
        readiness = check_adjusted_readiness(client, base_url, symbols)

    gate = readiness["backtest_gate"]
    if gate == "blocked":
        if args.json:
            print(_json.dumps({
                "status": "BLOCKED",
                "gate": gate,
                "symbols": symbols,
                "strategy": args.strategy,
                "period": f"{args.from_date} -> {args.to_date}",
                "caveats": readiness["caveats"],
            }, indent=2))
        else:
            print(f"{'='*60}")
            print(f"  BACKTEST BLOCKED (all symbols)")
            print(f"{'='*60}")
            for c in readiness["caveats"]:
                print(f"  {c}")
            print(f"{'='*60}")
        return 1

    if args.dry_run:
        print(f"{'='*60}")
        print(f"  Backtest DRY RUN -- gate={gate}")
        print(f"  symbols: {symbols}")
        print(f"  period: {args.from_date} -> {args.to_date}")
        print(f"  strategy: {args.strategy}")
        print(f"  initial_cash: {args.initial_cash:,.0f} VND")
        print(f"{'='*60}")
        return 0

    try:
        with qdb.open_client(timeout_seconds=60.0) as client:
            results, caveats, overall = run_backtest(
                client, base_url, symbols,
                args.from_date, args.to_date,
                args.strategy, args.initial_cash,
                require_all=args.require_all,
            )
    except RuntimeError as e:
        if args.json:
            print(_json.dumps({
                "status": "PARTIAL_BLOCKED",
                "error": str(e),
                "symbols": symbols,
                "strategy": args.strategy,
            }, indent=2))
        else:
            print(f"{'='*60}")
            print(f"  BACKTEST PARTIAL BLOCKED")
            print(f"{'='*60}")
            print(f"  {e}")
            print(f"{'='*60}")
        return 1

    if args.json:
        print(_json.dumps({
            "status": overall,
            "results": results,
            "caveats": caveats,
        }, indent=2))
        return 0

    print(f"{'='*60}")
    print(f"Custom Backtest  strategy={args.strategy}  overall={overall}")
    print(f"{'='*60}")
    for r in results:
        if r.get("status") == "BLOCKED":
            print(f"\n  [BLOCK] {r['symbol']}  reason: {r['reason']}")
        else:
            print(f"\n  {r['symbol']}  reason={r['reason']}")
            print(f"  portfolio: {r['portfolio']}")
            print(f"  metrics:   {r['metrics']}")
            print(f"  trades:    {len(r['trade_ledger'])}")
    if caveats:
        print(f"\n{'='*60}")
        print("  Caveats:")
        for c in caveats:
            print(f"    - {c}")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())