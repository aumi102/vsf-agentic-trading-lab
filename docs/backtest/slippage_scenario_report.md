# Slippage scenario report

Generated from persisted QuestDB backtest rows for the current demo scope.

## Scope

- Symbols: FPT, VNM, HPG
- Strategies: `buy_hold`, `ma20_ma50`, `rsi_mean_reversion`
- Window: 2020-01-01 to 2025-12-31
- Scenarios: 0, 5, 10, 15 bps
- Price-band guard: `price_band_guard_pass` for all 36 persisted runs

## Persisted row counts

| Table | Rows |
|---|---:|
| `backtest_runs` | 36 |
| `backtest_metrics` | 36 |
| `backtest_equity_curve` | 53,964 |
| `backtest_trades` | 400 |

## FPT scenario impact

| Strategy | Slippage bps | Final value | Total return % | Max drawdown % |
|---|---:|---:|---:|---:|
| `buy_hold` | 0 | 434,286,857 | 334.29 | 34.35 |
| `buy_hold` | 5 | 434,239,067 | 334.24 | 34.35 |
| `buy_hold` | 10 | 434,191,277 | 334.19 | 34.35 |
| `buy_hold` | 15 | 434,143,486 | 334.14 | 34.36 |
| `ma20_ma50` | 0 | 392,519,583 | 292.52 | 22.14 |
| `ma20_ma50` | 5 | 389,153,321 | 289.15 | 22.37 |
| `ma20_ma50` | 10 | 385,779,816 | 285.78 | 22.60 |
| `ma20_ma50` | 15 | 382,505,171 | 282.51 | 22.82 |
| `rsi_mean_reversion` | 0 | 140,790,781 | 40.79 | 29.06 |
| `rsi_mean_reversion` | 5 | 138,146,156 | 38.15 | 29.32 |
| `rsi_mean_reversion` | 10 | 135,608,245 | 35.61 | 29.56 |
| `rsi_mean_reversion` | 15 | 133,370,173 | 33.37 | 29.78 |

## Interpretation

Non-zero slippage reduces returns as expected. The effect is small for buy-and-hold and larger for strategies with more closed trades.

Agent and DeepAgents default comparison intentionally use `slippage_bps=0.0` unless a slippage scenario is explicitly requested. The scenario rows are persisted for research and validation, not for automatic recommendation.

## Caveats

- Slippage is modeled as a simple bps assumption, not a production market-impact model.
- Price-band validation checks that the slippage assumption is within known exchange price bands; it does not validate liquidity or fill probability.
- Adjusted OHLC remains source-unverified and raw-equivalent in current data.
- Backtests are research-only and not investment advice.
