from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.backtest.metrics import summarize_metrics
from trading_agent.signals.mvp_momentum import STRATEGY_ID
from trading_agent.tools._store import DEFAULT_DB_PATH, connect_readonly


DEFAULT_INITIAL_CAPITAL = 100_000_000.0
DEFAULT_TRANSACTION_COST = 0.001
DEFAULT_SLIPPAGE = 0.0005


def run_backtest(
    *,
    symbols: list[str] | tuple[str, ...],
    db_path: str | Path = DEFAULT_DB_PATH,
    strategy_id: str = STRATEGY_ID,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    transaction_cost: float = DEFAULT_TRANSACTION_COST,
    slippage: float = DEFAULT_SLIPPAGE,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    assumptions = {
        "initial_capital": float(initial_capital),
        "transaction_cost": float(transaction_cost),
        "slippage": float(slippage),
        "positioning": "long_cash_only",
        "position_sizing": "full_cash_per_symbol_allocation",
        "price_basis": None,
        "execution_convention": "same_day_close_for_exploratory_mvp",
        "data_source": "cached_sqlite_daily_prices_feature_snapshots_signals",
    }
    caveats = _base_caveats()
    invalid = _validate_inputs(requested, strategy_id, initial_capital, transaction_cost, slippage)
    if invalid:
        return _empty_result(
            status="invalid_assumptions",
            symbols=requested,
            strategy_id=strategy_id,
            assumptions=assumptions,
            caveats=caveats + invalid,
            validation_gates=[_gate("explicit_cost_slippage_assumptions", "fail", "; ".join(invalid))],
        )

    path = Path(db_path)
    if not path.exists():
        return _empty_result(
            status="error",
            symbols=requested,
            strategy_id=strategy_id,
            assumptions=assumptions,
            caveats=caveats
            + [
                f"MVP store not found: {path}",
                "Build it first with: python scripts/build_mvp_db.py --symbols FPT,VNM,VCB",
            ],
            validation_gates=[_gate("store_exists", "fail", str(path))],
        )

    validation_gates = [
        _gate("store_exists", "pass", str(path)),
        _gate(
            "explicit_cost_slippage_assumptions",
            "pass",
            f"transaction_cost={transaction_cost}, slippage={slippage}",
        ),
        _gate(
            "adjustment_corporate_action_warning",
            "warn",
            "adjustment_status is carried from the store; unknown adjustment remains a caveat.",
        ),
        _gate(
            "no_future_leakage_caveat",
            "warn",
            "MVP uses same-day close convention; production must execute on the next available bar.",
        ),
    ]

    with connect_readonly(path) as con:
        symbol_rows = {
            row["symbol"]: row["rows"]
            for row in con.execute(
                "SELECT symbol, COUNT(*) AS rows FROM daily_prices GROUP BY symbol"
            ).fetchall()
        }
        found_symbols = [symbol for symbol in requested if symbol_rows.get(symbol, 0) > 0]
        missing_symbols = [symbol for symbol in requested if symbol not in found_symbols]
        if not found_symbols:
            validation_gates.append(_gate("symbols_exist", "fail", f"missing={','.join(missing_symbols)}"))
            return _empty_result(
                status="not_found",
                symbols=requested,
                symbols_found=[],
                symbols_missing=missing_symbols,
                strategy_id=strategy_id,
                assumptions=assumptions,
                caveats=caveats + ["No requested symbols were found in the MVP store."],
                validation_gates=validation_gates,
            )
        validation_gates.append(
            _gate(
                "symbols_exist",
                "pass" if not missing_symbols else "warn",
                f"found={','.join(found_symbols)}; missing={','.join(missing_symbols)}",
            )
        )
        symbol_caveats = []
        if missing_symbols:
            symbol_caveats.append(
                f"Some requested symbols were not found in the MVP store: {','.join(missing_symbols)}."
            )

        allocation = float(initial_capital) / len(found_symbols)
        symbol_results: dict[str, dict[str, Any]] = {}
        all_price_bases: set[str] = set()
        total_fail_rows = 0
        lineage_missing = 0
        lookback_failures: list[str] = []
        no_usable_rows: list[str] = []

        for symbol in found_symbols:
            rows = _load_symbol_rows(con, symbol, strategy_id, start_date, end_date)
            fail_rows = [row for row in rows if row["price_quality_status"] == "fail"]
            usable_rows = [row for row in rows if row["price_quality_status"] != "fail"]
            total_fail_rows += len(fail_rows)
            if not usable_rows:
                no_usable_rows.append(symbol)
                symbol_results[symbol] = _run_symbol(symbol, usable_rows, allocation, transaction_cost, slippage)
                continue
            lineage_missing += sum(1 for row in usable_rows if not row["source_id"] or not row["raw_path"])
            all_price_bases.update(str(row["price_basis"]) for row in usable_rows if row["price_basis"])
            max_lookback = max([int(row["lookback_coverage"] or 0) for row in usable_rows] or [0])
            if max_lookback < 50:
                lookback_failures.append(symbol)
            symbol_results[symbol] = _run_symbol(symbol, usable_rows, allocation, transaction_cost, slippage)

    assumptions["price_basis"] = sorted(all_price_bases) if all_price_bases else None
    validation_gates.append(
        _gate(
            "usable_rows_exist",
            "pass" if not no_usable_rows else "fail",
            "usable rows available" if not no_usable_rows else f"missing_usable_rows={','.join(no_usable_rows)}",
        )
    )
    validation_gates.append(
        _gate(
            "daily_prices_have_source_id_raw_path",
            "pass" if lineage_missing == 0 else "fail",
            f"missing_lineage_rows={lineage_missing}",
        )
    )
    validation_gates.append(
        _gate(
            "fail_ohlc_rows_excluded",
            "pass",
            f"excluded_fail_rows={total_fail_rows}",
        )
    )
    validation_gates.append(
        _gate(
            "enough_lookback",
            "pass" if not lookback_failures else "fail",
            "minimum 50-day lookback available" if not lookback_failures else f"failed={','.join(lookback_failures)}",
        )
    )

    if no_usable_rows and len(no_usable_rows) == len(found_symbols):
        return _empty_result(
            status="not_found",
            symbols=requested,
            symbols_found=found_symbols,
            symbols_missing=missing_symbols,
            strategy_id=strategy_id,
            assumptions=assumptions,
            caveats=caveats
            + symbol_caveats
            + ["No usable price rows were found for the requested symbols and date range."],
            validation_gates=validation_gates,
        )

    if lineage_missing or lookback_failures:
        return _empty_result(
            status="quality_fail",
            symbols=requested,
            symbols_found=found_symbols,
            symbols_missing=missing_symbols,
            strategy_id=strategy_id,
            assumptions=assumptions,
            caveats=caveats + symbol_caveats + ["One or more blocking validation gates failed."],
            validation_gates=validation_gates,
        )

    portfolio_curve = _combine_equity_curves(symbol_results)
    portfolio_values = [point["portfolio_value"] for point in portfolio_curve]
    portfolio_dates = [point["date"] for point in portfolio_curve]
    position_flags = [bool(point["has_position"]) for point in portfolio_curve]
    trade_pnls = [
        pnl
        for result in symbol_results.values()
        for pnl in result["trade_pnls"]
    ]
    trades = sorted(
        [trade for result in symbol_results.values() for trade in result["trades"]],
        key=lambda item: (item["date"], item["symbol"], item["action"]),
    )
    metrics = summarize_metrics(
        equity=portfolio_values,
        dates=portfolio_dates,
        trade_pnls=trade_pnls,
        position_flags=position_flags,
        number_of_trades=len(trades),
    )
    metrics["by_symbol"] = {
        symbol: result["metrics"]
        for symbol, result in sorted(symbol_results.items())
    }
    metric_caveats = _metric_caveats(metrics)

    return {
        "status": "ok",
        "strategy_id": strategy_id,
        "symbols": requested,
        "symbols_found": found_symbols,
        "symbols_missing": missing_symbols,
        "start_date": portfolio_dates[0] if portfolio_dates else start_date,
        "end_date": portfolio_dates[-1] if portfolio_dates else end_date,
        "assumptions": assumptions,
        "metrics": metrics,
        "trades": trades,
        "equity_curve": portfolio_curve,
        "validation_gates": validation_gates,
        "caveats": caveats + symbol_caveats + metric_caveats,
        "not_financial_advice": True,
    }


def _run_symbol(
    symbol: str,
    rows: list[Any],
    initial_capital: float,
    transaction_cost: float,
    slippage: float,
) -> dict[str, Any]:
    cash = initial_capital
    shares = 0.0
    entry_cost_basis: float | None = None
    trades: list[dict[str, Any]] = []
    trade_pnls: list[float] = []
    equity_curve: list[dict[str, Any]] = []
    position_flags: list[bool] = []

    for row in rows:
        date = row["trade_date"]
        close = float(row["close"])
        action = row["signal_action"] or "HOLD_WITH_LOW_CONFIDENCE"
        if action == "BUY" and shares == 0:
            fill_price = close * (1.0 + slippage)
            gross_investment = cash / (1.0 + transaction_cost)
            cost_paid = gross_investment * transaction_cost
            shares = gross_investment / fill_price if fill_price else 0.0
            cash = cash - gross_investment - cost_paid
            entry_cost_basis = gross_investment + cost_paid
            trades.append(
                _trade(
                    date=date,
                    symbol=symbol,
                    action="BUY",
                    price=close,
                    fill_price=fill_price,
                    shares=shares,
                    transaction_cost=transaction_cost,
                    slippage=slippage,
                    cost_amount=cost_paid,
                    pnl=None,
                )
            )
        elif action == "SELL" and shares > 0:
            fill_price = close * (1.0 - slippage)
            gross_proceeds = shares * fill_price
            cost_paid = gross_proceeds * transaction_cost
            net_proceeds = gross_proceeds - cost_paid
            pnl = net_proceeds - (entry_cost_basis or 0.0)
            cash += net_proceeds
            trades.append(
                _trade(
                    date=date,
                    symbol=symbol,
                    action="SELL",
                    price=close,
                    fill_price=fill_price,
                    shares=shares,
                    transaction_cost=transaction_cost,
                    slippage=slippage,
                    cost_amount=cost_paid,
                    pnl=pnl,
                )
            )
            trade_pnls.append(pnl)
            shares = 0.0
            entry_cost_basis = None
        equity = cash + shares * close
        has_position = shares > 0
        position_flags.append(has_position)
        equity_curve.append(
            {
                "date": date,
                "symbol": symbol,
                "portfolio_value": equity,
                "has_position": has_position,
                "signal_action": action,
            }
        )

    metrics = summarize_metrics(
        equity=[point["portfolio_value"] for point in equity_curve],
        dates=[point["date"] for point in equity_curve],
        trade_pnls=trade_pnls,
        position_flags=position_flags,
        number_of_trades=len(trades),
    )
    return {
        "trades": trades,
        "trade_pnls": trade_pnls,
        "equity_curve": equity_curve,
        "metrics": metrics,
    }


def _load_symbol_rows(
    con: Any,
    symbol: str,
    strategy_id: str,
    start_date: str | None,
    end_date: str | None,
) -> list[Any]:
    clauses = ["p.symbol = ?"]
    params: list[Any] = [strategy_id, symbol]
    if start_date:
        clauses.append("p.trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("p.trade_date <= ?")
        params.append(end_date)
    where_sql = " AND ".join(clauses)
    return con.execute(
        f"""
        SELECT p.symbol, p.trade_date, p.open, p.high, p.low, p.close,
               p.price_basis, p.adjustment_status, p.source_id, p.raw_path,
               p.quality_status AS price_quality_status,
               f.lookback_coverage,
               s.action AS signal_action
        FROM daily_prices p
        LEFT JOIN feature_snapshots f
          ON f.symbol = p.symbol AND f.as_of_date = p.trade_date
        LEFT JOIN signals s
          ON s.symbol = p.symbol AND s.as_of_date = p.trade_date AND s.strategy_id = ?
        WHERE {where_sql}
        ORDER BY p.trade_date
        """,
        params,
    ).fetchall()


def _combine_equity_curves(symbol_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    dates = sorted(
        {
            point["date"]
            for result in symbol_results.values()
            for point in result["equity_curve"]
        }
    )
    latest_values = {
        symbol: result["equity_curve"][0]["portfolio_value"]
        for symbol, result in symbol_results.items()
        if result["equity_curve"]
    }
    by_symbol_date = {
        symbol: {point["date"]: point for point in result["equity_curve"]}
        for symbol, result in symbol_results.items()
        if result["equity_curve"]
    }
    combined: list[dict[str, Any]] = []
    for date in dates:
        has_position = False
        symbol_values: dict[str, float] = {}
        for symbol, points in by_symbol_date.items():
            point = points.get(date)
            if point is not None:
                latest_values[symbol] = point["portfolio_value"]
                has_position = has_position or bool(point["has_position"])
            symbol_values[symbol] = latest_values[symbol]
        combined.append(
            {
                "date": date,
                "portfolio_value": sum(symbol_values.values()),
                "has_position": has_position,
                "symbol_values": symbol_values,
            }
        )
    return combined


def _trade(
    *,
    date: str,
    symbol: str,
    action: str,
    price: float,
    fill_price: float,
    shares: float,
    transaction_cost: float,
    slippage: float,
    cost_amount: float,
    pnl: float | None,
) -> dict[str, Any]:
    return {
        "date": date,
        "symbol": symbol,
        "action": action,
        "price": price,
        "fill_price": fill_price,
        "shares": shares,
        "transaction_cost": transaction_cost,
        "slippage": slippage,
        "cost_amount": cost_amount,
        "pnl": pnl,
    }


def _normalize_symbols(symbols: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for symbol in symbols:
        item = str(symbol).strip().upper()
        if item and item not in seen:
            normalized.append(item)
            seen.add(item)
    return normalized


def _validate_inputs(
    symbols: list[str],
    strategy_id: str,
    initial_capital: float,
    transaction_cost: float,
    slippage: float,
) -> list[str]:
    errors: list[str] = []
    if not symbols:
        errors.append("At least one symbol is required.")
    if strategy_id != STRATEGY_ID:
        errors.append(f"Unsupported strategy_id={strategy_id}; expected {STRATEGY_ID}.")
    if initial_capital <= 0:
        errors.append("initial_capital must be greater than zero.")
    if transaction_cost < 0:
        errors.append("transaction_cost must be non-negative.")
    if slippage < 0:
        errors.append("slippage must be non-negative.")
    return errors


def _base_caveats() -> list[str]:
    return [
        "Exploratory Backtest MVP only; not financial advice.",
        "Uses cached SQLite daily_prices, feature_snapshots, and signals only; no network fetch.",
        "No broker execution, no live trading, no shorting, and no LLM-generated trades.",
        "Adjustment/corporate-action status may be unknown; returns can be distorted by splits or dividends.",
        "Signal/execution convention is same-day close for this MVP; production backtests must use a stricter next-bar convention.",
    ]


def _metric_caveats(metrics: dict[str, Any]) -> list[str]:
    caveats: list[str] = []
    for key in ["annualized_return", "sharpe", "sortino", "profit_factor", "win_rate"]:
        if metrics.get(key) is None:
            caveats.append(f"Metric {key} could not be computed reliably from available trades/returns.")
    return caveats


def _gate(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _empty_result(
    *,
    status: str,
    symbols: list[str],
    strategy_id: str,
    assumptions: dict[str, Any],
    caveats: list[str],
    validation_gates: list[dict[str, str]],
    symbols_found: list[str] | None = None,
    symbols_missing: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "strategy_id": strategy_id,
        "symbols": symbols,
        "symbols_found": symbols_found or [],
        "symbols_missing": symbols_missing or [],
        "start_date": None,
        "end_date": None,
        "assumptions": assumptions,
        "metrics": {},
        "trades": [],
        "equity_curve": [],
        "validation_gates": validation_gates,
        "caveats": caveats,
        "not_financial_advice": True,
    }
