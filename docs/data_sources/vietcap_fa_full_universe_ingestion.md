# Vietcap FA full-universe ingestion

This document describes the resumable, low-concurrency Vietcap financial-report
(FA) ingester that brings the FA tables to full-universe coverage over a series
of safe overnight passes.

## Scripts

| Script | Role |
|---|---|
| `scripts/batch_ingest_vietcap_fa_full_universe.py` | Resumable full-universe ingester. Reuses the verified single-symbol helpers in `scripts/ingest_vietcap_financial_reports_to_questdb.py`. Writes only to the existing FA tables (`fa_balance_sheet`, `fa_income_statement`, `fa_cash_flow`, `fa_notes`, `fa_raw_payloads`, `fa_ingest_runs`). |
| `scripts/questdb_fa_coverage.py` | Read-only coverage summary. Same data is exposed via `GET /api/demo/fa/coverage`. |
| `scripts/run_fa_quality_gates.py` | Read-only PASS/WARN/FAIL gate (tables, important symbols, latest run, mapping coverage). Mapping partial is WARN, never FAIL. |
| `scripts/inspect_fa_feature_candidates.py` | Lists source-backed candidate features and the source consensus coverage behind them. No feature values are invented. |
| `scripts/build_fa_feature_snapshots.py` | Optional safe feature builder. Only emits values whose source consensus coverage is above the candidate threshold. |
| `scripts/run_overnight_vietcap_fa_ingest.bat` / `.ps1` | Conservative nightly runner. Uses `--only-missing --resume`, sleep 2s + jitter 1s, stop on rate-limit, max 10 consecutive failures, 0 max symbols (run until done). No secrets. |

## Universe source

Default full-universe mode reads symbols from `securities` (currently 1,556
symbols). `--symbols VHM,FPT` is supported as an operator smoke/test override
but does NOT change the universe for production runs.

## CLI options

| Flag | Purpose |
|---|---|
| `--plan-only` | Print the plan and exit. No network, no writes. |
| `--symbols A,B,C` | Smoke/test override that bypasses the universe lookup. |
| `--run-id` | Force / resume a specific `run_id`. |
| `--max-symbols N` | Cap symbols per pass (default 0 = all remaining). |
| `--start-index N` | Slice the remaining list starting at index N. |
| `--resume` | Skip symbols already attempted in this `run_id`. |
| `--only-missing` | Skip symbols already covered globally in any run. |
| `--retry-failed` | Re-attempt symbols with no balance-sheet rows in this run. |
| `--sleep-seconds` | Sleep between symbols (default 1.0). |
| `--jitter-seconds` | Random extra sleep per symbol. |
| `--max-consecutive-failures N` | Stop after N consecutive failed symbols (HTTP errors; zero-facts excluded by default). |
| `--stop-on-rate-limit` | Stop cleanly on 429 / 503 throttle. |
| `--count-zero-facts-as-failure` | Include zero-fact symbols (http=200, no rows) in consecutive failure count. |
| `--cooldown-after-http-failures N` | Sleep cooldown-seconds after N consecutive HTTP failures (0 = disabled). |
| `--write-summary-json PATH` | Write a compact summary JSON to PATH. Not staged. |

## Failure classification

The ingester classifies each attempted symbol into one of:

- **HTTP failure**: non-2xx HTTP status or `access_status != verified`. Counts toward `--max-consecutive-failures`.
- **Zero-fact**: http=200, verified, but zero rows across all four statement types. Does NOT count toward `--max-consecutive-failures` by default (use `--count-zero-facts-as-failure` to include). These are legitimate "no financial reports available" symbols (ETFs, warrants, derivatives, delisted).
- **Partial**: some statements have rows, others are zero-fact. Coverage is partial but not zero.
- **Covered**: at least one balance-sheet row produced.

## 2026-06-28 run snapshot

- Smoke run id: `FA_SMOKE_VHM_FPT_20260626` — processed 2 symbols (VHM, FPT), 0 failures, status `complete`. VHM went from 0 → 13,571 BS rows.
- Full-universe run id: `FA_FULL_UNIVERSE_20260626` — multiple passes, status `in_progress`, resumable.
- Bounded pass (100 symbols): zero-facts no longer counted as consecutive failures; cooldown-after-http-failures added. Symbols processed without premature stop. 141 new all4 symbols added.
- Coverage progress:
  - Before smoke: 53 (BS symbols)
  - After smoke: 54
  - After full-universe resumes: 627 (all4 symbols), 929 remaining globally
- Failure classification (from `scripts/inspect_fa_missing_universe.py`):
  - `attempted_http_fail = 89`: mostly HTTP 503 (rate-limit on ETF/fund symbols like FUE*, E1VFVN30)
  - `attempted_zero_facts = 90`: http=200, verified, but no rows (legitimate no-FA symbols)
  - `pending_real = 1113`: symbols never attempted, mostly non-ETF stocks
  - `likely_no_fa_heuristic = 102`: ETF/fund prefix symbols (FUE*, E1*, BMK*, BHH*, BQP*, etc.)
- Zero-fact classification bug fixed: previously each section's empty rows was tracked independently (inflating zero_fact count); now symbol-level total rows across all sections determines zero-fact vs partial vs covered.

## Selection-bug fix

The previous `--only-missing --resume` combination was an `if/elif` chain where
`--resume` won over `--only-missing`. This meant `--only-missing` had no effect
and the script kept re-processing already-covered symbols. The fix combines the
flags:

- `--resume` (default when no flags) → skip symbols already attempted in this run_id.
- `--only-missing` → additionally skip symbols already covered in any run.
- `--retry-failed` → re-attempt symbols that were attempted but produced no BS rows.

`--max-symbols` default is now `0` (= all remaining). A positive value caps the
pass. The plan-only output now correctly reports `remaining=1502` (or current
remaining) and shows the first non-covered symbols instead of the already-covered
A-prefix symbols.

## FA query run-selection fix

Previously, `financial report VCB` returned `unavailable` even though VCB had
27,142 BS rows — because the tool scoped queries to `latest_complete_run_id`
which (after the smoke) was the partial `FA_SMOKE_VHM_FPT_20260626` run that
only contains FPT/VHM. Fixed by adding `_symbol_run_scope(symbol, table, url)`
that:

1. Tries the latest complete run; if the symbol has rows there, uses it.
2. Otherwise falls back to the most recent run_id that has rows for the symbol.
3. If no rows exist for the symbol in any run, returns the latest complete
   run_id so the query is honestly empty (`status=unavailable`).

Verified:

- FPT/VHM/VCB/VNM → `status=ok`, `domain=financial_report`, OHLCV tools rejected.
- CTG/HPG → `status=unavailable` (no rows in any run).

## FA feature snapshot fix

The previous `build_fa_feature_snapshots.py` reported `symbol_count=53` but the
target table had 0 rows. Two real bugs:

1. `csv.DictWriter` was not calling `writeheader()`, so the CSV had no header
   line. With `forceHeader=true`, QuestDB rejected the header as missing.
2. The builder did not verify the post-write row count; on silent failure it
   still reported a fake success.

Fixes:

- `_csv_bytes` now writes a real header line.
- After `imp_csv`, the builder reads back the table count and returns exit code
  3 with a clear error if it stayed at 0.

Result: `fa_feature_snapshots` has rows for all 53 symbols from
`run_id=20260624T044856Z` (revenue_yoy / net_profit_yoy / equity_latest /
operating_cashflow_latest). `total_assets` is intentionally NOT emitted because
the consensus mapping table has no `total_assets` code yet.

## Coverage before / after (per-table)

| Family | Before smoke | After smoke | After bounded resumes (2026-06-28) |
|---|---|---|---|
| `fa_balance_sheet` symbols | 53 | 54 | 639 |
| `fa_income_statement` symbols | 53 | 54 | 635 |
| `fa_cash_flow` symbols | 53 | 54 | 635 |
| `fa_notes` symbols | 53 | 54 | 627 |
| `all_four_symbol_count` | 53 | 54 | 627 |
| Remaining globally | — | — | 929 |

Important-symbol status (all OK as of 2026-06-28):

- FPT: covered (40,713 BS rows).
- VHM: covered (13,571 BS rows).
- VCB: covered (27,142 BS rows).
- CTG: covered (13,571 BS rows).
- HPG: covered (13,571 BS rows).
- VNM: covered (27,142 BS rows).

All six return `status=ok domain=financial_report` via FastAPI demo.

## Exact resume command

```bat
python scripts\batch_ingest_vietcap_fa_full_universe.py --run-id FA_FULL_UNIVERSE_20260626 --only-missing --resume --sleep-seconds 1 --jitter-seconds 0.5 --stop-on-rate-limit --max-consecutive-failures 20 --cooldown-after-http-failures 10 --write-summary-json data\cache\fa_full_universe_20260626_summary.json
```

## Overnight runner (safe defaults)

```bat
scripts\run_overnight_vietcap_fa_ingest.bat
:: or, on PowerShell:
powershell -File scripts\run_overnight_vietcap_fa_ingest.ps1
```

Both print:

- the exact `resume_command` if you Ctrl-C;
- the coverage command to run after the pass.

## Coverage endpoint

```bat
curl.exe -s http://127.0.0.1:8010/api/demo/fa/coverage
```

Returns the same structure as `scripts/questdb_fa_coverage.py` (PASS/WARN/FAIL
plus per-table counts, important symbols, latest run id, top missing symbols).

## FA quality gate

```bat
python scripts\run_fa_quality_gates.py
python scripts\run_fa_quality_gates.py --json
```

A read-only gate. `WARN` is the expected state while the full universe is being
filled. `FAIL` only triggers on missing tables or broken queries.

## FA feature layer status

- `scripts/inspect_fa_feature_candidates.py` reports 4/5 candidates READY
  (revenue, net profit, equity, operating cash flow). `total assets` is
  currently NOT in the consensus mapping table and is left to a later mapping
  pass.
- `scripts/build_fa_feature_snapshots.py` is provided as a safe builder that
  only emits features whose source codes are flagged READY by the inspector.
  It does NOT invent metric names or fall back to heuristic mappings.

## Caveats (unchanged, surfaced honestly in every response)

- Adjusted OHLC source is still unverified/raw-equivalent.
- FA metric mapping is partial (~69%–92% coverage by family); tool-side metric
  enrichment is best-effort.
- Slippage is a simple bps model, not market-impact.
- SimpleEngine is an explainability baseline, not a production backtest.
- The full-universe ingest is resumable; "complete" only flips to true once
  every universe symbol has been attempted.
