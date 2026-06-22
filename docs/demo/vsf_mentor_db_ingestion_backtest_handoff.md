---
title: vsf_mentor_db_ingestion_backtest_handoff
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# VSF Agentic Trading Lab - Mentor Handoff

## 1. Current Completed Milestone

The repo has completed the DB and ingestion readiness milestone for a local
agent/tool demo. Completed pieces are:

- SQLite MVP DB/tool demo for FPT, VNM, and VCB.
- Deterministic orchestrator and mentor demo suite.
- Cached OHLCV ingestion from saved payloads.
- Controlled live OHLCV adapter gated by explicit `--allow-network`.
- Successful one-symbol live smoke recorded in docs.
- Ingestion observability/status tool for runs, payloads, watermarks, lineage,
  freshness, and tool readiness.
- Production ingestion dry-run control plan with allowlist, batch cap,
  countBack, rate-limit, and retention checks.

## 2. Validated Commands

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
python scripts/run_ohlcv_ingestion.py --symbols FPT,VNM,VCB --mode cached
python scripts/run_ingestion_status.py --symbols FPT,VNM,VCB
python scripts/check_adjusted_ohlc_readiness.py --symbols FPT,VNM,VCB
python scripts/smoke_adjusted_price_evidence_pipeline.py
python scripts/plan_live_ingestion_run.py --symbols FPT,VNM,VCB
python scripts/run_mentor_demo_suite.py
```

Expected result: the DB build and cached ingestion succeed, ingestion status
returns `ok`, the adjusted-price evidence smoke returns `ok` against a
temporary local DB, the production ingestion planner returns `ok` without
network or DB mutation, and the mentor suite passes.

## 3. Current DB/Ingestion Architecture

The ingestion path keeps raw evidence separate from canonical tables. Raw
payloads remain under ignored `data/raw/...` paths and are referenced by
`raw_source_payloads`. Each ingestion run records `source_runs`, per-symbol
payload metadata, and `ingestion_watermarks`. Parsed data refreshes
`daily_prices`, then derives `feature_snapshots` and `signals`.

`run_ingestion_status.py` is read-only and checks source runs, raw lineage,
watermarks, freshness, row counts, and tool readiness. `plan_live_ingestion_run.py`
is also dry-run only; it validates allowlists and policy before any future live
run, scheduler, or larger ingestion.

## 4. Mentor Backtest Requirement

Mentor direction on 2026-06-18:

- Use Backtrader.
- Keep strategies simple.
- Use FA scanning to filter stocks.
- Use TA rules-based strategies.
- Optimize parameters by Sharpe Ratio.
- Use the current VN100 list for the MVP universe.
- Run about 5-10 strategy templates.
- Select one strategy per ticker.
- The selected strategy must have the highest Sharpe Ratio among candidates and
  must beat the ticker's buy-and-hold benchmark.

## 5. Adjusted OHLC Requirement

Adjusted price is mandatory for backtests. Do not use adjusted close alone while
leaving open, high, and low unadjusted. The ingestion/backtest layer must compute
or ingest an adjustment factor from dividend, split, and corporate action logic,
then adjust all OHLC fields consistently.

```text
adjust_factor = adjusted_close / close
adjusted_open = open * adjust_factor
adjusted_high = high * adjust_factor
adjusted_low = low * adjust_factor
adjusted_close = close * adjust_factor
```

Raw and adjusted columns must be clearly separated. Backtests must use adjusted
OHLC. Unadjusted prices may be retained only as raw evidence. If adjusted close
is unavailable, the factor must be derived from dividend/split events before
backtest hardening.

Current implementation status: adjusted OHLC schema slots and a readiness gate
exist, but the gap-chart demo data is expected to be `not_ready` because
adjusted columns are still empty. Backtrader VN100 runs remain blocked until
those fields are populated and validated. A source review and pure adjustment
factor record interface have been added, but no source path is wired for ETL
population yet. A dry-run source probe now plans small-symbol evidence checks and
can inspect local JSON payloads without network or DB mutation. Probe evidence
is candidate-level only and does not yet make a source usable. Local evidence
capture can record payload hashes for review, but still does not validate ETL
population. A local factor-application foundation can apply reviewed factor
records to explicit demo DB symbols and run readiness validation; it still does
not discover factors or fetch live data. Adjustment factor provenance is stored
separately from raw OHLC source lineage. A fixture-only source-adapter contract
now proves that adjusted-close or corporate-action payload parsers can produce
factor records compatible with local application, but no live source is wired
yet. A controlled, no-network verification layer
(`docs/data_platform/controlled_factor_source_verification.md`) reuses that
adapter to confirm a local payload yields usable factor records on a small
explicit symbol set before any ETL adjusted-OHLC population. PR #37 created
that controlled local verification layer. The adjusted-price policy is now
confirmed: current VN100 list, adjusted price mandatory, full OHLC adjustment,
dividend/split factor logic, project-researched transaction cost, and slippage
bounded by HSX/HOSE +/-7% and UPCoM +/-15%. See
`docs/data_platform/confirmed_adjusted_price_policy.md` and
`docs/demo/mentor_adjustment_factor_source_questions.md`. The local adjusted
price evidence pipeline now verifies payload evidence, writes factor records,
can explicitly apply them to a local DB, and runs readiness for FPT/VNM/VCB.
A synthetic local smoke/runbook now exercises that path with temporary payload
and DB artifacts before any reviewed real evidence or production adjusted OHLC
population. Reviewed adjusted-price evidence intake now accepts local JSON/CSV
files only after source, raw path, reviewer, review timestamp, and evidence
basis metadata are present and the payload SHA-256 matches the manifest.
Reviewed evidence package QA now checks a full synthetic package shape with
JSON, CSV, temporary execute, and readiness before real reviewed evidence is
used. The real evidence onboarding workflow keeps manually obtained evidence and
generated QA reports in ignored local paths while creating SHA-256 manifests for
review. The dry-run report workflow converts validation JSON into a
human-readable checklist before any execute-mode DB population. The local
execute-readiness workflow can then apply the package only to an explicit
temporary/local SQLite DB and write readiness reports. If package validation
fails before DB mutation, readiness is skipped rather than inferred from
unrelated DB state. The next inspection layer is an adjusted OHLC execution
audit before any Backtrader work. That audit is read-only and checks adjusted
row population, factor provenance, factor consistency, validation status, and
readiness status. Strict audit mode requires factor records, validation report,
and readiness report; raw OHLC unchanged is independently verified only when a
raw baseline is supplied. The feed contract then maps adjusted OHLC into preview
`open/high/low/close` fields for FPT/VNM/VCB planning only; it still does not
implement Backtrader or strategies. That feed preview is hardened: it requires a
strict adjusted OHLC execution audit whose metadata (evidence mode, required
evidence, unadjusted rows, readiness/validation/backtest gates, mutation flag,
covered symbols, and DB path) matches the current request, requires every
requested symbol to have eligible adjusted rows, and validates date and
`max_rows` inputs instead of silently correcting them. Raw OHLC stays
diagnostics-only and is never exposed as a trading price. A dry-run preparation
layer (`docs/backtest/adjusted_ohlc_feed_to_backtest_dry_run.md`) then converts
that feed preview into a backtest input contract for a research dry-run,
validating the adjusted feed plus explicit transaction-cost and slippage
assumptions and encoding the slippage bands (HOSE/HSX +/-7%, UPCoM +/-15%). It is
preparation only and still does not implement Backtrader, optimize a strategy,
run full VN100, or give investment advice. A fixture signal dry-run layer
(`docs/backtest/adjusted_ohlc_fixture_signal_dry_run.md`) then consumes that
preparation JSON and emits a tiny deterministic fixture signal preview (default
all-cash `NO_POSITION`, optional synthetic alternating flag). It is fixture
signal preview only: not a real strategy, not Backtrader, not an optimizer, not
full VN100, with no performance metrics by default and no investment advice. A
fixture metrics report layer
(`docs/backtest/adjusted_ohlc_fixture_metrics_report.md`) then consumes that
fixture signal output and produces deterministic, clearly fixture-labeled
diagnostic metrics (counts, dates, no-position ratio). It is fixture diagnostics
only: not strategy performance, not Backtrader, not an optimizer, not full VN100,
not investment advice, and it intentionally avoids Sharpe/Sortino/Profit
Factor/Max Drawdown/PnL/equity curve. The next step after it is mentor review
before any real adjusted-basis engine integration.

## 6. Proposed Backtrader Pipeline

Current VN100 -> FA scan/filter -> prepare adjusted OHLCV feed -> run 5-10 TA
strategy templates -> grid-search parameters -> compute Sharpe and buy-and-hold
benchmark -> select best strategy per ticker -> output per-ticker strategy
report -> later expose selected strategy to agent/tooling.

## 7. Candidate Simple Strategy Templates

| Template | Idea | Tunable params | Caveat |
|---|---|---|---|
| SMA crossover | Trade trend when fast SMA crosses slow SMA | fast, slow | Whipsaws in sideways markets |
| EMA crossover | Faster trend response than SMA | fast, slow | More noise-sensitive |
| RSI mean reversion | Buy oversold, exit overbought | period, low, high | Can fail in strong trends |
| MACD trend | Follow MACD/signal confirmation | fast, slow, signal | Lagging confirmation |
| Bollinger mean reversion | Buy lower-band weakness, exit mid/upper band | period, stdev | Breakouts can continue |
| Donchian breakout | Buy range breakout | lookback, exit lookback | False breakouts |
| Momentum / ROC | Rank or trade positive momentum | period, threshold | Reversal risk |
| ATR stop trend | Trend entry with volatility stop | MA period, ATR period, multiplier | Stop calibration risk |
| Volume breakout | Confirm price move with volume expansion | price lookback, volume multiple | Volume data quality risk |
| MA + RSI filter | Trend plus momentum filter | MA period, RSI period, thresholds | More parameters can overfit |

## 8. FA Scanning Plan

Proposed filters, pending final mentor review: current VN100 membership,
liquidity, market cap, revenue/profit growth, ROE, debt/equity, valuation
sanity, sector exclusion if needed, and data availability. The FA scan should
reduce the candidate set before TA backtests run.

## 9. Backtest Guardrails To Avoid Bugs

- No look-ahead bias.
- Adjusted OHLC only.
- Corporate action handling before hardening.
- Current VN100 introduces survivorship caveat.
- Transaction cost must be researched and proposed.
- Slippage must be reasonable and bounded by daily price bands: HSX +/-7%,
  UPCOM +/-15%.
- Buy-and-hold benchmark must use the same adjusted feed.
- Parameter overfitting risk must be disclosed.
- Train/test split or walk-forward validation should come later.
- Missing data handling must be explicit.
- One selected strategy per ticker.
- No investment advice.

## 10. ETL Dockerization and Scheduling Plan

Dockerize stable ETL/DB/status/control components first. Do not Dockerize the
experimental Backtrader optimizer yet.

The ETL container should support run-once mode, scheduled mode, configured
symbol lists, configured mode (`cached` or gated `live`), rate-limit policy, raw
retention policy, logs, and status output. Scheduling should ingest new data
automatically only with guardrails. Do not run a full-universe crawl without
batch and rate controls.

## 11. Current Boundaries

- No production readiness claim.
- No live trading.
- No broker execution.
- No QuestDB yet.
- No scheduler is enabled until the stable ETL Docker foundation is reviewed.
- No financial advice.

## 12. Next Implementation Steps

1. Place manually obtained FPT/VNM/VCB adjusted-price evidence under the ignored onboarding path.
2. Generate a SHA-256 manifest, validation JSON, and dry-run Markdown report for that package.
3. Use explicit local execute readiness only after reviewed local evidence and the report pass inspection.
4. Audit adjusted OHLC execution outputs in strict mode before considering backtest feed planning.
5. Review the adjusted OHLC backtest feed contract before implementing any Backtrader scaffold.
6. Add ETL Docker/scheduler foundation for stable ingestion only.
7. Add Backtrader research scaffold over a small subset after adjusted readiness passes.
8. Produce VN100 strategy selection report.
9. Only then consider broader scheduler, QuestDB, or realtime work.
