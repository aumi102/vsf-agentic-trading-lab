"""Custom backtest engine v1 -- gated on source-backed adjusted OHLC.

BLOCKED -- if adjusted OHLCV readiness check fails (no source-backed adjustment factors).
Do NOT backtest on raw OHLCV presented as adjusted.

Backtest contract v1:
  portfolio_state    = {cash, position, equity, bars_count}
  order_model        = BUY / SELL / HOLD  (no fractional, no short)
  trade_ledger      = list of {date, symbol, side, quantity, raw_base_price,
                       execution_price, commission, slippage_bps, slippage_value_estimate,
                       gross_value, net_value, realized_pnl, realized_pnl_pct, risk_flags}
  metrics            = {total_return, sharpe, max_drawdown, win_rate, total_trades,
                       closed_trades, profit_factor, cost_slippage_assumptions}
  execution_rule     = no-lookahead: signals fire at bar t+1 open price
  cost_model         = commission + slippage (user-configurable bps)
  price_band_guard   = optional HOSE±7%, UPCoM±15%, HNX±10%
  profit_factor      = from trade-level PnL (FIFO), not daily returns
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
from trading_agent.backtest import metrics as _metrics  # noqa: E402
from scripts.adjusted_ohlc_readiness import check_adjusted_readiness  # noqa: E402
from scripts.run_trading_signals import (  # noqa: E402
    _fetch_bars as _fetch_bars_signals,
    _signal_momentum_v1,
    _signal_mean_reversion_v1,
    _signal_buy_hold_v1,
    STRATEGIES as SIGNAL_STRATEGIES,
)
from scripts.trading_cost_model import ExecutionContext  # noqa: E402

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL

# Default Vietnam broker assumptions
DEFAULT_COMMISSION_BPS = 15.0
DEFAULT_SLIPPAGE_BPS = 5.0


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
    """Minimal no-lookahead backtest engine with cost/slippage model.

    Execution rule: signal at bar t triggers order at bar t+1 open price.
    No fractional shares. No short selling. No leverage.
    Profit Factor and Win Rate are computed from trade-level PnL (FIFO).
    """

    def __init__(
        self,
        initial_cash: float,
        commission_bps: float = DEFAULT_COMMISSION_BPS,
        slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
        price_band_guard: bool = False,
        exchange_default: str = "HOSE",
    ):
        self.initial_cash = initial_cash
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.price_band_guard = price_band_guard
        self.exchange_default = exchange_default
        self._reset()

    def _reset(self) -> None:
        self.cash = self.initial_cash
        self.position = 0  # shares held
        self.entry_price = 0.0
        self.entry_commission = 0.0
        self.ledger: list[dict] = []
        self.equity_curve: list[float] = []
        self.ctx = ExecutionContext(
            commission_bps=self.commission_bps,
            slippage_bps=self.slippage_bps,
            price_band_guard=self.price_band_guard,
            exchange_default=self.exchange_default,
        )

    def run(
        self, symbol: str,
        bars: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        strategy: str,
        exchange: str | None = "HOSE",
    ) -> dict[str, Any]:
        """Run backtest over bars with pre-computed signals.

        Signals must align with bars by index (signal[i] corresponds to bars[i]).
        Signal at bar i fires execution at bar i+1 open.
        Uses ExecutionContext for commission + slippage on every trade.
        """
        self._reset()

        if not bars or len(bars) < 2:
            return self._result(symbol, strategy, bars, "insufficient_bars")

        for i in range(len(bars) - 1):
            sig = signals[i] if i < len(signals) else {}
            side = sig.get("signal", "HOLD")
            bar = bars[i + 1]
            base_price = float(bar["open"])
            trade_date = str(bar["trade_date"])[:10]

            # Only call execute() when the trade CAN physically occur:
            # BUY: need flat position + sufficient cash
            # SELL: need an open position
            exec_result = None
            if side == "BUY" and self.position == 0:
                exec_result = self.ctx.execute(
                    side="BUY",
                    base_price=base_price,
                    quantity=100,
                    trade_date=trade_date,
                    symbol=symbol,
                    exchange=exchange,
                )
                if exec_result.net_value is not None and self.cash >= exec_result.net_value:
                    self.cash -= exec_result.net_value
                    self.position = exec_result.quantity
                    self.entry_price = exec_result.execution_price
                    self.entry_commission = exec_result.commission
                    self.ledger.append(exec_result.to_dict())
                elif exec_result.net_value is None:
                    self.ledger.append(exec_result.to_dict())
            elif side == "SELL" and self.position > 0:
                exec_result = self.ctx.execute(
                    side="SELL",
                    base_price=base_price,
                    quantity=self.position,
                    trade_date=trade_date,
                    symbol=symbol,
                    exchange=exchange,
                )
                if exec_result.net_value is not None:
                    proceeds = exec_result.net_value
                    self.cash += proceeds
                    realized_pnl = (proceeds
                                   - (self.entry_price * self.position)
                                   - self.entry_commission
                                   - exec_result.commission)
                    realized_pnl_pct = (realized_pnl / (self.entry_price * self.position)
                                        if self.entry_price > 0 else None)
                    sell_entry = exec_result.to_dict()
                    sell_entry["realized_pnl"] = round(realized_pnl, 2)
                    sell_entry["realized_pnl_pct"] = (
                        round(realized_pnl_pct * 100, 4) if realized_pnl_pct is not None else None)
                    sell_entry["entry_price"] = self.entry_price
                    sell_entry["entry_commission"] = round(self.entry_commission, 2)
                    self.ledger.append(sell_entry)
                    self.position = 0
                    self.entry_price = 0.0
                    self.entry_commission = 0.0
                elif exec_result.net_value is None:
                    self.ledger.append(exec_result.to_dict())

            # mark-to-market
            exec_price = exec_result.execution_price if exec_result else base_price
            mtm = self.cash + self.position * (exec_price or base_price)
            self.equity_curve.append(mtm)

        # close at last bar close
        if self.position > 0:
            last_close = float(bars[-1]["close"])
            close_result = self.ctx.execute(
                side="SELL",
                base_price=last_close,
                quantity=self.position,
                trade_date=str(bars[-1]["trade_date"])[:10],
                symbol=symbol,
                exchange=exchange,
            )
            if close_result.net_value is not None:
                proceeds = close_result.net_value
                self.cash += proceeds
                realized_pnl = proceeds - (self.entry_price * self.position) - self.entry_commission - close_result.commission
                realized_pnl_pct = realized_pnl / (self.entry_price * self.position) if self.entry_price > 0 else None
                close_dict = close_result.to_dict()
                close_dict["realized_pnl"] = round(realized_pnl, 2)
                close_dict["realized_pnl_pct"] = round(realized_pnl_pct * 100, 4) if realized_pnl_pct is not None else None
                close_dict["entry_price"] = self.entry_price
                close_dict["entry_commission"] = round(self.entry_commission, 2)
                if self.ledger:
                    self.ledger[-1] = {**self.ledger[-1], **close_dict}
                self.position = 0
                self.entry_price = 0.0
                self.entry_commission = 0.0
                self.equity_curve.append(self.cash)

        return self._result(symbol, strategy, bars, "ok")

    def _result(self, symbol: str, strategy: str, bars: list, reason: str) -> dict[str, Any]:
        final_equity = self.cash + self.position * float(bars[-1]["close"]) if bars else self.cash
        total_return = (final_equity - self.initial_cash) / self.initial_cash * 100 if self.initial_cash else 0

        # Trade-level PnL for profit factor and win rate
        trade_pnls = [t.get("realized_pnl", 0.0) or 0.0 for t in self.ledger if "realized_pnl" in t]
        closed_trades = sum(1 for t in self.ledger if "realized_pnl" in t)
        total_trades = len(self.ledger)
        pf = _metrics.profit_factor(trade_pnls)
        wr = _metrics.win_rate(trade_pnls)
        max_dd_pct = _metrics.max_drawdown(self.equity_curve)
        returns = _metrics.daily_returns(self.equity_curve)
        sharpe = _metrics.sharpe_ratio(returns)
        sortino = _metrics.sortino_ratio(returns)
        cost_summary = self.ctx.summary()

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
                "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
                "sortino_ratio": round(sortino, 3) if sortino is not None else None,
                "profit_factor": round(pf, 3) if pf is not None else None,
                "max_drawdown_pct": round(max_dd_pct * 100, 2) if max_dd_pct is not None else None,
                "win_rate": round(wr, 3) if wr is not None else None,
                "total_trades": total_trades,
                "closed_trades": closed_trades,
                "total_commission": cost_summary.total_commission,
                "total_slippage_estimate": cost_summary.total_slippage_estimate,
                "cost_slippage_assumptions": (
                    f"{self.commission_bps} bps commission per side (user-configurable). "
                    f"{self.slippage_bps} bps slippage per side (user-configurable assumption). "
                    f"Blocked orders due price band: {cost_summary.blocked_orders}."
                ),
            },
            "cost_summary": cost_summary.to_dict(),
            "trade_ledger": self.ledger,
        }


def run_backtest(
    client, base_url: str,
    symbols: list[str],
    from_date: str,
    to_date: str,
    strategy: str,
    initial_cash: float = 100_000_000,
    require_all: bool = False,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    price_band_guard: bool = False,
    exchange_default: str = "HOSE",
    source_policy: str = "approved_only",
) -> tuple[list[dict], list[str], str]:
    """Run backtest gated on adjusted OHLC readiness. PARTIAL if some symbols blocked."""
    readiness = check_adjusted_readiness(client, base_url, symbols,
                                         source_policy=source_policy)
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
            exchange = None
            for b in bars:
                if b.get("exchange"):
                    exchange = b["exchange"]
                    break
            feat_strategy = strategy.replace("_v1", "")
            if feat_strategy in ("momentum", "ma_cross"):
                sig = _signal_momentum_v1(bars)
            elif feat_strategy == "mean_reversion":
                sig = _signal_mean_reversion_v1(bars)
            elif feat_strategy in ("buy_hold", "baseline_buy_hold"):
                sig = _signal_buy_hold_v1(bars, adj_status)
            else:
                sig = {"signal": "HOLD", "score": 0.0, "reason": f"unknown strategy={strategy}"}
            sig_list = [sig] * len(bars)
            engine = BacktestEngineV1(
                initial_cash,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
                price_band_guard=price_band_guard,
                exchange_default=exchange or exchange_default,
            )
            result = engine.run(sym, bars, sig_list, strategy, exchange=exchange)
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
                        choices=["momentum_v1", "ma_cross_v1", "mean_reversion_v1", "buy_hold_v1", "baseline_buy_hold_v1"])
    parser.add_argument("--initial-cash", type=float, default=100_000_000)
    parser.add_argument("--dry-run", action="store_true", help="Skip execution, show gate status only")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-all", action="store_true",
        help="Exit 1 if any requested symbol is blocked"
    )
    parser.add_argument(
        "--source-policy",
        choices=["approved_only", "prototype_allowed"],
        default="approved_only",
        help="approved_only: vnstock rows are BLOCKED (default). "
             "prototype_allowed: vnstock rows count as PASS_PROTOTYPE.",
    )
    # Cost / slippage / risk args
    parser.add_argument("--commission-bps", type=float, default=DEFAULT_COMMISSION_BPS,
                        help=f"Commission bps per side (default: {DEFAULT_COMMISSION_BPS})")
    parser.add_argument("--slippage-bps", type=float, default=DEFAULT_SLIPPAGE_BPS,
                        help=f"Slippage bps per side (default: {DEFAULT_SLIPPAGE_BPS})")
    parser.add_argument("--price-band-guard", action="store_true",
                        help="Enable exchange price-band guard (HOSE±7%, UPCoM±15%, HNX±10%)")
    parser.add_argument("--exchange-default", default="HOSE",
                        help="Default exchange when not known from data (default: HOSE)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    base_url = args.questdb_url.rstrip("/")

    import json as _json

    # Gate check (readiness)
    with qdb.open_client(timeout_seconds=60.0) as client:
        readiness = check_adjusted_readiness(client, base_url, symbols,
                                             source_policy=args.source_policy)

    gate = readiness["backtest_gate"]
    if gate == "blocked":
        if args.json:
            print(_json.dumps({
                "status": "BLOCKED",
                "gate": gate,
                "symbols": symbols,
                "strategy": args.strategy,
                "period": f"{args.from_date} -> {args.to_date}",
                "cost_assumptions": {
                    "commission_bps": args.commission_bps,
                    "slippage_bps": args.slippage_bps,
                    "price_band_guard": args.price_band_guard,
                },
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
        print(f"  commission: {args.commission_bps} bps/side")
        print(f"  slippage: {args.slippage_bps} bps/side")
        print(f"  price_band_guard: {args.price_band_guard}")
        print(f"{'='*60}")
        return 0

    try:
        with qdb.open_client(timeout_seconds=60.0) as client:
            results, caveats, overall = run_backtest(
                client, base_url, symbols,
                args.from_date, args.to_date,
                args.strategy, args.initial_cash,
                require_all=args.require_all,
                commission_bps=args.commission_bps,
                slippage_bps=args.slippage_bps,
                price_band_guard=args.price_band_guard,
                exchange_default=args.exchange_default,
                source_policy=args.source_policy,
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
            "cost_assumptions": {
                "commission_bps": args.commission_bps,
                "slippage_bps": args.slippage_bps,
                "price_band_guard": args.price_band_guard,
                "exchange_default": args.exchange_default,
            },
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