# Mentor demo readiness

## Current demo scope

The local demo can show:

- market summary from QuestDB `daily_prices`, `feature_snapshots`, and `signals`;
- financial report lookup from Vietcap FA QuestDB tables;
- event/news guardrail, returning unavailable instead of using OHLCV as a proxy;
- persisted Backtrader result lookup from `backtest_*` tables;
- backend endpoints for market, FA, and persisted backtest lookup;
- optional DeepAgents checks when OpenAI credentials are valid in the current process.

DeepAgents and the backend do not run live Backtrader. They read persisted backtest results only.

## One-command readiness

Rule-based readiness:

```bat
python scripts\run_mentor_demo_readiness.py
```

Optional DeepAgents readiness:

```bat
python scripts\check_deepagents_env.py
python scripts\check_deepagents_env.py --live
python scripts\run_mentor_demo_readiness.py --deepagents
```

If the live DeepAgents check reports `FAILED_CREDENTIAL`, the API key in the current process is invalid or stale.

## DeepAgents routing checks

DeepAgents readiness validates semantic tool routing, not just successful process exit.

- `summary FPT` must use market tools only: `get_symbol_summary`, or `get_latest_ohlcv` / `get_latest_features` / `get_latest_signal`.
- `financial report FPT` must use FA tools only: `get_latest_financial_report`, `get_financial_metrics`, or `get_financial_report_summary`.
- `compare backtest strategies FPT` must use persisted backtest lookup, especially `get_backtest_strategy_comparison`.
- Backtest readiness must not expose or call live Backtrader execution.

## Backend demo commands

Start backend on the default demo port:

```bat
python scripts\run_questdb_agent_backend.py --host 127.0.0.1 --port 8010
```

Or use an isolated test port:

```bat
python scripts\run_questdb_agent_backend.py --host 127.0.0.1 --port 8014
```

Smoke test:

```bat
python scripts\smoke_questdb_agent_backend.py --api-url http://127.0.0.1:8014
```

Endpoint checks:

```bat
curl.exe -s http://127.0.0.1:8014/market/summary/FPT
curl.exe -s http://127.0.0.1:8014/features/latest/FPT
curl.exe -s http://127.0.0.1:8014/signals/latest/FPT
curl.exe -s http://127.0.0.1:8014/backtest/comparison/FPT
curl.exe -s http://127.0.0.1:8014/backtest/latest/FPT
curl.exe -s "http://127.0.0.1:8014/backtest/equity/FPT/ma20_ma50?limit=20"
curl.exe -s http://127.0.0.1:8014/v1/models
```

Agent examples:

```bat
python scripts\demo_agent_backend_cli.py "summary FPT"
python scripts\demo_agent_backend_cli.py "financial report FPT"
python scripts\demo_agent_backend_cli.py "summary 1 month events and financial report from FPT"
python scripts\demo_agent_backend_cli.py "compare backtest strategies FPT"
```

DeepAgents examples, only after `check_deepagents_env.py --live` passes:

```bat
python scripts\demo_deepagents_questdb_cli.py "summary FPT"
python scripts\demo_deepagents_questdb_cli.py "financial report FPT"
python scripts\demo_deepagents_questdb_cli.py "compare backtest strategies FPT"
```

## Fix stale OpenAI environment

Do not print or commit API keys.

If DeepAgents returns HTTP 401 invalid key:

1. Stop the backend process that was started with the stale environment.
2. Open a new terminal in the correct `vsf-trading` conda environment.
3. Set credentials in that terminal only:

   ```bat
   set OPENAI_API_KEY=<your key>
   set VSF_DEEPAGENTS_MODEL=gpt-4.1-mini
   ```

4. Verify without printing the key:

   ```bat
   python scripts\check_deepagents_env.py
   python scripts\check_deepagents_env.py --live
   ```

5. Rerun DeepAgents CLI or restart the backend from the same terminal.

## Caveats to state in the demo

- Adjusted OHLC source remains unverified; current backtests are research-only.
- FA metric mapping is still `metric_mapping_unverified`.
- Event/news ingestion is not implemented yet.
- Backtest `slippage_bps` is currently `0`; slippage is not modeled.
- `backtest_trades` exists but trade-level extraction is TODO.
- This is not real-money investment advice.
