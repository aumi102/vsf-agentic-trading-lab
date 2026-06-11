# HOSE Pipeline — Archived Sections

**Source:** `docs/data_sources/hose_pipeline.md` (archived 2026-06-11)
**Why archived:** §6 (Saved-Output Units And History Audit) and §12 (Appendix: Old Docs Merged) were
removed from the canonical doc during the word-count compaction pass (PR #9). These sections
contain historical audit run tables and a merge provenance log that exceed the 1500-word policy
but are too specific to belong in a compact reference doc.

---

## §6. Saved-Output Units And History Audit

Saved-output audit:

`data/processed/dry_run/hose_quote_report_saved_outputs_audit.json`

Saved quote-report dry-run folders found:

| Run ID | Dates | Data statuses | Rows | Stock-only output |
|---|---|---|---:|---|
| `20260603T094855Z` | `2026-06-02` | `final_candidate` | 662 | yes, 403 rows |
| `20260603T101327Z` | `2026-06-02` | `final_candidate` | 662 | no |
| `20260603T101349Z` | `2026-06-02`, `2026-06-03` | `final_candidate`, `provisional` | 1324 | no |

Audit conclusions:

- Units remain unconfirmed in all saved quote-report runs.
- Final EOD semantics remain unconfirmed.
- Historical availability remains unconfirmed.
- No saved-output audit fetched live data.
- DB/backtest remains blocked.

Unit hypotheses:

- Price fields may be displayed price units, likely thousand VND-style for Vietnam equities.
- `mainVolume` may be shares or lot-scaled volume.
- `mainValue` may be million VND or another display unit.
- Do not hard-code DB unit conversions until source evidence or mentor review confirms them.

Historical availability audit design:

- Test several completed trading days.
- Test at least one weekend or non-trading day.
- Test older historical dates.
- Record statuses as `verified_json`, `empty_data`, `rejected_response`, or `error`.
- Compare full row count, stock-only coverage, duplicate counts, and quality counts across dates.

Historical audit script:

```bash
python scripts/audit_hose_quote_report_historical_dates.py --dates 2026-06-02,2026-06-03,2026-05-30 --targets-config config/source_probe_targets.local.json
```

The script uses the configured HOSE quote-report target, rewrites only the `date` query parameter
for each requested date, stores per-date raw payloads and metadata under
`data/processed/dry_run/hose_quote_report_historical_audit/<run_id>/`, and writes:

- `historical_audit_summary.json`
- `historical_audit_report.md`
- per-date raw payload and metadata files
- per-date parser summaries when JSON is verified

It still does not write to a database or run a backtest. Local browser-derived headers remain
local-only through the source-probe config and must not be printed or committed.

Latest historical audit result (run `20260604T030039Z`):

| Date | Status | Full rows | Stock-only rows | Fail count | Notes |
|---|---|---:|---:|---:|---|
| `2026-06-02` | `verified_json` | 662 | 403 | 0 | Stable row coverage; all rows warn on unconfirmed source units. |
| `2026-06-03` | `verified_json` | 662 | 403 | 0 | Stable row coverage; all rows warn on unconfirmed source units. |
| `2026-05-30` | `rejected_response` | n/a | n/a | n/a | Likely non-trading-day/weekend signal; needs more samples before treating as confirmed behavior. |

Wider historical audit result (run `20260604T031010Z`, 10 requested dates):

| Result group | Count | Evidence |
|---|---:|---|
| Verified JSON dates | 7 | `2026-05-26`, `2026-05-27`, `2026-05-28`, `2026-05-29`, `2026-06-01`, `2026-06-02`, `2026-06-03` |
| Empty data dates | 3 | `2026-04-30`, `2026-05-30`, `2026-05-31` |

The seven verified dates had stable stock-only coverage: 403 stock-only rows on every verified
date, with `fail_count=0` and zero duplicate `symbol + trading_date + data_status`. Full
quote-report rows varied from 641 to 663 (date-to-date variation in non-stock-like instruments),
while the listed-stock subset stayed fixed. The three empty-data dates (`data: []` JSON) are
useful non-trading-day/holiday candidates but need official trading-calendar confirmation.

Remaining blockers:

- Source units remain unconfirmed.
- Final EOD timing remains unconfirmed.
- Official trading calendar integration is not done.
- `tradingBy=VNINDEX` coverage should still be reviewed across a longer date range.

---

## §12. Appendix: Old Docs Merged

The following old HOSE docs were merged into the canonical `hose_pipeline.md`:

| Old doc path | Merged into section | Action |
|---|---|---|
| `docs/hose_market_data_mapping_review.md` | Source endpoints, listed universe pipeline, quote-report pipeline | removed after merge |
| `docs/hose_listed_universe_parser_review.md` | Listed universe pipeline | removed after merge |
| `docs/hose_listed_universe_all_pages_review.md` | Listed universe pipeline | removed after merge |
| `docs/hose_quote_report_mapping_review.md` | Quote-report pipeline, data-quality gates | removed after merge |
| `docs/hose_quote_report_parser_review.md` | Quote-report pipeline | removed after merge |
| `docs/hose_quote_report_universe_coverage_audit.md` | Stock-only filter | removed after merge |
| `docs/hose_quote_report_stock_only_filter_review.md` | Stock-only filter | removed after merge |
| `docs/hose_quote_report_units_and_history_audit_plan.md` | Saved-output units and history audit, data-quality gates | removed after merge |
