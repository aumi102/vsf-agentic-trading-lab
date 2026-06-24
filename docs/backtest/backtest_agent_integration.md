# Persisted backtest agent integration

## Scope

The agent/backend/DeepAgents integration is read-only persisted-result lookup only.

Allowed:

- read `backtest_runs`
- read `backtest_metrics`
- read `backtest_equity_curve`
- read `backtest_trades` in future endpoints when needed

Disallowed:

- running Backtrader from the agent;
- running Backtrader from DeepAgents;
- mutating market, FA, or backtest result tables;
- using backtest tools for general market, FA, or event/news queries.

## Backend endpoints

```text
GET /backtest/latest/{symbol}
GET /backtest/latest/{symbol}?strategy_id=ma20_ma50
GET /backtest/latest/{symbol}?strategy_id=ma20_ma50&slippage_bps=10
GET /backtest/comparison/{symbol}
GET /backtest/comparison/{symbol}?slippage_bps=0
GET /backtest/equity/{symbol}/{strategy_id}?limit=5000
GET /backtest/slippage-scenarios/{symbol}
```

Status behavior:

- `200` when persisted rows exist;
- `404` when persisted backtest data is unavailable;
- `400` on invalid symbol/strategy input.

The legacy live endpoint `POST /backtest/ma-cross` is disabled and returns unsupported.

## Query examples

Rule-based agent:

```bat
python scripts\demo_agent_backend_cli.py "backtest FPT"
python scripts\demo_agent_backend_cli.py "compare backtest strategies FPT"
python scripts\demo_agent_backend_cli.py "MA20/MA50 backtest FPT"
```

Backend:

```bat
curl.exe -s http://127.0.0.1:8014/backtest/comparison/FPT
curl.exe -s http://127.0.0.1:8014/backtest/latest/FPT
curl.exe -s http://127.0.0.1:8014/backtest/equity/FPT/ma20_ma50?limit=20
curl.exe -s http://127.0.0.1:8014/backtest/slippage-scenarios/FPT
```

DeepAgents:

```bat
python scripts\demo_deepagents_questdb_cli.py "compare backtest strategies FPT"
```

## Guardrails

- Backtest lookup tools are only routed for explicit backtest/simulation/strategy-performance requests.
- `summary FPT` remains a market summary.
- `financial report FPT` remains an FA query.
- event/news prompts use the event/news tool only when persisted official-disclosure rows exist; otherwise they return unavailable and must not use OHLCV as a proxy.
- Missing persisted backtest rows return unavailable with the operator instruction:

```text
Run scripts/run_backtrader_questdb_persist.py first for this symbol/strategy.
```
- Default lookup filters to `slippage_bps=0.0` so slippage-scenario runs do not make normal strategy comparisons ambiguous.
- Scenario lookup is read-only persisted data through `/backtest/slippage-scenarios/{symbol}` or explicit `slippage_bps` filters.

## Caveats disclosed by tools

- Adjusted OHLC source remains unverified for the current persisted runs.
- `slippage_bps` is explicit. Current persisted scenarios cover 0, 5, 10, and 15 bps for FPT/VNM/HPG.
- `price_band_status` is persisted; current FPT/VNM/HPG demo runs show `price_band_guard_pass`.
- Exchange metadata is source-backed from captured Vietcap IQ universe and HOSE listed-universe dry-run evidence for all 1,556 current `securities` rows. New securities still require source-backed exchange metadata before price-band guard should be treated as complete.
- `backtest_trades` contains aggregate closed-trade events, not a full entry/exit fill ledger.
- Backtests are research-only and not investment advice.

## Next step

Before broader DeepAgents exposure:

- add strategy registry metadata;
- add persisted-result version selection;
- add a trade endpoint if mentor wants trade-level lookup in the backend;
- add explicit date/scope filters to lookup tools;
- keep live Backtrader execution as an offline/manual runner only.
