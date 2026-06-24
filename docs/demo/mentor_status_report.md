# Mentor status report

## Completed

- QuestDB market layer is loaded:
  - `daily_prices`: about 4.38M rows / 1,556 symbols;
  - `securities`: 1,556 symbols;
  - `feature_snapshots` and `signals`: parity with `daily_prices`.
- Adjusted OHLC audit was completed and the caveat is retained: adjusted OHLC source remains unverified.
- Vietcap financial report tables exist and smoke ingest succeeded for FPT/VNM/VCB; run-scoped FA expansion now covers 53 symbols:
  - `fa_balance_sheet`, `fa_income_statement`, `fa_cash_flow`, `fa_notes`;
  - `fa_raw_payloads` and `fa_ingest_runs` preserve run/source evidence.
- FA ingestion is run-scoped, with latest-complete-run lookup to avoid duplicate append rows in tools.
- Latest complete FA run: `20260624T044856Z`, `symbols_processed=53`, `failure_count=0`.
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
- FPT/VNM/HPG exchange metadata is now filled as `HOSE` from captured Vietcap IQ universe and HOSE listed-universe dry-run evidence.
- Demo backtest `price_band_status` now passes: `price_band_guard_pass`.
- Docker packaging has been added for a backend + QuestDB demo stack.
- Docker build and backend-local runtime verification passed against host QuestDB.
- Validation gates were added for the full architecture path:
  `source -> raw capture -> bronze parser -> silver canonical table -> gold features -> signal -> backtest -> validation -> agent answer`.
- Batch/cron operation notes are documented.

## Current validation snapshot

- Validation command: `python scripts\run_validation_gates.py --write-report docs\demo\validation_gate_latest.md`
- Overall status: `WARN`, with no blocking failures.
- Passing gates:
  - market table coverage;
  - feature/signal parity;
  - exchange metadata for FPT/VNM/HPG;
  - FA table coverage;
  - backtest table coverage;
  - agent guardrails;
  - Docker packaging.
- Expected warning gates:
  - adjusted OHLC source is still unverified/equal to raw;
  - FA metric-code mapping remains unverified;
  - backtest execution assumptions still use `slippage_bps=0`.

## Current FA expansion snapshot

- Target used: `FPT,VNM,VCB` plus 50 candidate symbols from `configs/fa_universe_symbols.txt`.
- This is not a VN100 list; it is a controlled securities-derived FA preflight universe.
- Latest complete run: `20260624T044856Z`.
- Symbols processed: 53.
- Failures: 0.
- Current FA row counts:
  - `fa_balance_sheet`: 862,586 rows / 53 symbols;
  - `fa_income_statement`: 474,039 rows / 53 symbols;
  - `fa_cash_flow`: 581,400 rows / 53 symbols;
  - `fa_notes`: 557,427 rows / 53 symbols;
  - `fa_raw_payloads`: 304 rows / 53 symbols.

## Docker snapshot

- `docker compose config`: PASS, no API key interpolation printed.
- `docker build -t vsf-agent-backend:demo .`: PASS.
- `docker compose -f docker-compose.backend-local.yml up --build -d`: PASS.
- Verified container endpoints against host QuestDB:
  - `/health`;
  - `/market/summary/FPT`;
  - `/backtest/comparison/FPT`;
  - `/v1/models`.
- The default image is backend-lean. Optional live DeepAgents fallback dependencies can be installed with:

```bat
docker build --build-arg INSTALL_DEEPAGENTS=true -t vsf-agent-backend:demo-deepagents .
```

## Remaining work

- Run full FA universe or a verified VN100 scope after mentor approval.
- Add event/news ingestion and tools.
- Replace the current simple execution model with a stronger slippage/liquidity model.
- Validate adjusted OHLC against corporate-action or vendor adjustment evidence.
- Extend source-backed exchange metadata beyond the demo symbols if broader price-band validation is needed.
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

Exchange metadata update/check:

```bat
python scripts\update_questdb_exchange_metadata.py
python scripts\check_price_band_guard.py --symbols FPT,VNM,HPG --slippage-bps 10
```

Validation gates:

```bat
python scripts\run_validation_gates.py
python scripts\run_validation_gates.py --write-report docs\demo\validation_gate_latest.md
```

Docker backend against local QuestDB:

```bat
docker compose -f docker-compose.backend-local.yml up --build
curl.exe -s http://127.0.0.1:8010/health
curl.exe -s http://127.0.0.1:8010/market/summary/FPT
curl.exe -s http://127.0.0.1:8010/backtest/comparison/FPT
```

## Short message to mentor

The local QuestDB-backed demo is ready for a controlled walkthrough. Market summaries, financial-report lookup, event/news guardrails, and persisted Backtrader results are available through rule-based agent, backend, and guarded DeepAgents routing. FA coverage has expanded from 3 smoke symbols to a controlled 53-symbol run with zero failures. FPT/VNM/HPG exchange metadata is source-backed as HOSE, so demo backtest price-band checks now pass. Validation gates still report WARN with no blocking failures because adjusted OHLC source validation, FA metric mapping, event/news ingestion, and the simple zero-slippage assumption remain open.
