# Mentor status report

## 2026-06-28 update — Zero-fact classification + bounded FA resume

Three semantic bugs in the full-universe ingester were fixed:

1. **Zero-facts counted as consecutive failures.** `http=200, verified, zero rows` symbols (ETFs, warrants, derivatives) were inflating the consecutive-failure counter, triggering premature stops. Now classified as `zero_fact` and excluded from consecutive-failure tracking by default. New flag `--count-zero-facts-as-failure` to include if needed.

2. **Per-section zero-fact tracking inflated counts.** Each section's empty result was tracked independently, doubling/tripling the zero_fact count for symbols with 2-4 empty sections. Fixed: symbol-level total rows across all sections determines classification (zero_fact / partial / covered).

3. **Parser exceptions crashed the loop.** Invalid/empty JSON payloads caused a hard crash. Wrapped `parse_payload()` in try/except — parser errors are now classified as HTTP failures and recorded, loop continues.

Also added:
- `--cooldown-after-http-failures N`: sleep cooldown-seconds after N consecutive HTTP 503/429 failures (resets counter after cooldown).
- `scripts/inspect_fa_missing_universe.py`: read-only failure-pattern inspector reporting attempted_http_fail, attempted_zero_facts, pending_never_attempted, likely_no_fa_heuristic, next symbols to process.
- Summary JSON now includes: `zero_facts_this_pass`, `http_failures_this_pass`, `rate_limit_failures_this_pass`, `zero_facts_samples`, `resume_command`.

Coverage jumped significantly from bounded passes:

| Table | Symbols (before) | Symbols (after) |
|---|---|---|
| fa_balance_sheet | 495 | 639 |
| fa_income_statement | 471 | 635 |
| fa_cash_flow | 471 | 635 |
| fa_notes | 465 | 627 |
| all_four | 486 | 627 |

Remaining globally: 929 (down from ~1,091). HTTP 503 rate-limits on ETF/fund symbols (FUE*, E1VFVN30, BMK*, BHH*, etc.) are the dominant failure pattern — these are legitimate non-FA instruments. Pending_real ≈ 1,113 non-attempted symbols still include real stocks.

All six important symbols return `status=ok domain=financial_report` via FastAPI demo.

Exact resume command:

```bat
python scripts\batch_ingest_vietcap_fa_full_universe.py --run-id FA_FULL_UNIVERSE_20260626 --only-missing --resume --sleep-seconds 1 --jitter-seconds 0.5 --stop-on-rate-limit --max-consecutive-failures 20 --cooldown-after-http-failures 10 --write-summary-json data\cache\fa_full_universe_20260626_summary.json
```

Full-universe ingest remains `in_progress`; run-scoped tools continue using `FA_SMOKE_VHM_FPT_20260626` as latest complete.

## 2026-06-26 update — Full-universe Vietcap FA coverage workflow

A resumable, low-concurrency full-universe FA ingester
(`scripts/batch_ingest_vietcap_fa_full_universe.py`) is now implemented and
ran for its first pass. Reuses the verified single-symbol helpers in
`scripts/ingest_vietcap_financial_reports_to_questdb.py`; writes only to the
existing FA tables; never drops/recreates market/OHLCV/backtest tables.

- Smoke (`FA_SMOKE_VHM_FPT_20260626`): VHM and FPT, 0 failures, status
  `complete`. VHM went from 0 → 13,571 balance-sheet rows.
- Full-universe resume (`FA_FULL_UNIVERSE_20260626`): status `in_progress`.
  Coverage progressed 53 → 54 (smoke) → 627 (all4 symbols) after bounded resumes.
  Selection bug found and fixed (`--only-missing --resume` was using an `elif`
  chain that ignored `--only-missing`; replaced with set-intersection filter
  combination). All six important symbols (FPT/VHM/VCB/VNM/CTG/HPG) now return
  `status=ok`. FA feature snapshot
  layer: builder now writes successfully (header fix + post-write
  verification); `fa_feature_snapshots` has rows for 53 source-backed symbols
  from `20260624T044856Z`. `total_assets` is intentionally NOT emitted
  (consensus mapping has no `total_assets` code yet).
- Coverage endpoint: `GET /api/demo/fa/coverage` returns the same structure as
  `scripts/questdb_fa_coverage.py` (PASS/WARN/FAIL, per-table counts, important
  symbols, latest run id, top missing symbols).
- FA quality gate: `scripts/run_fa_quality_gates.py` (WARN expected while
  coverage is partial; mapping-partial is WARN, not FAIL).
- FA feature layer: `scripts/inspect_fa_feature_candidates.py` reports
  revenue, net profit, equity, operating cash flow as READY (4/5). A safe
  builder `scripts/build_fa_feature_snapshots.py` is provided; it never
  invents metric names and only writes features whose source codes are
  consensus-mapped.
- Overnight runners: `scripts/run_overnight_vietcap_fa_ingest.{bat,ps1}` run
  with `--only-missing --resume`, sleep 2s + jitter 1s, stop on rate-limit,
  no secrets.

Important-symbol status (all covered as of 2026-06-28):

- FPT, VCB, VNM, VHM, CTG, HPG: all covered.

Exact resume command:

```bat
python scripts\batch_ingest_vietcap_fa_full_universe.py --run-id FA_FULL_UNIVERSE_20260626 --only-missing --resume --sleep-seconds 1 --jitter-seconds 0.5 --stop-on-rate-limit --max-consecutive-failures 20 --cooldown-after-http-failures 10 --write-summary-json data\cache\fa_full_universe_20260626_summary.json
```

Caveats (unchanged, surfaced honestly in every response):

- Adjusted OHLC source still unverified/raw-equivalent.
- FA metric mapping still partial.
- Slippage is a simple bps model, not market-impact.
- "Complete" only flips to true once every universe symbol has been attempted.

## 2026-06-26 update — SimpleEngine logic lab (deterministic, transparent)

Adds a third layer to the existing SimpleEngine: a fully explicit `engine_logic`
dict (data source, price input, signal, execution, sizing, commission, slippage,
metrics, divergences vs Backtrader) and a deterministic variant / sensitivity
lab `run_variants(...)` with nine rows (raw vs adjusted, next-open vs same-close,
95% vs 100% capital, 0/5/10/15 bps slippage, volume filter, RSI(14) mean
reversion). Exposed in the FastAPI demo console at:

- `GET /api/demo/backtest/{symbol}/simple-engine/logic` — explicit assumptions block.
- `GET /api/demo/backtest/{symbol}/simple-engine/variants` — variant lab with
  per-row narrative.
- The main `/simple-engine` response also embeds the same `logic` block.

The lab is a sensitivity / ablation tool, not a strategy search. No live
Backtrader is executed in the agent runtime. FA full-universe ingestion remains
a planned follow-up and is intentionally not part of this commit.

## 2026-06-25 update — FastAPI demo console + transparent execution stack

This update addresses the mentor's demo feedback. Nothing below mutated market/FA/
backtest tables; everything added is read-only or additive.

- **Demo is now FastAPI menu-driven, not command-driven.** Start once and open the
  browser console:

  ```bat
  uv run python scripts\run_fastapi_demo_app.py --host 127.0.0.1 --port 8010
  :: then open http://127.0.0.1:8010/demo
  ```

  `/demo` replaces the long sequence of terminal commands with buttons: system status,
  validation gates, mentor readiness, market summary, financial report, backtest
  comparison, slippage scenarios, official disclosure (FPT), event guardrail (VNM),
  pipeline-trace examples, query benchmark, and next recommended actions. The old
  stdlib backend and CLIs still work. All 13 demo GET endpoints + `POST /api/demo/ask`
  + `POST /v1/chat/completions` verified `200`/valid JSON; `/demo` returns HTML.

- **Every demo action returns an anti-blackbox trace.** It shows the pipeline position
  (`source → … → agent_answer`), the RouterAgent + the active domain agent
  (MarketDataAgent / FinancialReportAgent / BacktestAgent / EventNewsAgent / …), each
  agent's decision and concise reason, the allowed vs rejected tools, the tool calls,
  caveats, the final basis (source + query_mode + tables), and the next action. No
  hidden chain-of-thought is exposed. Backtest answers reject live-Backtrader tools;
  event/news for VNM returns `unavailable` (no OHLCV proxy). See
  `docs/agent_architecture/anti_blackbox_pipeline_trace.md`.

- **Transparent SimpleEngine added to explain backtest logic.**
  `src/trading_agent/backtest/simple_engine.py` re-implements MA20/MA50 in explicit
  Python (next-bar-open fills, 0.95 target, 0.1% commission, bps slippage). On FPT @
  0 bps it reproduces the persisted Backtrader run almost exactly — final value
  392.30M vs 392.52M, total return 292.30% vs 292.52%, max drawdown 22.18% vs 22.14%,
  **trades 12 = 12, win rate 58.33% = 58.33%**. Only Sharpe differs (1.23 vs 0.90),
  due to differing Sharpe definitions — exactly the black-box detail this makes
  explicit. See `docs/backtest/simple_engine_explainer.md`. It does not replace the
  persisted Backtrader results.

- **QuestDB query-speed issue diagnosed.** The demoed ~72ms was client/connection/JSON
  overhead, not the engine: server-side `execute` for a filtered query is ~0.0–0.3ms.
  The dominant cost was **`localhost` on Windows** paying a ~2s IPv6 (`::1`) connect
  fallback per fresh connection. Fix: normalize a literal `localhost` host to
  `127.0.0.1` (`to_ipv4_localhost`). Measured: localhost p50 2049ms → 127.0.0.1 p50
  18ms per fresh connection. **Use `127.0.0.1`, not `localhost`, on Windows demo
  machines.** See `docs/performance/questdb_query_benchmark.md` and
  `docs/operations/questdb_connection_modes.md`.

- **PGWire via psycopg is available and benchmarked.** A direct PGWire path
  (`questdb_pgwire_client`, default `127.0.0.1:8812`, admin/quest/qdb) sits alongside
  REST, selectable via `QUESTDB_QUERY_MODE=rest|pgwire`. Warm 50-repeat benchmark:
  REST p50 ≈ 1.38ms, PGWire p50 ≈ 1.08ms (PGWire ~22% faster for repeated reads).
  REST stays default and keeps `/imp` for CSV ingestion.

- **uv setup added (preferred); conda remains fallback.** `pyproject.toml`, `uv.lock`
  (100 packages, pinned), `.python-version`. Verified: `uv sync` then `uv run python`
  imports the FastAPI app (27 routes). Core group = fastapi/uvicorn/psycopg/httpx;
  `research`/`deepagents`/`dev` extras are opt-in. See `docs/operations/uv_setup.md`.

- **Docker now uses uv.** Lean 333MB image (`python:3.11-slim` + pinned uv binary,
  installs from the lockfile, serves the FastAPI console). `docker compose config` is
  clean (no `sk-` keys), `docker build` passes, and
  `docker compose -f docker-compose.backend-local.yml up --build -d` serves `/health`,
  `/demo`, `/api/demo/status` and `/api/demo/backtest/FPT` against host QuestDB. See
  `docs/operations/docker_uv_setup.md`.

- **Remaining caveats (unchanged, surfaced honestly in every response):** adjusted OHLC
  source still unverified/raw-equivalent; FA metric mapping partial; event/news scope
  narrow (FPT only; VNM/HPG return unavailable); slippage is a simple bps model, not
  market-impact; SimpleEngine is an explainability baseline, not yet a production
  engine. Fast next-action probes still report `WARN` across these four areas.

---

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
