---
title: vietcap_iq_fa_publicdate_pit_validation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA publicDate PIT Validation

## Purpose

Check whether Vietcap IQ FA `publicDate` can be treated as a point-in-time
availability/publication field. This package adds a machine-readable sample and
an offline validator. It does not unblock DB writes or backtests.

## Artifacts

- Sample CSV: `docs/data_sources/vietcap_iq_fa_publicdate_validation_samples.csv`
- Validator: `scripts/validate_vietcap_iq_fa_publicdate_samples.py`
- Tests: `tests/test_validate_vietcap_iq_fa_publicdate_samples.py`

The validator reads the CSV, parses dates, verifies `date_delta_days`, normalizes
blank statuses, preserves unresolved statuses, counts confidence levels, and
emits one of: `pit_red_flags_found`, `pit_inconclusive`, or
`pit_supported_small_sample`. It never emits `pit_confirmed_full`.

Optional flag `--check-payload-paths` verifies that each `payload_path` in the
CSV resolves to an existing file under the repo root.

## Evidence Priority Policy

Canonical PIT evidence must come from one of:

1. HOSE official disclosure record.
2. HNX official disclosure record.
3. Company official IR/disclosure page (directly accessible, not aggregated).
4. Official report or PDF metadata only if clearly tied to publication date.

Secondary sources such as Vietstock.vn or other news/data aggregators are
**non-canonical**. They may be recorded as investigation leads in `reviewer_note`
but must not populate `official_disclosure_date`, must not produce a comparable
`match_status`, and must not contribute to the credible-comparable ratio. They
do not unblock the PIT gate.

## Sample Selection

The 8-row sample uses saved local FA payloads only. It covers FPT and VCI,
BALANCE_SHEET / INCOME_STATEMENT / CASH_FLOW, annual and Q1 periods.

Saved payload sources:

- FPT BALANCE_SHEET: `20260609T075857Z`
- FPT CASH_FLOW: `20260610T025440Z`
- VCI BALANCE_SHEET: `20260609T035318Z`
- VCI INCOME_STATEMENT: `20260609T075846Z`
- VCI CASH_FLOW: `20260610T025429Z`

A third HOSE issuer (HPG) was considered but blocked: the saved HPG payload
(`20260611T083445Z`) is a metrics-code mapping probe with no financial statement
`publicDate` values.

## Validation Method

For each sample row, compare Vietcap `publicDate` to official disclosure evidence.

FPT official IR disclosures were accessible at
`https://fpt.com/en/ir/information-disclosures`. This is a company official IR
page — confidence `medium`.

For VCI, the Vietcap official IR page returned a login portal (inaccessible in
this run) and the HOSE disclosure page returned no usable VCI records. Vietstock
secondary leads were found and recorded in `reviewer_note` for investigation, but
are non-canonical per the policy above. VCI `official_disclosure_date` fields
remain empty; all VCI rows retain `official_not_found` / `none`.

## Sample Results

| Symbol | Section | Period | Vietcap date | Official date | Delta | Status | Confidence |
|---|---|---:|---|---|---:|---|---|
| FPT | BALANCE_SHEET | 2025 annual | 2026-03-20 | 2026-03-19 | +1 | `near_match_1_3_days` | medium |
| FPT | CASH_FLOW | 2025 annual | 2026-03-20 | 2026-03-19 | +1 | `near_match_1_3_days` | medium |
| FPT | BALANCE_SHEET | 2026 Q1 | 2026-04-28 | 2026-04-24 | +4 | `vietcap_after_official` | medium |
| FPT | CASH_FLOW | 2026 Q1 | 2026-04-28 | 2026-04-24 | +4 | `vietcap_after_official` | medium |
| VCI | BALANCE_SHEET | 2025 annual | 2026-02-13 | — | — | `official_not_found` | none |
| VCI | INCOME_STATEMENT | 2025 annual | 2026-02-13 | — | — | `official_not_found` | none |
| VCI | BALANCE_SHEET | 2026 Q1 | 2026-04-21 | — | — | `official_not_found` | none |
| VCI | CASH_FLOW | 2026 Q1 | 2026-04-21 | — | — | `official_not_found` | none |

Validator counts:

- `near_match_1_3_days`: 2
- `vietcap_after_official`: 2
- `official_not_found`: 4
- `exact_match`, `vietcap_before_official`, `ambiguous_basis`, `not_comparable`: 0
- Confidence: medium=4, none=4

## Findings

Final PIT sample status: `pit_inconclusive`.

FPT rows are supportive: Vietcap `publicDate` is at or after official company IR
disclosure dates in all four FPT rows. No credible `vietcap_before_official` red
flag was observed in any row with canonical evidence.

The sample is still inconclusive because 4/8 rows lack canonical official evidence
and only one issuer has comparable canonical evidence. Vietstock secondary leads
were found for VCI rows but are non-canonical and do not count toward the gate.
`publicDate` remains unconfirmed and must not be used for PIT backtests yet.

## Gate Status

- `publicDate` PIT semantics: **Unconfirmed** — status `pit_inconclusive`.
- Mapping coverage gate remains below 95%: BS 89.7%, IS 94.5%, CF 87.6%.
- DB write remains blocked.
- Backtest remains blocked.
- QuestDB schema not designed.
- Full-history FA fetch not implemented.

## Next Action

Build an official disclosure source discovery/crawler POC for HOSE/HNX/company
IR pages. Do not rely on Vietstock or other secondary aggregators as canonical
evidence. Official HOSE or Vietcap IR access for VCI would provide 4 more
canonical rows, moving the credible-comparable ratio from 0.50 toward the 0.70
threshold for `pit_supported_small_sample`.
