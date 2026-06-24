# Mentor status report

## Completed

- QuestDB market layer is loaded:
  - `daily_prices`: about 4.38M rows / 1,556 symbols;
  - `securities`: 1,556 symbols;
  - `feature_snapshots` and `signals`: parity with `daily_prices`.
- Adjusted OHLC audit was completed and the caveat is retained: adjusted OHLC source remains unverified.
- Vietcap financial report tables exist and smoke ingest succeeded for FPT/VNM/VCB:
  - `fa_balance_sheet`, `fa_income_statement`, `fa_cash_flow`, `fa_notes`;
  - `fa_raw_payloads` and `fa_ingest_runs` preserve run/source evidence.
- FA ingestion is run-scoped, with latest-complete-run lookup to avoid duplicate append rows in tools.
- DeepAgents routing bug is fixed:
  - market summary uses market tools only;
  - financial report uses FA tools only;
  - backtest queries use persisted backtest lookup only;
  - event/news remains unsupported instead of using OHLCV as a proxy.
- DeepAgents architecture and guardrails are documented.
- Backtrader research notebook and runner exist with three strategies:
  - buy-and-hold;
  - MA20/MA50 crossover;
  - RSI mean reversion.
- Persisted backtest result tables exist:
  - `backtest_runs`, `backtest_metrics`, `backtest_equity_curve`, `backtest_trades`.
- `backtest_trades` is now populated for closed trade events on demo strategies.
- Backtest runs now record commission, slippage bps, and price-band guard status.
- Docker packaging has been added for a backend + QuestDB demo stack.
- Batch/cron operation notes are documented.

## Remaining work

- Run full FA universe or VN100 scope after mentor approval.
- Add event/news ingestion and tools.
- Replace the current simple execution model with a stronger slippage/liquidity model.
- Validate adjusted OHLC against corporate-action or vendor adjustment evidence.
- Confirm exchange metadata for demo symbols so price-band checks can pass instead of remaining `exchange_unknown_price_band_guard_not_fully_verified`.
- Move batch jobs from local/manual commands into production scheduling.

## Exact demo commands

Readiness:

```bat
python scripts\run_mentor_demo_readiness.py --deepagents
```

Start backend:

```bat
python scripts\run_questdb_agent_backend.py --host 127.0.0.1 --port 8010
```

Market summary:

```bat
python scripts\demo_agent_backend_cli.py "summary FPT"
python scripts\demo_deepagents_questdb_cli.py "summary FPT"
```

Financial report:

```bat
python scripts\demo_agent_backend_cli.py "financial report FPT"
python scripts\demo_deepagents_questdb_cli.py "financial report FPT"
```

Persisted backtest comparison:

```bat
python scripts\demo_agent_backend_cli.py "compare backtest strategies FPT"
python scripts\demo_deepagents_questdb_cli.py "compare backtest strategies FPT"
```

Event/news guardrail:

```bat
python scripts\demo_agent_backend_cli.py "summary 1 month events and financial report from FPT"
python scripts\demo_deepagents_questdb_cli.py "summary 1 month events and financial report from FPT"
```

Backtest status:

```bat
python scripts\questdb_backtest_status.py
```

## Short message to mentor

The local QuestDB-backed demo is ready for a controlled walkthrough. Market summaries, financial-report lookup, event/news guardrails, and persisted Backtrader results are all available through rule-based agent, backend, and guarded DeepAgents routing. Backtests are read-only persisted lookups in the agent; DeepAgents does not run live Backtrader. Remaining caveats are explicit: adjusted OHLC source is unverified, FA metric mapping is unverified, event/news ingestion is not implemented, and price-band checks are conservative until exchange metadata is filled.
