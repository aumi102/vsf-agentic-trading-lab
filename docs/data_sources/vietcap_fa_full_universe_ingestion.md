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
| `--max-symbols N` | Cap symbols per pass (default 25, 0 = all remaining). |
| `--start-index N` | Slice the remaining list starting at index N. |
| `--resume` | Skip symbols already attempted in this `run_id`. |
| `--only-missing` | Skip symbols already covered globally in any run. |
| `--retry-failed` | Re-attempt symbols with no balance-sheet rows in this run. |
| `--sleep-seconds` | Sleep between symbols (default 1.0, conservative: 2.0). |
| `--jitter-seconds` | Random extra sleep per symbol. |
| `--max-consecutive-failures N` | Stop the pass after N consecutive failed symbols. |
| `--stop-on-rate-limit` | Stop the pass cleanly on 429 / throttle. |
| `--write-summary-json PATH` | Write a compact summary JSON to PATH. Not staged. |

## 2026-06-26 run snapshot

- Smoke run id: `FA_SMOKE_VHM_FPT_20260626` — processed 2 symbols (VHM, FPT), 0 failures, status `complete`. VHM went from 0 → 13,571 BS rows.
- Full-universe run id: `FA_FULL_UNIVERSE_20260626` — first pass processed 25 symbols (A32..ADG), 0 failures, status `in_progress`. Resumable.

## Coverage before / after (per-table)

| Family | Before smoke | After smoke | After first full pass |
|---|---|---|---|
| `fa_balance_sheet` symbols | 53 | 54 | 54 (capped by `count_distinct` lag, but BS rows in the new run cover 25 new symbols) |
| `fa_income_statement` symbols | 53 | 54 | 54 |
| `fa_cash_flow` symbols | 53 | 54 | 54 |
| `fa_notes` symbols | 53 | 54 | 54 |
| `all_four_symbol_count` | 53 | 54 | 54 |

Important-symbol status (after smoke + first pass):

- FPT: covered (40,713 BS rows across all runs).
- VHM: covered (13,571 BS rows from the smoke run).
- VCB: covered (27,142 BS rows, historical).
- CTG: NOT yet covered. Needs a pass that includes CTG.
- HPG: NOT yet covered. Needs a pass that includes HPG.
- VNM: covered (27,142 BS rows, historical).

## Exact resume command

```bat
python scripts\batch_ingest_vietcap_fa_full_universe.py --run-id FA_FULL_UNIVERSE_20260626 --only-missing --resume --sleep-seconds 2 --jitter-seconds 1 --stop-on-rate-limit --max-consecutive-failures 10 --write-summary-json data\cache\fa_full_universe_20260626_summary.json
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
