---
title: progress_report
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Progress Report — Autonomous Trading Agent

**Phase:** Source discovery plus local MVP DB/tool demo foundation.
No production DB write, no production backtest, no broker execution.

---

## Current Status

| Area | Status |
|---|---|
| Vietcap IQ universe | 2,080 rows; 1,598 listed-market candidates (HOSE/HNX/UPCOM) |
| OHLCV gap-chart | FPT/VNM/VCB confirmed HTTP 200; parser dry-run: 14,079 rows |
| Controlled fetcher | Tiny execute passed for FPT/VNM/VCB; full-universe fetch not approved |
| FA endpoint | HTTP 200 (clean 8-header profile); BS/IS/CF confirmed for VCI and FPT |
| FA parser | Dry-run complete; 7 validation checks; `--strict` mode; deterministic sort |
| FA mapping integration | Option C resolver wired; Mode B active for general symbols; 53,013 rows validated; 0 errors |
| FA mapping coverage gap probe | 3 general/fund symbols probed; union: 7 payloads, all known groups sampled; BS 89.7% / IS 94.5% / CF 87.6%; gap appears structural |
| FA `publicDate` PIT spot-check | 8-row CSV validator returns `pit_supported_small_sample`; 8/8 statement rows credible; 4/4 unique official disclosure events credible; 2 issuers; zero red flags |
| Official Disclosure Foundation v1 | Hardened+VCI: FPT IR 20 bounded records (pass), plus FY2025 audited FS in raw HTML; VCI FY2025 `2026-02-13` (pass); VCI Q1 2026 `2026-04-20` (pass); HOSE=js_app_shell; HNX=timeout. Honest UA; official disclosure fetches verify TLS; no pseudo rows. |
| MVP DB/tool demo | SQLite local store from saved gap-chart payloads; tools return latest market data, features, signal, risk, and Vietnamese answer. Demo symbols: FPT, VNM, VCB. |
| Agent tool orchestrator demo | Deterministic wrapper resolves a symbol, calls market/features/signal/risk/report tools, and returns a Vietnamese answer. No LLM, fetch, broker execution, or backtest. |
| Agent demo readiness | Scenario runner with `market_brief`, `risk_check`, `compare`. Structured result dict with tool-call trace, Vietnamese answer, caveats, `not_financial_advice=True`. CLI: `scripts/run_agent_demo.py`. |
| Mentor demo package | Runbook (`docs/demo/mentor_demo_runbook.md`), demo reports (`docs/reports/mentor_demo_report.md`, `docs/reports/backtest_mvp_demo_report.md`), and suite runner (`scripts/run_mentor_demo_suite.py`). Agent and Backtest MVP scenarios are included. Production hardening still blocked. |
| Mentor live demo package | Call-ready package under `docs/mentor/`: single index, Vin folder upload manifest, exact live-system runbook, backtest/strategy review agenda, strategy decision template, readiness checklist, current status, and mentor questions. `scripts/list_mentor_demo_package.py` reports file readiness without network or mutation. No strategy is finalized; no Backtrader, optimizer, full VN100, production-readiness, profitability, or investment-advice claim. |
| Final mentor handoff | Handoff note at `docs/demo/mentor_handoff_message.md`; awaiting mentor feedback before QuestDB/LLM/backtest hardening. |
| Post-demo acceptance | Mentor review checklist (`docs/demo/mentor_review_checklist.md`), post-demo technical roadmap (`docs/plans/post_demo_technical_roadmap.md`), current demo architecture (`docs/architecture/current_demo_architecture.md`). Awaiting mentor feedback on store, backtest, LLM timeline. |
| Data store decision | Decision matrix (`docs/plans/data_store_decision_matrix.md`); ADR-0001 (`docs/decisions/0001_local_sqlite_mvp_store.md`). Recommendation: keep SQLite for now; DuckDB when backtest needs columnar queries; QuestDB deferred until schema stable. |
| OHLCV ingestion foundation | Cached ingestion foundation records `source_runs`, per-run `raw_source_payloads`, and `ingestion_watermarks`; refreshes canonical prices/features/signals by symbol. |
| Controlled live OHLCV adapter | Vietcap IQ gap-chart adapter can run only with `--mode live --allow-network`, is capped at 3 explicit symbols, saves raw payloads before parsing, and reuses ingestion refresh. Docs: `docs/data_platform/live_ohlcv_adapter_foundation.md`, `docs/data_platform/live_ohlcv_smoke_report.md`, `docs/data_platform/live_ingestion_readiness_checklist.md`. No scheduler/full-universe crawl/QuestDB. |
| Ingestion observability status | Read-only status API/tool/CLI reports source runs, raw payloads, watermarks, lineage, freshness, and tool readiness. Docs: `docs/data_platform/ingestion_observability_status.md`. |
| Production ingestion control plan | Dry-run planner validates live symbol allowlist (non-empty, default subset), batch cap, countBack vs `max_count_back`, retention, scheduler-disabled, and manual-network-required policy before scheduler/full ingestion. No network or DB mutation. Mentor checklist: `docs/demo/mentor_ingestion_decision_checklist.md`. |
| Adjusted OHLC foundation | Nullable adjusted OHLC columns added to `daily_prices`; pure adjustment-factor/adjusted-OHLC validation helpers added. Current gap-chart ingestion leaves adjusted fields empty until a trusted adjusted close or dividend/split/corporate-action factor source is implemented. |
| Adjusted OHLC readiness gate | Read-only API/tool/CLI reports adjusted OHLC coverage, invalid factors, adjusted OHLC consistency, and backtest gate status. Current demo DB is expected `not_ready` until adjusted columns are populated. |
| Adjustment factor source foundation | Gap-chart source review records no tracked adjusted-close or corporate-action fields yet; pure factor record helpers require positive factors plus `source_id` and `raw_path`. ETL population is still blocked. |
| Adjusted factor source probe | Dry-run probe planner and local JSON inspector classify candidate adjusted close, factor, and corporate-action evidence on explicit small symbol sets. No network, DB mutation, or adjusted OHLC population by default. |
| Adjusted factor evidence capture | Local payload evidence capture records symbol/source/path, SHA-256 content hash, candidate evidence fields, and derivability status. No network, DB mutation, or adjusted OHLC population. |
| Local adjustment factor application | Dry-run-first module/CLI applies reviewed local factor records to adjusted OHLC columns for explicit symbols only. Execute mode mutates adjusted columns and separate factor provenance, not raw OHLC. No network, source discovery, full-universe mutation, or Backtrader. |
| Adjustment factor source adapter | Fixture-only parser interface converts synthetic adjusted-close or corporate-action payloads into provenance-backed factor records compatible with local factor application. No live source wired, no network, and no DB mutation. |
| Controlled factor source verification | PR #37 added no-network plan-only and local-payload verification that reuses the source adapter to confirm a payload yields usable, provenance-backed factor records on a small explicit symbol set. No live source wired, no full-universe crawl, no adjusted OHLC population, no DB mutation. |
| Confirmed adjusted price policy | Mentor confirmed: current VN100 list, adjusted price mandatory, full OHLC adjustment, dividend/split factor logic, project-researched transaction cost, and slippage bounded by HSX/HOSE +/-7% and UPCoM +/-15%. |
| Adjusted price evidence pipeline | Local-first pipeline verifies adjusted-price payload evidence, writes factor records, can explicitly apply to a local DB, and runs adjusted readiness for FPT/VNM/VCB. No live fetch, full universe, or Backtrader. |
| Adjusted price evidence smoke | Synthetic local smoke/runbook exercises FPT/VNM/VCB dry-run, execute against temporary SQLite, and adjusted readiness. No live fetch, production DB mutation, full universe, or Backtrader. |
| Reviewed adjusted price evidence intake | Local JSON/CSV intake validates source, raw path, reviewer, review timestamp, evidence basis, payload SHA-256, and price rows before factor generation or optional local execute. No live fetch, full VN100, or Backtrader. |
| Reviewed adjusted price evidence package QA | Synthetic/dev-only package smoke validates manifest+JSON+CSV shape, temporary execute, and readiness. No live fetch, production DB mutation, full VN100, or Backtrader. |
| Real adjusted price evidence onboarding | Local-only manifest generation and package validation for manually provided FPT/VNM/VCB evidence under ignored paths. No real data committed, no live fetch, no Backtrader. |
| Real adjusted price local execute readiness | Explicit local SQLite execute-readiness wrapper applies reviewed package factors, writes readiness JSON, and emits a Markdown report. No production/demo DB by default, no Backtrader. |
| Adjusted OHLC execution audit | Read-only strict audit checks adjusted OHLC population, provenance, factor consistency, validation report status, readiness report status, and optional raw OHLC baseline after local execute readiness. No DB mutation or Backtrader. |
| Adjusted OHLC backtest feed contract | Read-only small-symbol contract and preview maps adjusted OHLC to feed price fields only after strict audit passes. Hardened gates require every requested symbol to have eligible adjusted rows, reject stale/mismatched audit metadata, validate date and `max_rows` instead of silently correcting them, and emit `feed_contract_version=adjusted_ohlc_feed_v1`. No Backtrader implementation or strategy execution. |
| Adjusted OHLC backtest dry-run preparation | Preparation-only layer converts the PR #48 feed preview JSON into a backtest input contract for a research dry-run. Validates feed contract/price basis, requested symbols, date range, `max_rows`, explicit transaction cost/slippage, and exchange slippage bands (HOSE/HSX +/-7%, UPCoM +/-15%). Every requested symbol must survive the date-range filter and `max_rows` limit, else `prepared_input_missing_symbol_after_filter`/`_after_limit` blocks; output reports `requested_symbols`/`represented_symbols`/`missing_symbols` and `not_financial_advice=true` with no performance metrics. Optional `research_fixture_signal` is a deterministic all-cash placeholder. Does not call any engine, run Backtrader, optimize, mutate a DB, fetch live data, or give advice. |
| Adjusted OHLC fixture signal dry-run | Fixture-only layer consumes the PR #49 preparation JSON and emits a tiny deterministic fixture signal preview (default `all_cash` → `NO_POSITION` per row; optional synthetic `alternating_fixture_signal`). Validates preparation status/input status/price basis, requested symbol coverage, cost/slippage assumptions, signal mode, and `max_rows`. `performance_metrics=null` and `not_financial_advice=true` always; no buy/sell/hold wording. Renders a Markdown report. Does not call any engine, run Backtrader, optimize, mutate a DB, fetch live data, or give advice. |
| Adjusted OHLC fixture metrics report | Fixture-only diagnostics layer consumes the PR #50 fixture signal JSON and emits deterministic counts (`row_count`, `symbol_count`, `signal_action_counts`, `first_date`/`last_date`, `fixture_no_position_ratio`, `input_price_basis`). Blocks real actions (`BUY`/`SELL`/`HOLD`), non-null `performance_metrics`, and any PnL/equity/performance row field; sets `forbidden_performance_metrics_present`. Intentionally computes no Sharpe/Sortino/Profit Factor/Max Drawdown/PnL/equity/win rate/alpha. `not_financial_advice=true`. Renders Markdown. No engine call, Backtrader, optimizer, DB mutation, live fetch, or advice. |
| Adjusted OHLC fixture round-trip engine | Fixture-only deterministic engine consumes the PR #49 preparation, PR #50 fixture signal, and PR #51 fixture metrics, and emits round-trip state-transition diagnostics only (`fixture_enter_count`, `fixture_exit_count`, `duplicate_enter_count`, `unmatched_exit_count`, `open_fixture_state_count`) plus row counts, action counts, dates, and echoed cost/slippage assumptions. Per-symbol `OUT`/`IN_FIXTURE` state over `NO_POSITION`/`FIXTURE_ENTER`/`FIXTURE_EXIT`. Blocks `BUY`/`SELL`/`HOLD`, non-null `performance_metrics`, and PnL/equity/return/sharpe/drawdown row fields. Computes no PnL/equity/returns/Sharpe/drawdown and no trade list. `not_financial_advice=true`. Renders Markdown. No engine call, Backtrader, optimizer, DB mutation, live fetch, or advice. |
| Adjusted OHLC fixture cost diagnostics | Fixture-only layer consumes PR #49 preparation and PR #52 round-trip output, then attaches validated transaction-cost/slippage assumptions to fixture enter/exit event counts as bps-units diagnostics. Echoes exchange and slippage band. It never multiplies by price and computes no PnL, equity, returns, currency loss, strategy performance, or trade list. No Backtrader, optimizer, full VN100, DB mutation, live fetch, or investment advice. Mentor review is next before real adjusted-basis engine integration. |
| Mentor-approved strategy contract foundation | Machine-readable JSON contract validation plus schema, baseline candidates, pending decision record, first-run scope, validation gates, and Backtrader scaffold plan. Only explicit approved contracts over adjusted OHLC can return ready; pending/rejected contracts remain `not_ready`. No strategy execution, Backtrader implementation, optimizer, full VN100, DB mutation, network fetch, performance claim, or investment advice. |
| Strategy adapter interface preview | No-op adapter skeleton consumes an approved strategy contract and matching prepared adjusted-OHLC JSON, then emits `NO_SIGNAL` intent rows only. Validates contract readiness, input status/basis, per-symbol coverage (prepared input may be a superset; extra symbols ignored), and row coverage. Interface preview only: no real strategy logic, recommendation, trade, PnL/equity/returns, Backtrader, optimizer, DB mutation, network fetch, or investment advice. |
| Strategy adapter registry | Read-only catalogue of candidate adapter families (`noop`, `moving_average`, `momentum`, `breakout`, `mean_reversion`). Only `noop` is implemented/enabled (`interface_preview`); all others are disabled and `pending_mentor_approval`. `validate_family_enabled` blocks unknown/disabled families. Planning-only: not wired into the adapter execution path; no real strategy execution, Backtrader, optimizer, full VN100, performance metric, DB mutation, network fetch, or investment advice. CLI: `scripts/list_strategy_adapter_registry.py`. |
| Backtest MVP scaffold | Exploratory deterministic scaffold over cached SQLite store; included in mentor demo suite; report at `docs/reports/backtest_mvp_demo_report.md`. No LLM, broker execution, live trading, or network fetch. |
| Mentor feedback capture | 2026-06-18 mentor feedback captured in `docs/demo/mentor_feedback_capture.md`; single handoff file: `docs/demo/vsf_mentor_db_ingestion_backtest_handoff.md`. |
| Test suite | **1453 tests pass** |
| Production DB write | **Blocked** |
| Production backtest hardening | **Blocked** |

---

## Main Blockers

- **Mapping coverage:** Below 95% per section — BS 89.7% / IS 94.5% / CF 87.6% (7 payloads, all known groups sampled). Gap appears structural for `/metrics` endpoint: residual codes (`bsi*`, `bss*`, `bsb*`, `cfs*`, `cfi*`) absent from all probed mapping payloads.
- **PIT semantics:** `pit_supported_small_sample` (8/8 statement rows credible, 4/4 unique official disclosure events credible, 2 issuers, zero red flags). Evidence is date-level, not timestamp-level; do not claim full PIT confirmation or use for PIT backtest yet.
- **MVP DB/tool demo:** Implemented as local SQLite only. It is suitable for deterministic tool-call demo, not production storage.
- **Production DB write:** Blocked until all §17 gates met (see `vietcap_iq_fa_ingestion_v2_readiness.md`).
- **Full-history FA fetch:** Not implemented — blocked on mapping, PIT, and schema gates.
- **Production backtest hardening:** Store choice and execution convention still need review; adjusted-price policy is confirmed. Transaction cost is now a research task, and slippage must stay within HSX/HOSE +/-7% and UPCoM +/-15%.
- **Adjusted OHLC hardening:** Schema slots, pure helpers, local application, controlled local payload verification, and policy requirements exist. Implementation still needs verified adjusted-price/factor evidence; Backtrader VN100 runs remain blocked until adjusted OHLC rows are populated and validated.

---

## Key Validation Numbers

| Metric | Value |
|---|---|
| Universe symbols | 2,080 total / 1,598 listed-market candidates |
| OHLCV gap-chart bars (FPT) | 4,852 (2006–2026) |
| FA parser fact rows (5 payloads) | 53,013 |
| FA parser errors | 0 |
| FA mapping named rows | 46,412 / 53,013 (87.5% combined validation view) |
| FPT BS+CF Mode B code-row naming | 485 / 556 named (87%); primary=163; consensus=322; conflict_skipped=2; not_covered=62 |
| FA `publicDate` PIT sample | 8 rows; 4 unique official disclosure events; 2 issuers; 2 exact_match, 4 near_match, 2 vietcap_after_official; 0 red flags |
| MVP DB/tool demo | 3 demo securities; 14,079 daily price rows; 14,071 feature snapshots/signals; 8 OHLC fail rows excluded from features |
| Agent orchestrator demo | Exact tool sequence: market_data -> features -> signal -> risk -> report; missing DB and unknown-symbol paths return clear non-traceback statuses |
| Agent/backtest demo runner | market_brief, risk_check, compare, and Backtest MVP suite rows; expected nonzero edge cases display as OK when status matches |
| OHLCV ingestion/live adapter tests | 41 targeted tests |
| Ingestion status tests | 15 targeted tests |
| Production ingestion control-plan tests | 17 targeted tests |
| Adjusted OHLC tests | 13 targeted tests |
| Adjusted OHLC readiness tests | 17 targeted tests |
| Adjustment factor source tests | 16 targeted tests |
| Adjusted factor source probe tests | 18 targeted tests |
| Adjusted factor evidence capture tests | 18 targeted tests |
| Local adjustment factor application tests | 18 targeted tests |
| Adjustment factor source adapter tests | 14 targeted tests |
| Controlled factor source verification tests | 23 targeted tests |
| Adjusted price evidence pipeline tests | 20 targeted tests |
| Adjusted price evidence smoke tests | 7 targeted tests |
| Reviewed adjusted price evidence intake tests | 29 targeted tests |
| Reviewed adjusted price evidence package QA tests | 13 targeted tests |
| Real adjusted price evidence onboarding tests | 21 targeted tests |
| Reviewed adjusted price evidence report tests | 17 targeted tests |
| Reviewed adjusted price local execute readiness tests | 24 targeted tests |
| Adjusted OHLC execution audit tests | 33 targeted tests |
| Adjusted OHLC backtest feed readiness tests | 37 targeted tests |
| Adjusted OHLC backtest dry-run preparation tests | 38 targeted tests |
| Adjusted OHLC fixture signal dry-run tests | 26 targeted tests |
| Adjusted OHLC fixture metrics report tests | 28 targeted tests |
| Adjusted OHLC fixture round-trip engine tests | 33 targeted tests |
| Adjusted OHLC fixture cost diagnostics tests | 30 targeted tests |
| Mentor live demo package manifest tests | 11 targeted tests |
| Strategy contract validation tests | 30 targeted tests |
| Strategy adapter interface tests | 20 targeted tests |
| Strategy adapter registry tests | 13 targeted tests |
| Mapping coverage gate (95%) | Not met — union peak 94.5% (IS); gap structural; all known groups sampled |
| FA tests | 71 integration + 74 resolver + 54 firm-type |
| Disclosure foundation tests | 154 targeted tests |
| Total tests passing | 1453 |

---

## Architecture

- Product: **agent/tool product** — not just a backtest pipeline.
- Full doc: `docs/architecture/02_trading_agent_architecture_overview.md`.
- Backtest is one module/tool; current state is local exploratory scaffold, pre-production.
- Online questions (e.g. "HPG hôm nay thế nào?") should read cache/store, not trigger heavy fetches.

---

## Next Steps

1. ~~Close mapping coverage gap (probe additional firm types)~~ — gap appears structural; all known groups sampled.
2. ~~Activate FPT primary mapping for general symbols~~ — Mode B implemented; legacy `line_item_name` remains empty.
3. Decide on coverage gate response: lower threshold, or supplement mapping from a secondary source.
4. ~~Build official disclosure source discovery/crawler POC for HOSE/HNX/company IR~~ — Foundation v1 hardened+VCI: FPT IR (20 records), VCI FY2025+Q1 2026 (2 records, exact/near match). Honest UA, TLS enforced, no pseudo rows. PIT gate: `pit_supported_small_sample`.
5. ~~Use the SQLite MVP tools and orchestrator CLI to demo agent-style answers from cached data.~~ — Scenario runner (`market_brief`, `risk_check`, `compare`) added in phase/agent-demo-readiness.
6. Decide production DB path: extend SQLite contracts, design QuestDB, or add another durable store.
7. ~~Present mentor-facing demo and collect feedback before adding LLM reasoning layer.~~ — Demo package complete. Send `docs/demo/mentor_demo_runbook.md` + `docs/demo/mentor_review_checklist.md` to mentor. Wait for feedback.
8. ~~Execute `docs/plans/post_demo_technical_roadmap.md` phases based on mentor answers.~~ — Decision pack created: store matrix, backtest spec, ADR-0001, and feedback capture template ready. Awaiting mentor session to unlock next phase.
9. ~~Implement exploratory backtest MVP (`mvp_ma20_ma50_momentum` strategy over FPT/VNM/VCB).~~ - Scaffold added over cached SQLite data with explicit caveats and validation gates.
10. ~~Run mentor demo session and capture answers before QuestDB/LLM/backtest hardening.~~ — 2026-06-18 feedback captured; Backtrader, current VN100, adjusted OHLC, FA scan, simple TA templates, and ETL-first Docker direction recorded.
11. ~~Add adjusted OHLC readiness gates so Backtrader work is blocked while adjusted columns are missing or invalid.~~ — Read-only API/tool/CLI added; current demo DB returns `not_ready` as expected.
12. Use the real adjusted-price evidence onboarding workflow to generate a manifest, validation JSON, human-readable dry-run report, local execute-readiness report, and adjusted OHLC execution audit for manually provided FPT/VNM/VCB evidence before any Backtrader VN100 work.
13. Build full-history FA fetcher only after mapping, PIT, and schema gates are clearer.

---

## Docs Policy

All docs under `docs/` target ≤1500 words. All files comply as of PR #9 (2026-06-11).

| File | Words | Status |
|---|---|---|
| `docs/architecture/02_trading_agent_architecture_overview.md` | 1497 | Compliant |
| `docs/data_sources/hose_pipeline.md` | 1151 | Compliant |
| `docs/autonomous_trading_agent_dev_master.md` | 1496 | Compliant |
| `docs/data_sources/vietcap_iq_fa_ingestion_v2_readiness.md` | 846 | Compliant |
| `docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md` | 1159 | Compliant |
| `docs/data_sources/vietcap_iq_fa_firm_type_determination.md` | 1110 | Compliant |
| `docs/data_sources/vietcap_iq_fa_mapping_coverage_bank_probe.md` | 892 | Compliant |
| `docs/data_sources/vietcap_iq_fa_mapping_cashflow_probe.md` | 887 | Compliant |
| `docs/data_sources/vietcap_iq_fa_mapping_coverage_gap_probe.md` | ~1050 | Compliant |
| `docs/ingestion_v2_schema_plan.md` | 1473 | Compliant |
| `docs/data_sources/vietcap_iq_fa_parser_mapping_integration.md` | 876 | Compliant |
| `docs/data_platform/agent_demo_readiness.md` | ~500 | Compliant |
| All other `docs/` files (stubs + minor docs) | below 500 | Compliant |

Archived historical detail (probe notes, paper notes, writing guide, legacy sections) lives in `notes/archive/` (outside Docusaurus tree).
