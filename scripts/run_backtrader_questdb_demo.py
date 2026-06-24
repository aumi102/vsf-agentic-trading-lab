"""Run Backtrader research strategies using QuestDB daily_prices data.

This is a research/demo runner only. It does not mutate QuestDB and is not wired
into the agent or DeepAgents services.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import backtrader as bt
except ImportError as exc:  # pragma: no cover - exercised by CLI environment
    raise SystemExit("Backtrader is missing. Install with: pip install backtrader") from exc

from export_questdb_ohlcv_for_backtrader import export_symbol_to_csv, parse_symbols, validate_date  # noqa: E402
from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_OUT_DIR = Path("data/cache/backtrader")
SUMMARY_COLUMNS = [
    "symbol", "strategy", "start_date", "end_date", "start_value", "final_value",
    "total_return_pct", "annualized_return_pct", "max_drawdown_pct", "sharpe_ratio",
    "closed_trades", "win_rate_pct", "csv_path",
]
EQUITY_COLUMNS = ["symbol", "strategy", "date", "value", "cash"]


class BuyAndHoldStrategy(bt.Strategy):
    params = (("target_percent", 0.95),)

    def __init__(self) -> None:
        self._entered = False

    def next(self) -> None:
        if not self._entered:
            self.order_target_percent(target=self.p.target_percent)
            self._entered = True


class MA20MA50CrossoverStrategy(bt.Strategy):
    params = (("fast", 20), ("slow", 50), ("target_percent", 0.95),)

    def __init__(self) -> None:
        fast = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.fast)
        slow = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.slow)
        self.cross = bt.indicators.CrossOver(fast, slow)

    def next(self) -> None:
        if not self.position and self.cross > 0:
            self.order_target_percent(target=self.p.target_percent)
        elif self.position and self.cross < 0:
            self.order_target_percent(target=0.0)


class RSIMeanReversionStrategy(bt.Strategy):
    params = (("period", 14), ("buy_below", 30), ("exit_above", 55), ("target_percent", 0.95),)

    def __init__(self) -> None:
        self.rsi = bt.indicators.RSI_SMA(self.data.close, period=self.p.period)

    def next(self) -> None:
        if not self.position and self.rsi < self.p.buy_below:
            self.order_target_percent(target=self.p.target_percent)
        elif self.position and self.rsi > self.p.exit_above:
            self.order_target_percent(target=0.0)


class EquityCurveAnalyzer(bt.Analyzer):
    def start(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def next(self) -> None:
        self.rows.append({
            "date": self.strategy.datas[0].datetime.date(0).isoformat(),
            "value": float(self.strategy.broker.getvalue()),
            "cash": float(self.strategy.broker.getcash()),
        })

    def get_analysis(self) -> list[dict[str, Any]]:
        return self.rows


class ClosedTradeAnalyzer(bt.Analyzer):
    """Capture one compact row per closed Backtrader trade.

    Backtrader's ``Trade`` object exposes aggregate closed-trade fields reliably,
    but not a fully normalized entry/exit pair without enabling deeper history.
    This analyzer records the available closed-trade event data and leaves fields
    blank only when Backtrader does not expose them.
    """

    def start(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def notify_trade(self, trade) -> None:  # type: ignore[no-untyped-def]
        if not getattr(trade, "isclosed", False):
            return
        dtclose = getattr(trade, "dtclose", None)
        if dtclose:
            trade_date = bt.num2date(dtclose).date().isoformat()
        else:
            trade_date = self.strategy.datas[0].datetime.date(0).isoformat()
        price = _float_or_none(getattr(trade, "price", None))
        value = _float_or_none(getattr(trade, "value", None))
        pnl = _float_or_none(getattr(trade, "pnlcomm", None))
        if pnl is None:
            pnl = _float_or_none(getattr(trade, "pnl", None))
        size = _float_or_none(getattr(trade, "size", None))
        if size == 0.0:
            size = None
        if value == 0.0:
            value = None
        if (size is None or size == 0.0) and value and price:
            size = abs(value) / price
        pnl_pct = (pnl / abs(value) * 100.0) if pnl is not None and value not in (None, 0.0) else None
        self.rows.append({
            "trade_date": trade_date,
            "event_type": "closed_trade",
            "size": size,
            "price": price,
            "value": value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })

    def get_analysis(self) -> list[dict[str, Any]]:
        return self.rows


STRATEGIES: dict[str, type[bt.Strategy]] = {
    "buy_hold": BuyAndHoldStrategy,
    "ma20_ma50": MA20MA50CrossoverStrategy,
    "rsi_mean_reversion": RSIMeanReversionStrategy,
}


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    start_value: float
    final_value: float
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float | None
    sharpe_ratio: float | None
    closed_trades: int
    win_rate_pct: float | None
    csv_path: Path
    equity_curve: list[dict[str, Any]]
    trades: list[dict[str, Any]]


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _load_csv_date_range(path: Path) -> tuple[str, str]:
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        dates = [row["datetime"] for row in reader]
    if not dates:
        raise RuntimeError(f"CSV has no data rows: {path}")
    return dates[0], dates[-1]


def _annualized_return(start_value: float, final_value: float, start_date: str, end_date: str) -> float:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days = max((end - start).days, 1)
    if start_value <= 0:
        return 0.0
    return ((final_value / start_value) ** (365.25 / days) - 1.0) * 100.0


def _trade_stats(analysis: dict[str, Any]) -> tuple[int, float | None]:
    total = analysis.get("total", {}) if isinstance(analysis, dict) else {}
    won = analysis.get("won", {}) if isinstance(analysis, dict) else {}
    closed = int(total.get("closed") or 0)
    won_total = int(won.get("total") or 0)
    win_rate = (won_total / closed * 100.0) if closed else None
    return closed, win_rate


def _make_data_feed(csv_path: Path) -> bt.feeds.GenericCSVData:
    return bt.feeds.GenericCSVData(
        dataname=str(csv_path),
        dtformat="%Y-%m-%d",
        datetime=0,
        open=1,
        high=2,
        low=3,
        close=4,
        volume=5,
        openinterest=6,
        headers=True,
        timeframe=bt.TimeFrame.Days,
        compression=1,
    )


def run_one(
    *,
    symbol: str,
    strategy_name: str,
    strategy_cls: type[bt.Strategy],
    csv_path: Path,
    start_value: float,
    commission: float,
    slippage_bps: float = 0.0,
) -> BacktestResult:
    start_date, end_date = _load_csv_date_range(csv_path)
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(start_value)
    cerebro.broker.setcommission(commission=commission)
    if slippage_bps:
        cerebro.broker.set_slippage_perc(slippage_bps / 10_000.0)
    cerebro.adddata(_make_data_feed(csv_path), name=symbol)
    cerebro.addstrategy(strategy_cls)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name="sharpe", riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(EquityCurveAnalyzer, _name="equity")
    cerebro.addanalyzer(ClosedTradeAnalyzer, _name="closed_trade_events")
    results = cerebro.run()
    strategy = results[0]
    final_value = float(cerebro.broker.getvalue())
    drawdown = strategy.analyzers.drawdown.get_analysis()
    max_drawdown = drawdown.get("max", {}).get("drawdown") if isinstance(drawdown, dict) else None
    sharpe = strategy.analyzers.sharpe.get_analysis()
    sharpe_ratio = sharpe.get("sharperatio") if isinstance(sharpe, dict) else None
    trades = strategy.analyzers.trades.get_analysis()
    closed_trades, win_rate = _trade_stats(trades)
    total_return = (final_value / start_value - 1.0) * 100.0
    return BacktestResult(
        symbol=symbol,
        strategy=strategy_name,
        start_date=start_date,
        end_date=end_date,
        start_value=start_value,
        final_value=final_value,
        total_return_pct=total_return,
        annualized_return_pct=_annualized_return(start_value, final_value, start_date, end_date),
        max_drawdown_pct=float(max_drawdown) if max_drawdown is not None else None,
        sharpe_ratio=float(sharpe_ratio) if sharpe_ratio is not None and not math.isnan(float(sharpe_ratio)) else None,
        closed_trades=closed_trades,
        win_rate_pct=win_rate,
        csv_path=csv_path,
        equity_curve=strategy.analyzers.equity.get_analysis(),
        trades=strategy.analyzers.closed_trade_events.get_analysis(),
    )


def _format_num(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{decimals}f}"


def print_results(results: list[BacktestResult]) -> None:
    headers = ["symbol", "strategy", "final", "total_%", "ann_%", "max_dd_%", "sharpe", "trades", "win_%"]
    rows = [
        [
            result.symbol,
            result.strategy,
            _format_num(result.final_value, 0),
            _format_num(result.total_return_pct),
            _format_num(result.annualized_return_pct),
            _format_num(result.max_drawdown_pct),
            _format_num(result.sharpe_ratio),
            str(result.closed_trades),
            _format_num(result.win_rate_pct),
        ]
        for result in results
    ]
    widths = [max(len(str(cell)) for cell in [header] + [row[i] for row in rows]) for i, header in enumerate(headers)]
    print(" | ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def write_summary(results: list[BacktestResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for result in results:
            writer.writerow({
                "symbol": result.symbol,
                "strategy": result.strategy,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "start_value": result.start_value,
                "final_value": result.final_value,
                "total_return_pct": result.total_return_pct,
                "annualized_return_pct": result.annualized_return_pct,
                "max_drawdown_pct": "" if result.max_drawdown_pct is None else result.max_drawdown_pct,
                "sharpe_ratio": "" if result.sharpe_ratio is None else result.sharpe_ratio,
                "closed_trades": result.closed_trades,
                "win_rate_pct": "" if result.win_rate_pct is None else result.win_rate_pct,
                "csv_path": str(result.csv_path),
            })


def write_equity_curves(results: list[BacktestResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=EQUITY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for result in results:
            for row in result.equity_curve:
                writer.writerow({
                    "symbol": result.symbol,
                    "strategy": result.strategy,
                    "date": row.get("date"),
                    "value": row.get("value"),
                    "cash": row.get("cash"),
                })


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Backtrader demo strategies from QuestDB daily_prices data.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol")
    group.add_argument("--symbols")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--start-cash", type=float, default=100_000_000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    args = parser.parse_args()
    try:
        validate_date(args.start_date, "start_date")
        validate_date(args.end_date, "end_date")
        symbols = parse_symbols(args.symbol or args.symbols)
        out_dir = Path(args.out_dir)
        results: list[BacktestResult] = []
        for symbol in symbols:
            csv_path = out_dir / f"backtrader_{symbol}_{args.start_date}_{args.end_date}.csv"
            export_result = export_symbol_to_csv(
                symbol=symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                out_path=csv_path,
                questdb_url=args.questdb_url,
            )
            print(
                f"exported symbol={symbol} rows={export_result.rows} "
                f"date_range={export_result.first_date}..{export_result.last_date} path={csv_path}"
            )
            for caveat in export_result.caveats:
                print(f"caveat={symbol}: {caveat}")
            for strategy_name, strategy_cls in STRATEGIES.items():
                results.append(run_one(
                    symbol=symbol,
                    strategy_name=strategy_name,
                    strategy_cls=strategy_cls,
                    csv_path=csv_path,
                    start_value=args.start_cash,
                    commission=args.commission,
                    slippage_bps=args.slippage_bps,
                ))
        print_results(results)
        summary_path = out_dir / "backtrader_summary.csv"
        equity_path = out_dir / "backtrader_equity_curves.csv"
        write_summary(results, summary_path)
        write_equity_curves(results, equity_path)
        print(f"summary_csv={summary_path}")
        print(f"equity_curves_csv={equity_path}")
    except Exception as exc:
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
