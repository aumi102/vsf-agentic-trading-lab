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
- FA metric mapping has a source-backed partial mapping table:
  - `fa_metric_mapping`: 1,957 rows;
  - consensus mapping coverage by statement ranges from 69.2% to 92.7% of distinct metric codes in the current FA fact tables;
  - tools enrich metric names only where consensus mappings exist.
- DeepAgents routing bug is fixed:
  - market summary uses market tools only;
  - financial report uses FA tools only;
  - backtest queries use persisted backtest lookup only;
  - event/news uses official disclosure records when available and never uses OHLCV as a proxy.
- DeepAgents architecture and guardrails are documented.
- Backtrader research notebook and runner exist with three strategies:
  - buy-and-hold;
  - MA20/MA50 crossover;
  - RSI mean reversion.
- Persisted backtest result tables exist:
  - `backtest_runs`, `backtest_metrics`, `backtest_equity_curve`, `backtest_trades`.
- `backtest_trades` is now populated for closed trade events on demo strategies.
- Backtest runs now record commission, slippage bps, and price-band guard status.
- Exchange metadata is now source-backed for all current `securities` rows from captured Vietcap IQ universe and HOSE listed-universe dry-run evidence:
  - 1,556/1,556 symbols covered;
  - no conflicts detected in the generated override file.
- Demo backtest `price_band_status` now passes across all persisted slippage scenarios: `price_band_guard_pass`.
- Slippage scenarios are persisted for FPT/VNM/HPG:
  - scenarios: 0, 5, 10, 15 bps;
  - `backtest_runs`: 36;
  - `backtest_metrics`: 36;
  - `backtest_equity_curve`: 53,964;
  - `backtest_trades`: 400.
- Minimal event/news layer exists for official disclosure records:
  - source probe parsed 22 official disclosure records;
  - QuestDB event layer loaded 20 FPT disclosure rows;
  - VNM/HPG still return unavailable until symbol-level event records are sourced.
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
  - exchange metadata coverage and price-band mapping;
  - FA table coverage;
  - backtest table coverage;
  - official-disclosure event layer guardrail;
  - agent guardrails;
  - Docker packaging.
- Expected warning gates:
  - adjusted OHLC source is still unverified/equal to raw;
  - FA metric-code mapping is partial rather than complete;
  - default backtest comparison still uses the simple `slippage_bps=0` scenario.

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

## Current hardening snapshot

- Adjusted OHLC audit:
  - internal factor consistency: PASS;
  - raw-equivalent ratio: 100% for audited samples;
  - source verification: WARN because no corporate-action/vendor adjustment evidence has been attached.
- FA mapping:
  - table loaded: `fa_metric_mapping`;
  - consensus rows: 1,858;
  - conflict rows retained for audit: 99;
  - FA fact tables remain untouched.
- Event/news:
  - official disclosure probe succeeded for FPT company IR;
  - HOSE/HNX parent pages are not reliable structured sources yet;
  - event/news remains source-scoped, not broad market news.
- Exchange metadata:
  - generated override rows: 1,556;
  - QuestDB symbols found/updated: 1,556;
  - conflicts skipped: 0.

## Remaining work

- Run full FA universe or a verified VN100 scope after mentor approval.
- Add broader event/news/disclosure sources beyond FPT official disclosure records.
- Replace the current simple execution model with a stronger slippage/liquidity/market-impact model.
- Validate adjusted OHLC against corporate-action or vendor adjustment evidence.
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

Official disclosure event lookup:

```bat
python scripts\demo_agent_backend_cli.py "latest news FPT"
python scripts\demo_deepagents_questdb_cli.py "latest news FPT"
```

Backtest status:

```bat
python scripts\questdb_backtest_status.py
curl.exe -s http://127.0.0.1:8010/backtest/slippage-scenarios/FPT
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

The local QuestDB-backed demo is ready for a controlled walkthrough. Market summaries, financial-report lookup, official-disclosure event lookup, and persisted Backtrader results are available through rule-based agent, backend, and guarded DeepAgents routing. FA coverage has expanded from 3 smoke symbols to a controlled 53-symbol run with zero failures. Exchange metadata is source-backed for all 1,556 current securities, so price-band checks pass across the persisted 0/5/10/15 bps slippage scenarios. Validation gates still report WARN with no blocking failures because adjusted OHLC source validation, FA metric mapping completeness, broader event/news coverage, and the simple execution model remain open.
