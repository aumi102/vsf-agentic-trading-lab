---
title: vietcap_iq_fa_ingestion_v2_readiness
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Ingestion V2 Readiness

Master gate table for production Vietcap IQ FA ingestion. No DB write until all
DB gates are met.

## Current Status

| Item | Status |
|---|---|
| FA endpoint access | Confirmed: HTTP 200 clean profile for BS/IS/CF on VCI and FPT |
| Parser dry-run | Done: 53,013 fact rows from saved payloads; 7 validation checks |
| Mapping integration | Done: Option C resolver, Mode B active, 7 output columns, 0 dry-run errors |
| Mapping coverage | Below gate: BS 89.7% / IS 94.5% / CF 87.6%; 99 conflicts |
| `publicDate` PIT sample | Supported small sample: 8/8 statement rows credible; 4/4 unique official disclosure events credible; 2 issuers; 0 red flags; `pit_supported_small_sample` |
| PIT breadth v2 | Draft: 10 target issuers, 8 sectors, 23 rows, 6 credible unique events, 3 comparable issuers/sectors, 3 blocked rows; `pit_inconclusive` |
| Full-history FA fetch | Not implemented |
| QuestDB schema | Not implemented |
| DB write | Blocked |
| Backtest | Blocked |

## Key Confirmed Facts

- FA payloads expose `data.quarters` and `data.years`; `publicDate` is present
  and date-formatted in reviewed payloads.
- Null and `0.0` remain distinct in parser output.
- `nos*` columns are null for non-securities firms such as FPT.
- Mapping is firm-type-specific; VCI/SSI, bank, insurance, fund, and general
  symbols differ.
- Union mapping across 7 payloads covers all known groups but remains below the
  95% gate.
- FPT official IR evidence: Q1 2026 financial statements `2026-04-24` in
  bounded bronze output; FY2025 audited financial statements `2026-03-19` in
  the captured honest-UA raw page, outside the bounded 20-record bronze output.
- VCI official IR evidence: FY2025 financial statements `2026-02-13`, Q1 2026
  financial statements `2026-04-20`.
- PIT breadth v2 has comparable rows for FPT, VCI, and HPG. KDH Q1, ACB
  FY2025, ACB Q1 2026, and DGC Q1 2026 are official-only or blocked because
  bounded Vietcap fa-direct probes returned HTTP 403 or no usable JSON
  `publicDate`.

## PIT Availability Policy

The current validator status is `pit_supported_small_sample`, not full PIT
confirmation. It is based on 8 credible statement rows, 4 credible unique
official disclosure events, 2 issuers, and zero red flags. Evidence is
date-level, not timestamp-level.

`publicDate` must not be used for PIT backtests yet. Broader issuer and exchange
validation is still required. Statement rows are not independent evidence
events. Secondary aggregators remain non-canonical.
`availability_status` remains `unknown_until_publicDate_validated` for
production ingestion.

## Mapping Policy

- Option C resolver is wired into parser dry-run.
- Mode B uses FPT as representative primary mapping for general symbols, then
  union consensus fallback.
- Legacy `line_item_name` stays empty.
- English/Vietnamese names are populated only when resolver evidence is clean.
- Mapping integration does not unblock DB write.

## DB Write Gates

| Gate | Current Status |
|---|---|
| Metric mapping coverage >= 95% per section | Not met |
| `publicDate` PIT breadth validated | Not met |
| QuestDB schema designed and implemented | Not met |
| Natural key / dedup policy defined | Not met |
| Full-history FA fetch tested for small symbol set | Not met |
| Parser strict mode on broader sample | Not met |
| Round-trip ingestion test | Not met |

## Backtest Gates

All DB write gates must pass first. Full-history FA data, completeness audit,
strategy definition, and backtest framework selection are not implemented.

## Next Steps

1. Decide mapping gate response: lower threshold or supplement mapping source.
2. Broaden official PIT validation beyond the current 2-issuer, 4-event sample.
3. Design and implement canonical QuestDB schema plus dedup/upsert policy.
4. Build full-history FA fetcher after mapping, PIT, and schema gates improve.
5. Run a small-batch end-to-end dry run before any DB write or backtest.
